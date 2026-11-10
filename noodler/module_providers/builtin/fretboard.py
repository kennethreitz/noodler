"""A guitar, as a module: tuning, capo, and the chord in your hand.

PyTheory's fretboard knows the open strings of a guitar, including the
alternate tunings — drop D, DADGAD, open G — and a capo that raises all of
them. This module publishes those strings as pitch, and strums them, so a
voice downstream plays the guitar you described rather than a scale someone
typed in semitones.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import Fretboard
from pytheory.charts import Fingering

from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.music import hz_to_volts
from noodler.transport import (
    CHOICES,
    FREE,
    TransportFrame,
    block_clock,
    division_quarters,
    sample_crossings,
)

from ._dsp import FloatBlock, block, empty_outputs, port


STRINGS = 6
TUNINGS: tuple[str, ...] = tuple(Fretboard.TUNINGS)
STRUMS = ("down", "up", "together")
DEFAULT_TUNING = "standard"
VOICING_LIMIT = 8
"""How many ranked grips a chord offers. The first is the one PyTheory likes best."""


def _board(tuning: str, capo: int, barre: int) -> Fretboard:
    board = Fretboard.guitar(tuning, capo=capo)
    if barre:
        return board.capo(barre)
    return board


def _open_strings(board: Fretboard) -> tuple[tuple[str, float] | None, ...]:
    return tuple((tone.full_name, float(tone.frequency)) for tone in board.tones)


def _grip(board: Fretboard, shape: Fingering) -> tuple[tuple[str, float] | None, ...]:
    """Six strings, low to high. A muted string is None."""
    sounded: list[tuple[str, float] | None] = []
    for position, tone in zip(shape.positions, board.tones, strict=False):
        if position is None:
            sounded.append(None)
        else:
            fretted = tone.add(int(position))
            sounded.append((fretted.full_name, float(fretted.frequency)))
    while len(sounded) < STRINGS:
        sounded.append(None)
    return tuple(sounded[:STRINGS])


def _voicings(
    tuning: str,
    capo: int,
    barre: int,
    chord: str,
) -> tuple[tuple[tuple[str, float] | None, ...], ...]:
    """The grips PyTheory will actually play, best first.

    An empty chord name is the open strings. ``Fretboard.chord(..., multiple=True)``
    is the ranked list for a name, in this tuning and under this capo.
    """
    board = _board(tuning, capo, barre)
    if not chord:
        return (_open_strings(board),)
    shapes = board.chord(chord, multiple=True, limit=VOICING_LIMIT)
    if isinstance(shapes, Fingering):
        shapes = (shapes,)
    grips = tuple(_grip(board, shape) for shape in shapes)
    if not grips:
        raise ValueError(chord)
    return grips


class FretboardParameters(BaseModel):
    """Which guitar this is, and how it is strummed when nothing else clocks it."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tuning: str = DEFAULT_TUNING
    capo: int = Field(default=0, ge=0, le=12)
    chord: str = ""
    """A chord to fret, such as G or Am7. Empty means the open strings."""
    voicing: int = Field(default=0, ge=0, le=VOICING_LIMIT - 1)
    """Which ranked grip to hold. Zero is the one PyTheory puts first."""
    strum: str = "down"
    division: str = "1/4"
    rate_hz: float = Field(default=2.0, gt=0.0, le=20.0)
    """Quarters per second when the clock is not running. Two is 120 BPM."""
    strum_ms: float = Field(default=18.0, ge=0.0, le=80.0)
    """How far apart the strings of one strum are."""
    gate_ms: float = Field(default=140.0, ge=5.0, le=2_000.0)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def known(self) -> "FretboardParameters":
        if self.tuning not in Fretboard.TUNINGS:
            object.__setattr__(self, "tuning", DEFAULT_TUNING)
        if self.strum not in STRUMS:
            object.__setattr__(self, "strum", "down")
        if self.division not in CHOICES:
            object.__setattr__(self, "division", "1/4")
        object.__setattr__(self, "chord", self.chord.strip())
        return self


_STRING_PORTS = tuple(
    port(
        f"string_{index}",
        f"String {index}",
        PortDirection.OUTPUT,
        SignalType.CV,
        f"String {index}, low to high, one volt per octave. Zero when muted.",
    )
    for index in range(1, STRINGS + 1)
)

FRETBOARD_OUTPUTS = ("pitch", "gate", "low", "high", *(f"string_{index}" for index in range(1, STRINGS + 1)))

FRETBOARD_MANIFEST = ModuleManifest(
    id="fretboard",
    name="Fretboard",
    category="Musical Brains",
    description=(
        "A guitar's tuning, capo and chord, from PyTheory. A chord name offers "
        "its ranked voicings — the first is the one that plays unless you pick "
        "another — and a strum walks the strings into one voice."
    ),
    ports=(
        port("strum", "Strum", PortDirection.INPUT, SignalType.GATE, "A rising edge plays the strings. Unpatched, the module strums on its own."),
        port("barre", "Barre", PortDirection.INPUT, SignalType.CV, "Extra capo, in octaves: one volt is twelve frets."),
        port("pitch", "Pitch", PortDirection.OUTPUT, SignalType.CV, "The string being plucked, one volt per octave."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High for each plucked string."),
        port("low", "Low", PortDirection.OUTPUT, SignalType.CV, "The lowest sounding string."),
        port("high", "High", PortDirection.OUTPUT, SignalType.CV, "The highest sounding string."),
        *_STRING_PORTS,
    ),
)


class FretboardVoice:
    """Hold a tuning, and strum it."""

    manifest = FRETBOARD_MANIFEST
    uses_transport = True
    readout = True

    def __init__(self, parameters: FretboardParameters | None = None) -> None:
        self.parameters = parameters or FretboardParameters()
        self._key: tuple[object, ...] | None = None
        self._barre = 0
        self._voicing: tuple[tuple[str, float] | None, ...] = ()
        self._place = 0
        self._available = 0
        self._failed = ""
        self._pitch = 0.0
        self._gap = 0
        self._gate_left = 0
        self._queued: list[tuple[int, float]] = []
        self._free_quarters = 0.0
        self._strum_high = False

    def choices_for(self, field: str) -> tuple[str, ...]:
        if field == "tuning":
            return TUNINGS
        if field == "strum":
            return STRUMS
        if field == "division":
            return CHOICES
        return ()

    @property
    def label(self) -> str:
        self._tune(self._barre)
        names = " ".join(item[0] for item in self._voicing if item) or "—"
        capo = self.parameters.capo
        chord = f" · {self.parameters.chord}" if self.parameters.chord else ""
        grip = ""
        if self.parameters.chord and self._available > 1:
            grip = f" · {self._place + 1}/{self._available}"
        if self._failed:
            return f"{self.parameters.tuning} · capo {capo}{chord} · {self._failed}"
        return f"{self.parameters.tuning} · capo {capo}{chord}{grip} · {names}"

    def _tune(self, barre: int) -> None:
        parameters = self.parameters
        key = (
            parameters.tuning,
            parameters.capo,
            barre,
            parameters.chord,
            parameters.voicing,
            parameters.reference_frequency_hz,
        )
        if key == self._key:
            return
        self._key = key
        self._barre = barre
        try:
            grips = _voicings(parameters.tuning, parameters.capo, barre, parameters.chord)
            place = min(parameters.voicing, len(grips) - 1)
            self._voicing = grips[place]
            self._place = place
            self._available = len(grips)
            self._failed = ""
        except (KeyError, TypeError, ValueError):
            board = _board(parameters.tuning, parameters.capo, barre)
            self._voicing = _open_strings(board)
            self._place = 0
            self._available = 1
            self._failed = "open strings"
        sounding = [
            hz_to_volts(item[1], parameters.reference_frequency_hz)
            for item in self._voicing
            if item
        ]
        self._pitch = sounding[0] if sounding else 0.0

    def _volts(self) -> list[float]:
        reference = self.parameters.reference_frequency_hz
        return [
            0.0 if item is None else hz_to_volts(item[1], reference)
            for item in self._voicing
        ]

    def _schedule(self, at: int, sample_rate: float) -> None:
        sounding = [
            hz_to_volts(item[1], self.parameters.reference_frequency_hz)
            for item in self._voicing
            if item
        ]
        if not sounding:
            return
        if self.parameters.strum == "up":
            sounding = list(reversed(sounding))
        gap = int(self.parameters.strum_ms * sample_rate / 1_000.0)
        if self.parameters.strum == "together" or gap <= 0 or len(sounding) == 1:
            self._queued.append((at, sounding[0]))
        else:
            self._queued.extend(
                (at + index * gap, pitch) for index, pitch in enumerate(sounding)
            )
        self._queued.sort()

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
            return empty_outputs(FRETBOARD_OUTPUTS)

        inputs = inputs or {}
        barre_cv = block("barre", inputs, frame_count)
        barre = int(np.clip(np.round(float(barre_cv[0]) * 12.0), 0, 12))
        self._tune(barre)
        volts = self._volts()
        sounding = [value for value, item in zip(volts, self._voicing, strict=False) if item is not None]

        transport = inputs.get("transport")
        if not isinstance(transport, TransportFrame):
            transport = None
        start, per_sample, per_bar, running, self._free_quarters = block_clock(
            transport,
            free_quarters=self._free_quarters,
            rate_hz=self.parameters.rate_hz,
            frame_count=frame_count,
            sample_rate=sample_rate,
        )

        if "strum" in inputs:
            strum = block("strum", inputs, frame_count)
            high = self._strum_high
            hits = []
            for index in range(frame_count):
                event, high = _rise(float(strum[index]), high)
                if event:
                    hits.append(index)
            self._strum_high = high
        elif running and self.parameters.division != FREE:
            period = division_quarters(self.parameters.division, per_bar)
            hits = sample_crossings(start, per_sample, frame_count, period)
        else:
            hits = sample_crossings(start, per_sample, frame_count, 1.0) if running else []

        for hit in hits:
            self._schedule(hit, sample_rate)

        pitch = np.full(frame_count, self._pitch, dtype=np.float64)
        gate = np.zeros(frame_count, dtype=np.float64)
        gap = self._gap
        left = self._gate_left
        pending = self._queued
        hold = int(self.parameters.gate_ms * sample_rate / 1_000.0)
        for index in range(frame_count):
            while pending and pending[0][0] <= index:
                _at, note = pending.pop(0)
                gap = 8
                self._pitch = note
                left = hold
            if gap > 0:
                gap -= 1
                gate[index] = 0.0
            elif left > 0:
                gate[index] = 1.0
                left -= 1
                pitch[index] = self._pitch
            else:
                pitch[index] = self._pitch
        self._gap = gap
        self._gate_left = left
        self._queued = [(at - frame_count, note) for at, note in pending if at - frame_count >= 0]

        low = sounding[0] if sounding else 0.0
        high = sounding[-1] if sounding else 0.0
        outputs: dict[str, FloatBlock] = {
            "pitch": np.asarray(pitch, dtype=np.float32),
            "gate": np.asarray(gate, dtype=np.float32),
            "low": np.full(frame_count, low, dtype=np.float32),
            "high": np.full(frame_count, high, dtype=np.float32),
        }
        for index, value in enumerate(volts, start=1):
            outputs[f"string_{index}"] = np.full(frame_count, value, dtype=np.float32)
        return outputs


def _rise(value: float, was_high: bool) -> tuple[bool, bool]:
    high = value > 0.0
    return high and not was_high, high


__all__ = [
    "FRETBOARD_MANIFEST",
    "FretboardParameters",
    "FretboardVoice",
    "STRUMS",
    "TUNINGS",
]
