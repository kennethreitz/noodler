"""PyTheory-prepared compositional brains for the real-time patch graph."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import permutations, product
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import Chord, Key, TonedScale

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge
from .scale_generator import SUPPORTED_SCALE_SYSTEMS, TONICS, scale_names


MELODY_OUTPUTS = (
    "note",
    "pitch",
    "frequency",
    "degree",
    "accent",
    "gate",
    "trigger",
    "phrase",
)
HARMONY_OUTPUTS = (
    "chord",
    "bass",
    "voice_1",
    "voice_2",
    "voice_3",
    "voice_4",
    "degree",
    "function",
    "gate",
    "trigger",
    "cadence",
)
ARPEGGIO_OUTPUTS = ("note", "pitch", "position", "gate", "trigger")


class MelodyStyle(StrEnum):
    """Phrase generators offered by Melody Brain."""

    WANDER = "weighted wander"
    ARCH = "rising arch"
    MOTIF = "motif and answer"
    RANDOM = "free random"


class MelodyBrainParameters(BaseModel):
    """Serializable controls for a cached PyTheory melody phrase."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    system: str = "western"
    tonic: str = "C"
    octave: int = Field(default=4, ge=0, le=7)
    scale_name: str = "dorian"
    style: MelodyStyle = MelodyStyle.WANDER
    phrase_length: int = Field(default=16, ge=4, le=64)
    octave_range: int = Field(default=2, ge=1, le=4)
    density: float = Field(default=0.82, ge=0.05, le=1.0)
    step_bias: float = Field(default=0.78, ge=0.0, le=1.0)
    rate_hz: float = Field(default=2.0, ge=0.01, le=100.0)
    gate_length: float = Field(default=0.55, ge=0.01, le=0.99)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def selection_exists_in_pytheory(self) -> "MelodyBrainParameters":
        if self.system not in SUPPORTED_SCALE_SYSTEMS:
            raise ValueError(f"unsupported scale system: {self.system}")
        if self.tonic not in TONICS:
            raise ValueError(f"unsupported tonic: {self.tonic}")
        if self.scale_name not in scale_names(self.system):
            raise ValueError(f"{self.scale_name!r} is not a {self.system} scale")
        TonedScale(
            tonic=f"{self.tonic}{self.octave}",
            system=self.system,
        )[self.scale_name]
        return self


@dataclass(frozen=True, slots=True)
class _MelodyStep:
    tone_index: int
    active: bool
    accent: float


MELODY_BRAIN_MANIFEST = ModuleManifest(
    id="melody_brain",
    name="PyTheory Melody Brain",
    category="Musical Brains",
    description=(
        "A seeded phrase composer with rests, accents, mutation, and "
        "scale-correct pitch prepared by PyTheory."
    ),
    ports=(
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "Advance the phrase."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Return to phrase step one."),
        port("mutate", "Mutate", PortDirection.INPUT, SignalType.TRIGGER, "Alter one interior phrase tone."),
        port("transpose", "Transpose", PortDirection.INPUT, SignalType.CV, "Continuous octave transposition."),
        port("density_cv", "Density CV", PortDirection.INPUT, SignalType.CV, "Bipolar live rest-probability offset."),
        port("note", "Note", PortDirection.OUTPUT, SignalType.MUSICAL, "Current PyTheory tone as a MIDI-compatible value."),
        port("pitch", "1 V/oct", PortDirection.OUTPUT, SignalType.CV, "Pitch relative to the configured reference."),
        port("frequency", "Frequency", PortDirection.OUTPUT, SignalType.CV, "Current tone frequency in hertz."),
        port("degree", "Degree", PortDirection.OUTPUT, SignalType.CV, "Normalized position in the prepared pitch range."),
        port("accent", "Accent", PortDirection.OUTPUT, SignalType.CV, "Per-step expression from zero to one."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "Clock gate with composed rests applied."),
        port("trigger", "Trigger", PortDirection.OUTPUT, SignalType.TRIGGER, "Pulse on each active phrase event."),
        port("phrase", "Phrase", PortDirection.OUTPUT, SignalType.TRIGGER, "Pulse at the start of each phrase."),
    ),
)


class MelodyBrain:
    """Compose a repeatable scale-aware phrase without theory work in callback."""

    manifest = MELODY_BRAIN_MANIFEST

    def __init__(self, parameters: MelodyBrainParameters | None = None) -> None:
        self.parameters = parameters or MelodyBrainParameters()
        self._rng = np.random.default_rng(self.parameters.seed)
        self._tones = self._tones_for(self.parameters)
        self._phrase = self._compose_phrase()
        self.reset()

    @property
    def current_note(self) -> str:
        step = self._phrase[max(0, self._step)]
        return self._tones[step.tone_index][0]

    @property
    def phrase(self) -> tuple[int | None, ...]:
        return tuple(step.tone_index if step.active else None for step in self._phrase)

    def configure(self, **changes: object) -> None:
        values = self.parameters.model_dump()
        values.update(changes)
        parameters = MelodyBrainParameters.model_validate(values)
        self.parameters = parameters
        self._rng = np.random.default_rng(parameters.seed)
        self._tones = self._tones_for(parameters)
        self._phrase = self._compose_phrase()
        self.reset()

    def reset(self) -> None:
        self._step = -1
        self._live_active = self._phrase[0].active
        self._clock_phase = 0.0
        self._clock_high = False
        self._reset_high = False
        self._mutate_high = False

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
            return empty_outputs(MELODY_OUTPUTS)

        inputs = inputs or {}
        external_clock = "clock" in inputs
        clock = block("clock", inputs, frame_count)
        reset = block("reset", inputs, frame_count)
        mutate = block("mutate", inputs, frame_count)
        transpose = block("transpose", inputs, frame_count)
        density_cv = block("density_cv", inputs, frame_count)
        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in MELODY_OUTPUTS
        }

        for sample in range(frame_count):
            clock_event, clock_high = rising_edge(clock[sample], self._clock_high)
            if external_clock:
                raw_gate = 1.0 if clock_high else 0.0
            else:
                raw_gate = 1.0 if self._clock_phase < self.parameters.gate_length else 0.0
                self._clock_phase += self.parameters.rate_hz / sample_rate
                clock_event = self._clock_phase >= 1.0
                if clock_event:
                    self._clock_phase %= 1.0

            reset_event, reset_high = rising_edge(reset[sample], self._reset_high)
            mutate_event, mutate_high = rising_edge(mutate[sample], self._mutate_high)
            if mutate_event:
                self._mutate_phrase()

            trigger = 0.0
            phrase_trigger = 0.0
            if reset_event:
                self._step = 0
                phrase_trigger = 1.0
            elif clock_event:
                self._step = (self._step + 1) % len(self._phrase)
                phrase_trigger = 1.0 if self._step == 0 else 0.0

            phrase_step = self._phrase[max(0, self._step)]
            name, midi, base_frequency = self._tones[phrase_step.tone_index]
            del name
            transposition = float(np.clip(transpose[sample], -8.0, 8.0))
            frequency = base_frequency * 2.0**transposition
            pitch = math.log2(frequency / self.parameters.reference_frequency_hz)
            if reset_event or clock_event:
                live_density = float(
                    np.clip(
                        self.parameters.density + density_cv[sample],
                        0.0,
                        1.0,
                    )
                )
                self._live_active = phrase_step.active and (
                    live_density >= self.parameters.density
                    or self._rng.random() < live_density / self.parameters.density
                )
                trigger = 1.0 if self._live_active else 0.0

            outputs["note"][sample] = midi + 12.0 * transposition
            outputs["pitch"][sample] = pitch
            outputs["frequency"][sample] = frequency
            outputs["degree"][sample] = (
                phrase_step.tone_index / (len(self._tones) - 1)
                if len(self._tones) > 1
                else 0.0
            )
            outputs["accent"][sample] = phrase_step.accent if self._live_active else 0.0
            outputs["gate"][sample] = raw_gate if self._live_active else 0.0
            outputs["trigger"][sample] = trigger
            outputs["phrase"][sample] = phrase_trigger
            self._clock_high = clock_high
            self._reset_high = reset_high
            self._mutate_high = mutate_high

        return {
            name: np.asarray(value, dtype=np.float32)
            for name, value in outputs.items()
        }

    @staticmethod
    def _tones_for(
        parameters: MelodyBrainParameters,
    ) -> tuple[tuple[str, float, float], ...]:
        tones: list[tuple[str, float, float]] = []
        for offset in range(parameters.octave_range):
            scale = TonedScale(
                tonic=f"{parameters.tonic}{parameters.octave + offset}",
                system=parameters.system,
            )[parameters.scale_name]
            octave_tones = list(scale.tones)
            if offset < parameters.octave_range - 1:
                octave_tones = octave_tones[:-1]
            tones.extend(
                (str(tone), float(tone.midi), float(tone.frequency))
                for tone in octave_tones
            )
        return tuple(tones)

    def _compose_phrase(self) -> tuple[_MelodyStep, ...]:
        length = self.parameters.phrase_length
        count = len(self._tones)
        style = self.parameters.style
        indices: list[int] = [0]
        current = 0
        motif: list[int] = []
        for step in range(1, length):
            if step == length - 1:
                current = 0
            elif style is MelodyStyle.RANDOM:
                current = int(self._rng.integers(count))
            elif style is MelodyStyle.ARCH:
                midpoint = max(1, (length - 1) // 2)
                position = step if step <= midpoint else length - 1 - step
                current = round(position * (count - 1) / midpoint)
            elif style is MelodyStyle.MOTIF and step >= max(2, length // 2):
                source = motif[(step - max(2, length // 2)) % len(motif)]
                answer = 1 if (step // max(2, length // 2)) % 2 else 0
                current = min(count - 1, source + answer)
            else:
                local = self.parameters.step_bias / 2.0
                leap = (1.0 - self.parameters.step_bias) / 2.0
                interval = int(
                    self._rng.choice((-2, -1, 1, 2), p=(leap, local, local, leap))
                )
                current += interval
                if current < 0:
                    current = -current
                if current >= count:
                    current = 2 * (count - 1) - current
                current = max(0, min(count - 1, current))
            indices.append(current)
            if step < max(2, length // 2):
                motif.append(current)

        phrase = []
        for position, tone_index in enumerate(indices):
            structural = position in {0, length - 1, length // 2}
            active = structural or self._rng.random() < self.parameters.density
            accent = 0.95 if position == 0 else float(self._rng.uniform(0.48, 0.88))
            phrase.append(_MelodyStep(tone_index, active, accent))
        return tuple(phrase)

    def _mutate_phrase(self) -> None:
        if len(self._phrase) <= 3:
            return
        position = int(self._rng.integers(1, len(self._phrase) - 1))
        step = self._phrase[position]
        shift = int(self._rng.choice((-2, -1, 1, 2)))
        tone_index = max(0, min(len(self._tones) - 1, step.tone_index + shift))
        phrase = list(self._phrase)
        phrase[position] = _MelodyStep(tone_index, step.active, step.accent)
        self._phrase = tuple(phrase)


class HarmonicStyle(StrEnum):
    """Prepared progression grammars for Harmony Brain."""

    JOURNEY = "tonic journey"
    CIRCLE = "circle motion"
    DREAM = "dream changes"
    FUNCTIONAL = "functional choices"


class HarmonyBrainParameters(BaseModel):
    """Serializable key, progression, voicing, and clock controls."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tonic: str = "C"
    mode: str = "major"
    style: HarmonicStyle = HarmonicStyle.JOURNEY
    length: int = Field(default=8, ge=2, le=32)
    register_octave: int = Field(default=4, ge=1, le=6)
    rate_hz: float = Field(default=0.5, ge=0.01, le=20.0)
    gate_length: float = Field(default=0.8, ge=0.01, le=0.99)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def key_exists(self) -> "HarmonyBrainParameters":
        if self.tonic not in TONICS:
            raise ValueError(f"unsupported tonic: {self.tonic}")
        if self.mode not in {"major", "minor"}:
            raise ValueError("mode must be major or minor")
        Key(self.tonic, self.mode)
        return self


HARMONY_BRAIN_MANIFEST = ModuleManifest(
    id="harmony_brain",
    name="PyTheory Harmony Brain",
    category="Musical Brains",
    description=(
        "A key-aware progression source with deterministic functional choices "
        "and four smoothly voiced pitch outputs."
    ),
    ports=(
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "Advance to the next harmony."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Return to the opening chord."),
        port("chord", "Chord", PortDirection.OUTPUT, SignalType.MUSICAL, "Current chord represented by its root MIDI value."),
        port("bass", "Bass", PortDirection.OUTPUT, SignalType.CV, "Root voice one octave below the voicing register."),
        port("voice_1", "Voice 1", PortDirection.OUTPUT, SignalType.CV, "Lowest voice-led chord pitch."),
        port("voice_2", "Voice 2", PortDirection.OUTPUT, SignalType.CV, "Second voice-led chord pitch."),
        port("voice_3", "Voice 3", PortDirection.OUTPUT, SignalType.CV, "Third voice-led chord pitch."),
        port("voice_4", "Voice 4", PortDirection.OUTPUT, SignalType.CV, "Highest voice-led chord pitch."),
        port("degree", "Progress", PortDirection.OUTPUT, SignalType.CV, "Normalized progression position."),
        port("function", "Function", PortDirection.OUTPUT, SignalType.CV, "Tonic 0, subdominant 0.5, or dominant 1."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "Held harmony gate."),
        port("trigger", "Change", PortDirection.OUTPUT, SignalType.TRIGGER, "Pulse when the chord advances."),
        port("cadence", "Cadence", PortDirection.OUTPUT, SignalType.TRIGGER, "Pulse when the progression returns home."),
    ),
)


class HarmonyBrain:
    """Cache PyTheory chords and voice-leading for block-safe playback."""

    manifest = HARMONY_BRAIN_MANIFEST

    def __init__(self, parameters: HarmonyBrainParameters | None = None) -> None:
        self.parameters = parameters or HarmonyBrainParameters()
        self._chords: tuple[Chord, ...] = ()
        self._voicings: tuple[tuple[int, int, int, int], ...] = ()
        self._bass: tuple[int, ...] = ()
        self._functions: tuple[float, ...] = ()
        self._prepare_harmony()
        self.reset()

    @property
    def chord_symbols(self) -> tuple[str, ...]:
        return tuple(chord.symbol for chord in self._chords)

    @property
    def current_chord(self) -> str:
        return self._chords[self._index].symbol

    def configure(self, **changes: object) -> None:
        values = self.parameters.model_dump()
        values.update(changes)
        self.parameters = HarmonyBrainParameters.model_validate(values)
        self._prepare_harmony()
        self.reset()

    def reset(self) -> None:
        self._index = 0
        self._started = False
        self._clock_phase = 0.0
        self._clock_high = False
        self._reset_high = False

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
            return empty_outputs(HARMONY_OUTPUTS)

        inputs = inputs or {}
        external_clock = "clock" in inputs
        clock = block("clock", inputs, frame_count)
        reset = block("reset", inputs, frame_count)
        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in HARMONY_OUTPUTS
        }

        for sample in range(frame_count):
            clock_event, clock_high = rising_edge(clock[sample], self._clock_high)
            if external_clock:
                gate = 1.0 if clock_high else 0.0
            else:
                gate = 1.0 if self._clock_phase < self.parameters.gate_length else 0.0
                self._clock_phase += self.parameters.rate_hz / sample_rate
                clock_event = self._clock_phase >= 1.0
                if clock_event:
                    self._clock_phase %= 1.0
            reset_event, reset_high = rising_edge(reset[sample], self._reset_high)

            trigger = 0.0
            cadence = 0.0
            if reset_event:
                self._index = 0
                self._started = True
                trigger = 1.0
                cadence = 1.0
            elif clock_event:
                if self._started:
                    self._index = (self._index + 1) % len(self._chords)
                else:
                    self._started = True
                trigger = 1.0
                cadence = 1.0 if self._index == 0 else 0.0

            chord = self._chords[self._index]
            voices = self._voicings[self._index]
            root_midi = float(chord.root.midi)
            outputs["chord"][sample] = root_midi
            outputs["bass"][sample] = self._midi_pitch(self._bass[self._index])
            for voice_index, midi in enumerate(voices, start=1):
                outputs[f"voice_{voice_index}"][sample] = self._midi_pitch(midi)
            outputs["degree"][sample] = (
                self._index / (len(self._chords) - 1)
                if len(self._chords) > 1
                else 0.0
            )
            outputs["function"][sample] = self._functions[self._index]
            outputs["gate"][sample] = gate
            outputs["trigger"][sample] = trigger
            outputs["cadence"][sample] = cadence
            self._clock_high = clock_high
            self._reset_high = reset_high

        return {
            name: np.asarray(value, dtype=np.float32)
            for name, value in outputs.items()
        }

    def _prepare_harmony(self) -> None:
        parameters = self.parameters
        key = Key(parameters.tonic, parameters.mode)
        rng = np.random.default_rng(parameters.seed)
        if parameters.style is HarmonicStyle.FUNCTIONAL:
            tonic = key.progression("I" if parameters.mode == "major" else "i")[0]
            chords = [tonic]
            while len(chords) < parameters.length:
                choices = key.suggest_next(chords[-1])
                rank = min(len(choices) - 1, int(rng.geometric(0.58)) - 1)
                chords.append(choices[rank])
        else:
            romans = self._roman_pattern(parameters.mode, parameters.style)
            sequence = tuple(romans[index % len(romans)] for index in range(parameters.length))
            chords = list(key.progression(*sequence))

        previous: tuple[int, int, int, int] | None = None
        voicings = []
        bass = []
        for chord in chords:
            voice = self._voice_chord(chord, parameters.register_octave, previous)
            voicings.append(voice)
            previous = voice
            root_pc = int(round(float(chord.root.midi))) % 12
            bass.append(12 * parameters.register_octave + root_pc)

        functions = key.chords_by_function()
        symbol_groups = {
            name: {chord.symbol for chord in group}
            for name, group in functions.items()
        }
        function_values = []
        tonic_pc = int(round(float(chords[0].root.midi))) % 12
        subdominant_pc = (tonic_pc + 5) % 12
        dominant_pc = (tonic_pc + 7) % 12
        for chord in chords:
            root_pc = int(round(float(chord.root.midi))) % 12
            if root_pc == dominant_pc or chord.symbol in symbol_groups["dominant"]:
                function_values.append(1.0)
            elif (
                root_pc == subdominant_pc
                or chord.symbol in symbol_groups["subdominant"]
            ):
                function_values.append(0.5)
            else:
                function_values.append(0.0)

        self._chords = tuple(chords)
        self._voicings = tuple(voicings)
        self._bass = tuple(bass)
        self._functions = tuple(function_values)

    @staticmethod
    def _roman_pattern(mode: str, style: HarmonicStyle) -> tuple[str, ...]:
        if mode == "minor":
            return {
                HarmonicStyle.JOURNEY: ("i", "VI", "III", "VII"),
                HarmonicStyle.CIRCLE: ("i", "iv", "VI", "V"),
                HarmonicStyle.DREAM: ("i", "III", "VII", "VI"),
            }[style]
        return {
            HarmonicStyle.JOURNEY: ("I", "vi", "IV", "V"),
            HarmonicStyle.CIRCLE: ("I", "IV", "ii", "V"),
            HarmonicStyle.DREAM: ("I", "iii", "vi", "IV"),
        }[style]

    @staticmethod
    def _voice_chord(
        chord: Chord,
        octave: int,
        previous: tuple[int, int, int, int] | None,
    ) -> tuple[int, int, int, int]:
        pitch_classes = [int(round(float(tone.midi))) % 12 for tone in chord.tones[:3]]
        while len(pitch_classes) < 3:
            pitch_classes.append(pitch_classes[-1])
        pitch_classes.append(pitch_classes[0])
        low = 12 * (octave + 1)
        high = low + 24
        candidates = {
            pitch_class: tuple(
                midi for midi in range(low, high + 1) if midi % 12 == pitch_class
            )
            for pitch_class in set(pitch_classes)
        }
        target = previous or (low, low + 4, low + 7, low + 12)
        best: tuple[int, int, int, int] | None = None
        best_score = math.inf
        for ordering in set(permutations(pitch_classes)):
            for voicing in product(*(candidates[pitch_class] for pitch_class in ordering)):
                if tuple(sorted(voicing)) != voicing or len(set(voicing)) != 4:
                    continue
                score = sum(abs(note - prior) for note, prior in zip(voicing, target, strict=True))
                score += 0.12 * (voicing[-1] - voicing[0])
                if score < best_score:
                    best = tuple(int(note) for note in voicing)
                    best_score = score
        if best is None:
            raise ValueError(f"could not voice chord {chord.symbol}")
        return best

    def _midi_pitch(self, midi: int) -> float:
        frequency = 440.0 * 2.0 ** ((midi - 69.0) / 12.0)
        return math.log2(frequency / self.parameters.reference_frequency_hz)


class ArpeggioPattern(StrEnum):
    """Traversal orders for Arpeggio Brain."""

    UP = "up"
    DOWN = "down"
    UP_DOWN = "up / down"
    AS_PLAYED = "as patched"
    RANDOM = "random"


class ArpeggioBrainParameters(BaseModel):
    """Serializable traversal and fallback-chord controls."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    pattern: ArpeggioPattern = ArpeggioPattern.UP_DOWN
    octave_range: int = Field(default=1, ge=1, le=4)
    rate_hz: float = Field(default=4.0, ge=0.01, le=100.0)
    gate_length: float = Field(default=0.45, ge=0.01, le=0.99)
    fallback_pitches: tuple[float, float, float, float] = (0.0, 4 / 12, 7 / 12, 1.0)
    reference_midi: float = Field(default=57.0, ge=0.0, le=127.0)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)


ARPEGGIO_BRAIN_MANIFEST = ModuleManifest(
    id="arpeggio_brain",
    name="Arpeggio Brain",
    category="Musical Brains",
    description="A four-voice chord-to-pitch sequencer with clocked octave patterns.",
    ports=(
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "Advance one arpeggio step."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Return to step one."),
        port("hold", "Hold", PortDirection.INPUT, SignalType.GATE, "Keep the currently sampled chord."),
        port("voice_1", "Voice 1", PortDirection.INPUT, SignalType.CV, "First chord pitch."),
        port("voice_2", "Voice 2", PortDirection.INPUT, SignalType.CV, "Second chord pitch."),
        port("voice_3", "Voice 3", PortDirection.INPUT, SignalType.CV, "Third chord pitch."),
        port("voice_4", "Voice 4", PortDirection.INPUT, SignalType.CV, "Fourth chord pitch."),
        port("transpose", "Transpose", PortDirection.INPUT, SignalType.CV, "Octave transposition after traversal."),
        port("note", "Note", PortDirection.OUTPUT, SignalType.MUSICAL, "Current pitch as a MIDI-compatible value."),
        port("pitch", "1 V/oct", PortDirection.OUTPUT, SignalType.CV, "Selected chord pitch."),
        port("position", "Position", PortDirection.OUTPUT, SignalType.CV, "Normalized arpeggio step."),
        port("gate", "Gate", PortDirection.OUTPUT, SignalType.GATE, "Clock-shaped output gate."),
        port("trigger", "Trigger", PortDirection.OUTPUT, SignalType.TRIGGER, "Pulse on every new arpeggio note."),
    ),
)


class ArpeggioBrain:
    """Sample four CV voices and serialize them into a pitch/gate line."""

    manifest = ARPEGGIO_BRAIN_MANIFEST

    def __init__(self, parameters: ArpeggioBrainParameters | None = None) -> None:
        self.parameters = parameters or ArpeggioBrainParameters()
        self._rng = np.random.default_rng(self.parameters.seed)
        self._sampled = self.parameters.fallback_pitches
        self._sequence = self._ordered(self._sampled)
        self.reset()

    def reset(self) -> None:
        self._index = -1
        self._clock_phase = 0.0
        self._clock_high = False
        self._reset_high = False

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
            return empty_outputs(ARPEGGIO_OUTPUTS)

        inputs = inputs or {}
        external_clock = "clock" in inputs
        clock = block("clock", inputs, frame_count)
        reset = block("reset", inputs, frame_count)
        hold = block("hold", inputs, frame_count)
        transpose = block("transpose", inputs, frame_count)
        voice_blocks = [
            block(
                f"voice_{voice}",
                inputs,
                frame_count,
                default=self.parameters.fallback_pitches[voice - 1],
            )
            for voice in range(1, 5)
        ]
        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in ARPEGGIO_OUTPUTS
        }

        for sample in range(frame_count):
            clock_event, clock_high = rising_edge(clock[sample], self._clock_high)
            if external_clock:
                gate = 1.0 if clock_high else 0.0
            else:
                gate = 1.0 if self._clock_phase < self.parameters.gate_length else 0.0
                self._clock_phase += self.parameters.rate_hz / sample_rate
                clock_event = self._clock_phase >= 1.0
                if clock_event:
                    self._clock_phase %= 1.0
            reset_event, reset_high = rising_edge(reset[sample], self._reset_high)
            trigger = 0.0
            if reset_event:
                self._index = 0
                trigger = 1.0
            elif clock_event:
                if hold[sample] <= 0.0:
                    sampled = tuple(float(voice[sample]) for voice in voice_blocks)
                    if sampled != self._sampled:
                        self._sampled = sampled
                        self._sequence = self._ordered(sampled)
                if self.parameters.pattern is ArpeggioPattern.RANDOM:
                    self._index = int(self._rng.integers(len(self._sequence)))
                else:
                    self._index = (self._index + 1) % len(self._sequence)
                trigger = 1.0

            sequence_index = max(0, self._index)
            pitch = self._sequence[sequence_index] + float(transpose[sample])
            outputs["pitch"][sample] = pitch
            outputs["note"][sample] = self.parameters.reference_midi + 12.0 * pitch
            outputs["position"][sample] = (
                sequence_index / (len(self._sequence) - 1)
                if len(self._sequence) > 1
                else 0.0
            )
            outputs["gate"][sample] = gate
            outputs["trigger"][sample] = trigger
            self._clock_high = clock_high
            self._reset_high = reset_high

        return {
            name: np.asarray(value, dtype=np.float32)
            for name, value in outputs.items()
        }

    def _ordered(self, pitches: tuple[float, float, float, float]) -> tuple[float, ...]:
        base = list(pitches)
        if self.parameters.pattern is ArpeggioPattern.UP:
            base.sort()
        elif self.parameters.pattern is ArpeggioPattern.DOWN:
            base.sort(reverse=True)
        elif self.parameters.pattern is ArpeggioPattern.UP_DOWN:
            ascending = sorted(base)
            base = ascending + ascending[-2:0:-1]
        sequence = [
            pitch + octave
            for octave in range(self.parameters.octave_range)
            for pitch in base
        ]
        return tuple(sequence)


__all__ = [
    "ARPEGGIO_BRAIN_MANIFEST",
    "HARMONY_BRAIN_MANIFEST",
    "MELODY_BRAIN_MANIFEST",
    "ArpeggioBrain",
    "ArpeggioBrainParameters",
    "ArpeggioPattern",
    "HarmonicStyle",
    "HarmonyBrain",
    "HarmonyBrainParameters",
    "MelodyBrain",
    "MelodyBrainParameters",
    "MelodyStyle",
]
