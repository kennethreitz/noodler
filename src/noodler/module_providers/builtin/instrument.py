"""A voice built from one of PyTheory's instruments.

PyTheory describes eighty-four instruments, and each description is a recipe
rather than a recording: which oscillator, which envelope, how much low-pass,
how much detune, how much room. Those are the same things a rack is made of, so
an instrument can be read as a patch that has already been made — pick "celesta"
and the oscillator, the contour and the filter are all decided at once.

The synth names in those recipes belong to PyTheory's own offline renderer, and
this is a real-time module, so the recipe is *realised* rather than executed:
each is mapped onto the nearest oscillator and contour Noodler can run inside an
audio callback. That mapping is stated here rather than implied, because it is
an interpretation and should be arguable.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import INSTRUMENTS

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


INSTRUMENT_NAMES: tuple[str, ...] = tuple(sorted(INSTRUMENTS))
DEFAULT_INSTRUMENT = "celesta" if "celesta" in INSTRUMENTS else INSTRUMENT_NAMES[0]

VOICE_OUTPUTS = ("audio", "envelope")

CONTOURS: dict[str, tuple[float, float, float, float]] = {
    "none": (0.004, 0.02, 1.0, 0.08),
    "organ": (0.012, 0.02, 1.0, 0.10),
    "pad": (0.60, 0.80, 0.75, 1.30),
    "strings": (0.18, 0.30, 0.80, 0.50),
    "bowed": (0.12, 0.20, 0.85, 0.35),
    "piano": (0.003, 1.20, 0.25, 0.90),
    "pluck": (0.002, 0.55, 0.00, 0.55),
    "mallet": (0.001, 0.35, 0.00, 0.35),
    "bell": (0.001, 2.60, 0.00, 2.60),
}
"""Attack, decay, sustain and release for each envelope PyTheory names."""

SINE_LIKE = (
    "sine", "flute", "theremin", "bowl", "vocal", "choir", "whistle", "ocarina",
)
FM_LIKE = (
    "fm", "bell", "crotales", "tingsha", "kalimba", "vibraphone", "marimba",
    "celesta", "music_box", "steel_drum", "glock",
)
PULSE_LIKE = ("clarinet", "square", "harpsichord", "organ", "accordion", "harmonium")
"""Families mapped onto the oscillator that comes nearest to them."""


def _shape_for(spec: Mapping[str, object]) -> str:
    """Choose the oscillator a recipe is asking for."""
    synth = str(spec.get("synth", "saw")).lower()
    for family, shape in ((SINE_LIKE, "sine"), (FM_LIKE, "fm"), (PULSE_LIKE, "pulse")):
        if any(word in synth for word in family):
            return shape
    return "saw"


def instrument_voice(name: str) -> dict[str, object]:
    """Read one instrument as the settings a voice can be built from."""
    spec = INSTRUMENTS.get(name) or INSTRUMENTS[DEFAULT_INSTRUMENT]
    attack, decay, sustain, release = CONTOURS.get(
        str(spec.get("envelope", "none")), CONTOURS["none"]
    )
    return {
        "shape": _shape_for(spec),
        "attack": attack,
        "decay": decay,
        "sustain": sustain,
        "release": release,
        "cutoff": float(spec.get("lowpass") or 12_000.0),
        "detune": float(spec.get("detune") or 0.0),
        "room": float(spec.get("reverb") or 0.0),
        "synth": str(spec.get("synth", "")),
        "envelope": str(spec.get("envelope", "none")),
    }


class InstrumentVoiceParameters(BaseModel):
    """Which instrument to be, and how far to take its advice."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    instrument: str = DEFAULT_INSTRUMENT
    level: float = Field(default=0.35, ge=0.0, le=1.0)
    brightness: float = Field(default=0.0, ge=-4.0, le=4.0)
    """Octaves of low-pass added to whatever the instrument asks for."""

    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def known(self) -> "InstrumentVoiceParameters":
        if self.instrument not in INSTRUMENTS:
            object.__setattr__(self, "instrument", DEFAULT_INSTRUMENT)
        return self


INSTRUMENT_VOICE_MANIFEST = ModuleManifest(
    id="instrument_voice",
    name="Instrument Voice",
    category="Oscillators",
    description=(
        "A whole voice from one of PyTheory's eighty-four instruments — "
        "oscillator, contour and filter chosen together. Give it a pitch and a "
        "gate and it plays."
    ),
    ports=(
        port("pitch", "1 V/oct", PortDirection.INPUT, SignalType.CV, "Pitch, against the reference."),
        port("gate", "Gate", PortDirection.INPUT, SignalType.GATE, "Hold to sustain the contour."),
        port("brightness_cv", "Bright", PortDirection.INPUT, SignalType.CV, "Opens or closes the filter, in octaves."),
        port("audio", "Out", PortDirection.OUTPUT, SignalType.AUDIO, "The voice."),
        port("envelope", "Env", PortDirection.OUTPUT, SignalType.CV, "Its contour, for anything else that wants it."),
    ),
)


class InstrumentVoice:
    """Play a PyTheory instrument as a real-time voice."""

    manifest = INSTRUMENT_VOICE_MANIFEST

    @property
    def strip_name(self) -> str:
        """What a console strip calls this: the instrument's last word, four letters."""
        return str(self.parameters.instrument).split("_")[-1][:4].upper()

    def __init__(self, parameters: InstrumentVoiceParameters | None = None) -> None:
        self.parameters = parameters or InstrumentVoiceParameters()
        self._phase = 0.0
        self._modulator_phase = 0.0
        self._level = 0.0
        self._releasing = False
        self._filter = 0.0
        self._voice_name: str | None = None
        self._voice: dict[str, object] = {}

    @property
    def voice(self) -> dict[str, object]:
        """The current recipe, read once per change rather than per block."""
        if self._voice_name != self.parameters.instrument:
            self._voice = instrument_voice(self.parameters.instrument)
            self._voice_name = self.parameters.instrument
        return self._voice

    def choices_for(self, field: str) -> tuple[str, ...]:
        return INSTRUMENT_NAMES if field == "instrument" else ()

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
            return empty_outputs(VOICE_OUTPUTS)

        inputs = inputs or {}
        voice = self.voice
        pitch = np.asarray(block("pitch", inputs, frame_count), dtype=np.float64)
        gate = np.asarray(block("gate", inputs, frame_count), dtype=np.float64)
        bright = np.asarray(
            block("brightness_cv", inputs, frame_count), dtype=np.float64
        )

        frequency = np.clip(
            self.parameters.reference_frequency_hz * np.exp2(np.clip(pitch, -8.0, 8.0)),
            1.0,
            sample_rate * 0.45,
        )
        increment = frequency / sample_rate
        phase = (self._phase + np.cumsum(increment)) % 1.0
        self._phase = float(phase[-1])

        shape = voice["shape"]
        if shape == "sine":
            tone = np.sin(2.0 * np.pi * phase)
        elif shape == "pulse":
            tone = np.where(phase < 0.5, 1.0, -1.0) * 0.7
        elif shape == "fm":
            modulator_increment = increment * 2.0
            modulator = (
                self._modulator_phase + np.cumsum(modulator_increment)
            ) % 1.0
            self._modulator_phase = float(modulator[-1])
            tone = np.sin(
                2.0 * np.pi * phase + 2.4 * np.sin(2.0 * np.pi * modulator)
            )
        else:
            tone = 2.0 * phase - 1.0
        detune = float(voice["detune"])
        if detune:
            spread = (phase * (1.0 + detune * 0.01)) % 1.0
            tone = (tone + (2.0 * spread - 1.0)) * 0.5

        # The contour and the filter are both one-pole recursions, so they share
        # one bare float loop: no numpy is touched per sample.
        attack = max(1e-4, float(voice["attack"]))
        decay = max(1e-4, float(voice["decay"]))
        sustain = float(voice["sustain"])
        release = max(1e-4, float(voice["release"]))
        attack_step = 1.0 / (attack * sample_rate)
        decay_step = 1.0 / (decay * sample_rate)
        release_step = 1.0 / (release * sample_rate)

        cutoff = np.clip(
            float(voice["cutoff"])
            * np.exp2(np.clip(bright + self.parameters.brightness, -6.0, 6.0)),
            30.0,
            sample_rate * 0.45,
        )
        coefficients = (
            1.0 - np.exp(-2.0 * np.pi * cutoff / sample_rate)
        ).tolist()

        gates = gate.tolist()
        tones = tone.tolist()
        envelope = [0.0] * frame_count
        voiced = [0.0] * frame_count
        level = self._level
        filtered = self._filter
        for sample in range(frame_count):
            if gates[sample] > 0.0:
                if level < 1.0 and not self._releasing:
                    level = min(1.0, level + attack_step)
                elif level > sustain:
                    level = max(sustain, level - decay_step)
                self._releasing = False
            else:
                self._releasing = True
                level = max(0.0, level - release_step)
            envelope[sample] = level
            filtered += coefficients[sample] * (tones[sample] * level - filtered)
            voiced[sample] = filtered
        self._level = level
        self._filter = filtered

        output = np.asarray(voiced, dtype=np.float64) * self.parameters.level
        return {
            "audio": np.asarray(np.tanh(output * 1.2), dtype=np.float32),
            "envelope": np.asarray(envelope, dtype=np.float32),
        }


__all__ = [
    "CONTOURS",
    "DEFAULT_INSTRUMENT",
    "INSTRUMENT_NAMES",
    "INSTRUMENT_VOICE_MANIFEST",
    "InstrumentVoice",
    "InstrumentVoiceParameters",
    "instrument_voice",
]
