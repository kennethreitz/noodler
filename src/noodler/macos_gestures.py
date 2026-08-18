"""Small AppKit bridge for gestures Dear PyGui does not expose."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

try:
    from AppKit import NSCursor, NSEvent, NSEventMaskMagnify
except ImportError:  # pragma: no cover - exercised on non-macOS hosts
    NSCursor = None
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


@dataclass(slots=True)
class MacCursor:
    """Show a pointer that describes the gesture currently in hand.

    Dear PyGui exposes no cursor API, so the shape is set through AppKit. Only
    the image changes — the pointer is never hidden or detached from the mouse —
    so the worst outcome on an unsupported host is the arrow the user already
    had.

    The cursor is pushed and popped rather than set and restored: outside a
    running application `NSCursor.arrowCursor()` answers with nothing, so there
    is no dependable arrow to put back. A balanced stack does not need one.
    """

    shape: str = "arrow"
    _pushed: Any = field(default=None, init=False, repr=False)

    @property
    def held(self) -> bool:
        return self._pushed is not None

    def grab(self) -> bool:
        """Show the pointer that means the canvas is being moved."""
        if NSCursor is None:
            return False
        if self._pushed is not None:
            # Re-assert it: the window may have reset the cursor on its own.
            self._pushed.set()
            return True
        cursor = NSCursor.closedHandCursor()
        if cursor is None:
            return False
        cursor.push()
        self._pushed = cursor
        self.shape = "closedHand"
        return True

    def reset(self) -> bool:
        """Give the pointer back, popping exactly what was pushed."""
        if self._pushed is None:
            return False
        self._pushed = None
        self.shape = "arrow"
        if NSCursor is not None:
            NSCursor.pop()
        return True
