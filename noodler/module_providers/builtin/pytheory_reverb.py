"""PyTheory's reverbs, played in real time.

PyTheory has two kinds of room. One is an algorithm — Schroeder's, four
parallel feedback combs into two series allpasses, the 1962 topology — and the
library already runs it a block at a time. The other is a set of impulse
responses it synthesises: a hall, a plate, a spring, a cathedral, a cave, a
canyon, a parking garage, and the Taj Mahal, each rendered as a decaying,
shaped noise tail. Offline it convolves with them; a rack cannot wait for that,
so here the impulse response is cut into block-sized partitions once, on the
control thread, and every audio block multiplies its spectrum by all of them
at once. A twelve-second room costs about a fifth of a millisecond a block.

Both are stereo the way PyTheory makes them stereo: two comb sets tuned a
little apart, or two impulse responses from two seeds.
"""

from collections.abc import Mapping
import importlib

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


# The package exports functions named ``play`` and ``live`` that shadow the
# modules of the same names, so the modules are fetched by their full names.
_play = importlib.import_module("pytheory.play")
_live = importlib.import_module("pytheory.live")

PYTHEORY_RATE = 44_100.0
SCHROEDER = "schroeder"
IR_SPACES: tuple[str, ...] = tuple(sorted(_play._IR_DURATIONS))
SPACES: tuple[str, ...] = (SCHROEDER, *IR_SPACES)
"""The rooms on offer: the algorithm first, then every impulse response."""

MAX_IR_SECONDS = 12.0
DEFAULT_SPACE = "hall" if "hall" in IR_SPACES else SCHROEDER

REVERB_OUTPUTS = ("left", "right", "wet_left", "wet_right")

COMB_DELAYS_LEFT = (0.0297, 0.0371, 0.0411, 0.0437)
COMB_DELAYS_RIGHT = (0.0313, 0.0389, 0.0427, 0.0453)
"""PyTheory's own comb tunings for its stereo Schroeder: the right side a
little longer, which is what puts the tail somewhere rather than dead centre."""


class _RightSchroeder(_live._StreamReverb):
    COMB_DELAY_SECS = COMB_DELAYS_RIGHT


class _LeftSchroeder(_live._StreamReverb):
    COMB_DELAY_SECS = COMB_DELAYS_LEFT


def render_impulse(space: str, sample_rate: float, seed: int, seconds: float) -> NDArray[np.float32]:
    """Ask PyTheory for a room, at the rate the rack runs at, cut to length."""
    ir = np.asarray(_play._generate_ir(space, int(PYTHEORY_RATE), seed=seed), dtype=np.float32)
    ratio = PYTHEORY_RATE / float(sample_rate)
    if abs(ratio - 1.0) > 1e-9 and ir.size > 1:
        positions = np.arange(0.0, ir.size - 1, ratio)
        lower = positions.astype(np.int64)
        fraction = (positions - lower).astype(np.float32)
        ir = ir[lower] * (1.0 - fraction) + ir[lower + 1] * fraction
    keep = int(min(seconds, MAX_IR_SECONDS) * sample_rate)
    if 0 < keep < ir.size:
        ir = ir[:keep].copy()
        fade = min(keep, int(0.05 * sample_rate))
        if fade > 1:
            ir[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    energy = float(np.sqrt(np.sum(ir.astype(np.float64) ** 2)))
    if energy > 0.0:
        ir = ir / energy
    return np.asarray(ir, dtype=np.float32)


class _Convolver:
    """Uniform partitioned convolution: one FFT in, one out, per block."""

    def __init__(self, impulse: NDArray[np.float32], block_size: int) -> None:
        self.block = int(block_size)
        size = 2 * self.block
        count = max(1, -(-impulse.size // self.block))
        padded = np.zeros(count * self.block, dtype=np.float32)
        padded[: impulse.size] = impulse
        parts = padded.reshape(count, self.block)
        self.spectra = np.fft.rfft(parts, n=size, axis=1).astype(np.complex64)
        self.history = np.zeros_like(self.spectra)
        self.position = 0
        self.tail = np.zeros(self.block, dtype=np.float32)

    def process(self, chunk: NDArray[np.float32]) -> NDArray[np.float32]:
        frame = np.concatenate([self.tail, chunk]).astype(np.float32)
        self.tail = chunk.astype(np.float32)
        spectrum = np.fft.rfft(frame).astype(np.complex64)
        self.history[self.position] = spectrum
        # The newest block meets partition zero, the one before it partition
        # one, and so on round the ring: a roll of the partitions lines them up.
        count = self.spectra.shape[0]
        order = (self.position - np.arange(count)) % count
        combined = (self.history[order] * self.spectra).sum(axis=0)
        self.position = (self.position + 1) % count
        return np.fft.irfft(combined, n=2 * self.block)[self.block :].astype(np.float32)


class PyTheoryReverbParameters(BaseModel):
    """Which room, how much, how long, how wide, how late."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    space: str = DEFAULT_SPACE
    mix: float = Field(default=0.35, ge=0.0, le=1.0)
    decay_seconds: float = Field(default=3.0, ge=0.1, le=MAX_IR_SECONDS)
    """Tail length. Sets the Schroeder's feedback; cuts an impulse to length."""
    width: float = Field(default=0.8, ge=0.0, le=1.0)
    pre_delay_ms: float = Field(default=0.0, ge=0.0, le=250.0)
    level: float = Field(default=1.0, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def known(self) -> "PyTheoryReverbParameters":
        if self.space not in SPACES:
            object.__setattr__(self, "space", DEFAULT_SPACE)
        return self


PYTHEORY_REVERB_MANIFEST = ModuleManifest(
    id="pytheory_reverb",
    name="PyTheory Reverb",
    category="Effects",
    description=(
        "PyTheory's rooms, live: Schroeder's algorithm, or one of the "
        "impulse responses it synthesises -- hall, plate, spring, cathedral, "
        "cave, canyon, parking garage, the Taj Mahal -- convolved in real time."
    ),
    ports=(
        port("audio", "Audio In", PortDirection.INPUT, SignalType.AUDIO, "What goes into the room."),
        port("mix_cv", "Mix CV", PortDirection.INPUT, SignalType.CV, "Added to the mix, plus or minus one."),
        port("left", "Left", PortDirection.OUTPUT, SignalType.AUDIO, "Dry and wet together, left."),
        port("right", "Right", PortDirection.OUTPUT, SignalType.AUDIO, "Dry and wet together, right."),
        port("wet_left", "Wet Left", PortDirection.OUTPUT, SignalType.AUDIO, "The room alone, left."),
        port("wet_right", "Wet Right", PortDirection.OUTPUT, SignalType.AUDIO, "The room alone, right."),
    ),
)


class PyTheoryReverb:
    """Put a signal in one of PyTheory's rooms."""

    manifest = PYTHEORY_REVERB_MANIFEST

    def __init__(self, parameters: PyTheoryReverbParameters | None = None) -> None:
        self.parameters = parameters or PyTheoryReverbParameters()
        self._sample_rate = 48_000.0
        self._block = 256
        self._engine: tuple[object, object] | None = None
        self._built_for: tuple[str, float, float, int] | None = None
        self._pre_delay = np.zeros(1, dtype=np.float32)
        self._pre_delay_index = 0
        self._pending_in = np.zeros(0, dtype=np.float32)
        self._pending_out: list[NDArray[np.float32]] = []

    @property
    def ready(self) -> bool:
        return self._built_for == self._signature()

    @property
    def label(self) -> str:
        space = self.parameters.space.replace("_", " ").upper()
        how = "ALGORITHM" if self.parameters.space == SCHROEDER else "IMPULSE RESPONSE"
        return f"{space}  ·  {how}"

    def choices_for(self, field: str) -> tuple[str, ...]:
        return SPACES if field == "space" else ()

    def _signature(self) -> tuple[str, float, float, int]:
        return (
            self.parameters.space,
            float(self.parameters.decay_seconds),
            self._sample_rate,
            self._block,
        )

    def refresh(self) -> None:
        """Build the room. Control thread only: an impulse takes milliseconds."""
        space = self.parameters.space
        decay = float(self.parameters.decay_seconds)
        if space == SCHROEDER:
            engine = (
                _LeftSchroeder(decay=decay, sample_rate=int(self._sample_rate)),
                _RightSchroeder(decay=decay, sample_rate=int(self._sample_rate)),
            )
        else:
            engine = (
                _Convolver(render_impulse(space, self._sample_rate, 42, decay), self._block),
                _Convolver(render_impulse(space, self._sample_rate, 4242, decay), self._block),
            )
        self._engine = engine
        self._built_for = self._signature()

    def prepare(self, sample_rate: float, block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._sample_rate = float(sample_rate)
        if block_size:
            self._block = int(block_size)
        self._pre_delay = np.zeros(int(0.25 * self._sample_rate) + 1, dtype=np.float32)
        self._pre_delay_index = 0
        self._pending_in = np.zeros(0, dtype=np.float32)
        self._pending_out = []
        if not self.ready:
            self.refresh()

    def _delayed(self, dry: NDArray[np.float32]) -> NDArray[np.float32]:
        """The input, late by the pre-delay, through a ring buffer."""
        delay = int(self.parameters.pre_delay_ms * self._sample_rate / 1_000.0)
        if delay <= 0:
            return dry
        size = self._pre_delay.size
        out = np.empty_like(dry)
        for index, sample in enumerate(dry.tolist()):
            self._pre_delay[self._pre_delay_index] = sample
            out[index] = self._pre_delay[(self._pre_delay_index - delay) % size]
            self._pre_delay_index = (self._pre_delay_index + 1) % size
        return out

    def _wet(self, dry: NDArray[np.float32]) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """Both channels of room for one block, at whatever block size arrives."""
        engine = self._engine
        if engine is None:
            return np.zeros_like(dry), np.zeros_like(dry)
        left_engine, right_engine = engine
        if isinstance(left_engine, _Convolver):
            # The convolver works in its own block size; other sizes go through
            # a queue and come out one block late.
            wanted = dry.size
            self._pending_in = np.concatenate([self._pending_in, dry])
            while self._pending_in.size >= self._block:
                chunk, self._pending_in = self._pending_in[: self._block], self._pending_in[self._block :]
                self._pending_out.append(
                    np.stack([left_engine.process(chunk), right_engine.process(chunk)], axis=1)
                )
            have = sum(part.shape[0] for part in self._pending_out)
            if have < wanted:
                self._pending_out.insert(0, np.zeros((wanted - have, 2), dtype=np.float32))
            joined = np.concatenate(self._pending_out, axis=0)
            out, rest = joined[:wanted], joined[wanted:]
            self._pending_out = [rest] if rest.size else []
            return out[:, 0], out[:, 1]
        return (
            np.asarray(left_engine.process(dry), dtype=np.float32),
            np.asarray(right_engine.process(dry), dtype=np.float32),
        )

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
            return empty_outputs(REVERB_OUTPUTS)
        if self._sample_rate != float(sample_rate) or self._engine is None:
            self.prepare(sample_rate, self._block)
        inputs = inputs or {}
        dry = np.asarray(block("audio", inputs, frame_count), dtype=np.float32)
        mix_cv = np.asarray(block("mix_cv", inputs, frame_count), dtype=np.float32)

        wet_left, wet_right = self._wet(self._delayed(dry))
        # Width: mid stays, sides scale, as PyTheory's own stereo reverb does.
        mid = (wet_left + wet_right) * 0.5
        width = float(self.parameters.width)
        wet_left = (mid + (wet_left - mid) * width) * self.parameters.level
        wet_right = (mid + (wet_right - mid) * width) * self.parameters.level

        mix = np.clip(self.parameters.mix + mix_cv, 0.0, 1.0)
        return {
            "left": np.asarray(dry * (1.0 - mix) + wet_left * mix, dtype=np.float32),
            "right": np.asarray(dry * (1.0 - mix) + wet_right * mix, dtype=np.float32),
            "wet_left": np.asarray(wet_left, dtype=np.float32),
            "wet_right": np.asarray(wet_right, dtype=np.float32),
        }


__all__ = [
    "IR_SPACES",
    "PYTHEORY_REVERB_MANIFEST",
    "PyTheoryReverb",
    "PyTheoryReverbParameters",
    "SCHROEDER",
    "SPACES",
    "render_impulse",
]
