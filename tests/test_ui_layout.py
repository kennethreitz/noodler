"""The rack decides where modules sit, so the arithmetic has to be right."""

import pytest

from noodler.ui.layout import (
    MIN_MODULE_WIDTH,
    Panel,
    content_height,
    flow,
    insertion_index,
    reorder,
)


def _panels(*widths: float, height: float = 200.0) -> list[Panel]:
    return [Panel(f"m{index}", width, height) for index, width in enumerate(widths)]


def test_an_empty_rack_lays_out_to_nothing() -> None:
    assert flow((), view_width=1000.0) == ()
    assert content_height(()) == 0.0


def test_modules_fill_a_row_left_to_right() -> None:
    placed = flow(_panels(200.0, 200.0, 200.0), view_width=1000.0, margin=10.0, gap=10.0)

    assert [p.row for p in placed] == [0, 0, 0]
    assert [p.x for p in placed] == [10.0, 220.0, 430.0]
    assert [p.index for p in placed] == [0, 1, 2]


def test_a_row_that_runs_out_wraps_to_the_next() -> None:
    """Nothing goes off the edge, so nothing has to be gone looking for."""
    placed = flow(_panels(400.0, 400.0, 400.0), view_width=1000.0, margin=10.0, gap=10.0)

    assert [p.row for p in placed] == [0, 0, 1]
    assert placed[2].x == 10.0, "a wrapped module starts the row"
    assert placed[2].y > placed[0].y


def test_no_two_modules_can_overlap() -> None:
    placed = flow(
        _panels(300.0, 260.0, 420.0, 180.0, 500.0),
        view_width=900.0,
        margin=12.0,
        gap=12.0,
    )
    for first in placed:
        for second in placed:
            if first is second:
                continue
            apart = (
                first.right <= second.x
                or second.right <= first.x
                or first.bottom <= second.y
                or second.bottom <= first.y
            )
            assert apart, f"{first.module_id} overlaps {second.module_id}"


def test_a_row_is_only_as_tall_as_its_own_modules() -> None:
    panels = [Panel("short", 200.0, 120.0), Panel("tall", 900.0, 400.0)]
    placed = flow(panels, view_width=1000.0, margin=10.0, gap=10.0, row_gap=10.0)

    assert placed[0].row == 0 and placed[1].row == 1
    # The second row starts below the first row's own height, not the tallest.
    assert placed[1].y == pytest.approx(10.0 + 120.0 + 10.0)


def test_a_panel_is_never_narrower_than_the_minimum() -> None:
    placed = flow(_panels(10.0), view_width=1000.0)
    assert placed[0].width == MIN_MODULE_WIDTH


def test_a_module_wider_than_the_rack_still_gets_a_row() -> None:
    placed = flow(_panels(4_000.0), view_width=600.0)
    assert len(placed) == 1
    assert placed[0].row == 0


def test_content_height_covers_the_lowest_module() -> None:
    placed = flow(_panels(400.0, 400.0, 400.0), view_width=1000.0, margin=10.0, gap=10.0)
    assert content_height(placed) > max(p.bottom for p in placed) - 1


def test_a_drag_picks_the_position_it_was_dropped_beside() -> None:
    placed = flow(_panels(200.0, 200.0, 200.0), view_width=1000.0, margin=10.0, gap=10.0)

    # Left of everything.
    assert insertion_index(placed, 0.0, 20.0) == 0
    # Just past the first module's midpoint.
    assert insertion_index(placed, 120.0, 20.0) == 1
    # Past the last.
    assert insertion_index(placed, 900.0, 20.0) == 3


def test_a_drag_ignores_the_module_being_moved() -> None:
    """Its own slot must not count, or it can never pass its neighbour."""
    placed = flow(_panels(200.0, 200.0, 200.0), view_width=1000.0, margin=10.0, gap=10.0)

    assert insertion_index(placed, 900.0, 20.0, moving="m0") == 2
    assert insertion_index(placed, 0.0, 20.0, moving="m2") == 0


def test_a_drag_downward_reaches_the_next_row() -> None:
    placed = flow(_panels(400.0, 400.0, 400.0), view_width=1000.0, margin=10.0, gap=10.0)
    second_row_y = placed[2].y

    assert insertion_index(placed, 0.0, second_row_y + 10.0) == 2
    assert insertion_index(placed, 900.0, second_row_y + 10.0) == 3


def test_an_empty_rack_takes_the_first_position() -> None:
    assert insertion_index((), 100.0, 100.0) == 0


def test_reorder_moves_one_module_through_the_order() -> None:
    order = ("a", "b", "c", "d")

    assert reorder(order, "a", 2) == ("b", "c", "a", "d")
    assert reorder(order, "d", 0) == ("d", "a", "b", "c")
    assert reorder(order, "b", 99) == ("a", "c", "d", "b")
    assert reorder(order, "b", -5) == ("b", "a", "c", "d")
    assert reorder(order, "missing", 1) == ("a", "missing", "b", "c", "d")
