"""The knob is exactly the size it is asked to be.

Dear PyGui's knob widget is drawn at a fixed forty pixels: its width, its
height and its font change nothing. Four rounds of "the knobs are too big"
each shrank a number that was never read. These tests pin the replacement to
the property that was missing -- that the number on the panel is the number on
the screen.
"""

import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    KNOB_INTERACTION,
    KNOB_SIZE,
    KNOB_SIZE_LARGE,
    KNOB_SIZE_MINIMUM,
    LEVEL_DIAL_SIZE,
    VCO_NODE,
    _control_position,
    _knob_position,
    _resize_knob,
    _set_knob_position,
    build_ui,
)


def test_a_knob_is_a_drawlist_not_the_fixed_size_widget() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        for knob in KNOB_INTERACTION.bindings:
            if dpg.does_item_exist(knob):
                assert dpg.get_item_type(knob).endswith("mvDrawlist"), knob
    finally:
        dpg.destroy_context()


def test_the_requested_size_is_the_configured_size() -> None:
    """A drawlist honours width and height; the knob widget did not."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        sizes = set()
        for knob, binding in KNOB_INTERACTION.bindings.items():
            if not dpg.does_item_exist(knob):
                continue
            configuration = dpg.get_item_configuration(knob)
            assert configuration["width"] == binding.size
            assert configuration["height"] == binding.size
            sizes.add(binding.size)
        assert sizes == {KNOB_SIZE, KNOB_SIZE_LARGE, LEVEL_DIAL_SIZE}
        assert max(sizes) < 40, "no knob is the size the widget forced"
    finally:
        dpg.destroy_context()


def test_every_knob_is_painted() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        for knob in KNOB_INTERACTION.bindings:
            if not dpg.does_item_exist(knob):
                continue
            art = KNOB_INTERACTION.art[knob]
            drawn = set(dpg.get_item_children(knob, slot=2))
            for part in (art.body, art.track, art.arc, art.pointer):
                assert dpg.does_item_exist(part)
                assert part in drawn, "painted onto the knob itself"
    finally:
        dpg.destroy_context()


def test_moving_a_knob_moves_its_pointer() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        art = KNOB_INTERACTION.art[knob]

        _set_knob_position(knob, 0.0)
        low = dpg.get_item_configuration(art.pointer)["p2"]
        _set_knob_position(knob, 1.0)
        high = dpg.get_item_configuration(art.pointer)["p2"]

        assert _knob_position(knob) == 1.0
        assert low != high
        # Seven o'clock to five o'clock: both ends are below the centre and
        # on opposite sides of it.
        centre = art.size * 0.5
        assert low[0] < centre < high[0]
        assert low[1] > centre and high[1] > centre
    finally:
        dpg.destroy_context()


def test_zooming_redraws_at_the_new_size() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        before = KNOB_INTERACTION.art[knob]

        _resize_knob(knob, 30)

        after = KNOB_INTERACTION.art[knob]
        assert dpg.get_item_configuration(knob)["width"] == 30
        assert dpg.get_item_configuration(knob)["height"] == 30
        assert after.size == 30
        assert not dpg.does_item_exist(before.pointer), "the old picture is gone"
        assert dpg.does_item_exist(after.pointer)
    finally:
        dpg.destroy_context()


def test_zooming_out_never_draws_below_the_minimum() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        _resize_knob(knob, 3)
        assert dpg.get_item_configuration(knob)["width"] == KNOB_SIZE_MINIMUM
    finally:
        dpg.destroy_context()


def test_the_position_survives_a_repaint() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        binding = KNOB_INTERACTION.bindings[knob]
        position = _control_position(880.0, 1.0, 20_000.0, True)
        _set_knob_position(knob, position)

        _resize_knob(knob, 26)

        assert _knob_position(knob) == pytest.approx(position)
        # And the module was not touched by any of it.
        assert runtime.vco.parameters.frequency == pytest.approx(220.0)
    finally:
        dpg.destroy_context()
