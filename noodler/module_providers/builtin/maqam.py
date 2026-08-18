"""A maqam, played the way a maqam is played: up its degrees and back down,
in just intonation, quarter-tones and all.

PyTheory knows ten maqamat -- Rast, Bayati, Hijaz, Saba and the rest -- each
as degrees in quarter-tones, a family, a mood, its ajnas (the tetrachords it
is built from) and its seyir, the way a performance of it tends to move; and
it can tune one justly from a tonic, so a neutral third is a neutral third
and not the nearest piano key. This module walks one: mostly by step in a
direction, turning round now and then, leaping sometimes, resting on the
tonic and the fifth as a seyir does; or straight up and down its scale. It
is clocked like the rack's other brains and puts out pitch and gate for any
voice.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import Maqam

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


MAQAM_NAMES: tuple[str, ...] = tuple(Maqam.names())
DEFAULT_MAQAM = "Rast" if "Rast" in MAQAM_NAMES else MAQAM_NAMES[0]
TONIC_CHOICES: tuple[str, ...] = tuple(
    f"{name}{octave}" for octave in (2, 3, 4) for name in ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
)
STYLES = ("walk", "up down")
TRIGGER_SAMPLES = 240


class MaqamParameters(BaseModel):
    """Which maqam, where its tonic is, and how the line moves."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    maqam: str = DEFAULT_MAQAM
    tonic: str = "D3"
    style: str = "walk"
    span_octaves: int = Field(default=1, ge=1, le=2)
    """How far above the tonic the line may go: one octave, or two."""
    rest_chance: float = Field(default=0.2, ge=0.0, le=1.0)
    """How often a step rests on the tonic or the fifth, as a seyir does."""
    density: float = Field(default=0.8, ge=0.0, le=1.0)
    gate_length: float = Field(default=0.6, ge=0.05, le=1.0)
    rate_hz: float = Field(default=2.0, gt=0.0, le=40.0)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    seed: int = Field(default=11, ge=0)

    @model_validator(mode="after")
    def known(self) -> "MaqamParameters":
        if self.maqam not in MAQAM_NAMES:
            object.__setattr__(self, "maqam", DEFAULT_MAQAM)
        if self.tonic not in TONIC_CHOICES:
            object.__setattr__(self, "tonic", "D3")
        if self.style not in STYLES:
            object.__setattr__(self, "style", "walk")
        return self


MAQAM_OUTPUTS = ("pitch", "frequency", "gate", "trigger", "degree", "tonic")

MAQAM_MANIFEST = ModuleManifest(
    id="pytheory_maqam",
    name="PyTheory Maqam",
    category="Musical Brains",
    description=(
        "One of PyTheory's ten maqamat, walked the way a maqam is played -- "
        "by step, turning, resting on the tonic and the fifth -- in just "
        "intonation with its quarter-tones, from any tonic."
    ),
    ports=(
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "Each rising edge is a step."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Back to the tonic."),
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The degree, one volt per octave, justly tuned."),
        port("frequency", "Hz", PortDirection.OUTPUT, SignalType.CV, "The same, in hertz."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High while a note sounds."),
        port("trigger", "Trig", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger at every note."),
        port("degree", "Deg", PortDirection.OUTPUT, SignalType.CV, "Where in the maqam, zero at the tonic to one at the octave."),
        port("tonic", "Tonic", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger when the line lands on the tonic."),
    ),
)


class MaqamVoice:
    """Improvise in a maqam."""

    manifest = MAQAM_MANIFEST
    readout = True
    """The panel shows the label: what is sounding, or which one this is."""

    def __init__(self, parameters: MaqamParameters | None = None) -> None:
        self.parameters = parameters or MaqamParameters()
        self._read_for: tuple[str, str, int] | None = None
        self._ladder: list[float] = []
        """The maqam's degrees as frequencies, tonic up to the top of the span."""
        self._tonic_hz = 146.83
        self._rng = np.random.default_rng(self.parameters.seed)
        self._at = 0
        self._direction = 1
        self._land_on_tonic = True
        """The next note is the tonic itself: at the start, and after a reset."""
        self._phase = 0.0
        self._clock_high = False
        self._reset_high = False
        self._gate_until = -1.0
        self._pending_trigger = 0
        self._pending_tonic = 0
        self._elapsed = 0.0

    @property
    def label(self) -> str:
        maqam = Maqam.get(self.parameters.maqam)
        parts = [self.parameters.maqam.upper()]
        family = getattr(maqam, "family", "")
        if family and str(family).lower() != self.parameters.maqam.lower():
            parts.append(f"FAMILY {str(family).upper()}")
        if getattr(maqam, "has_quartertones", False):
            parts.append("QUARTER-TONES")
        return "  ·  ".join(parts)

    def choices_for(self, field: str) -> tuple[str, ...]:
        if field == "maqam":
            return MAQAM_NAMES
        if field == "tonic":
            return TONIC_CHOICES
        if field == "style":
            return STYLES
        return ()

    def _read(self) -> None:
        key = (self.parameters.maqam, self.parameters.tonic, self.parameters.span_octaves)
        if key == self._read_for:
            return
        maqam = Maqam.get(self.parameters.maqam)
        # PyTheory gives the just frequencies up the octave and back down; the
        # first half, up to and including the octave, is the ladder.
        up_and_down = [float(f) for f in maqam.just_frequencies(self.parameters.tonic)]
        top = up_and_down.index(max(up_and_down)) + 1 if up_and_down else 0
        ladder = up_and_down[:top]
        if not ladder:
            ladder = [146.83]
        octave = ladder[0] * 2.0
        if self.parameters.span_octaves > 1:
            ladder = ladder[:-1] + [f * 2.0 for f in ladder]
        self._tonic_hz = ladder[0]
        self._ladder = ladder
        self._at = 0
        self._direction = 1
        self._read_for = key
        del octave

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._read()

    def _next(self) -> tuple[int, bool]:
        """The next rung of the ladder; whether it is a rest on tonic or fifth."""
        top = len(self._ladder) - 1
        if self.parameters.style == "up down":
            nxt = self._at + self._direction
            if nxt > top or nxt < 0:
                self._direction = -self._direction
                nxt = self._at + self._direction
            self._at = max(0, min(top, nxt))
            return self._at, self._at % 7 in (0, 4)
        if self._rng.random() < self.parameters.rest_chance:
            # A rest: the tonic or the fifth nearest where the line is.
            rests = [i for i in range(len(self._ladder)) if i % 7 in (0, 4)]
            self._at = min(rests, key=lambda i: abs(i - self._at)) if rests else 0
            return self._at, True
        if self._rng.random() < 0.25:
            self._direction = -self._direction
        leap = int(self._rng.integers(2, 4)) if self._rng.random() < 0.15 else 1
        nxt = self._at + self._direction * leap
        if nxt > top or nxt < 0:
            self._direction = -self._direction
            nxt = self._at + self._direction
        self._at = max(0, min(top, nxt))
        return self._at, False

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
            return empty_outputs(MAQAM_OUTPUTS)
        self._read()
        inputs = inputs or {}
        external = "clock" in inputs
        clock = np.asarray(block("clock", inputs, frame_count), dtype=np.float64)
        reset = np.asarray(block("reset", inputs, frame_count), dtype=np.float64)
        outputs = {name: np.zeros(frame_count, dtype=np.float32) for name in MAQAM_OUTPUTS}
        if self._pending_trigger:
            outputs["trigger"][: min(self._pending_trigger, frame_count)] = 1.0
            self._pending_trigger = max(0, self._pending_trigger - frame_count)
        if self._pending_tonic:
            outputs["tonic"][: min(self._pending_tonic, frame_count)] = 1.0
            self._pending_tonic = max(0, self._pending_tonic - frame_count)

        period = 1.0 / self.parameters.rate_hz
        hertz = self._ladder[self._at]
        for index in range(frame_count):
            clock_event, self._clock_high = rising_edge(clock[index], self._clock_high)
            reset_event, self._reset_high = rising_edge(reset[index], self._reset_high)
            if reset_event:
                self._at = 0
                self._direction = 1
                self._land_on_tonic = True
                clock_event = True
            if not external:
                self._phase += 1.0 / sample_rate
                if self._phase >= period:
                    self._phase -= period
                    clock_event = True
            if clock_event:
                if self._land_on_tonic:
                    rung = self._at = 0
                    self._land_on_tonic = False
                else:
                    rung, _rest = self._next()
                # The tonic always sounds; the rest of the line, as dense as asked.
                if rung == 0 or self._rng.random() <= self.parameters.density:
                    hertz = self._ladder[rung]
                    self._gate_until = self._elapsed + index / sample_rate + period * self.parameters.gate_length
                    end = index + TRIGGER_SAMPLES
                    outputs["trigger"][index:end] = 1.0
                    if end > frame_count:
                        self._pending_trigger = end - frame_count
                    if rung % 7 == 0:
                        outputs["tonic"][index:end] = 1.0
                        if end > frame_count:
                            self._pending_tonic = end - frame_count
            outputs["frequency"][index] = hertz
            outputs["gate"][index] = 1.0 if (self._elapsed + index / sample_rate) < self._gate_until else 0.0
        self._elapsed += frame_count / sample_rate
        volts = np.log2(np.maximum(outputs["frequency"], 1e-6) / self.parameters.reference_frequency_hz)
        outputs["pitch"] = np.asarray(volts, dtype=np.float32)
        octave = np.log2(np.maximum(outputs["frequency"], 1e-6) / self._tonic_hz)
        outputs["degree"] = np.asarray(np.clip(octave, 0.0, 1.0), dtype=np.float32)
        return outputs


__all__ = ["MAQAM_MANIFEST", "MAQAM_NAMES", "MaqamParameters", "MaqamVoice", "STYLES", "TONIC_CHOICES"]
