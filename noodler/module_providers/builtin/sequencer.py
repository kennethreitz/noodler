"""A step sequencer that can speak in scale degrees.

The steps are a line of text — ``0 2 4 3  4 2 0 .`` — because that is how a
person writes a phrase. A dot is a rest. Patch a Key into it and each number
is a degree of that scale; with nothing patched, each number is a semitone
above the reference. Either way the pitch that leaves is one volt per octave,
the same language as every voice in the rack.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.music import ScaleField, hz_to_volts
from noodler.transport import (
    CHOICES,
    FREE,
    TransportFrame,
    block_clock,
    division_quarters,
    sample_crossings,
)

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


def parse_steps(text: str) -> tuple[int | None, ...]:
    """Degrees and rests from a line of text. Anything unreadable is skipped."""
    steps: list[int | None] = []
    for token in text.replace(",", " ").split():
        if token in {".", "-", "~", "r", "rest"}:
            steps.append(None)
            continue
        try:
            steps.append(int(token))
        except ValueError:
            continue
    return tuple(steps) or (0,)


class SequencerParameters(BaseModel):
    """The phrase, and how fast it walks when the clock has not been asked."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    steps: str = "0 2 4 7 7 4 2 0"
    division: str = "1/8"
    rate_hz: float = Field(default=2.0, gt=0.0, le=20.0)
    """Quarters per second when running free. Two is 120 BPM."""
    gate_length: float = Field(default=0.45, ge=0.05, le=0.95)
    octave: int = Field(default=0, ge=-4, le=4)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def known(self) -> "SequencerParameters":
        if self.division not in CHOICES:
            object.__setattr__(self, "division", "1/8")
        return self


SEQUENCER_OUTPUTS = ("pitch", "gate", "trigger", "step")

SEQUENCER_MANIFEST = ModuleManifest(
    id="sequencer",
    name="Sequencer",
    category="Sequencers",
    description=(
        "A phrase written as scale degrees. Patch a Key into it and the "
        "numbers mean that scale; a dot is a rest. The pitch out is one volt "
        "per octave."
    ),
    ports=(
        port("scale", "Scale", PortDirection.INPUT, SignalType.MUSICAL, "Degrees are of this scale. Without one, a step is a semitone."),
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "A rising edge advances one step. Unpatched, the division does."),
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The current degree, one volt per octave."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High for the note, low for a rest."),
        port("trigger", "Trigger", PortDirection.OUTPUT, SignalType.TRIGGER, "A pulse at the start of each note."),
        port("step", "Step", PortDirection.OUTPUT, SignalType.CV, "Which step this is, from zero to one."),
    ),
)


class Sequencer:
    """Walk a phrase, one step at a time."""

    manifest = SEQUENCER_MANIFEST
    uses_transport = True
    readout = True

    def __init__(self, parameters: SequencerParameters | None = None) -> None:
        self.parameters = parameters or SequencerParameters()
        self._steps: tuple[int | None, ...] = parse_steps(self.parameters.steps)
        self._from = self.parameters.steps
        self._index = -1
        self._pitch = 0.0
        self._degree: int | None = None
        self._gate_left = 0
        self._last_hit: int | None = None
        self._elapsed = 0
        self._free_quarters = 0.0
        self._clock_high = False
        self._field: ScaleField | None = None

    def choices_for(self, field: str) -> tuple[str, ...]:
        return CHOICES if field == "division" else ()

    @property
    def label(self) -> str:
        count = len(self._steps)
        place = (self._index % count) + 1 if self._index >= 0 else 0
        degree = "rest" if self._degree is None else str(self._degree)
        return f"step {place}/{count} · {degree}"

    def _phrase(self) -> tuple[int | None, ...]:
        if self.parameters.steps != self._from:
            self._steps = parse_steps(self.parameters.steps)
            self._from = self.parameters.steps
            self._index = -1
        return self._steps

    def _pitch_of(self, degree: int) -> float:
        field = self._field
        reference = self.parameters.reference_frequency_hz
        shift = self.parameters.octave
        if field is None or not field.tones:
            hertz = reference * 2.0 ** (degree / 12.0 + shift)
        else:
            count = len(field.tones)
            index = degree % count
            wraps = degree // count
            hertz = field.tones[index][1] * (field.period ** (wraps + shift))
        return hz_to_volts(hertz, reference)

    def _take(self, steps: tuple[int | None, ...], period: int) -> None:
        self._index = (self._index + 1) % len(steps)
        degree = steps[self._index]
        self._degree = degree
        if degree is None:
            self._gate_left = 0
            return
        self._pitch = self._pitch_of(degree)
        self._gate_left = max(1, int(period * self.parameters.gate_length))

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if frame_count == 0:
            return empty_outputs(SEQUENCER_OUTPUTS)

        inputs = inputs or {}
        offered = inputs.get("scale")
        self._field = offered if isinstance(offered, ScaleField) else None
        steps = self._phrase()

        transport = inputs.get("transport")
        if not isinstance(transport, TransportFrame):
            transport = None
        start, per_sample, per_bar, running, self._free_quarters = block_clock(
            transport,
            free_quarters=self._free_quarters,
            rate_hz=self.parameters.rate_hz,
            frame_count=frame_count,
            sample_rate=sample_rate,
        )
        if "clock" in inputs:
            clock = block("clock", inputs, frame_count)
            hits: list[int] = []
            high = self._clock_high
            for index in range(frame_count):
                event, high = rising_edge(float(clock[index]), high)
                if event:
                    hits.append(index)
            self._clock_high = high
        elif running and self.parameters.division != FREE:
            period_q = division_quarters(self.parameters.division, per_bar)
            hits = sample_crossings(start, per_sample, frame_count, period_q)
        elif running:
            hits = sample_crossings(start, per_sample, frame_count, 1.0)
        else:
            hits = []

        pitch = np.empty(frame_count, dtype=np.float64)
        gate = np.zeros(frame_count, dtype=np.float64)
        trigger = np.zeros(frame_count, dtype=np.float64)
        left = self._gate_left
        due = set(hits)
        fallback = max(1, int(sample_rate / self.parameters.rate_hz))
        for index in range(frame_count):
            if index in due:
                now = self._elapsed + index
                period = fallback if self._last_hit is None else max(1, now - self._last_hit)
                self._last_hit = now
                self._take(steps, period)
                if self._degree is not None:
                    trigger[index] = 1.0
                left = self._gate_left
            if left > 0:
                gate[index] = 1.0
                left -= 1
            pitch[index] = self._pitch
        self._gate_left = left
        self._elapsed += frame_count

        count = len(steps)
        position = 0.0 if self._index < 0 or count <= 1 else (self._index % count) / (count - 1)
        return {
            "pitch": np.asarray(pitch, dtype=np.float32),
            "gate": np.asarray(gate, dtype=np.float32),
            "trigger": np.asarray(trigger, dtype=np.float32),
            "step": np.full(frame_count, position, dtype=np.float32),
        }


__all__ = [
    "SEQUENCER_MANIFEST",
    "Sequencer",
    "SequencerParameters",
    "parse_steps",
]
