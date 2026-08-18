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
