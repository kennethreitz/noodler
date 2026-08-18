"""Keys: play the rack from the keyboard in front of you.

Arm it and the letter keys are a piano the way every DAW's are -- A is C, W
is C sharp, S is D, and so on up to the semicolon; Z and X take the octave
down and up -- and the panel's drawn keybed lights the notes held and can be
clicked as well. The module puts out pitch and gate for whatever voice is
patched to it, with a little glide if asked. Last note wins; letting every
key go closes the gate; the trigger fires on every press so a plucked voice
plucks again on a repeated note.

The DSP here is a gate and a pitch that the interface changes: which keys
are down is state, written from the UI thread and read by the audio thread,
which is why it is a small locked set and not a queue of events.
"""

from collections.abc import Mapping
import math
import threading

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, empty_outputs, port


KEY_ROW = "AWSEDFTGYHUJKOLP;'"
"""The letters, low to high: white keys on the home row, black on the row
above, as on every DAW's typing keyboard. Eighteen keys: an octave and a
half from C."""
KEY_SEMITONES: dict[str, int] = {letter: index for index, letter in enumerate(KEY_ROW)}
"""Each letter's semitone above the octave's C."""
BLACK_SEMITONES = {1, 3, 6, 8, 10, 13, 15}
"""Which of the eighteen are black keys: sharps in an octave and a half."""
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
TRIGGER_SAMPLES = 240


class KeysParameters(BaseModel):
    """Where the keyboard sits and how it plays."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    octave: int = Field(default=3, ge=0, le=7)
    """The octave of the A key's C: 3 puts A on C3, 130.8 Hz."""
    glide_ms: float = Field(default=0.0, ge=0.0, le=1000.0)
    """Portamento between notes; zero steps."""
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)


KEYS_OUTPUTS = ("pitch", "gate", "trigger", "velocity")

KEYS_MANIFEST = ModuleManifest(
    id="keys",
    name="QWERTY Keys",
    category="Musical Brains",
    description=(
        "Play the rack from the keyboard in front of you: arm it and the "
        "letter keys are a piano -- A is C, W is C sharp -- with Z and X for "
        "the octave. Pitch and gate out, last note wins, glide if asked."
    ),
    ports=(
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The held note, one volt per octave."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High while any key is down."),
        port("trigger", "Trig", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger at every key press."),
        port("velocity", "Vel", PortDirection.OUTPUT, SignalType.CV, "How many keys are down, over four: a chord presses harder."),
    ),
)


def semitone_for_letter(letter: str) -> int | None:
    """The semitone a typed character plays, or None if it is not a key."""
    return KEY_SEMITONES.get(letter.upper())


class Keys:
    """A keyboard played from the interface."""

    manifest = KEYS_MANIFEST
    display = "keys"
    """The panel builder looks for this and adds the keybed and the arm button."""

    def __init__(self, parameters: KeysParameters | None = None) -> None:
        self.parameters = parameters or KeysParameters()
        self._held: list[int] = []
        """Semitones down, in the order they went down: the last is the note."""
        self._lock = threading.Lock()
        self._presses = 0
        self._played = 0
        self._pitch = 0.0
        self._target = 0.0
        self._pending_trigger = 0
        self.armed = False
        """Whether typing plays it: the interface sets this."""

    # ---- what the interface does to it ----------------------------------

    def press(self, semitone: int) -> None:
        with self._lock:
            if semitone in self._held:
                self._held.remove(semitone)
            self._held.append(semitone)
            self._presses += 1

    def release(self, semitone: int) -> None:
        with self._lock:
            if semitone in self._held:
                self._held.remove(semitone)

    def release_all(self) -> None:
        with self._lock:
            self._held.clear()

    def held(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(self._held)

    def octave_up(self) -> None:
        self.parameters.octave = min(7, self.parameters.octave + 1)

    def octave_down(self) -> None:
        self.parameters.octave = max(0, self.parameters.octave - 1)

    def midi_of(self, semitone: int) -> int:
        return 12 * (self.parameters.octave + 1) + semitone

    def note_name(self, semitone: int) -> str:
        midi = self.midi_of(semitone)
        return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"

    @property
    def label(self) -> str:
        held = self.held()
        state = "ARMED  ·  " if self.armed else ""
        if held:
            names = " ".join(self.note_name(s) for s in held[-4:])
            return f"{state}{names}"
        return f"{state}OCTAVE {self.parameters.octave}  ·  A–;  ·  Z/X"

    # ---- the block --------------------------------------------------------

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

    def _volts(self, semitone: int) -> float:
        hertz = 440.0 * 2.0 ** ((self.midi_of(semitone) - 69) / 12.0)
        return math.log2(hertz / self.parameters.reference_frequency_hz)

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
            return empty_outputs(KEYS_OUTPUTS)
        with self._lock:
            held = tuple(self._held)
            presses = self._presses
        outputs = {name: np.zeros(frame_count, dtype=np.float32) for name in KEYS_OUTPUTS}
        if self._pending_trigger:
            outputs["trigger"][: min(self._pending_trigger, frame_count)] = 1.0
            self._pending_trigger = max(0, self._pending_trigger - frame_count)
        if presses != self._played:
            # Presses since the last block: one trigger, at the top of it.
            self._played = presses
            end = min(TRIGGER_SAMPLES, frame_count)
            outputs["trigger"][:end] = 1.0
            if TRIGGER_SAMPLES > frame_count:
                self._pending_trigger = TRIGGER_SAMPLES - frame_count
        if held:
            self._target = self._volts(held[-1])
        glide = self.parameters.glide_ms * 0.001
        if glide <= 0.0 or not held:
            self._pitch = self._target
            outputs["pitch"][:] = self._pitch
        else:
            # An exponential slide toward the target, most of the way in the glide time.
            step = 1.0 - math.exp(-1.0 / max(1.0, glide * sample_rate) * 4.0)
            pitch = np.empty(frame_count, dtype=np.float64)
            value = self._pitch
            for index in range(frame_count):
                value += (self._target - value) * step
                pitch[index] = value
            self._pitch = float(value)
            outputs["pitch"][:] = pitch
        outputs["gate"][:] = 1.0 if held else 0.0
        outputs["velocity"][:] = min(1.0, len(held) / 4.0)
        return outputs


__all__ = ["BLACK_SEMITONES", "KEYS_MANIFEST", "KEY_ROW", "Keys", "KeysParameters", "semitone_for_letter"]
