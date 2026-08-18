"""The desktop the window opens onto: how big to make it, and what to call us.

Two things a desktop application settles before it has a window. The window's
first size, which used to be a number that fit one laptop and looked like a
postage stamp on a monitor; it is now taken from the screen it is about to
open on. And the process's name -- the one in the menu bar, the Dock and the
process list -- which without a bundle reads "python", and should read
Noodler.
"""

from __future__ import annotations

import sys


APP_NAME = "Noodler"
FLOOR_WIDTH, FLOOR_HEIGHT = 1280, 800
"""No smaller than this, however small the screen says it is."""
CEILING_WIDTH, CEILING_HEIGHT = 2400, 1500
"""No larger than this: past it a rack is a lot of empty grid."""
SCREEN_SHARE = 0.9
"""How much of the visible screen a fresh window takes."""


def visible_screen() -> tuple[int, int, int, int] | None:
    """The screen's usable area as (left, top, width, height), top-left origin.

    macOS only, through AppKit: the main screen's frame less the menu bar and
    the Dock. Anywhere else, or if AppKit is not there, None -- and the window
    takes its floor size wherever the platform puts it.
    """
    if sys.platform != "darwin":
        return None
    try:
        from AppKit import NSScreen
    except Exception:  # pragma: no cover - no AppKit on this machine
        return None
    try:
        screen = NSScreen.mainScreen()
        if screen is None:
            return None
        whole = screen.frame()
        usable = screen.visibleFrame()
        # Cocoa measures from the bottom-left; windows are placed from the top.
        top = float(whole.size.height) - (float(usable.origin.y) + float(usable.size.height))
        return (
            int(usable.origin.x),
            int(top),
            int(usable.size.width),
            int(usable.size.height),
        )
    except Exception:  # pragma: no cover - a headless or odd display
        return None


def default_window(
    screen: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int | None, int | None]:
    """The first window: (width, height, x, y), sized to the screen and centred.

    Nine tenths of the usable screen, never below the floor, never above the
    ceiling; centred in the usable area when a screen is known. Without a
    screen the floor size, and the position is left to the platform.
    """
    if screen is None:
        return FLOOR_WIDTH, FLOOR_HEIGHT, None, None
    left, top, screen_width, screen_height = screen
    width = int(round(screen_width * SCREEN_SHARE))
    height = int(round(screen_height * SCREEN_SHARE))
    width = max(FLOOR_WIDTH, min(CEILING_WIDTH, width))
    height = max(FLOOR_HEIGHT, min(CEILING_HEIGHT, height))
    # Never wider than the screen itself, if the screen is smaller than the floor.
    width = min(width, screen_width) if screen_width > 0 else width
    height = min(height, screen_height) if screen_height > 0 else height
    x = left + max(0, (screen_width - width) // 2)
    y = top + max(0, (screen_height - height) // 2)
    return width, height, x, y


def name_the_process(name: str = APP_NAME) -> None:
    """Call the process by its name, everywhere a name shows.

    The process title, for ps and the process list, through setproctitle
    where it is installed. On macOS the application name too -- the app menu,
    the Dock -- which the window toolkit reads from the main bundle's
    CFBundleName and, failing that, the process name; both are set. Must run
    before the first window, since the menu bar is built once.
    """
    try:
        import setproctitle
    except ImportError:  # pragma: no cover - optional
        setproctitle = None
    if setproctitle is not None:
        try:
            setproctitle.setproctitle(name.lower())
        except Exception:  # pragma: no cover - a platform that refuses
            pass
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle, NSProcessInfo
    except Exception:  # pragma: no cover - no Foundation on this machine
        return
    try:
        bundle = NSBundle.mainBundle()
        if bundle is not None:
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info is not None:
                info["CFBundleName"] = name
                info["CFBundleDisplayName"] = name
        NSProcessInfo.processInfo().setProcessName_(name)
    except Exception:  # pragma: no cover - a bundle that will not be told
        pass


__all__ = ["APP_NAME", "default_window", "name_the_process", "visible_screen"]
