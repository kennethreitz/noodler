"""One chord, held, so the rest of the rack can play it.

A name such as ``Am7`` is asked of PyTheory once. What comes out is four
voices at one volt per octave — root on the first, the rest above it — which
is what the arpeggiator already expects to be handed.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field
from pytheory import Chord

from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.music import hz_to_volts

from ._dsp import FloatBlock, empty_outputs, port


VOICES = 4
CHORD_OUTPUTS = ("root", *(f"voice_{index}" for index in range(1, VOICES + 1)))


def voice_chord(name: str, octave: int) -> tuple[str, tuple[tuple[str, float], ...]]:
    """PyTheory's reading of a chord name, as up to four sounding tones.

    Returns the name PyTheory settled on, and ``(spelling, hertz)`` pairs.
    An unknown name comes back as an empty voicing rather than an exception:
    a rack should show that it did not understand, and keep running.
    """
    try:
        chord = Chord.from_name(name, octave=octave)
    except (TypeError, ValueError, KeyError):
        return name, ()
    tones = []
    for tone in chord.tones:
        frequency = getattr(tone, "frequency", None)
        if not frequency:
            continue
        tones.append((str(getattr(tone, "full_name", tone)), float(frequency)))
    return str(getattr(chord, "name", name) or name), tuple(tones)


class ChordParameters(BaseModel):
    """The chord, and the octave its root sits in."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str = "C"
    octave: int = Field(default=3, ge=0, le=8)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)


CHORD_MANIFEST = ModuleManifest(
    id="chord",
    name="Chord",
    category="Musical Brains",
    description=(
        "A chord by name — C, Am7, Dmaj9 — voiced as four one-volt-per-octave "
        "pitches. Patch them into the arpeggiator, or straight into voices."
    ),
    ports=(
        port("root", "Root", PortDirection.OUTPUT, SignalType.CV, "The root, one volt per octave."),
        *(
            port(
                f"voice_{index}",
                f"Voice {index}",
                PortDirection.OUTPUT,
                SignalType.CV,
                f"Chord tone {index}, one volt per octave.",
            )
            for index in range(1, VOICES + 1)
        ),
    ),
)


class ChordModule:
    """Hold one named chord and publish its voices."""

    manifest = CHORD_MANIFEST
    readout = True

    def __init__(self, parameters: ChordParameters | None = None) -> None:
        self.parameters = parameters or ChordParameters()
        self._key: tuple[object, ...] | None = None
        self._title = ""
        self._tones: tuple[tuple[str, float], ...] = ()

    def _resolve(self) -> None:
        parameters = self.parameters
        key = (parameters.name.strip(), parameters.octave)
        if key == self._key:
            return
        self._key = key
        self._title, self._tones = voice_chord(*key)

    @property
    def label(self) -> str:
        self._resolve()
        if not self._tones:
            return f"{self.parameters.name.strip() or '—'} · unrecognised"
        names = " ".join(name for name, _hertz in self._tones)
        return f"{self._title} · {names}"

    def _volts(self) -> list[float]:
        self._resolve()
        reference = self.parameters.reference_frequency_hz
        base = [hz_to_volts(hertz, reference) for _name, hertz in self._tones]
        if not base:
            return [0.0] * VOICES
        # Fewer than four tones still fills a four-voice arpeggio: the chord
        # again, an octave higher.
        voices: list[float] = []
        octave = 0
        while len(voices) < VOICES:
            for pitch in base:
                voices.append(pitch + octave)
                if len(voices) == VOICES:
                    break
            octave += 1
        return voices

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        del inputs
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if frame_count == 0:
            return empty_outputs(CHORD_OUTPUTS)
        pitches = self._volts()
        outputs = {
            "root": np.full(frame_count, pitches[0], dtype=np.float32),
        }
        for index, pitch in enumerate(pitches, start=1):
            outputs[f"voice_{index}"] = np.full(frame_count, pitch, dtype=np.float32)
        return outputs


__all__ = [
    "CHORD_MANIFEST",
    "ChordModule",
    "ChordParameters",
    "voice_chord",
]
