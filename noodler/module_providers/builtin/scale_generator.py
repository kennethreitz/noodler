"""Clocked scale sequencing prepared with PyTheory."""

from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import TonedScale

from noodler.module_providers import (
    AudioCvPolicy,
    ModuleManifest,
    PortDirection,
    PortManifest,
    SignalType,
)


FloatBlock = NDArray[np.float32]
OUTPUT_NAMES = ("note", "pitch", "frequency", "degree", "gate", "trigger")
SUPPORTED_SCALE_SYSTEMS = (
    "western",
    "blues",
    "japanese",
    "19-tet",
    "31-tet",
    "bohlen-pierce",
)
TONICS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


class SequencePattern(StrEnum):
    """Ways a clock can walk the prepared scale tones."""

    UP = "up"
    DOWN = "down"
    UP_DOWN = "up / down"
    RANDOM = "random"
    WANDER = "melodic wander"


@lru_cache(maxsize=None)
def scale_names(system: str) -> tuple[str, ...]:
    """Return the scale names PyTheory exposes for a supported system."""
    if system not in SUPPORTED_SCALE_SYSTEMS:
        raise ValueError(f"unsupported scale system: {system}")
    return tuple(TonedScale(tonic="C4", system=system).scales)


class ScaleGeneratorParameters(BaseModel):
    """Serializable controls for a prepared PyTheory scale sequence."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    system: str = "western"
    tonic: str = "C"
    octave: int = Field(default=4, ge=0, le=8)
    scale_name: str = "dorian"
    pattern: SequencePattern = SequencePattern.UP_DOWN
    rate_hz: float = Field(default=1.5, ge=0.01, le=100.0)
    gate_length: float = Field(default=0.5, ge=0.01, le=0.99)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def selection_exists_in_pytheory(self) -> "ScaleGeneratorParameters":
        if self.system not in SUPPORTED_SCALE_SYSTEMS:
            raise ValueError(f"unsupported scale system: {self.system}")
        if self.tonic not in TONICS:
            raise ValueError(f"unsupported tonic: {self.tonic}")
        if self.scale_name not in scale_names(self.system):
            raise ValueError(
                f"{self.scale_name!r} is not a {self.system} scale"
            )
        try:
            TonedScale(
                tonic=f"{self.tonic}{self.octave}",
                system=self.system,
            )[self.scale_name]
        except (KeyError, ValueError) as exc:
            raise ValueError(f"PyTheory cannot build this scale: {exc}") from exc
        return self


def _port(
    port_id: str,
    name: str,
    direction: PortDirection,
    signal_type: SignalType,
    description: str,
) -> PortManifest:
    return PortManifest(
        id=port_id,
        name=name,
        direction=direction,
        signal_type=signal_type,
        description=description,
        audio_cv_policy=(
            AudioCvPolicy.ALLOW
            if signal_type in {SignalType.AUDIO, SignalType.CV}
            else AudioCvPolicy.WARN
        ),
    )


SCALE_GENERATOR_MANIFEST = ModuleManifest(
    id="scale_generator",
    name="PyTheory Scale Generator",
    category="Sequencers",
    description=(
        "A clocked scale-degree generator whose tones, spellings, MIDI notes, "
        "and frequencies are prepared by PyTheory."
    ),
    ports=(
        _port(
            "clock",
            "Clock",
            PortDirection.INPUT,
            SignalType.GATE,
            "Rising edges advance the scale and replace the internal clock.",
        ),
        _port(
            "reset",
            "Reset",
            PortDirection.INPUT,
            SignalType.TRIGGER,
            "Rising edge returns to the tonic and restarts the traversal.",
        ),
        _port(
            "transpose",
            "Transpose",
            PortDirection.INPUT,
            SignalType.CV,
            "Continuous transposition in octaves, applied after scale lookup.",
        ),
        _port(
            "note",
            "Note",
            PortDirection.OUTPUT,
            SignalType.MUSICAL,
            "PyTheory tone represented provisionally as a MIDI-compatible note block.",
        ),
        _port(
            "pitch",
            "1 V/oct",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Octave pitch relative to the configured reference frequency.",
        ),
        _port(
            "frequency",
            "Frequency",
            PortDirection.OUTPUT,
            SignalType.CV,
            "The selected PyTheory tone frequency in hertz.",
        ),
        _port(
            "degree",
            "Degree",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Current scale position normalized from zero to one.",
        ),
        _port(
            "gate",
            "Gate",
            PortDirection.OUTPUT,
            SignalType.GATE,
            "Internal gate or a squared copy of the external clock.",
        ),
        _port(
            "trigger",
            "Trigger",
            PortDirection.OUTPUT,
            SignalType.TRIGGER,
            "A one-sample pulse whenever the selected tone changes.",
        ),
    ),
)


class ScaleGenerator:
    """Sequence cached PyTheory tones without theory work in the audio callback."""

    manifest = SCALE_GENERATOR_MANIFEST

    def __init__(self, parameters: ScaleGeneratorParameters | None = None) -> None:
        self.parameters = parameters or ScaleGeneratorParameters()
        self._tones = self._tones_for(self.parameters)
        self._index = 0
        self._direction = 1
        self._phrase_step = 0
        self._clock_phase = 0.0
        self._external_clock_high = False
        self._reset_high = False
        self._rng = np.random.default_rng(self.parameters.seed)

    @property
    def current_note(self) -> str:
        return self._tones[self._index][0]

    @property
    def current_frequency(self) -> float:
        return self._tones[self._index][1]

    @property
    def current_degree(self) -> int:
        return self._index + 1

    @property
    def degree_count(self) -> int:
        return len(self._tones)

    @property
    def scale_label(self) -> str:
        return (
            f"{self.parameters.tonic} {self.parameters.scale_name}"
            f" · {self.parameters.system}"
        )

    def configure(self, **changes: object) -> None:
        """Validate a new selection and prepare its tones on the control path."""
        values = self.parameters.model_dump()
        values.update(changes)
        parameters = ScaleGeneratorParameters.model_validate(values)
        tones = self._tones_for(parameters)
        self.parameters = parameters
        self._tones = tones
        self._index = 0
        self._direction = 1
        self._phrase_step = 0
        self._rng = np.random.default_rng(parameters.seed)

    def reset(self) -> None:
        """Return the traversal and deterministic random pattern to the tonic."""
        self._index = 0
        self._direction = 1
        self._phrase_step = 0
        self._clock_phase = 0.0
        self._external_clock_high = False
        self._reset_high = False
        self._rng = np.random.default_rng(self.parameters.seed)

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        """Render pitch, musical-note, timing, and degree blocks."""
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if frame_count == 0:
            return {
                name: np.empty(0, dtype=np.float32)
                for name in OUTPUT_NAMES
            }

        inputs = inputs or {}
        external_clock_patched = "clock" in inputs
        clock = self._optional_block("clock", inputs, frame_count)
        reset = self._optional_block("reset", inputs, frame_count)
        transpose = self._optional_block("transpose", inputs, frame_count)
        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in OUTPUT_NAMES
        }

        for index in range(frame_count):
            clock_high = bool(clock[index] > 0.0)
            if external_clock_patched:
                clock_event = clock_high and not self._external_clock_high
                gate = 1.0 if clock_high else 0.0
            else:
                gate = (
                    1.0
                    if self._clock_phase < self.parameters.gate_length
                    else 0.0
                )
                self._clock_phase += self.parameters.rate_hz / sample_rate
                clock_event = self._clock_phase >= 1.0
                if clock_event:
                    self._clock_phase %= 1.0

            reset_high = bool(reset[index] > 0.0)
            reset_event = reset_high and not self._reset_high
            trigger = 0.0
            if reset_event:
                self._index = 0
                self._direction = 1
                trigger = 1.0
            elif clock_event:
                self._advance()
                trigger = 1.0

            name, base_frequency, midi = self._tones[self._index]
            transposition = float(np.clip(transpose[index], -16.0, 16.0))
            frequency = base_frequency * 2.0**transposition
            pitch = math.log2(
                frequency / self.parameters.reference_frequency_hz
            )

            outputs["note"][index] = midi + 12.0 * transposition
            outputs["pitch"][index] = pitch
            outputs["frequency"][index] = frequency
            outputs["degree"][index] = (
                self._index / (len(self._tones) - 1)
                if len(self._tones) > 1
                else 0.0
            )
            outputs["gate"][index] = gate
            outputs["trigger"][index] = trigger
            self._external_clock_high = clock_high
            self._reset_high = reset_high

        return {
            name: np.asarray(block, dtype=np.float32)
            for name, block in outputs.items()
        }

    @staticmethod
    def _tones_for(
        parameters: ScaleGeneratorParameters,
    ) -> tuple[tuple[str, float, float], ...]:
        scale = TonedScale(
            tonic=f"{parameters.tonic}{parameters.octave}",
            system=parameters.system,
        )[parameters.scale_name]
        tones = tuple(
            (str(tone), float(tone.frequency), float(tone.midi))
            for tone in scale.tones
        )
        if not tones:
            raise ValueError("PyTheory returned an empty scale")
        return tones

    def _advance(self) -> None:
        count = len(self._tones)
        if count <= 1:
            return
        pattern = self.parameters.pattern
        if pattern is SequencePattern.UP:
            self._index = (self._index + 1) % count
        elif pattern is SequencePattern.DOWN:
            self._index = (self._index - 1) % count
        elif pattern is SequencePattern.RANDOM:
            self._index = int(self._rng.integers(count))
        elif pattern is SequencePattern.WANDER:
            self._advance_wander(count)
        else:
            candidate = self._index + self._direction
            if candidate >= count:
                self._direction = -1
                candidate = count - 2
            elif candidate < 0:
                self._direction = 1
                candidate = 1
            self._index = candidate

    def _advance_wander(self, count: int) -> None:
        """Take a seeded, phrase-aware walk instead of choosing isolated notes."""
        self._phrase_step = (self._phrase_step + 1) % 16
        if self._phrase_step in {0, 8}:
            # Every eight events comes home; every other phrase lands an octave up.
            self._index = 0 if self._phrase_step == 0 else count - 1
            return
        if self._phrase_step in {4, 12}:
            # Mid-phrase anchors favor characteristic interior scale tones.
            anchors = sorted({min(count - 1, 2), min(count - 1, 4)})
            self._index = int(self._rng.choice(anchors))
            return

        interval = int(
            self._rng.choice((-2, -1, 1, 2), p=(0.12, 0.38, 0.38, 0.12))
        )
        candidate = self._index + interval
        # Reflect at the boundaries so the melody changes direction naturally.
        if candidate < 0:
            candidate = -candidate
        if candidate >= count:
            candidate = 2 * (count - 1) - candidate
        self._index = max(0, min(count - 1, candidate))

    @staticmethod
    def _optional_block(
        name: str,
        inputs: Mapping[str, ArrayLike],
        frame_count: int,
    ) -> NDArray[np.float64]:
        if name not in inputs:
            return np.zeros(frame_count, dtype=np.float64)
        value = np.asarray(inputs[name], dtype=np.float64)
        if value.ndim == 0:
            return np.full(frame_count, float(value), dtype=np.float64)
        if value.shape != (frame_count,):
            raise ValueError(
                f"{name} must be scalar or have shape ({frame_count},), "
                f"got {value.shape}"
            )
        return value


__all__ = [
    "SCALE_GENERATOR_MANIFEST",
    "SUPPORTED_SCALE_SYSTEMS",
    "TONICS",
    "ScaleGenerator",
    "ScaleGeneratorParameters",
    "SequencePattern",
    "scale_names",
]
