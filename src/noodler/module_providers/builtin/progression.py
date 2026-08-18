"""A chord progression, one chord per so many bars, on the rack's clock.

PyTheory keeps thirty-odd progressions by name -- I-V-vi-IV, the twelve-bar
blues, Pachelbel, the Andalusian cadence, rhythm changes' bridge -- and can
realise any of them, or any numerals you write, in any key and mode, as
chords whose tones it knows how to voice: close, open, drop-two, inverted. It
also knows what tends to come next after a chord. This module puts that on
the clock: a chord for so many bars, then the next, round the progression --
or wandering, each chord chosen from what PyTheory suggests after the last --
and puts each chord out as four pitches, a root, a gate and a trigger, for
any voices in the rack to play. Its label is the chord that is sounding.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import PROGRESSIONS, Chord, Key

from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.transport import TransportFrame

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


PROGRESSION_NAMES: tuple[str, ...] = tuple(PROGRESSIONS) + ("custom",)
DEFAULT_PROGRESSION = "I-V-vi-IV"
TONICS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MODES = ("major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "aeolian", "locrian")
VOICINGS = ("close", "open", "drop2", "first inversion", "second inversion")
STYLES = ("loop", "wander", "random")
TRIGGER_SAMPLES = 240
VOICES = 4


class ProgressionError(ValueError):
    """Numerals PyTheory could not read as chords."""


def parse_numerals(text: str) -> tuple[str, ...]:
    """Roman numerals separated by spaces, dashes or commas: 'I V vi IV'."""
    tokens = [t for t in text.replace(",", " ").replace("-", " ").replace("|", " ").split() if t]
    if not tokens:
        raise ProgressionError("write at least one numeral")
    return tuple(tokens)


class ProgressionParameters(BaseModel):
    """Which progression, in what key, voiced how, and how it moves."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    progression: str = DEFAULT_PROGRESSION
    custom: str = "I V vi IV"
    """The numerals, when the progression is 'custom'."""
    tonic: str = "C"
    mode: str = "major"
    voicing: str = "close"
    octave: int = Field(default=4, ge=2, le=6)
    style: str = "loop"
    """loop: round the progression. wander: after each chord, one of what
    PyTheory suggests next. random: a fresh random progression each time round."""
    bars_per_chord: int = Field(default=1, ge=1, le=8)
    follow_clock: bool = True
    """Change chords on the transport's bars. Off, on its own rate."""
    rate_hz: float = Field(default=0.5, gt=0.0, le=20.0)
    """Chords per second when running free."""
    gate_length: float = Field(default=0.9, ge=0.05, le=1.0)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    seed: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def known(self) -> "ProgressionParameters":
        if self.progression not in PROGRESSION_NAMES:
            object.__setattr__(self, "progression", DEFAULT_PROGRESSION)
        if self.tonic not in TONICS:
            object.__setattr__(self, "tonic", "C")
        if self.mode not in MODES:
            object.__setattr__(self, "mode", "major")
        if self.voicing not in VOICINGS:
            object.__setattr__(self, "voicing", "close")
        if self.style not in STYLES:
            object.__setattr__(self, "style", "loop")
        return self


PROGRESSION_OUTPUTS = ("voice_1", "voice_2", "voice_3", "voice_4", "root", "gate", "change", "position")

PROGRESSION_MANIFEST = ModuleManifest(
    id="pytheory_progression",
    name="PyTheory Progression",
    category="Musical Brains",
    description=(
        "One of PyTheory's chord progressions -- or your own numerals -- in any "
        "key and mode, a chord every so many bars on the rack's clock, voiced "
        "as four pitches with a root, a gate and a trigger; or wandering, each "
        "chord one PyTheory suggests after the last."
    ),
    ports=(
        port("step", "Step", PortDirection.INPUT, SignalType.GATE, "Each rising edge is the next chord, instead of the clock."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Back to the first chord."),
        port("voice_1", "V1", PortDirection.OUTPUT, SignalType.CV, "The chord's lowest voice, one volt per octave."),
        port("voice_2", "V2", PortDirection.OUTPUT, SignalType.CV, "The second voice."),
        port("voice_3", "V3", PortDirection.OUTPUT, SignalType.CV, "The third voice."),
        port("voice_4", "V4", PortDirection.OUTPUT, SignalType.CV, "The fourth voice: the seventh, or the root an octave up."),
        port("root", "Root", PortDirection.OUTPUT, SignalType.CV, "The chord's root, an octave below the voices."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "High for the gate length of each chord."),
        port("change", "Chg", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger at every new chord."),
        port("position", "Pos", PortDirection.OUTPUT, SignalType.CV, "How far through the progression, zero to one."),
    ),
)


def _midi_to_volts(midi: float, reference_hz: float) -> float:
    hertz = 440.0 * 2.0 ** ((midi - 69.0) / 12.0)
    return math.log2(hertz / reference_hz)


class PyTheoryProgression:
    """Step through a chord progression on the clock."""

    manifest = PROGRESSION_MANIFEST
    uses_transport = True

    def __init__(self, parameters: ProgressionParameters | None = None) -> None:
        self.parameters = parameters or ProgressionParameters()
        self._read_for: tuple | None = None
        self._key: Key | None = None
        self._numerals: tuple[str, ...] = ()
        self._chords: list[Chord] = []
        self.fault: str | None = None
        self._rng = np.random.default_rng(self.parameters.seed)
        self._index = -1
        self._current: Chord | None = None
        self._voices: list[float] = [0.0] * VOICES
        self._root = 0.0
        self._free_phase = 0.0
        self._free_index = 0
        self._step_high = False
        self._reset_high = False
        self._pending_change = 0
        self._elapsed = 0.0
        self._gate_until = -1.0
        self._chord_seconds = 2.0

    # ---- reading the progression -----------------------------------------

    def choices_for(self, field: str) -> tuple[str, ...]:
        return {
            "progression": PROGRESSION_NAMES,
            "tonic": TONICS,
            "mode": MODES,
            "voicing": VOICINGS,
            "style": STYLES,
        }.get(field, ())

    @property
    def label(self) -> str:
        if self.fault:
            return f"PROGRESSION FAULT  ·  {self.fault}"[:90]
        name = str(self._current) if self._current is not None else "—"
        numeral = ""
        if self._numerals and 0 <= self._index < len(self._numerals) and self.parameters.style == "loop":
            numeral = f"  ·  {self._numerals[self._index]}"
        return f"{name.upper()}{numeral}  ·  {self.parameters.tonic} {self.parameters.mode.upper()}"

    def _read(self) -> None:
        p = self.parameters
        key = (p.progression, p.custom, p.tonic, p.mode, p.style)
        if key == self._read_for:
            return
        self._read_for = key
        try:
            self._key = Key(p.tonic, p.mode)
            if p.progression == "custom":
                numerals = parse_numerals(p.custom)
            else:
                numerals = tuple(PROGRESSIONS[p.progression])
            chords = list(self._key.progression(*numerals))
        except (ProgressionError, ValueError, KeyError, TypeError) as error:
            self.fault = str(error)
            return
        if not chords:
            self.fault = "no chords"
            return
        self.fault = None
        self._numerals = numerals
        self._chords = chords
        self._index = -1
        self._current = None

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._read()

    # ---- voicing ---------------------------------------------------------

    def _voice(self, chord: Chord) -> tuple[list[float], float]:
        """Four MIDI notes for a chord in the chosen voicing and octave, and its root."""
        voicing = self.parameters.voicing
        try:
            if voicing == "open":
                shaped = chord.open_voicing()
            elif voicing == "drop2":
                shaped = chord.drop2()
            elif voicing == "first inversion":
                shaped = chord.inversion(1)
            elif voicing == "second inversion":
                shaped = chord.inversion(2)
            else:
                shaped = chord.close_voicing()
        except Exception:  # a voicing PyTheory declines for this chord
            shaped = chord
        midis = sorted(float(t.midi) for t in shaped.tones if t.midi is not None)
        if not midis:
            return [60.0] * VOICES, 48.0
        # Into the chosen octave: the lowest note within it.
        floor = 12.0 * (self.parameters.octave + 1)  # C of that octave, MIDI
        while midis[0] < floor:
            midis = [m + 12.0 for m in midis]
        while midis[0] >= floor + 12.0:
            midis = [m - 12.0 for m in midis]
        # A triad's fourth voice is its lowest note an octave up.
        size = len(midis)
        while len(midis) < VOICES:
            midis.append(midis[len(midis) - size] + 12.0)
        midis = sorted(midis)
        root_tone = chord.root
        root_midi = float(root_tone.midi) if root_tone is not None and root_tone.midi is not None else midis[0]
        while root_midi >= midis[0]:
            root_midi -= 12.0
        return midis[:VOICES], root_midi

    def _next_chord(self) -> tuple[Chord, int]:
        """The chord after the current one, by the style; returns it and its index."""
        style = self.parameters.style
        if style == "wander" and self._current is not None and self._key is not None:
            options = list(self._key.suggest_next(self._current)) or self._chords
            choice = options[int(self._rng.integers(0, len(options)))]
            return choice, (self._index + 1) % max(1, len(self._chords))
        if style == "random" and self._key is not None and (self._index + 1) % max(1, len(self._chords)) == 0 and self._index >= 0:
            fresh = list(self._key.random_progression(len(self._chords) or 4))
            if fresh:
                self._chords = fresh
        index = (self._index + 1) % len(self._chords)
        return self._chords[index], index

    def _play(self, chord: Chord, index: int, at_sample: int, frame_count: int, sample_rate: float, outputs) -> None:
        self._current = chord
        self._index = index
        midis, root_midi = self._voice(chord)
        reference = self.parameters.reference_frequency_hz
        self._voices = [_midi_to_volts(m, reference) for m in midis]
        self._root = _midi_to_volts(root_midi, reference)
        self._gate_until = self._elapsed + at_sample / sample_rate + self._chord_seconds * self.parameters.gate_length
        end = at_sample + TRIGGER_SAMPLES
        outputs["change"][at_sample:end] = 1.0
        if end > frame_count:
            self._pending_change = end - frame_count

    # ---- the block ---------------------------------------------------------

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
            return empty_outputs(PROGRESSION_OUTPUTS)
        self._read()
        inputs = inputs or {}
        outputs = {name: np.zeros(frame_count, dtype=np.float32) for name in PROGRESSION_OUTPUTS}
        if self._pending_change:
            outputs["change"][: min(self._pending_change, frame_count)] = 1.0
            self._pending_change = max(0, self._pending_change - frame_count)
        if self.fault or not self._chords:
            self._elapsed += frame_count / sample_rate
            return outputs

        transport = inputs.get("transport")
        if not isinstance(transport, TransportFrame):
            transport = None
        stepped = "step" in inputs
        step = np.asarray(block("step", inputs, frame_count), dtype=np.float64) if stepped else None
        reset = np.asarray(block("reset", inputs, frame_count), dtype=np.float64)

        # How long a chord lasts, for the gate: a bar's worth of bars, or the rate.
        follow = self.parameters.follow_clock and transport is not None and not stepped
        if transport is not None and follow:
            self._chord_seconds = self.parameters.bars_per_chord * transport.quarters_per_bar / max(1e-6, transport.quarters_per_second)
        else:
            self._chord_seconds = 1.0 / self.parameters.rate_hz

        for index in range(frame_count):
            reset_event, self._reset_high = rising_edge(reset[index], self._reset_high)
            if reset_event:
                self._index = -1
                self._current = None
                self._free_phase = 0.0
                if follow:
                    self._free_index = -1
            change = False
            if stepped:
                event, self._step_high = rising_edge(step[index], self._step_high)
                change = event or (reset_event and self._current is None)
            elif follow:
                # The bar the clock is in, in units of chords: a new one is a change.
                quarters = transport.quarters + (index * transport.quarters_per_second / sample_rate if transport.running else 0.0)
                bar_index = int(quarters // (transport.quarters_per_bar * self.parameters.bars_per_chord))
                if bar_index != self._free_index or self._current is None:
                    if self._current is None or transport.running or reset_event:
                        self._free_index = bar_index
                        change = True
            else:
                if self._current is None:
                    change = True
                self._free_phase += 1.0 / sample_rate
                if self._free_phase >= self._chord_seconds:
                    self._free_phase -= self._chord_seconds
                    change = True
            if change:
                chord, chord_index = self._next_chord()
                self._play(chord, chord_index, index, frame_count, sample_rate, outputs)
            for voice, value in enumerate(self._voices):
                outputs[f"voice_{voice + 1}"][index] = value
            outputs["root"][index] = self._root
            outputs["gate"][index] = 1.0 if (self._elapsed + index / sample_rate) < self._gate_until else 0.0
            outputs["position"][index] = (self._index / max(1, len(self._chords) - 1)) if self._index >= 0 and len(self._chords) > 1 else 0.0
        self._elapsed += frame_count / sample_rate
        return outputs


__all__ = [
    "MODES",
    "PROGRESSION_MANIFEST",
    "PROGRESSION_NAMES",
    "ProgressionError",
    "ProgressionParameters",
    "PyTheoryProgression",
    "STYLES",
    "TONICS",
    "VOICINGS",
    "parse_numerals",
]
