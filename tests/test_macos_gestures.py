from dataclasses import dataclass

from noodler import macos_gestures
from noodler.macos_gestures import MacMagnifyMonitor


@dataclass
class FakeMagnifyEvent:
    delta: float

    def magnification(self) -> float:
        return self.delta


class FakeEventAPI:
    handler = None
    removed = []

    @classmethod
    def addLocalMonitorForEventsMatchingMask_handler_(cls, mask, handler):
        cls.handler = handler
        return ("monitor", mask)

    @classmethod
    def removeMonitor_(cls, token):
        cls.removed.append(token)


def test_native_magnify_monitor_forwards_events_and_cleans_up(monkeypatch) -> None:
    FakeEventAPI.handler = None
    FakeEventAPI.removed = []
    monkeypatch.setattr(macos_gestures, "NSEvent", FakeEventAPI)
    monkeypatch.setattr(macos_gestures, "NSEventMaskMagnify", 123)
    deltas = []
    monitor = MacMagnifyMonitor(deltas.append)

    assert monitor.start() is True
    event = FakeMagnifyEvent(0.125)
    assert FakeEventAPI.handler(event) is event
    assert deltas == [0.125]

    monitor.stop()
    monitor.stop()
    assert FakeEventAPI.removed == [("monitor", 123)]


class _FakeCursor:
    def __init__(self, log: list[str], name: str) -> None:
        self._log = log
        self._name = name

    def push(self) -> None:
        self._log.append(f"push {self._name}")

    def set(self) -> None:
        self._log.append(f"set {self._name}")


class _FakeNSCursor:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def closedHandCursor(self):
        return _FakeCursor(self._log, "closedHand")

    def pop(self) -> None:
        self._log.append("pop")


def test_the_pan_cursor_pushes_once_and_pops_once(monkeypatch) -> None:
    log: list[str] = []
    monkeypatch.setattr(macos_gestures, "NSCursor", _FakeNSCursor(log))
    cursor = macos_gestures.MacCursor()

    assert cursor.grab() is True
    assert cursor.held is True
    assert cursor.grab() is True, "a repeat re-asserts rather than stacking"
    assert cursor.reset() is True
    assert cursor.reset() is False, "nothing left to pop"

    assert log == ["push closedHand", "set closedHand", "pop"]
    assert cursor.shape == "arrow"


def test_the_pan_cursor_is_a_no_op_without_appkit(monkeypatch) -> None:
    """A host without AppKit keeps the arrow it already had."""
    monkeypatch.setattr(macos_gestures, "NSCursor", None)
    cursor = macos_gestures.MacCursor()

    assert cursor.grab() is False
    assert cursor.held is False
    assert cursor.reset() is False
    assert cursor.shape == "arrow"


def test_a_cursor_the_platform_will_not_supply_is_left_alone(monkeypatch) -> None:
    class _Empty:
        def closedHandCursor(self):
            return None

    monkeypatch.setattr(macos_gestures, "NSCursor", _Empty())
    cursor = macos_gestures.MacCursor()

    assert cursor.grab() is False
    assert cursor.held is False
