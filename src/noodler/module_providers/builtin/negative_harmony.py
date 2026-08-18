"""Negative harmony: a melody mirrored about a key's axis.

Ernst Levy's idea, and Jacob Collier's party trick: reflect every note about
the axis between a key's tonic and its dominant -- for C major, the point
between E flat and E -- and major becomes minor, the dominant becomes the
subdominant, a line that rose now falls, and it all still belongs to the key.
PyTheory works the mapping out for a key; this module does it to a pitch
voltage, note by note, so any brain's line can be heard mirrored, or the same
line and its mirror at once.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import Key

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


TONICS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MODES = ("major", "minor")
AXIS_ABOVE_TONIC = 3.5
"""The axis of negative harmony lies between the minor and major third above
the tonic: three and a half semitones up. C major's is between E flat and E."""


class NegativeHarmonyParameters(BaseModel):
    """The key whose axis the pitch is mirrored about."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tonic: str = "C"
    mode: str = "major"
    mirror: bool = True
    """Off, the pitch passes through untouched: the same module, A or B."""
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def known(self) -> "NegativeHarmonyParameters":
        if self.tonic not in TONICS:
            object.__setattr__(self, "tonic", "C")
        if self.mode not in MODES:
            object.__setattr__(self, "mode", "major")
        return self


NEGATIVE_HARMONY_MANIFEST = ModuleManifest(
    id="pytheory_negative_harmony",
    name="PyTheory Negative Harmony",
    category="Musical Brains",
    description=(
        "Mirrors a pitch about a key's axis of negative harmony -- between the "
        "minor and major third above the tonic -- so major becomes minor and a "
        "line that rose falls, still in the key. PyTheory's mapping, applied "
        "to a voltage."
    ),
    ports=(
        port("pitch", "Pitch", PortDirection.INPUT, SignalType.CV, "A pitch, one volt per octave."),
        port("mirror", "Mirror", PortDirection.INPUT, SignalType.GATE, "Mirror while high; unpatched, the switch decides."),
        port("out", "Out", PortDirection.OUTPUT, SignalType.CV, "The pitch, mirrored."),
        port("straight", "Same", PortDirection.OUTPUT, SignalType.CV, "The pitch as it came, for playing both."),
    ),
)


def mirror_midi(midi: float, tonic_index: int) -> float:
    """Reflect a MIDI note about the key's axis, in the octave nearest to it."""
    axis = tonic_index + AXIS_ABOVE_TONIC
    # Reflect about the axis in the note's own octave, then pick the octave
    # copy of the result closest to the note, so a line does not leap.
    reflected = 2.0 * axis - midi
    while reflected - midi > 6.0:
        reflected -= 12.0
    while midi - reflected > 6.0:
        reflected += 12.0
    return reflected


class NegativeHarmony:
    """Mirror pitches about a key's axis."""

    manifest = NEGATIVE_HARMONY_MANIFEST

    def __init__(self, parameters: NegativeHarmonyParameters | None = None) -> None:
        self.parameters = parameters or NegativeHarmonyParameters()

    def choices_for(self, field: str) -> tuple[str, ...]:
        if field == "tonic":
            return TONICS
        if field == "mode":
            return MODES
        return ()

    @property
    def label(self) -> str:
        try:
            axis = Key(self.parameters.tonic, self.parameters.mode).negative_harmony().get("axis_notes", ())
        except Exception:
            axis = ()
        between = f"  ·  AXIS {'/'.join(str(a) for a in axis)}" if axis else ""
        state = "" if self.parameters.mirror else "  ·  STRAIGHT"
        return f"{self.parameters.tonic} {self.parameters.mode.upper()}{between}{state}"

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

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
            return empty_outputs(("out", "straight"))
        inputs = inputs or {}
        volts = np.asarray(block("pitch", inputs, frame_count), dtype=np.float64)
        reference = self.parameters.reference_frequency_hz
        # Volts to MIDI, reflect, back to volts: all vectorised.
        midi = 69.0 + 12.0 * np.log2(np.maximum(reference * np.exp2(volts), 1e-6) / 440.0)
        tonic_index = TONICS.index(self.parameters.tonic)
        axis = tonic_index + AXIS_ABOVE_TONIC
        reflected = 2.0 * axis - midi
        # Nearest octave copy: shift by whole octaves so |reflected - midi| <= 6.
        octaves = np.round((reflected - midi) / 12.0)
        reflected = reflected - 12.0 * octaves
        mirrored_volts = np.log2(np.maximum(440.0 * np.exp2((reflected - 69.0) / 12.0), 1e-6) / reference)
        if "mirror" in inputs:
            on = np.asarray(block("mirror", inputs, frame_count), dtype=np.float64) > 0.5
        else:
            on = np.full(frame_count, self.parameters.mirror)
        out = np.where(on, mirrored_volts, volts)
        return {
            "out": np.asarray(out, dtype=np.float32),
            "straight": np.asarray(volts, dtype=np.float32),
        }


__all__ = ["AXIS_ABOVE_TONIC", "NEGATIVE_HARMONY_MANIFEST", "NegativeHarmony", "NegativeHarmonyParameters", "mirror_midi"]
