"""Modules that trade in musical meaning rather than in one of its notes."""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.music import (
    DEFAULT_OCTAVE,
    DEFAULT_SCALE,
    DEFAULT_SYSTEM,
    DEFAULT_TONIC,
    SYSTEM_NAMES,
    ScaleField,
    build_scale,
    quantize,
    scale_names_for,
    tonics_for,
)

from ._dsp import FloatBlock, block, empty_outputs, port


KEY_OUTPUTS = ("scale", "root", "frequency", "tones")
QUANTIZER_OUTPUTS = ("pitch", "frequency", "degree", "trigger")


def _coerce(system: str, tonic: str, octave: int, name: str) -> tuple[str, str, str]:
    """Settle on a system, tonic and mode that actually go together.

    Systems do not share a vocabulary, so changing one invalidates the other
    two. Rather than refuse the edit, the nearest valid neighbours are taken:
    a rack should keep playing while it is being retuned.
    """
    if system not in SYSTEM_NAMES:
        system = DEFAULT_SYSTEM
    tonics = tonics_for(system)
    if tonics and tonic not in tonics:
        tonic = tonics[0]
    names = scale_names_for(system, tonic, octave)
    if names and name not in names:
        name = names[0]
    return system, tonic, name


class KeyParameters(BaseModel):
    """Which music this rack is in."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    system: str = DEFAULT_SYSTEM
    tonic: str = DEFAULT_TONIC
    octave: int = Field(default=DEFAULT_OCTAVE, ge=0, le=9)
    scale_name: str = DEFAULT_SCALE
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def settle(self) -> "KeyParameters":
        system, tonic, name = _coerce(
            self.system, self.tonic, self.octave, self.scale_name
        )
        object.__setattr__(self, "system", system)
        object.__setattr__(self, "tonic", tonic)
        object.__setattr__(self, "scale_name", name)
        return self


KEY_MANIFEST = ModuleManifest(
    id="key",
    name="Key / Scale",
    category="Musical Brains",
    description=(
        "The music a patch is in — any of PyTheory's tone systems, from maqamat "
        "and melakarta ragas to gamelan and Bohlen-Pierce — sent as a scale "
        "rather than as one of its notes."
    ),
    ports=(
        port("scale", "Scale", PortDirection.OUTPUT, SignalType.MUSICAL, "The whole scale, for modules that can read one."),
        port("root", "Root", PortDirection.OUTPUT, SignalType.CV, "Tonic as one-volt-per-octave pitch."),
        port("frequency", "Root Hz", PortDirection.OUTPUT, SignalType.CV, "Tonic frequency in hertz."),
        port("tones", "Tones", PortDirection.OUTPUT, SignalType.CV, "How many tones the scale has."),
    ),
)


class Key:
    """Publish a scale, so that the rest of the rack can be in it."""

    manifest = KEY_MANIFEST

    def __init__(self, parameters: KeyParameters | None = None) -> None:
        self.parameters = parameters or KeyParameters()
        self._field: ScaleField | None = None
        self._settings: tuple[str, str, int, str] | None = None

    @property
    def field(self) -> ScaleField | None:
        """The current scale, rebuilt only when the settings change."""
        parameters = self.parameters
        settings = (
            parameters.system,
            parameters.tonic,
            parameters.octave,
            parameters.scale_name,
        )
        if settings != self._settings:
            built = build_scale(*settings)
            if built is not None:
                self._field = built
            self._settings = settings
        return self._field

    @property
    def label(self) -> str:
        field = self.field
        return field.label if field else "—"

    def choices_for(self, field: str) -> tuple[str, ...]:
        """Offer a panel the words this system actually recognises."""
        parameters = self.parameters
        if field == "system":
            return SYSTEM_NAMES
        if field == "tonic":
            return tonics_for(parameters.system)
        if field == "scale_name":
            return scale_names_for(
                parameters.system, parameters.tonic, parameters.octave
            )
        return ()

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, object]:
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        field = self.field
        if frame_count == 0:
            outputs: dict[str, object] = dict(
                empty_outputs(("root", "frequency", "tones"))
            )
            outputs["scale"] = field
            return outputs

        reference = self.parameters.reference_frequency_hz
        root_hz = field.root_hz if field else reference
        pitch = float(np.log2(root_hz / reference)) if root_hz > 0.0 else 0.0
        return {
            "scale": field,
            "root": np.full(frame_count, pitch, dtype=np.float32),
            "frequency": np.full(frame_count, root_hz, dtype=np.float32),
            "tones": np.full(
                frame_count, float(len(field.tones)) if field else 0.0, dtype=np.float32
            ),
        }


class QuantizerParameters(BaseModel):
    """How a voltage is read as a pitch, and what to do without a scale."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    transpose_octaves: float = Field(default=0.0, ge=-4.0, le=4.0)
    system: str = DEFAULT_SYSTEM
    tonic: str = DEFAULT_TONIC
    octave: int = Field(default=DEFAULT_OCTAVE, ge=0, le=9)
    scale_name: str = DEFAULT_SCALE

    @model_validator(mode="after")
    def settle(self) -> "QuantizerParameters":
        system, tonic, name = _coerce(
            self.system, self.tonic, self.octave, self.scale_name
        )
        object.__setattr__(self, "system", system)
        object.__setattr__(self, "tonic", tonic)
        object.__setattr__(self, "scale_name", name)
        return self


QUANTIZER_MANIFEST = ModuleManifest(
    id="quantizer",
    name="Scale Quantizer",
    category="Musical Brains",
    description=(
        "Snap any voltage into a scale. Patch a Key into it and a random source "
        "becomes a melody in that music; change the Key and everything "
        "downstream is retuned at once."
    ),
    ports=(
        port("cv", "Pitch In", PortDirection.INPUT, SignalType.CV, "One volt per octave, to be snapped."),
        port("scale", "Scale", PortDirection.INPUT, SignalType.MUSICAL, "The scale to snap into. Falls back to the panel."),
        port("transpose", "Transpose", PortDirection.INPUT, SignalType.CV, "Octaves added before quantising."),
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The nearest tone, one volt per octave."),
        port("frequency", "Hz", PortDirection.OUTPUT, SignalType.CV, "The nearest tone in hertz."),
        port("degree", "Degree", PortDirection.OUTPUT, SignalType.CV, "Where in the scale the tone sits, zero to one."),
        port("trigger", "Changed", PortDirection.OUTPUT, SignalType.TRIGGER, "A pulse whenever the tone changes."),
    ),
)


class Quantizer:
    """Read a voltage as the nearest tone of whatever scale it is handed."""

    manifest = QUANTIZER_MANIFEST

    def __init__(self, parameters: QuantizerParameters | None = None) -> None:
        self.parameters = parameters or QuantizerParameters()
        self._table = np.zeros(0, dtype=np.float64)
        self._table_key: tuple[object, ...] | None = None
        self._last_pitch: float | None = None
        self._field: ScaleField | None = None

    @property
    def field(self) -> ScaleField | None:
        return self._field

    def choices_for(self, field: str) -> tuple[str, ...]:
        """Offer a panel the words this system actually recognises."""
        parameters = self.parameters
        if field == "system":
            return SYSTEM_NAMES
        if field == "tonic":
            return tonics_for(parameters.system)
        if field == "scale_name":
            return scale_names_for(
                parameters.system, parameters.tonic, parameters.octave
            )
        return ()

    def _table_for(self, field: ScaleField | None) -> np.ndarray:
        """Cache the pitch table; the callback should only ever search it."""
        parameters = self.parameters
        if field is None:
            field = build_scale(
                parameters.system,
                parameters.tonic,
                parameters.octave,
                parameters.scale_name,
            )
        self._field = field
        key = (
            id(field),
            field.label if field else None,
            parameters.reference_frequency_hz,
        )
        if key != self._table_key:
            self._table = (
                field.pitch_table(parameters.reference_frequency_hz)
                if field is not None
                else np.zeros(0, dtype=np.float64)
            )
            self._table_key = key
        return self._table

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
            return empty_outputs(QUANTIZER_OUTPUTS)

        inputs = inputs or {}
        offered = inputs.get("scale")
        table = self._table_for(offered if isinstance(offered, ScaleField) else None)

        pitch = block("cv", inputs, frame_count)
        transpose = block("transpose", inputs, frame_count)
        wanted = (
            np.asarray(pitch, dtype=np.float64)
            + np.asarray(transpose, dtype=np.float64)
            + self.parameters.transpose_octaves
        )
        snapped = quantize(wanted, table)

        reference = self.parameters.reference_frequency_hz
        frequency = reference * np.exp2(snapped)
        if table.size > 1:
            position = np.searchsorted(table, snapped)
            degree = np.clip(position / (table.size - 1), 0.0, 1.0)
        else:
            degree = np.zeros(frame_count, dtype=np.float64)

        trigger = np.zeros(frame_count, dtype=np.float64)
        previous = self._last_pitch
        for index in range(frame_count):
            here = float(snapped[index])
            if previous is None or here != previous:
                trigger[index] = 1.0
                previous = here
        self._last_pitch = previous

        return {
            "pitch": np.asarray(snapped, dtype=np.float32),
            "frequency": np.asarray(frequency, dtype=np.float32),
            "degree": np.asarray(degree, dtype=np.float32),
            "trigger": np.asarray(trigger, dtype=np.float32),
        }


__all__ = [
    "KEY_MANIFEST",
    "QUANTIZER_MANIFEST",
    "Key",
    "KeyParameters",
    "Quantizer",
    "QuantizerParameters",
]
