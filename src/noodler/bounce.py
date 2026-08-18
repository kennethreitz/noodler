"""Render a patch to a file, at the transport's tempo, from bar one.

A bounce is an offline performance: a fresh copy of the patch, a fresh clock,
so many bars at the tempo the document was saved at, and then a tail with the
clock stopped for the rooms to ring out. It runs on whatever thread asks for
it, reports each bar as it finishes, and writes a stereo 16-bit WAV, which is
the file everything can open.
"""

from collections.abc import Callable
from pathlib import Path
import struct
import wave

import numpy as np

from .preset import PatchPreset
from .transport import Transport


DEFAULT_SAMPLE_RATE = 48_000.0
DEFAULT_BLOCK = 256


def bounce(
    preset: PatchPreset,
    *,
    bars: int = 8,
    tail_seconds: float = 3.0,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    block_size: int = DEFAULT_BLOCK,
    progress: Callable[[int, int], None] | None = None,
) -> np.ndarray:
    """Play a document for some bars and a tail, and return the stereo audio.

    The patch is built fresh from the document -- never the one that is
    playing, whose state would be disturbed -- and every module that renders
    on a worker is given time to finish before the clock starts.
    """
    from .app import build_runtime_from_preset  # the graph builder lives with the app

    if bars <= 0:
        raise ValueError("bars must be positive")
    runtime = build_runtime_from_preset(preset)
    patch = runtime.patch
    patch.prepare(sample_rate, block_size)
    for module in patch.modules.values():
        worker = getattr(module, "_worker", None)
        if worker is not None:
            worker.join(timeout=60.0)

    transport = Transport(
        bpm=preset.transport.bpm,
        beats_per_bar=preset.transport.beats_per_bar,
        beat_unit=preset.transport.beat_unit,
        running=True,
    )
    bar_seconds = transport.quarters_per_bar * 60.0 / transport.bpm
    total_blocks = int(round(bars * bar_seconds * sample_rate / block_size))
    tail_blocks = int(round(tail_seconds * sample_rate / block_size))
    blocks: list[np.ndarray] = []
    reported = -1
    for index in range(total_blocks):
        patch.transport = transport.tick(block_size, sample_rate)
        blocks.append(patch.render_stereo(block_size, sample_rate))
        bar = transport.bars
        if progress is not None and bar != reported:
            reported = bar
            progress(min(bar, bars), bars)
    transport.running = False
    for _ in range(tail_blocks):
        patch.transport = transport.tick(block_size, sample_rate)
        blocks.append(patch.render_stereo(block_size, sample_rate))
    if progress is not None:
        progress(bars, bars)
    if not blocks:
        return np.zeros((0, 2), dtype=np.float32)
    audio = np.concatenate(blocks).astype(np.float32)
    audio *= float(preset.system_output.master_gain)
    return np.clip(np.nan_to_num(audio), -1.0, 1.0)


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: float = DEFAULT_SAMPLE_RATE) -> Path:
    """Write stereo float audio as a 16-bit PCM WAV."""
    destination = Path(path)
    if destination.suffix.lower() != ".wav":
        destination = destination.with_suffix(".wav")
    samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim == 1:
        samples = np.stack([samples, samples], axis=1)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(int(round(sample_rate)))
        handle.writeframes(pcm.tobytes())
    return destination


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit WAV back, for tests and for anyone who wants to check."""
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    count = len(frames) // 2
    values = np.array(struct.unpack(f"<{count}h", frames), dtype=np.float32) / 32767.0
    return values.reshape(-1, channels), rate


__all__ = ["bounce", "read_wav", "write_wav"]
