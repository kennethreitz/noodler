"""The window's first size and the process's name."""

from noodler.desktop import (
    APP_NAME,
    CEILING_HEIGHT,
    CEILING_WIDTH,
    FLOOR_HEIGHT,
    FLOOR_WIDTH,
    default_window,
    name_the_process,
    visible_screen,
)


def test_without_a_screen_the_window_is_the_floor_size_wherever_the_platform_puts_it() -> None:
    assert default_window(None) == (FLOOR_WIDTH, FLOOR_HEIGHT, None, None)


def test_a_laptop_screen_gets_nine_tenths_of_itself_centred() -> None:
    width, height, x, y = default_window((0, 33, 1728, 1027))
    assert (width, height) == (1555, 924)
    assert (x, y) == (86, 33 + 51)


def test_a_small_screen_never_goes_below_the_floor_nor_past_its_own_edge() -> None:
    width, height, x, y = default_window((0, 25, 1400, 875))
    assert (width, height) == (FLOOR_WIDTH, FLOOR_HEIGHT)
    assert x == 60 and y == 25 + 37
    # Smaller than the floor: the screen wins, the window is not wider than it.
    width, height, x, y = default_window((0, 0, 1024, 700))
    assert (width, height) == (1024, 700)
    assert (x, y) == (0, 0)


def test_a_huge_screen_stops_at_the_ceiling() -> None:
    width, height, _x, _y = default_window((0, 0, 5120, 2880))
    assert (width, height) == (CEILING_WIDTH, CEILING_HEIGHT)


def test_naming_the_process_never_raises_and_the_screen_reads_or_declines() -> None:
    name_the_process(APP_NAME)
    screen = visible_screen()
    assert screen is None or (len(screen) == 4 and screen[2] > 0 and screen[3] > 0)
