"""An oscilloscope: watch a signal as well as hear it.

Patch anything into it -- an oscillator, an envelope, a clock, a brain's pitch
-- and its panel draws the last few milliseconds, or the last few seconds, of
it. A periodic wave is held still by triggering on its rising crossing, the
way a bench scope does, so a saw is a saw and not a smear; a slow control
rolls by. The signal passes straight through, so a scope can sit in a cable
without changing anything. The module keeps the samples; the panel draws
them.
"""

from collections.abc import Mapping
import threading

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


HISTORY_SECONDS = 2.5
"""How much of the signal the scope keeps: enough for the longest window and
a trigger search before it."""
MODES = ("trigger", "roll")
DISPLAY_POINTS = 200
"""How many points the panel asks for: one per pixel of its trace."""


class ScopeParameters(BaseModel):
    """What the scope shows and how."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    window_ms: float = Field(default=20.0, ge=1.0, le=2000.0)
    """How much time the trace spans, left to right."""
    mode: str = "trigger"
    """trigger: hold a periodic wave still on its rising crossing. roll: the
    newest window, scrolling."""
    gain: float = Field(default=1.0, ge=0.1, le=10.0)
    """Vertical scale: one fills the trace with a full-scale signal."""
    centered: bool = True
    """Zero in the middle, for a wave; off, zero at the bottom, for a gate
    or an envelope."""

    @model_validator(mode="after")
    def known(self) -> "ScopeParameters":
        if self.mode not in MODES:
            object.__setattr__(self, "mode", "trigger")
        return self


SCOPE_MANIFEST = ModuleManifest(
    id="scope",
    name="Scope",
    category="Utilities",
    description=(
        "An oscilloscope: its panel draws whatever is patched into it -- a wave "
        "held still on its rising crossing, or a control rolling by -- and the "
        "signal passes straight through."
    ),
    ports=(
        port("signal", "In", PortDirection.INPUT, SignalType.CV, "What to watch: audio or control, either."),
        port("trigger", "Trig", PortDirection.INPUT, SignalType.TRIGGER, "Start each sweep here instead of on the signal's own crossing."),
        port("through", "Thru", PortDirection.OUTPUT, SignalType.CV, "The signal, unchanged."),
        port("peak", "Peak", PortDirection.OUTPUT, SignalType.CV, "The loudest the signal has been lately, held and falling."),
    ),
)


class Scope:
    """Keep the recent past of a signal for the panel to draw."""

    manifest = SCOPE_MANIFEST
    display = "scope"
    """The panel builder looks for this and adds a trace."""

    def __init__(self, parameters: ScopeParameters | None = None) -> None:
        self.parameters = parameters or ScopeParameters()
        self._sample_rate = 48_000.0
        self._history = np.zeros(int(HISTORY_SECONDS * self._sample_rate), dtype=np.float32)
        self._write = 0
        self._triggers = np.zeros(int(HISTORY_SECONDS * self._sample_rate), dtype=np.bool_)
        self._external_trigger = False
        self._trigger_high = False
        self._peak = 0.0
        self._lock = threading.Lock()

    @property
    def label(self) -> str:
        window = self.parameters.window_ms
        span = f"{window:.0f} ms" if window < 1000.0 else f"{window / 1000.0:.1f} s"
        return f"{span}  ·  {self.parameters.mode.upper()}  ·  ×{self.parameters.gain:g}"

    def choices_for(self, field: str) -> tuple[str, ...]:
        return MODES if field == "mode" else ()

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if float(sample_rate) != self._sample_rate or self._history.size == 0:
            self._sample_rate = float(sample_rate)
            with self._lock:
                self._history = np.zeros(int(HISTORY_SECONDS * self._sample_rate), dtype=np.float32)
                self._triggers = np.zeros(self._history.size, dtype=np.bool_)
                self._write = 0

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
            return empty_outputs(("through", "peak"))
        if float(sample_rate) != self._sample_rate:
            self.prepare(sample_rate)
        inputs = inputs or {}
        signal = np.asarray(block("signal", inputs, frame_count), dtype=np.float32)
        external = "trigger" in inputs
        trigger = np.asarray(block("trigger", inputs, frame_count), dtype=np.float32) > 0.5 if external else None
        size = self._history.size
        indices = (self._write + np.arange(frame_count)) % size
        with self._lock:
            self._history[indices] = signal
            if external:
                # Rising edges of the trigger input, marked where they land,
                # across block boundaries too.
                previous = np.concatenate(([self._trigger_high], trigger[:-1]))
                self._triggers[indices] = trigger & ~previous
                self._trigger_high = bool(trigger[-1])
            else:
                self._triggers[indices] = False
                self._trigger_high = False
            self._external_trigger = external
            self._write = int((self._write + frame_count) % size)
        peak_now = float(np.abs(signal).max()) if frame_count else 0.0
        # A peak that falls at about 6 dB a second: readable, not frozen.
        self._peak = max(peak_now, self._peak * (0.5 ** (frame_count / sample_rate)))
        return {
            "through": signal,
            "peak": np.full(frame_count, self._peak, dtype=np.float32),
        }

    # ---- what the panel draws --------------------------------------------

    def trace(self, points: int = DISPLAY_POINTS) -> NDArray[np.float32]:
        """The window to draw, as ``points`` values in -1..1 (before gain).

        Roll: the newest window. Trigger: the window that starts at the last
        rising zero crossing (or the last external trigger) that leaves a
        whole window after it, so a periodic wave stands still; failing one,
        the newest window.
        """
        points = max(2, int(points))
        window = max(2, int(self.parameters.window_ms * 0.001 * self._sample_rate))
        with self._lock:
            history = np.roll(self._history, -self._write)  # oldest first
            triggers = np.roll(self._triggers, -self._write) if self._external_trigger else None
        size = history.size
        window = min(window, size // 2)
        start = size - window
        if self.parameters.mode == "trigger":
            search_from = max(0, size - 2 * window - 1)
            segment = history[search_from : size - window + 1]
            if triggers is not None:
                # An external trigger may be slow: the last one anywhere in the
                # history that leaves a whole window after it starts the sweep.
                marks = np.flatnonzero(triggers[: size - window + 1])
                if marks.size:
                    start = int(marks[-1])
            else:
                # Rising crossings of the middle of the segment's own range.
                middle = 0.5 * (float(segment.max()) + float(segment.min()))
                above = segment > middle
                rising = np.flatnonzero(~above[:-1] & above[1:])
                if rising.size and float(segment.max()) - float(segment.min()) > 1e-4:
                    start = search_from + int(rising[-1]) + 1
        chunk = history[start : start + window]
        if chunk.size < 2:
            return np.zeros(points, dtype=np.float32)
        positions = np.linspace(0.0, chunk.size - 1, points)
        return np.interp(positions, np.arange(chunk.size), chunk).astype(np.float32)


__all__ = ["DISPLAY_POINTS", "MODES", "SCOPE_MANIFEST", "Scope", "ScopeParameters"]
