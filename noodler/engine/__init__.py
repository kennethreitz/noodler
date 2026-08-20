"""Real-time system audio output for a prepared Noodler patch."""

from collections.abc import Callable
from threading import Event, Lock, Thread
from typing import Any

import numpy as np
import sounddevice as sd

from noodler.patch import PatchGraph
from noodler.transport import Transport

from .adaptive import (
    DEFAULT_INITIAL_BLOCKS,
    DEFAULT_MAX_BLOCKS,
    DEFAULT_STABLE_SECONDS,
    AdaptiveOutputBuffer,
)


SCOPE_POINTS = 480
"""Samples kept for display: a couple of hundred milliseconds of the output."""

LIFECYCLE_TIMEOUT = 2.0
"""Seconds to wait for the device lock before shutting down regardless."""

PREFILL_TIMEOUT = 3.0
"""Seconds a graph may take to prepare the first adaptive buffer."""

SCOPE_STRIDE = 8
"""Only every eighth sample is kept. A trace is a shape, not a measurement."""


class SystemAudioEngine:
    """Render a patch through the default Core Audio output device."""

    def __init__(
        self,
        patch: PatchGraph,
        *,
        sample_rate: float | None = None,
        block_size: int = 256,
        channels: int = 2,
        device: int | str | None = None,
        master_gain: float = 0.8,
        stream_factory: Callable[..., Any] | None = None,
        transport: Transport | None = None,
        initial_buffer_blocks: int = DEFAULT_INITIAL_BLOCKS,
        max_buffer_blocks: int = DEFAULT_MAX_BLOCKS,
        stable_buffer_seconds: float = DEFAULT_STABLE_SECONDS,
    ) -> None:
        if sample_rate is not None and sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")
        if initial_buffer_blocks <= 0:
            raise ValueError("initial_buffer_blocks must be positive")
        if max_buffer_blocks < initial_buffer_blocks:
            raise ValueError(
                "max_buffer_blocks must be at least initial_buffer_blocks"
            )
        if stable_buffer_seconds < 0.0:
            raise ValueError("stable_buffer_seconds must not be negative")

        self.patch = patch
        self.transport = transport
        """The clock this engine keeps time for, advanced per block on the sample
        clock so a beat lands on the sample it should. None means the engine
        keeps no time and clocked modules run free."""
        self.requested_sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.device = device
        self._master_gain = 0.0
        self.master_gain = master_gain
        self._stream_factory = stream_factory or sd.OutputStream
        self.initial_buffer_blocks = int(initial_buffer_blocks)
        self.max_buffer_blocks = int(max_buffer_blocks)
        self.stable_buffer_seconds = float(stable_buffer_seconds)
        self._stream: Any | None = None
        self._active_sample_rate: float | None = None
        self._output_buffer: AdaptiveOutputBuffer | None = None
        self._render_stop: Event | None = None
        self._render_thread: Thread | None = None
        self._lifecycle_lock = Lock()
        self.last_status: str | None = None
        self.last_error: str | None = None
        self.last_peak = 0.0
        self._scope = np.zeros(SCOPE_POINTS, dtype=np.float32)
        self._scope_write = 0

    @property
    def master_gain(self) -> float:
        return self._master_gain

    @master_gain.setter
    def master_gain(self, value: float) -> None:
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ValueError("master_gain must be between 0 and 1")
        self._master_gain = value

    @property
    def sample_rate(self) -> float | None:
        return self._active_sample_rate or self.requested_sample_rate

    @property
    def is_running(self) -> bool:
        return self._stream is not None and bool(
            getattr(self._stream, "active", False)
        )

    @property
    def output_device_name(self) -> str:
        device = sd.query_devices(self.device, kind="output")
        return str(device["name"])

    @property
    def buffered_frames(self) -> int:
        buffer = self._output_buffer
        return buffer.available_frames if buffer is not None else 0

    @property
    def target_buffer_frames(self) -> int:
        buffer = self._output_buffer
        return buffer.target_frames if buffer is not None else 0

    @property
    def target_buffer_ms(self) -> float:
        buffer = self._output_buffer
        return buffer.target_latency_ms if buffer is not None else 0.0

    @property
    def underrun_count(self) -> int:
        buffer = self._output_buffer
        return buffer.underruns if buffer is not None else 0

    def start(self) -> None:
        """Open and start the output stream; repeated starts are harmless."""
        with self._lifecycle_lock:
            if self.is_running:
                return
            self.last_error = None
            stream = self._stream_factory(
                samplerate=self.requested_sample_rate,
                blocksize=self.block_size,
                device=self.device,
                channels=self.channels,
                dtype="float32",
                latency="low",
                callback=self._audio_callback,
            )
            self._stream = stream
            self._active_sample_rate = float(stream.samplerate)
            try:
                self.patch.prepare(self._active_sample_rate, self.block_size)
                output_buffer = AdaptiveOutputBuffer(
                    block_size=self.block_size,
                    sample_rate=self._active_sample_rate,
                    initial_blocks=self.initial_buffer_blocks,
                    max_blocks=self.max_buffer_blocks,
                    stable_seconds=self.stable_buffer_seconds,
                )
                render_stop = Event()
                render_thread = Thread(
                    target=self._render_ahead,
                    args=(output_buffer, render_stop, self._active_sample_rate),
                    name="noodler-audio-render",
                    daemon=True,
                )
                self._output_buffer = output_buffer
                self._render_stop = render_stop
                self._render_thread = render_thread
                render_thread.start()
                if not output_buffer.wait_until_target(PREFILL_TIMEOUT, render_stop):
                    detail = self.last_error or "audio render worker did not fill the buffer"
                    raise RuntimeError(detail)
                stream.start()
            except Exception:
                self._stop_render_worker()
                stream.close()
                self._stream = None
                self._active_sample_rate = None
                raise

    def stop(self) -> None:
        """Stop and close the current output stream.

        The stream is taken under the lock, but stopped and closed outside it.
        Closing waits for the callback thread to finish, and holding a lock
        across that wait is how quitting mid-edit ended up hanging on a
        keyboard interrupt instead of shutting down.
        """
        acquired = self._lifecycle_lock.acquire(timeout=LIFECYCLE_TIMEOUT)
        try:
            stream = self._stream
            self._stream = None
            render_stop = self._render_stop
            output_buffer = self._output_buffer
            render_thread = self._render_thread
            self._render_stop = None
            self._output_buffer = None
            self._render_thread = None
        finally:
            if acquired:
                self._lifecycle_lock.release()
        if render_stop is not None:
            render_stop.set()
        if output_buffer is not None:
            output_buffer.wake()
        if stream is None:
            self._active_sample_rate = None
            if render_thread is not None:
                render_thread.join(timeout=LIFECYCLE_TIMEOUT)
            return
        try:
            stream.stop()
        finally:
            stream.close()
            if render_thread is not None:
                render_thread.join(timeout=LIFECYCLE_TIMEOUT)
            self._active_sample_rate = None
            self.last_peak = 0.0

    def _stop_render_worker(self) -> None:
        """Stop a worker created by a start that did not reach the device."""
        render_stop = self._render_stop
        output_buffer = self._output_buffer
        render_thread = self._render_thread
        self._render_stop = None
        self._output_buffer = None
        self._render_thread = None
        if render_stop is not None:
            render_stop.set()
        if output_buffer is not None:
            output_buffer.wake()
        if render_thread is not None:
            render_thread.join(timeout=LIFECYCLE_TIMEOUT)

    close = stop

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frame_count: int,
        _time_info: Any,
        status: Any,
    ) -> None:
        if status:
            self.last_status = str(status)
        try:
            output_buffer = self._output_buffer
            if output_buffer is not None:
                buffer_underflow = output_buffer.read_into(outdata)
                if self._status_has_output_underflow(status) and not buffer_underflow:
                    output_buffer.report_device_underflow()
                render_stop = self._render_stop
                if (
                    buffer_underflow
                    and render_stop is not None
                    and render_stop.is_set()
                    and self.last_error
                ):
                    raise RuntimeError(self.last_error)
            else:
                sample_rate = self._active_sample_rate
                if sample_rate is None:
                    raise RuntimeError("audio callback ran without an active sample rate")
                stereo = self._render_block(frame_count, sample_rate)
                self._copy_to_device(stereo, outdata)
            self.last_peak = float(np.max(np.abs(outdata), initial=0.0))
            self._capture_scope(outdata)
        except Exception as exc:
            outdata.fill(0.0)
            self.last_peak = 0.0
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise sd.CallbackAbort from exc

    def _render_ahead(
        self,
        output_buffer: AdaptiveOutputBuffer,
        stop: Event,
        sample_rate: float,
    ) -> None:
        """Keep prepared audio ahead of the device on a non-callback thread."""
        try:
            while not stop.is_set():
                if not output_buffer.wait_for_render_need():
                    continue
                if stop.is_set():
                    break
                stereo = self._render_block(self.block_size, sample_rate)
                output_buffer.write(stereo)
        except Exception as exc:  # the callback will drain, then report silence
            self.last_error = f"{type(exc).__name__}: {exc}"
            stop.set()
            output_buffer.wake()

    def _render_block(self, frame_count: int, sample_rate: float) -> np.ndarray:
        transport = self.transport
        if transport is not None:
            self.patch.transport = transport.tick(frame_count, sample_rate)
        stereo = self.patch.render_stereo(frame_count, sample_rate)
        stereo *= self.master_gain
        np.nan_to_num(stereo, copy=False, nan=0.0, posinf=1.0, neginf=-1.0)
        np.clip(stereo, -1.0, 1.0, out=stereo)
        return stereo

    @staticmethod
    def _copy_to_device(stereo: np.ndarray, outdata: np.ndarray) -> None:
        if outdata.shape[1] == 1:
            np.add(stereo[:, 0], stereo[:, 1], out=outdata[:, 0])
            outdata[:, 0] *= 0.5
            return
        outdata[:, :2] = stereo
        for channel in range(2, outdata.shape[1]):
            np.add(stereo[:, 0], stereo[:, 1], out=outdata[:, channel])
            outdata[:, channel] *= 0.5

    @staticmethod
    def _status_has_output_underflow(status: Any) -> bool:
        if not status:
            return False
        flag = getattr(status, "output_underflow", False)
        return bool(flag) or "underflow" in str(status).lower()

    def _capture_scope(self, stereo: np.ndarray) -> None:
        """Keep a decimated trace of what was just played.

        The callback writes into a fixed ring and never allocates; the reader is
        the interface, one frame behind at worst, which is all a trace needs.
        """
        trace = np.mean(stereo, axis=1)[::SCOPE_STRIDE].astype(np.float32)
        taken = trace.size
        if not taken:
            return
        if taken >= SCOPE_POINTS:
            self._scope[:] = trace[-SCOPE_POINTS:]
            self._scope_write = 0
            return
        start = self._scope_write
        end = start + taken
        if end <= SCOPE_POINTS:
            self._scope[start:end] = trace
        else:
            split = SCOPE_POINTS - start
            self._scope[start:] = trace[:split]
            self._scope[: end - SCOPE_POINTS] = trace[split:]
        self._scope_write = end % SCOPE_POINTS

    def scope_trace(self) -> np.ndarray:
        """The recent output, oldest sample first."""
        return np.roll(self._scope, -self._scope_write)

    def __enter__(self) -> "SystemAudioEngine":
        self.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.stop()


__all__ = ["AdaptiveOutputBuffer", "SystemAudioEngine"]
