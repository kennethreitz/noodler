"""Real-time system audio output for a prepared Noodler patch."""

from collections.abc import Callable
from threading import Lock
from typing import Any

import numpy as np
import sounddevice as sd

from noodler.patch import PatchGraph


SCOPE_POINTS = 480
"""Samples kept for display: a couple of hundred milliseconds of the output."""

LIFECYCLE_TIMEOUT = 2.0
"""Seconds to wait for the device lock before shutting down regardless."""

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
    ) -> None:
        if sample_rate is not None and sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")

        self.patch = patch
        self.requested_sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.device = device
        self._master_gain = 0.0
        self.master_gain = master_gain
        self._stream_factory = stream_factory or sd.OutputStream
        self._stream: Any | None = None
        self._active_sample_rate: float | None = None
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
                stream.start()
            except Exception:
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
            self._active_sample_rate = None
        finally:
            if acquired:
                self._lifecycle_lock.release()
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            stream.close()
            self.last_peak = 0.0

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
            sample_rate = self._active_sample_rate
            if sample_rate is None:
                raise RuntimeError("audio callback ran without an active sample rate")
            stereo = self.patch.render_stereo(frame_count, sample_rate)
            stereo *= self.master_gain
            np.nan_to_num(stereo, copy=False, nan=0.0, posinf=1.0, neginf=-1.0)
            np.clip(stereo, -1.0, 1.0, out=stereo)
            self.last_peak = float(np.max(np.abs(stereo), initial=0.0))
            self._capture_scope(stereo)
            if outdata.shape[1] == 1:
                outdata[:, 0] = np.mean(stereo, axis=1)
            else:
                outdata[:, :2] = stereo
                if outdata.shape[1] > 2:
                    outdata[:, 2:] = np.mean(stereo, axis=1)[:, np.newaxis]
        except Exception as exc:
            outdata.fill(0.0)
            self.last_peak = 0.0
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise sd.CallbackAbort from exc

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


__all__ = ["SystemAudioEngine"]
