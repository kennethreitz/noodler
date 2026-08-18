"""A written phrase, played on the clock.

The brains improvise. This module reads: a phrase written down in a small
notation -- ``E5:q D5:e C5:e r:q [A3,C4,E4]:h`` -- and plays it round and
round, locked to the transport, so what a bar contains is decided rather than
drawn. Notes are named as PyTheory names them (``F#3``, ``Bb2``, ``C4``) and
resolved by PyTheory into MIDI numbers; durations are letters -- w h q e s for
whole through sixteenth, a dot after for dotted, a t for triplet -- or a bare
number of beats. ``r`` is a rest, and square brackets hold up to four notes at
once, which come out on four pitch outputs.

The phrase is re-read the moment it changes, and a phrase that will not parse
plays the last one that did, with the fault in the status line rather than
silence in the rack.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field
from pytheory import Tone

from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.transport import TransportFrame

from ._dsp import FloatBlock, block, empty_outputs, port
from .clocked import _steps_in_block


DURATION_LETTERS = {"w": 4.0, "h": 2.0, "q": 1.0, "e": 0.5, "s": 0.25}
DEFAULT_PHRASE = "E5:e D5:e C5:q r:e G4:e A4:e B4:e"
MAX_VOICES = 4
TRIGGER_SAMPLES = 240


class PhraseError(ValueError):
    """A phrase that could not be read, and where."""


class Step:
    """One event of a phrase: some notes, or none, for a length in beats."""

    __slots__ = ("midis", "beats", "velocity")

    def __init__(self, midis: tuple[int, ...], beats: float, velocity: float = 1.0) -> None:
        self.midis = midis
        self.beats = beats
        self.velocity = velocity


def parse_duration(text: str) -> float:
    """Beats for a duration token: a letter, dotted or triplet, or a number."""
    token = text.strip().lower()
    if not token:
        raise PhraseError("a note needs a duration after the colon")
    try:
        beats = float(token)
        if beats <= 0.0:
            raise PhraseError(f"a duration must be positive, not {token}")
        return beats
    except ValueError:
        pass
    dotted = token.endswith(".")
    triplet = token.endswith("t")
    core = token.rstrip(".t")
    if core not in DURATION_LETTERS:
        raise PhraseError(f"unknown duration {text!r}: use w h q e s, dotted with . or triplet with t, or beats")
    beats = DURATION_LETTERS[core]
    if dotted:
        beats *= 1.5
    if triplet:
        beats *= 2.0 / 3.0
    return beats


def parse_note(text: str) -> int:
    """MIDI number for a note name, as PyTheory reads it."""
    name = text.strip()
    if not name:
        raise PhraseError("an empty note name")
    try:
        midi = Tone.from_string(name).midi
    except Exception as error:  # noqa: BLE001 - PyTheory's own message is the useful one
        raise PhraseError(f"unknown note {name!r}") from error
    if midi is None:
        raise PhraseError(f"{name!r} has no pitch")
    return int(midi)


def parse_phrase(text: str) -> list[Step]:
    """Read a whole phrase. Tokens are NAME:DUR, r:DUR, or [N1,N2,...]:DUR;
    a trailing *N (or !) after the duration is an accent level, 1-9."""
    steps: list[Step] = []
    for raw in text.replace("\n", " ").split():
        token = raw.strip()
        if ":" not in token:
            raise PhraseError(f"{token!r} needs a colon and a duration, like E5:q")
        head, _, tail = token.partition(":")
        velocity = 1.0
        if "*" in tail:
            tail, _, accent = tail.partition("*")
            try:
                velocity = min(1.0, max(0.1, int(accent) / 9.0))
            except ValueError as error:
                raise PhraseError(f"an accent is a digit 1-9, not {accent!r}") from error
        beats = parse_duration(tail)
        if head.lower() == "r":
            steps.append(Step((), beats, velocity))
            continue
        if head.startswith("[") and head.endswith("]"):
            names = [n for n in head[1:-1].split(",") if n.strip()]
            if not names:
                raise PhraseError("empty brackets: a chord needs notes")
            if len(names) > MAX_VOICES:
                raise PhraseError(f"a chord holds at most {MAX_VOICES} notes")
            steps.append(Step(tuple(parse_note(n) for n in names), beats, velocity))
            continue
        steps.append(Step((parse_note(head),), beats, velocity))
    if not steps:
        raise PhraseError("the phrase is empty")
    return steps


class PyTheoryScoreParameters(BaseModel):
    """The phrase, and how it is played."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    phrase: str = DEFAULT_PHRASE
    gate_length: float = Field(default=0.7, ge=0.05, le=1.0)
    """How much of each note the gate stays high for."""
    octave_shift: int = Field(default=0, ge=-4, le=4)
    follow_clock: bool = True
    rate_hz: float = Field(default=2.0, gt=0.0, le=50.0)
    """Beats per second when running free."""
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    """The pitch that reads as zero volts: A3 by default, one volt per octave."""


SCORE_OUTPUTS = ("pitch", "voice_2", "voice_3", "voice_4", "gate", "trigger", "accent", "phrase")

PYTHEORY_SCORE_MANIFEST = ModuleManifest(
    id="pytheory_score",
    name="PyTheory Score",
    category="Musical Brains",
    description=(
        "A written phrase, played round and round on the clock. E5:q D5:e "
        "[A3,C4,E4]:h r:q -- PyTheory reads the notes; the rack plays them."
    ),
    ports=(
        port("reset", "Reset", PortDirection.INPUT, SignalType.GATE, "Back to the top of the phrase (when running free)."),
        port("transpose", "Transpose", PortDirection.INPUT, SignalType.CV, "Added to every pitch, in octaves."),
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The first (or only) note, one volt per octave."),
        port("voice_2", "Voice 2", PortDirection.OUTPUT, SignalType.CV, "The second note of a chord."),
        port("voice_3", "Voice 3", PortDirection.OUTPUT, SignalType.CV, "The third note of a chord."),
        port("voice_4", "Voice 4", PortDirection.OUTPUT, SignalType.CV, "The fourth note of a chord."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High while a note sounds."),
        port("trigger", "Trig", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger at the start of every note."),
        port("accent", "Accent", PortDirection.OUTPUT, SignalType.CV, "The note's accent, held."),
        port("phrase", "Phrase", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger when the phrase starts over."),
    ),
)


class PyTheoryScore:
    """Play a written phrase in time with the rack."""

    manifest = PYTHEORY_SCORE_MANIFEST
    uses_transport = True

    def __init__(self, parameters: PyTheoryScoreParameters | None = None) -> None:
        self.parameters = parameters or PyTheoryScoreParameters()
        self._read_phrase: str | None = None
        self._steps: list[Step] = []
        self._onsets: list[float] = []
        self._length = 0.0
        self.fault: str | None = None
        self._free_quarters = 0.0
        self._reset_high = False
        self._pitches = [0.0] * MAX_VOICES
        self._gate_until = -1.0
        self._accent = 0.0
        self._pending_trigger = 0
        self._pending_phrase = 0

    @property
    def label(self) -> str:
        if self.fault:
            return f"PHRASE FAULT  ·  {self.fault}"[:90]
        return f"{len(self._steps)} STEPS  ·  {self._length:g} BEATS"

    def _read(self) -> None:
        text = self.parameters.phrase
        if text == self._read_phrase:
            return
        self._read_phrase = text
        try:
            steps = parse_phrase(text)
        except PhraseError as error:
            self.fault = str(error)
            return
        self.fault = None
        self._steps = steps
        onsets: list[float] = []
        at = 0.0
        for step in steps:
            onsets.append(at)
            at += step.beats
        self._onsets = onsets
        self._length = at

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._read()

    def _volts(self, midi: int) -> float:
        hertz = 440.0 * 2.0 ** ((midi + 12 * self.parameters.octave_shift - 69) / 12.0)
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
            return empty_outputs(SCORE_OUTPUTS)
        self._read()
        inputs = inputs or {}
        transport = inputs.get("transport")
        if not isinstance(transport, TransportFrame):
            transport = None
        transpose = np.asarray(block("transpose", inputs, frame_count), dtype=np.float64)

        follow = self.parameters.follow_clock and transport is not None
        if follow:
            start = transport.quarters
            per_sample = transport.quarters_per_second / sample_rate if transport.running else 0.0
        else:
            reset = np.asarray(block("reset", inputs, frame_count), dtype=np.float64) > 0.0
            if bool(reset.any()) and not self._reset_high:
                self._free_quarters = 0.0
            self._reset_high = bool(reset[-1])
            start = self._free_quarters
            per_sample = self.parameters.rate_hz / sample_rate
            self._free_quarters += frame_count * per_sample

        outputs = {name: np.zeros(frame_count, dtype=np.float32) for name in SCORE_OUTPUTS}
        gate = outputs["gate"]
        trigger = outputs["trigger"]
        phrase = outputs["phrase"]
        if self._pending_trigger:
            trigger[: min(self._pending_trigger, frame_count)] = 1.0
            self._pending_trigger = max(0, self._pending_trigger - frame_count)
        if self._pending_phrase:
            phrase[: min(self._pending_phrase, frame_count)] = 1.0
            self._pending_phrase = max(0, self._pending_phrase - frame_count)

        pitch_lanes = [outputs["pitch"], outputs["voice_2"], outputs["voice_3"], outputs["voice_4"]]
        events: list[tuple[int, Step]] = []
        if per_sample > 0.0 and self._steps and self._length > 0.0:
            for onset, step in zip(self._onsets, self._steps):
                for index in _steps_in_block(start, per_sample, frame_count, self._length, onset):
                    events.append((index, step))
            for index in _steps_in_block(start, per_sample, frame_count, self._length):
                phrase[index : index + TRIGGER_SAMPLES] = 1.0
                if index + TRIGGER_SAMPLES > frame_count:
                    self._pending_phrase = index + TRIGGER_SAMPLES - frame_count
        events.sort(key=lambda pair: pair[0])

        # Walk the block: pitches hold from each note on, the gate is high for
        # gate_length of the note, and everything before the first event keeps
        # what was already sounding.
        cursor = 0
        positions = start + np.arange(frame_count) * per_sample
        for index, step in events:
            self._fill(pitch_lanes, gate, positions, cursor, index)
            cursor = index
            if step.midis:
                for voice, midi in enumerate(step.midis[:MAX_VOICES]):
                    self._pitches[voice] = self._volts(midi)
                self._gate_until = positions[index] + step.beats * self.parameters.gate_length
                self._accent = step.velocity
                trigger[index : index + TRIGGER_SAMPLES] = 1.0
                if index + TRIGGER_SAMPLES > frame_count:
                    self._pending_trigger = index + TRIGGER_SAMPLES - frame_count
            else:
                self._gate_until = -1.0
        self._fill(pitch_lanes, gate, positions, cursor, frame_count)
        outputs["accent"].fill(self._accent)
        for lane in pitch_lanes:
            lane += transpose.astype(np.float32)
        return outputs

    def _fill(self, pitch_lanes, gate, positions, begin: int, end: int) -> None:
        if end <= begin:
            return
        for voice, lane in enumerate(pitch_lanes):
            lane[begin:end] = self._pitches[voice]
        if self._gate_until >= 0.0:
            # The gate is high while the pattern position is before the note's
            # release, allowing for the position wrapping round the phrase.
            span = positions[begin:end]
            gate[begin:end] = np.where(
                (span <= self._gate_until) | (span - self._length <= self._gate_until - self._length) & (span < self._gate_until),
                1.0,
                0.0,
            ).astype(np.float32)


__all__ = [
    "DEFAULT_PHRASE",
    "PYTHEORY_SCORE_MANIFEST",
    "PhraseError",
    "PyTheoryScore",
    "PyTheoryScoreParameters",
    "parse_phrase",
]
