"""Modules that keep time with the rack's one clock.

The DSP has never known about tempo: a division is turned into hertz on the
control thread and the module sees a rate. That is right for anything that
merely repeats. It is wrong for anything that has to land on *beat one* — a
drum pattern, a bar trigger — because a rate says how often and not when.

So a module may ask for the clock. One that sets ``uses_transport`` is handed a
:class:`~noodler.transport.TransportFrame` in its inputs each block: tempo,
where the bar stood at the block's first sample, how many bars have gone by,
and whether the clock is running. Nothing else in the graph sees it, and a
module rendered without one — offline, in a test — runs free from its own rate,
so it is never *dependent* on the clock, only faithful to it when there is one.

Two modules live here. **Clock** turns the transport into signals the rest of
the rack can be patched to — a trigger every beat, a trigger every bar, the
bar as a ramp, and a gate that is high while the clock runs — so a melody
brain clocked from it lands its phrases on the bar. **PyTheory Beats** plays
one of PyTheory's hundred-odd rhythm presets through the library's own drum
synthesis, bar-locked to the transport, at whatever tempo the menu bar says.
"""

from collections.abc import Mapping
import importlib
import math
import threading

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import DrumSound, Pattern

from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.transport import TransportFrame

from ._dsp import FloatBlock, block, empty_outputs, port


# The package exports a function called ``play`` that shadows the module of
# the same name, so the module has to be fetched by its full name.
_pytheory_play = importlib.import_module("pytheory.play")

PYTHEORY_RATE = 44_100.0
"""The rate PyTheory renders at, whatever the audio device is doing."""

HIT_SECONDS = 0.5
"""How long PyTheory renders a drum for. Trailing silence is trimmed after."""


# --------------------------------------------------------------------- clock


def _steps_in_block(
    start: float,
    per_sample: float,
    frame_count: int,
    period: float,
    offset: float = 0.0,
) -> list[int]:
    """Sample offsets in this block at which ``start + i*per_sample`` crosses
    ``offset`` modulo ``period``. The arithmetic every clocked thing shares."""
    if per_sample <= 0.0 or period <= 0.0 or frame_count <= 0:
        return []
    end = start + frame_count * per_sample
    first = math.ceil((start - offset) / period - 1e-9)
    hits: list[int] = []
    at = offset + first * period
    while at < end - 1e-12:
        index = int(round((at - start) / per_sample))
        if 0 <= index < frame_count:
            if not hits or hits[-1] != index:
                hits.append(index)
        at += period
    return hits


class ClockParameters(BaseModel):
    """What the clock does when there is no transport to follow."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rate_hz: float = Field(default=2.0, gt=0.0, le=50.0)
    """Beats per second when running free. Two is 120 BPM."""

    beats_per_bar: int = Field(default=4, ge=1, le=32)
    """Only used when running free; the transport's signature wins otherwise."""

    trigger_ms: float = Field(default=5.0, ge=1.0, le=50.0)


CLOCK_OUTPUTS = ("beat", "bar", "phase", "run", "eighth", "sixteenth")

CLOCK_MANIFEST = ModuleManifest(
    id="clock",
    name="Clock",
    category="Musical Brains",
    description=(
        "The rack's clock, as signals. A trigger every beat and every bar, "
        "the bar as a ramp, and a gate while it runs -- so anything with a "
        "clock input can be patched to the tempo in the menu bar."
    ),
    ports=(
        port("beat", "Beat", PortDirection.OUTPUT, SignalType.GATE, "A trigger on every beat."),
        port("eighth", "1/8", PortDirection.OUTPUT, SignalType.GATE, "A trigger every eighth note."),
        port("sixteenth", "1/16", PortDirection.OUTPUT, SignalType.GATE, "A trigger every sixteenth."),
        port("bar", "Bar", PortDirection.OUTPUT, SignalType.GATE, "A trigger on the downbeat."),
        port("phase", "Phase", PortDirection.OUTPUT, SignalType.CV, "Where the bar is, zero to one."),
        port("run", "Run", PortDirection.OUTPUT, SignalType.GATE, "High while the clock is running."),
    ),
)


class Clock:
    """The transport, made patchable."""

    manifest = CLOCK_MANIFEST
    uses_transport = True

    def __init__(self, parameters: ClockParameters | None = None) -> None:
        self.parameters = parameters or ClockParameters()
        self._free_quarters = 0.0
        self._pending: dict[str, int] = {name: 0 for name in ("beat", "bar", "eighth", "sixteenth")}

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

    def _position(
        self, transport: TransportFrame | None, frame_count: int, sample_rate: float
    ) -> tuple[float, float, float, bool]:
        """Quarter-note position at block start, quarters per sample, quarters
        per bar, and whether the clock is running."""
        if transport is not None:
            per_sample = transport.quarters_per_second / sample_rate
            return (
                transport.quarters,
                per_sample if transport.running else 0.0,
                transport.quarters_per_bar,
                transport.running,
            )
        per_sample = self.parameters.rate_hz / sample_rate
        start = self._free_quarters
        self._free_quarters += frame_count * per_sample
        return start, per_sample, float(self.parameters.beats_per_bar), True

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
            return empty_outputs(CLOCK_OUTPUTS)
        inputs = inputs or {}
        transport = inputs.get("transport")
        if not isinstance(transport, TransportFrame):
            transport = None

        start, per_sample, per_bar, running = self._position(
            transport, frame_count, sample_rate
        )
        pulse = max(1, int(self.parameters.trigger_ms * sample_rate / 1_000.0))
        outputs = {
            name: np.zeros(frame_count, dtype=np.float32) for name in CLOCK_OUTPUTS
        }
        for name, period in (
            ("beat", 1.0),
            ("eighth", 0.5),
            ("sixteenth", 0.25),
            ("bar", per_bar),
        ):
            lane = outputs[name]
            # A trigger that began in the previous block is still high.
            carried = self._pending[name]
            if carried > 0:
                lane[: min(carried, frame_count)] = 1.0
                self._pending[name] = max(0, carried - frame_count)
            for index in _steps_in_block(start, per_sample, frame_count, period):
                end = index + pulse
                lane[index : min(end, frame_count)] = 1.0
                if end > frame_count:
                    self._pending[name] = max(self._pending[name], end - frame_count)
        positions = start + np.arange(frame_count) * per_sample
        outputs["phase"] = np.asarray(
            (positions / per_bar) % 1.0 if per_bar > 0 else positions * 0.0,
            dtype=np.float32,
        )
        outputs["run"].fill(1.0 if running else 0.0)
        return outputs


# --------------------------------------------------------------------- beats


PATTERN_NAMES: tuple[str, ...] = tuple(Pattern.list_presets())
DEFAULT_PATTERN = "funk" if "funk" in PATTERN_NAMES else PATTERN_NAMES[0]

SOUND_BY_VALUE = {member.value: member for member in DrumSound}


def render_hit(sound: DrumSound) -> NDArray[np.float32]:
    """Ask PyTheory for one drum, trimmed of the silence after it."""
    rendered = _pytheory_play._render_drum_hit(
        sound.value, int(PYTHEORY_RATE * HIT_SECONDS)
    )
    samples = np.asarray(rendered, dtype=np.float32)
    if not samples.size:
        return samples
    loud = np.flatnonzero(np.abs(samples) > 1e-4)
    if loud.size:
        samples = samples[: int(loud[-1]) + 1]
    peak = float(np.max(np.abs(samples)))
    return samples / peak if peak > 0.0 else samples


def _resample(samples: NDArray[np.float32], ratio: float) -> NDArray[np.float32]:
    """Play a 44.1k render at another rate, once, on the control thread."""
    if samples.size < 2 or abs(ratio - 1.0) < 1e-9:
        return samples
    positions = np.arange(0.0, samples.size - 1, ratio)
    lower = positions.astype(np.int64)
    fraction = positions - lower
    return np.asarray(
        samples[lower] * (1.0 - fraction) + samples[lower + 1] * fraction,
        dtype=np.float32,
    )


class PyTheoryBeatsParameters(BaseModel):
    """Which pattern, how loud, how swung, and what to do without a clock."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    pattern: str = DEFAULT_PATTERN
    level: float = Field(default=0.6, ge=0.0, le=1.0)
    swing: float = Field(default=0.0, ge=0.0, le=1.0)
    """How far the off-beat eighths lean toward the triplet. Zero is straight."""

    follow_clock: bool = True
    """Lock to the transport's bars. Off, the pattern runs from its own rate."""

    rate_hz: float = Field(default=2.0, gt=0.0, le=50.0)
    """Beats per second when running free, or when there is no clock at all."""

    @model_validator(mode="after")
    def known(self) -> "PyTheoryBeatsParameters":
        if self.pattern not in PATTERN_NAMES:
            object.__setattr__(self, "pattern", DEFAULT_PATTERN)
        return self


BEATS_OUTPUTS = ("audio", "trigger", "accent", "downbeat")

PYTHEORY_BEATS_MANIFEST = ModuleManifest(
    id="pytheory_beats",
    name="PyTheory Beats",
    category="Musical Brains",
    description=(
        "One of PyTheory's rhythm presets -- funk, teental, bossa nova, trap -- "
        "played through the library's own drum synthesis and locked to the "
        "rack's clock, so beat one is beat one."
    ),
    ports=(
        port("reset", "Reset", PortDirection.INPUT, SignalType.GATE, "Back to the top of the pattern (when running free)."),
        port("audio", "Out", PortDirection.OUTPUT, SignalType.AUDIO, "The drums."),
        port("trigger", "Trig", PortDirection.OUTPUT, SignalType.GATE, "A trigger on every hit."),
        port("accent", "Accent", PortDirection.OUTPUT, SignalType.CV, "The last hit's velocity, held."),
        port("downbeat", "Down", PortDirection.OUTPUT, SignalType.GATE, "A trigger when the pattern starts over."),
    ),
)

TRIGGER_SAMPLES = 240
MAX_VOICES = 24


class PyTheoryBeats:
    """Play a PyTheory drum pattern in time with the rack."""

    manifest = PYTHEORY_BEATS_MANIFEST
    uses_transport = True
    strip_name = "DRUM"

    def __init__(self, parameters: PyTheoryBeatsParameters | None = None) -> None:
        self.parameters = parameters or PyTheoryBeatsParameters()
        self._sample_rate = 48_000.0
        self._sounds: dict[DrumSound, NDArray[np.float32]] = {}
        self._rendered_for: tuple[str, float] | None = None
        self._hits: list[tuple[float, DrumSound, float]] = []
        self._length = 4.0
        self._voices: list[tuple[NDArray[np.float32], int, float]] = []
        self._free_quarters = 0.0
        self._last_quarters: float | None = None
        self._accent = 0.0
        self._reset_high = False
        self._pending_trigger = 0
        self._pending_downbeat = 0
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._rendered_for == (self.parameters.pattern, self._sample_rate)

    @property
    def label(self) -> str:
        return f"{self.parameters.pattern.upper()}  ·  {len(self._hits)} HITS  ·  {self._length:g} BEATS"

    def choices_for(self, field: str) -> tuple[str, ...]:
        return PATTERN_NAMES if field == "pattern" else ()

    def refresh(self) -> None:
        """Read the pattern and render its drums. Control thread only."""
        name = self.parameters.pattern
        pattern = Pattern.preset(name)
        ratio = PYTHEORY_RATE / self._sample_rate
        needed = {hit.sound for hit in pattern.hits}
        sounds = {
            sound: _resample(render_hit(sound), ratio) for sound in sorted(needed, key=lambda s: s.value)
        }
        hits = sorted(
            (
                (float(hit.position), hit.sound, float(hit.velocity) / 127.0)
                for hit in pattern.hits
            ),
            key=lambda hit: (hit[0], hit[1].value),
        )
        with self._lock:
            self._sounds = sounds
            self._hits = hits
            self._length = float(pattern.beats) if pattern.beats > 0 else 4.0
            self._rendered_for = (name, self._sample_rate)

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._sample_rate = float(sample_rate)
        if not self.ready:
            self.refresh()

    def _swung(self, position: float) -> float:
        """Off-beat eighths lean late by up to a sixth of a beat."""
        swing = self.parameters.swing
        if swing <= 0.0:
            return position
        within = position % 1.0
        if abs(within - 0.5) < 1e-6:
            return position + swing / 6.0
        return position

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
            return empty_outputs(BEATS_OUTPUTS)
        if self._sample_rate != float(sample_rate):
            self._sample_rate = float(sample_rate)
        inputs = inputs or {}
        transport = inputs.get("transport")
        if not isinstance(transport, TransportFrame):
            transport = None

        with self._lock:
            hits = self._hits
            sounds = self._sounds
            length = self._length

        # Where in the pattern this block begins, and how fast it moves.
        follow = self.parameters.follow_clock and transport is not None
        if follow:
            start = transport.quarters
            per_sample = (
                transport.quarters_per_second / sample_rate if transport.running else 0.0
            )
        else:
            reset = np.asarray(block("reset", inputs, frame_count), dtype=np.float64)
            high = reset > 0.0
            if bool(high.any()) and not self._reset_high:
                self._free_quarters = 0.0
            self._reset_high = bool(high[-1])
            start = self._free_quarters
            per_sample = self.parameters.rate_hz / sample_rate
            self._free_quarters += frame_count * per_sample

        audio = np.zeros(frame_count, dtype=np.float64)
        trigger = np.zeros(frame_count, dtype=np.float32)
        downbeat = np.zeros(frame_count, dtype=np.float32)
        accent = np.full(frame_count, self._accent, dtype=np.float32)

        # Triggers still high from the previous block.
        if self._pending_trigger:
            trigger[: min(self._pending_trigger, frame_count)] = 1.0
            self._pending_trigger = max(0, self._pending_trigger - frame_count)
        if self._pending_downbeat:
            downbeat[: min(self._pending_downbeat, frame_count)] = 1.0
            self._pending_downbeat = max(0, self._pending_downbeat - frame_count)

        if per_sample > 0.0 and hits and length > 0.0:
            for position, sound, velocity in hits:
                wave = sounds.get(sound)
                if wave is None or wave.size == 0:
                    continue
                for index in _steps_in_block(
                    start, per_sample, frame_count, length, self._swung(position)
                ):
                    if len(self._voices) >= MAX_VOICES:
                        self._voices.pop(0)
                    self._voices.append((wave, index, velocity))
                    trigger[index : index + TRIGGER_SAMPLES] = 1.0
                    if index + TRIGGER_SAMPLES > frame_count:
                        self._pending_trigger = index + TRIGGER_SAMPLES - frame_count
                    self._accent = velocity
                    accent[index:] = velocity
            for index in _steps_in_block(start, per_sample, frame_count, length):
                downbeat[index : index + TRIGGER_SAMPLES] = 1.0
                if index + TRIGGER_SAMPLES > frame_count:
                    self._pending_downbeat = index + TRIGGER_SAMPLES - frame_count

        # Mix every sounding drum. A voice is what is left of its wave and the
        # sample of this block its next sample lands on -- zero for one that
        # was already sounding, later for one that starts here.
        surviving = []
        for wave, offset, velocity in self._voices:
            take = min(wave.size, frame_count - offset)
            if take > 0:
                audio[offset : offset + take] += wave[:take] * velocity
            if wave.size > take:
                surviving.append((wave[take:], 0, velocity))
        self._voices = surviving

        level = self.parameters.level
        return {
            "audio": np.asarray(np.tanh(audio * level * 1.4), dtype=np.float32),
            "trigger": trigger,
            "accent": accent,
            "downbeat": downbeat,
        }


__all__ = [
    "CLOCK_MANIFEST",
    "Clock",
    "ClockParameters",
    "DEFAULT_PATTERN",
    "PATTERN_NAMES",
    "PYTHEORY_BEATS_MANIFEST",
    "PyTheoryBeats",
    "PyTheoryBeatsParameters",
    "render_hit",
]
