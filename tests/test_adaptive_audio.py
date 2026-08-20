"""The device drains prepared audio while the safety depth tunes itself."""

from threading import current_thread
from typing import Any

import numpy as np
import pytest

from noodler.engine import AdaptiveOutputBuffer, SystemAudioEngine


class FakeOutputStream:
    def __init__(self, **configuration: Any) -> None:
        self.configuration = configuration
        self.samplerate = configuration["samplerate"] or 48_000.0
        self.active = False
        self.closed = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def close(self) -> None:
        self.closed = True


class ConstantPatch:
    def __init__(self, level: float = 0.25) -> None:
        self.level = level
        self.prepared: tuple[float, int] | None = None
        self.render_threads: list[str] = []
        self.transport = None

    def prepare(self, sample_rate: float, block_size: int) -> None:
        self.prepared = (sample_rate, block_size)

    def render_stereo(self, frame_count: int, _sample_rate: float) -> np.ndarray:
        self.render_threads.append(current_thread().name)
        return np.full((frame_count, 2), self.level, dtype=np.float32)


def test_ring_preserves_sample_order_across_its_wrap() -> None:
    buffer = AdaptiveOutputBuffer(
        block_size=2,
        sample_rate=100.0,
        initial_blocks=2,
        max_blocks=3,
    )
    first = np.arange(12, dtype=np.float32).reshape(6, 2)
    assert buffer.write(first) == 6
    heard = np.empty((4, 2), dtype=np.float32)
    assert buffer.read_into(heard) is False
    np.testing.assert_array_equal(heard, first[:4])

    second = np.arange(12, 20, dtype=np.float32).reshape(4, 2)
    assert buffer.write(second) == 4
    wrapped = np.empty((6, 2), dtype=np.float32)
    assert buffer.read_into(wrapped) is False
    np.testing.assert_array_equal(wrapped, np.concatenate((first[4:], second)))


def test_underrun_grows_quickly_and_stability_shrinks_one_block() -> None:
    buffer = AdaptiveOutputBuffer(
        block_size=4,
        sample_rate=100.0,
        initial_blocks=2,
        max_blocks=8,
        stable_reads_before_shrink=2,
    )
    assert buffer.target_frames == 8

    silence = np.empty((4, 2), dtype=np.float32)
    assert buffer.read_into(silence) is True
    assert np.all(silence == 0.0)
    assert buffer.underruns == 1
    assert buffer.target_frames == 16

    buffer.write(np.ones((16, 2), dtype=np.float32))
    assert buffer.read_into(np.empty((4, 2), dtype=np.float32)) is False
    assert buffer.read_into(np.empty((4, 2), dtype=np.float32)) is False
    assert buffer.target_frames == 12

    buffer.report_device_underflow()
    assert buffer.underruns == 2
    assert buffer.target_frames == 24


def test_engine_prefills_off_callback_and_drains_prepared_samples() -> None:
    patch = ConstantPatch()
    engine = SystemAudioEngine(
        patch,  # type: ignore[arg-type] - a deliberately tiny PatchGraph double
        master_gain=0.8,
        stream_factory=FakeOutputStream,
    )
    engine.start()
    assert patch.prepared == (48_000.0, 256)
    assert engine.target_buffer_frames == 3 * 256
    assert engine.buffered_frames == 3 * 256
    assert patch.render_threads
    assert set(patch.render_threads) == {"noodler-audio-render"}

    output = np.empty((256, 2), dtype=np.float32)
    engine._stream.configuration["callback"](output, 256, None, None)
    np.testing.assert_allclose(output, 0.2)
    assert "MainThread" not in patch.render_threads
    engine.stop()


def test_device_underflow_flag_increases_the_safety_target() -> None:
    class Underflow:
        output_underflow = True

        def __bool__(self) -> bool:
            return True

        def __str__(self) -> str:
            return "output underflow"

    engine = SystemAudioEngine(
        ConstantPatch(),  # type: ignore[arg-type]
        stream_factory=FakeOutputStream,
    )
    engine.start()
    before = engine.target_buffer_frames
    output = np.empty((64, 2), dtype=np.float32)
    engine._stream.configuration["callback"](output, 64, None, Underflow())

    assert engine.underrun_count == 1
    assert engine.target_buffer_frames == before * 2
    assert engine.last_status == "output underflow"
    engine.stop()


def test_render_worker_failure_closes_the_stream_instead_of_starting_silent() -> None:
    class BrokenPatch(ConstantPatch):
        def render_stereo(self, frame_count: int, sample_rate: float) -> np.ndarray:
            raise ValueError("broken graph")

    streams: list[FakeOutputStream] = []

    def factory(**configuration: Any) -> FakeOutputStream:
        stream = FakeOutputStream(**configuration)
        streams.append(stream)
        return stream

    engine = SystemAudioEngine(
        BrokenPatch(),  # type: ignore[arg-type]
        stream_factory=factory,
    )
    with pytest.raises(RuntimeError, match="broken graph"):
        engine.start()
    assert streams[0].closed is True
    assert engine.is_running is False
