"""A small adaptive reservoir between patch rendering and Core Audio."""

from __future__ import annotations

from threading import Condition, Event, Lock
import time

import numpy as np
from numpy.typing import NDArray


DEFAULT_INITIAL_BLOCKS = 3
"""Start with enough audio to absorb an ordinary scheduler hiccup."""

DEFAULT_MAX_BLOCKS = 32
"""Bound automatic latency growth even when the graph cannot keep up."""

DEFAULT_STABLE_SECONDS = 20.0
"""A buffer earns one lower-latency step after this long without an underrun."""


class AdaptiveOutputBuffer:
    """A stereo sample ring whose target depth responds to underruns.

    The storage capacity is fixed at construction, so recovery never allocates
    on the audio callback.  An underrun grows the desired fill quickly; a long
    run of complete reads shrinks it one render block at a time.
    """

    def __init__(
        self,
        *,
        block_size: int,
        sample_rate: float,
        channels: int = 2,
        initial_blocks: int = DEFAULT_INITIAL_BLOCKS,
        max_blocks: int = DEFAULT_MAX_BLOCKS,
        stable_seconds: float = DEFAULT_STABLE_SECONDS,
        stable_reads_before_shrink: int | None = None,
    ) -> None:
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")
        if initial_blocks <= 0:
            raise ValueError("initial_blocks must be positive")
        if max_blocks < initial_blocks:
            raise ValueError("max_blocks must be at least initial_blocks")
        if stable_seconds < 0.0:
            raise ValueError("stable_seconds must not be negative")

        self.block_size = int(block_size)
        self.sample_rate = float(sample_rate)
        self.channels = int(channels)
        self.minimum_target_frames = self.block_size * int(initial_blocks)
        self.maximum_target_frames = self.block_size * int(max_blocks)
        if stable_reads_before_shrink is None:
            stable_reads_before_shrink = max(
                1,
                round(stable_seconds * self.sample_rate / self.block_size),
            )
        if stable_reads_before_shrink <= 0:
            raise ValueError("stable_reads_before_shrink must be positive")
        self.stable_reads_before_shrink = int(stable_reads_before_shrink)

        self._samples = np.zeros(
            (self.maximum_target_frames, self.channels), dtype=np.float32
        )
        self._read_at = 0
        self._write_at = 0
        self._available = 0
        self._target_frames = self.minimum_target_frames
        self._stable_reads = 0
        self._underruns = 0
        self._condition = Condition(Lock())

    @property
    def available_frames(self) -> int:
        with self._condition:
            return self._available

    @property
    def target_frames(self) -> int:
        with self._condition:
            return self._target_frames

    @property
    def target_latency_ms(self) -> float:
        return 1_000.0 * self.target_frames / self.sample_rate

    @property
    def underruns(self) -> int:
        with self._condition:
            return self._underruns

    def needs_render(self) -> bool:
        """Whether the producer should make another complete render block."""
        with self._condition:
            return self._available + self.block_size <= self._target_frames

    def wait_for_render_need(self, timeout: float = 0.1) -> bool:
        """Sleep while the target is full; return whether rendering is needed."""
        with self._condition:
            if self._available + self.block_size > self._target_frames:
                self._condition.wait(timeout=timeout)
            return self._available + self.block_size <= self._target_frames

    def wait_until_target(self, timeout: float, cancelled: Event | None = None) -> bool:
        """Wait for startup prefill without polling the render worker."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._available < self._target_frames:
                if cancelled is not None and cancelled.is_set():
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    return False
                self._condition.wait(timeout=min(remaining, 0.05))
            return True

    def write(self, samples: NDArray[np.float32]) -> int:
        """Append prepared stereo frames, returning the number accepted."""
        source = np.asarray(samples, dtype=np.float32)
        if source.ndim != 2 or source.shape[1] != self.channels:
            raise ValueError(
                f"samples must have shape (frames, {self.channels}), got {source.shape}"
            )
        with self._condition:
            taken = min(source.shape[0], self.maximum_target_frames - self._available)
            if taken <= 0:
                return 0
            first = min(taken, self.maximum_target_frames - self._write_at)
            self._samples[self._write_at : self._write_at + first] = source[:first]
            second = taken - first
            if second:
                self._samples[:second] = source[first : first + second]
            self._write_at = (self._write_at + taken) % self.maximum_target_frames
            self._available += taken
            self._condition.notify_all()
            return taken

    def read_into(self, output: NDArray[np.float32]) -> bool:
        """Drain frames into a device buffer; return whether it underruns."""
        destination = np.asarray(output)
        if destination.ndim != 2 or destination.shape[1] <= 0:
            raise ValueError("output must have shape (frames, channels)")
        if destination.dtype != np.float32:
            raise ValueError("output must be float32")
        destination.fill(0.0)
        requested = destination.shape[0]
        with self._condition:
            taken = min(requested, self._available)
            first = min(taken, self.maximum_target_frames - self._read_at)
            self._copy_device_channels(
                self._samples[self._read_at : self._read_at + first],
                destination[:first],
            )
            second = taken - first
            if second:
                self._copy_device_channels(
                    self._samples[:second],
                    destination[first : first + second],
                )
            self._read_at = (self._read_at + taken) % self.maximum_target_frames
            self._available -= taken
            underrun = taken < requested
            if underrun:
                self._record_underrun_locked()
            else:
                self._record_stable_read_locked()
            self._condition.notify_all()
            return underrun

    def report_device_underflow(self) -> None:
        """React when PortAudio reports that the hardware stream missed time."""
        with self._condition:
            self._record_underrun_locked()
            self._condition.notify_all()

    def wake(self) -> None:
        """Wake a producer that may be waiting during engine shutdown."""
        with self._condition:
            self._condition.notify_all()

    def _record_underrun_locked(self) -> None:
        self._underruns += 1
        self._stable_reads = 0
        self._target_frames = min(
            self.maximum_target_frames,
            max(
                self._target_frames + self.block_size,
                self._target_frames * 2,
            ),
        )

    def _record_stable_read_locked(self) -> None:
        if self._target_frames <= self.minimum_target_frames:
            self._stable_reads = 0
            return
        self._stable_reads += 1
        if self._stable_reads < self.stable_reads_before_shrink:
            return
        self._target_frames = max(
            self.minimum_target_frames,
            self._target_frames - self.block_size,
        )
        self._stable_reads = 0

    @staticmethod
    def _copy_device_channels(
        source: NDArray[np.float32], destination: NDArray[np.float32]
    ) -> None:
        if not source.size:
            return
        device_channels = destination.shape[1]
        if device_channels == 1:
            np.add(source[:, 0], source[:, 1], out=destination[:, 0])
            destination[:, 0] *= 0.5
            return
        destination[:, :2] = source[:, :2]
        for channel in range(2, device_channels):
            np.add(source[:, 0], source[:, 1], out=destination[:, channel])
            destination[:, channel] *= 0.5


__all__ = [
    "AdaptiveOutputBuffer",
    "DEFAULT_INITIAL_BLOCKS",
    "DEFAULT_MAX_BLOCKS",
    "DEFAULT_STABLE_SECONDS",
]
