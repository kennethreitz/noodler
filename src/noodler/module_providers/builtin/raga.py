"""A raga, improvising the way a raga is played.

A raga is not a scale. It is a way up (the aroha), a way down (the avaroha)
that may differ from it, a characteristic phrase (the pakad) that names it in
a few notes, and a set of ratios against Sa. PyTheory knows fifty-four of
them, with all of that, and this module plays one: a walk that climbs by the
aroha and descends by the avaroha, sometimes quoting the pakad, tuned in just
intonation from the raga's own ratios rather than from a piano.

Clocked like the other brains -- a trigger in steps it, or it runs from its own
rate -- and put out as pitch and gate for any voice in the rack.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import Raga, Tone

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


RAGA_NAMES: tuple[str, ...] = tuple(Raga.names())
DEFAULT_RAGA = "Yaman" if "Yaman" in RAGA_NAMES else RAGA_NAMES[0]
SA_CHOICES: tuple[str, ...] = tuple(
    f"{name}{octave}" for octave in (2, 3, 4) for name in ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
)
STYLES = ("walk", "aroha avaroha", "pakad")
TRIGGER_SAMPLES = 240


def swara_octave(token: str) -> tuple[str, int]:
    """Split a swara as PyTheory writes it: N. is the octave below, S' above."""
    core = token.rstrip("'.")
    shift = token.count("'") - token.count(".")
    return core, shift


class RagaVoiceParameters(BaseModel):
    """Which raga, where Sa is, and how the line moves."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    raga: str = DEFAULT_RAGA
    sa: str = "C3"
    style: str = "walk"
    pakad_chance: float = Field(default=0.15, ge=0.0, le=1.0)
    """How often a step becomes the pakad instead."""
    density: float = Field(default=0.75, ge=0.0, le=1.0)
    gate_length: float = Field(default=0.6, ge=0.05, le=1.0)
    rate_hz: float = Field(default=2.0, gt=0.0, le=40.0)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    seed: int = Field(default=7, ge=0)

    @model_validator(mode="after")
    def known(self) -> "RagaVoiceParameters":
        if self.raga not in RAGA_NAMES:
            object.__setattr__(self, "raga", DEFAULT_RAGA)
        if self.sa not in SA_CHOICES:
            object.__setattr__(self, "sa", "C3")
        if self.style not in STYLES:
            object.__setattr__(self, "style", "walk")
        return self


RAGA_OUTPUTS = ("pitch", "frequency", "gate", "trigger", "phrase", "swara")

RAGA_VOICE_MANIFEST = ModuleManifest(
    id="pytheory_raga",
    name="PyTheory Raga",
    category="Musical Brains",
    description=(
        "One of PyTheory's fifty-four ragas, improvising the way a raga is "
        "played: up by the aroha, down by the avaroha, sometimes the pakad, in "
        "just intonation from its own ratios."
    ),
    ports=(
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "Each rising edge is a step."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Back to Sa."),
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The swara, one volt per octave, justly tuned."),
        port("frequency", "Hz", PortDirection.OUTPUT, SignalType.CV, "The same, in hertz."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High while a note sounds."),
        port("trigger", "Trig", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger at every note."),
        port("phrase", "Pakad", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger when the pakad begins."),
        port("swara", "Swara", PortDirection.OUTPUT, SignalType.CV, "Where in the raga, zero at Sa to one at Sa above."),
    ),
)


class RagaVoice:
    """Improvise in a raga."""

    manifest = RAGA_VOICE_MANIFEST
    readout = True
    """The panel shows the label: what is sounding, or which one this is."""

    def __init__(self, parameters: RagaVoiceParameters | None = None) -> None:
        self.parameters = parameters or RagaVoiceParameters()
        self._read_for: tuple[str, str] | None = None
        self._ratios: dict[str, float] = {}
        self._aroha: list[tuple[str, int]] = []
        self._avaroha: list[tuple[str, int]] = []
        self._pakad: list[tuple[str, int]] = []
        self._sa_hz = 130.81
        self._rng = np.random.default_rng(self.parameters.seed)
        self._current: tuple[str, int] = ("S", 0)
        self._direction = 1
        self._pending: list[tuple[str, int]] = []
        self._phase = 0.0
        self._clock_high = False
        self._reset_high = False
        self._gate_until = -1.0
        self._pending_trigger = 0
        self._pending_phrase = 0
        self._elapsed = 0.0

    @property
    def label(self) -> str:
        raga = Raga.get(self.parameters.raga)
        thaat = getattr(raga, "thaat", "")
        when = getattr(raga, "time", "")
        parts = [self.parameters.raga.upper()]
        if thaat:
            parts.append(f"THAAT {str(thaat).upper()}")
        if when:
            parts.append(str(when).upper())
        return "  ·  ".join(parts)

    def choices_for(self, field: str) -> tuple[str, ...]:
        if field == "raga":
            return RAGA_NAMES
        if field == "sa":
            return SA_CHOICES
        if field == "style":
            return STYLES
        return ()

    def _read(self) -> None:
        key = (self.parameters.raga, self.parameters.sa)
        if key == self._read_for:
            return
        raga = Raga.get(self.parameters.raga)
        self._ratios = {k: float(v) for k, v in raga.just_ratios().items()}
        self._aroha = [swara_octave(t) for t in raga.aroha_swaras()]
        self._avaroha = [swara_octave(t) for t in raga.avaroha_swaras()]
        self._pakad = [swara_octave(t) for t in raga.pakad_swaras()]
        midi = Tone.from_string(self.parameters.sa).midi
        self._sa_hz = 440.0 * 2.0 ** ((int(midi) - 69) / 12.0) if midi is not None else 130.81
        self._current = ("S", 0)
        self._direction = 1
        self._pending = []
        self._read_for = key

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._read()

    def _hertz(self, swara: tuple[str, int]) -> float:
        name, shift = swara
        ratio = self._ratios.get(name, 1.0)
        return self._sa_hz * ratio * (2.0 ** shift)

    def _index_in(self, line: list[tuple[str, int]], swara: tuple[str, int]) -> int | None:
        for index, candidate in enumerate(line):
            if candidate == swara:
                return index
        return None

    def _next_swara(self) -> tuple[tuple[str, int], bool]:
        """Choose the next note. Returns it and whether a pakad began."""
        style = self.parameters.style
        if self._pending:
            return self._pending.pop(0), False
        if style == "pakad" or (style == "walk" and self._rng.random() < self.parameters.pakad_chance):
            self._pending = list(self._pakad[1:])
            return self._pakad[0], True
        if style == "aroha avaroha":
            line = self._aroha if self._direction > 0 else self._avaroha
            at = self._index_in(line, self._current)
            nxt = 0 if at is None else at + 1
            if nxt >= len(line):
                self._direction = -self._direction
                line = self._aroha if self._direction > 0 else self._avaroha
                nxt = 1 if len(line) > 1 else 0
            self._current = line[nxt]
            return self._current, False
        # The walk: mostly a step in the current direction along that
        # direction's line, sometimes turning round, sometimes leaping.
        if self._rng.random() < 0.22:
            self._direction = -self._direction
        line = self._aroha if self._direction > 0 else self._avaroha
        at = self._index_in(line, self._current)
        if at is None:
            # Coming from the other line: land on the nearest note of this one.
            here = math.log2(self._hertz(self._current))
            at = min(range(len(line)), key=lambda i: abs(math.log2(self._hertz(line[i])) - here))
        leap = int(self._rng.integers(1, 3)) if self._rng.random() < 0.15 else 1
        nxt = at + leap
        if nxt >= len(line):
            self._direction = -self._direction
            other = self._aroha if self._direction > 0 else self._avaroha
            self._current = other[min(1, len(other) - 1)]
        else:
            self._current = line[nxt]
        return self._current, False

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
            return empty_outputs(RAGA_OUTPUTS)
        self._read()
        inputs = inputs or {}
        external = "clock" in inputs
        clock = np.asarray(block("clock", inputs, frame_count), dtype=np.float64)
        reset = np.asarray(block("reset", inputs, frame_count), dtype=np.float64)

        outputs = {name: np.zeros(frame_count, dtype=np.float32) for name in RAGA_OUTPUTS}
        if self._pending_trigger:
            outputs["trigger"][: min(self._pending_trigger, frame_count)] = 1.0
            self._pending_trigger = max(0, self._pending_trigger - frame_count)
        if self._pending_phrase:
            outputs["phrase"][: min(self._pending_phrase, frame_count)] = 1.0
            self._pending_phrase = max(0, self._pending_phrase - frame_count)

        step_period = 1.0 / self.parameters.rate_hz
        hertz = self._hertz(self._current)
        for index in range(frame_count):
            clock_event, self._clock_high = rising_edge(clock[index], self._clock_high)
            reset_event, self._reset_high = rising_edge(reset[index], self._reset_high)
            if reset_event:
                self._current = ("S", 0)
                self._direction = 1
                self._pending = []
                clock_event = True
            if not external:
                self._phase += 1.0 / sample_rate
                if self._phase >= step_period:
                    self._phase -= step_period
                    clock_event = True
            if clock_event:
                swara, began_pakad = self._next_swara()
                if self._rng.random() <= self.parameters.density:
                    hertz = self._hertz(swara)
                    self._gate_until = self._elapsed + index / sample_rate + step_period * self.parameters.gate_length
                    end = index + TRIGGER_SAMPLES
                    outputs["trigger"][index:end] = 1.0
                    if end > frame_count:
                        self._pending_trigger = end - frame_count
                    if began_pakad:
                        outputs["phrase"][index:end] = 1.0
                        if end > frame_count:
                            self._pending_phrase = end - frame_count
            outputs["frequency"][index] = hertz
            outputs["gate"][index] = 1.0 if (self._elapsed + index / sample_rate) < self._gate_until else 0.0
        self._elapsed += frame_count / sample_rate

        volts = np.log2(np.maximum(outputs["frequency"], 1e-6) / self.parameters.reference_frequency_hz)
        outputs["pitch"] = np.asarray(volts, dtype=np.float32)
        octave = np.log2(np.maximum(outputs["frequency"], 1e-6) / self._sa_hz)
        outputs["swara"] = np.asarray(np.clip(octave, 0.0, 1.0), dtype=np.float32)
        return outputs


__all__ = ["RAGA_NAMES", "RAGA_VOICE_MANIFEST", "RagaVoice", "RagaVoiceParameters", "swara_octave"]
