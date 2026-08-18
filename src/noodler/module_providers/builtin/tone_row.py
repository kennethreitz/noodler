"""A twelve-tone row, stepped through in any of its forms.

Serialism's one rule: all twelve pitch classes, in an order, before any comes
round again. PyTheory keeps the row and knows its forms -- prime, inversion,
retrograde, retrograde inversion, at any transposition -- and this module
steps through whichever is chosen on the clock, one pitch a step, round and
round. The row is written as note names or pitch-class numbers; the octave of
each note is placed by a small span, so a row is a line rather than a leap.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import ToneRow

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


DEFAULT_ROW = "0 11 7 8 3 1 2 10 6 5 4 9"
"""Webern's Op. 27 row, near enough: all twelve, none twice."""
FORMS = ("P", "I", "R", "RI")
TRIGGER_SAMPLES = 240
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


class RowError(ValueError):
    """A row that is not a row."""


def parse_row(text: str) -> ToneRow:
    """Twelve pitch classes -- numbers 0-11 or note names -- each exactly once."""
    tokens = [t for t in text.replace(",", " ").split() if t]
    if len(tokens) != 12:
        raise RowError(f"a row has twelve pitch classes, not {len(tokens)}")
    classes: list[int] = []
    for token in tokens:
        try:
            classes.append(int(token) % 12)
            continue
        except ValueError:
            pass
        name = FLATS.get(token, token)
        if name not in NOTE_NAMES:
            raise RowError(f"{token!r} is not a pitch class or a note name")
        classes.append(NOTE_NAMES.index(name))
    if len(set(classes)) != 12:
        raise RowError("every pitch class must appear exactly once")
    return ToneRow(classes)


class ToneRowParameters(BaseModel):
    """The row, the form to play, and how it steps."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    row: str = DEFAULT_ROW
    form: str = "P"
    transposition: int = Field(default=0, ge=0, le=11)
    span_octaves: int = Field(default=1, ge=1, le=3)
    """Notes are placed within this many octaves above the reference, each as
    near the last as it can be, so the line stays a line."""
    gate_length: float = Field(default=0.5, ge=0.05, le=1.0)
    rate_hz: float = Field(default=2.0, gt=0.0, le=40.0)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def known(self) -> "ToneRowParameters":
        if self.form not in FORMS:
            object.__setattr__(self, "form", "P")
        return self


ROW_OUTPUTS = ("pitch", "gate", "trigger", "row_start", "position")

TONE_ROW_MANIFEST = ModuleManifest(
    id="tone_row",
    name="Tone Row",
    category="Musical Brains",
    description=(
        "A twelve-tone row, stepped through on the clock in any of its forms -- "
        "prime, inversion, retrograde, retrograde inversion, at any transposition."
    ),
    ports=(
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "Each rising edge is a step."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Back to the row's first note."),
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The note, one volt per octave."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High for the gate length of each step."),
        port("trigger", "Trig", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger at every note."),
        port("row_start", "Row", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger when the row starts over."),
        port("position", "Pos", PortDirection.OUTPUT, SignalType.CV, "How far through the row, zero to one."),
    ),
)


class ToneRowVoice:
    """Step through a twelve-tone row."""

    manifest = TONE_ROW_MANIFEST

    def __init__(self, parameters: ToneRowParameters | None = None) -> None:
        self.parameters = parameters or ToneRowParameters()
        self._read_for: tuple[str, str, int] | None = None
        self._classes: list[int] = list(range(12))
        self.fault: str | None = None
        self._step = -1
        self._last_midi: float | None = None
        self._pitch = 0.0
        self._phase = 0.0
        self._clock_high = False
        self._reset_high = False
        self._gate_until = -1.0
        self._elapsed = 0.0
        self._pending_trigger = 0
        self._pending_start = 0

    @property
    def label(self) -> str:
        if self.fault:
            return f"ROW FAULT  ·  {self.fault}"[:90]
        return f"{self.parameters.form}{self.parameters.transposition}  ·  " + " ".join(str(c) for c in self._classes)

    def choices_for(self, field: str) -> tuple[str, ...]:
        return FORMS if field == "form" else ()

    def _read(self) -> None:
        key = (self.parameters.row, self.parameters.form, self.parameters.transposition)
        if key == self._read_for:
            return
        self._read_for = key
        try:
            row = parse_row(self.parameters.row)
        except RowError as error:
            self.fault = str(error)
            return
        self.fault = None
        self._classes = list(row.form(f"{self.parameters.form}{self.parameters.transposition}"))
        self._step = -1
        self._last_midi = None

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._read()

    def _place(self, pitch_class: int) -> float:
        """The MIDI note for a class: within the span, nearest the last note."""
        base = 57  # A3, the reference at 220 Hz
        candidates = [base + octave * 12 + pitch_class for octave in range(self.parameters.span_octaves)]
        if self._last_midi is None:
            return float(candidates[0])
        return float(min(candidates, key=lambda m: abs(m - self._last_midi)))

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
            return empty_outputs(ROW_OUTPUTS)
        self._read()
        inputs = inputs or {}
        external = "clock" in inputs
        clock = np.asarray(block("clock", inputs, frame_count), dtype=np.float64)
        reset = np.asarray(block("reset", inputs, frame_count), dtype=np.float64)
        outputs = {name: np.zeros(frame_count, dtype=np.float32) for name in ROW_OUTPUTS}
        if self._pending_trigger:
            outputs["trigger"][: min(self._pending_trigger, frame_count)] = 1.0
            self._pending_trigger = max(0, self._pending_trigger - frame_count)
        if self._pending_start:
            outputs["row_start"][: min(self._pending_start, frame_count)] = 1.0
            self._pending_start = max(0, self._pending_start - frame_count)

        period = 1.0 / self.parameters.rate_hz
        for index in range(frame_count):
            clock_event, self._clock_high = rising_edge(clock[index], self._clock_high)
            reset_event, self._reset_high = rising_edge(reset[index], self._reset_high)
            if reset_event:
                self._step = -1
                self._last_midi = None
                clock_event = True
            if not external:
                self._phase += 1.0 / sample_rate
                if self._phase >= period:
                    self._phase -= period
                    clock_event = True
            if clock_event and self._classes:
                self._step = (self._step + 1) % len(self._classes)
                midi = self._place(self._classes[self._step])
                self._last_midi = midi
                hertz = 440.0 * 2.0 ** ((midi - 69.0) / 12.0)
                self._pitch = float(np.log2(hertz / self.parameters.reference_frequency_hz))
                self._gate_until = self._elapsed + index / sample_rate + period * self.parameters.gate_length
                end = index + TRIGGER_SAMPLES
                outputs["trigger"][index:end] = 1.0
                if end > frame_count:
                    self._pending_trigger = end - frame_count
                if self._step == 0:
                    outputs["row_start"][index:end] = 1.0
                    if end > frame_count:
                        self._pending_start = end - frame_count
            outputs["pitch"][index] = self._pitch
            outputs["gate"][index] = 1.0 if (self._elapsed + index / sample_rate) < self._gate_until else 0.0
            outputs["position"][index] = (self._step / 11.0) if self._step >= 0 else 0.0
        self._elapsed += frame_count / sample_rate
        return outputs


__all__ = ["FORMS", "TONE_ROW_MANIFEST", "ToneRowParameters", "ToneRowVoice", "parse_row"]
