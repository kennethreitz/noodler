"""An ear for chords: name what is sounding, from the pitches patched in.

PyTheory can look at a handful of tones and say what chord they make -- a
dominant seventh, a diminished triad, a power chord -- and how dissonant the
set is. Patch a brain's voices into this and it names the chord live, in its
label, and puts out the root and the dissonance as voltages, and a trigger
when the name changes, so something in the rack can answer a harmony rather
than only play one.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field
from pytheory import Chord, Tone

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


EAR_INPUTS = ("pitch_1", "pitch_2", "pitch_3", "pitch_4")
EAR_OUTPUTS = ("root", "dissonance", "changed", "known")
TRIGGER_SAMPLES = 240
DISSONANCE_CEILING = 8.0
"""PyTheory's dissonance for a fistful of semitones is around here; the
voltage is that, over this, clipped to one."""


class ChordEarParameters(BaseModel):
    """How the ear listens."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    hold: bool = True
    """Keep the last chord's name and root while the pitches are unreadable."""


CHORD_EAR_MANIFEST = ModuleManifest(
    id="pytheory_chord_ear",
    name="PyTheory Chord Ear",
    category="Musical Brains",
    description=(
        "Names the chord the pitches patched into it make -- PyTheory's ear -- "
        "and puts out its root, its dissonance, and a trigger when the name "
        "changes."
    ),
    ports=(
        port("pitch_1", "P1", PortDirection.INPUT, SignalType.CV, "A voice, one volt per octave."),
        port("pitch_2", "P2", PortDirection.INPUT, SignalType.CV, "Another voice."),
        port("pitch_3", "P3", PortDirection.INPUT, SignalType.CV, "Another."),
        port("pitch_4", "P4", PortDirection.INPUT, SignalType.CV, "And another."),
        port("listen", "Listen", PortDirection.INPUT, SignalType.TRIGGER, "Listen only at each rising edge; unpatched, always."),
        port("root", "Root", PortDirection.OUTPUT, SignalType.CV, "The chord's root, one volt per octave, in the lowest voice's octave."),
        port("dissonance", "Diss", PortDirection.OUTPUT, SignalType.CV, "How dissonant the set is, zero to one."),
        port("changed", "Chg", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger when the chord's name changes."),
        port("known", "Known", PortDirection.OUTPUT, SignalType.GATE, "High while the pitches make a chord PyTheory can name."),
    ),
)


def _volts_to_midi(volts: float, reference_hz: float) -> int:
    hertz = reference_hz * 2.0 ** volts
    return int(round(69.0 + 12.0 * math.log2(max(hertz, 1e-6) / 440.0)))


def name_chord(midis: list[int]) -> tuple[str | None, int | None, float]:
    """PyTheory's name for a set of MIDI notes, its root's MIDI, and its dissonance."""
    notes = sorted(set(midis))
    if len(notes) < 2:
        return None, None, 0.0
    try:
        chord = Chord([Tone.from_midi(int(m)) for m in notes])
        name = chord.identify()
        root = chord.root
        dissonance = float(chord.dissonance)
    except Exception:
        return None, None, 0.0
    root_midi = None
    if root is not None and getattr(root, "midi", None) is not None:
        root_midi = int(root.midi)
        # In the lowest voice's octave.
        while root_midi > notes[0]:
            root_midi -= 12
        while root_midi + 12 <= notes[0]:
            root_midi += 12
    return name, root_midi, dissonance


class ChordEar:
    """Name the chord on the inputs."""

    manifest = CHORD_EAR_MANIFEST

    def __init__(self, parameters: ChordEarParameters | None = None) -> None:
        self.parameters = parameters or ChordEarParameters()
        self._heard: tuple[int, ...] = ()
        self._name: str | None = None
        self._root_volts = 0.0
        self._dissonance = 0.0
        self._listen_high = False
        self._pending_change = 0

    @property
    def label(self) -> str:
        return (self._name or "LISTENING…").upper()

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

    def _hear(self, midis: list[int]) -> bool:
        """Take in a set of notes; return whether the chord's name changed."""
        heard = tuple(sorted(set(midis)))
        if heard == self._heard:
            return False
        self._heard = heard
        name, root_midi, dissonance = name_chord(list(heard))
        changed = name != self._name
        if name is None and self.parameters.hold and self._name is not None:
            # Unreadable for the moment: keep saying what it was.
            return False
        self._name = name
        if root_midi is not None:
            hertz = 440.0 * 2.0 ** ((root_midi - 69) / 12.0)
            self._root_volts = math.log2(hertz / self.parameters.reference_frequency_hz)
        self._dissonance = min(1.0, dissonance / DISSONANCE_CEILING)
        return changed

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
            return empty_outputs(EAR_OUTPUTS)
        inputs = inputs or {}
        outputs = {name: np.zeros(frame_count, dtype=np.float32) for name in EAR_OUTPUTS}
        if self._pending_change:
            outputs["changed"][: min(self._pending_change, frame_count)] = 1.0
            self._pending_change = max(0, self._pending_change - frame_count)
        patched = [name for name in EAR_INPUTS if name in inputs]
        pitches = {name: np.asarray(block(name, inputs, frame_count), dtype=np.float64) for name in patched}
        reference = self.parameters.reference_frequency_hz

        def notes_at(index: int) -> list[int]:
            return [_volts_to_midi(float(pitches[name][index]), reference) for name in patched]

        moments: list[int]
        if "listen" in inputs:
            listen = np.asarray(block("listen", inputs, frame_count), dtype=np.float64)
            moments = []
            for index in range(frame_count):
                event, self._listen_high = rising_edge(listen[index], self._listen_high)
                if event:
                    moments.append(index)
        else:
            # Always listening: the block's last sample says what is sounding.
            moments = [frame_count - 1] if patched else []
        for index in moments:
            if self._hear(notes_at(index)):
                end = index + TRIGGER_SAMPLES
                outputs["changed"][index:end] = 1.0
                if end > frame_count:
                    self._pending_change = end - frame_count
        outputs["root"][:] = self._root_volts
        outputs["dissonance"][:] = self._dissonance
        outputs["known"][:] = 1.0 if self._name else 0.0
        return outputs


__all__ = ["CHORD_EAR_MANIFEST", "ChordEar", "ChordEarParameters", "name_chord"]
