"""Small AppKit bridge for gestures Dear PyGui does not expose."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

try:
    from AppKit import NSEvent, NSEventMaskMagnify
except ImportError:  # pragma: no cover - exercised on non-macOS hosts
    NSEvent = None
    NSEventMaskMagnify = 0


@dataclass(slots=True)
class MacMagnifyMonitor:
    """Forward this app's native trackpad magnification events."""

    callback: Callable[[float], None]
    _token: Any = field(default=None, init=False, repr=False)
    _handler: Any = field(default=None, init=False, repr=False)

    def start(self) -> bool:
        """Install the local monitor once, returning whether it is active."""
        if self._token is not None:
            return True
        if NSEvent is None:
            return False

        def handle(event: Any) -> Any:
            self.callback(float(event.magnification()))
            return event

        self._handler = handle
        self._token = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskMagnify,
            handle,
        )
        return self._token is not None

    def stop(self) -> None:
        """Remove the monitor exactly once."""
        if self._token is None or NSEvent is None:
            return
        NSEvent.removeMonitor_(self._token)
        self._token = None
        self._handler = None
