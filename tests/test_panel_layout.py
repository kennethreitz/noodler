"""Panels that can be read, and modules that can be picked up."""

import dearpygui.dearpygui as dpg

from noodler.app import (
    AUDIO_RAIL,
    CONTROL_RAIL,
    CANVAS_INTERACTION,
    KNOB_COLUMN_CHARS,
    KNOB_INTERACTION,
    RACK_NODES,
    RACK_RAILS,
    RACK_SUMMARY,
    SCALE_NODE,
    VCO_NODE,
    _add_selected_module,
    _control_label_and_unit,
    _dragged_rack_node,
    _fit_column,
    _reflow_rail_lanes,
    build_ui,
)


def test_a_parameter_name_becomes_a_label_and_a_unit() -> None:
    """A row read "FREQUENCY FINE TUNE CENTS AMPLITUDE" before this."""
    assert _control_label_and_unit("fine_tune_cents") == ("Fine Tune", " ct")
    assert _control_label_and_unit("frequency_cv_1_amount") == ("Freq Cv 1", "")
    assert _control_label_and_unit("decay_seconds") == ("Decay", " s")
    assert _control_label_and_unit("pre_delay_ms") == ("Pre Delay", " ms")
    assert _control_label_and_unit("cutoff_hz") == ("Cutoff", " Hz")
    assert _control_label_and_unit("morph") == ("Morph", "")


def test_every_cell_is_the_same_width() -> None:
    """The rack is monospaced, so equal characters means aligned columns."""
    assert len(_fit_column("MORPH")) == KNOB_COLUMN_CHARS
    assert len(_fit_column("0.200")) == KNOB_COLUMN_CHARS
    long_one = _fit_column("ABSURDLY LONG PARAMETER")
    assert len(long_one) == KNOB_COLUMN_CHARS
    assert long_one.endswith("…"), "an over-long label is trimmed, not wrapped"


def test_generated_panels_line_their_columns_up() -> None:
    """Every control cell is one column wide, label and readout alike."""
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "complex_vco"))

        checked = 0
        for knob, binding in KNOB_INTERACTION.bindings.items():
            if not dpg.does_item_exist(knob):
                continue
            group = dpg.get_item_parent(knob)
            texts = [
                child
                for child in dpg.get_item_children(group, 1) or []
                if dpg.get_item_type(child).endswith("mvText")
            ]
            assert texts, "a control should carry a label and a readout"
            for text in texts:
                assert len(dpg.get_value(text)) == KNOB_COLUMN_CHARS
            checked += 1
        assert checked >= 6, "the oscillator should have several controls"
    finally:
        dpg.destroy_context()


def test_the_header_describes_the_rack_in_front_of_the_user() -> None:
    """It read "EMPTY RACK" over three mounted modules."""
    dpg.create_context()
    try:
        runtime = build_ui()
        assert "EMPTY RACK" in dpg.get_value(RACK_SUMMARY)

        _add_selected_module("test", None, (runtime, "complex_vco"))
        assert dpg.get_value(RACK_SUMMARY) == "1 MODULE  ·  0 CABLES"

        _add_selected_module("test", None, (runtime, "melody_brain"))
        assert dpg.get_value(RACK_SUMMARY) == "2 MODULES  ·  0 CABLES"
    finally:
        dpg.destroy_context()


def test_finding_the_dragged_module_never_raises() -> None:
    """A node publishes no "active" state, so asking for it raised every frame.

    The regression that hid this was in the test, not the code: mocking
    is_item_active granted an API the real item does not have.
    """
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        # The real Dear PyGui state, unmocked.
        assert "active" not in dpg.get_item_state(VCO_NODE)
        assert _dragged_rack_node() is None  # nothing is being dragged
    finally:
        dpg.destroy_context()


def test_the_dragged_module_is_the_one_the_pointer_has(monkeypatch) -> None:
    """Overlapping panels made the first in list order win every drag."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg, "is_mouse_button_dragging", lambda button, threshold: True
        )
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (400.0, 300.0)
        )
        # Every panel claims to contain the pointer, as overlapping ones do.
        monkeypatch.setattr(dpg, "get_item_rect_min", lambda _item: [0.0, 0.0])
        monkeypatch.setattr(
            dpg, "get_item_rect_max", lambda _item: [4_000.0, 4_000.0]
        )
        monkeypatch.setattr(
            dpg,
            "get_item_state",
            lambda item: {"hovered": item == VCO_NODE},
        )

        assert _dragged_rack_node() == VCO_NODE

        # With nothing hovered, the front-most panel wins, not the first.
        monkeypatch.setattr(dpg, "get_item_state", lambda _item: {})
        assert _dragged_rack_node() == RACK_NODES[-1]
    finally:
        dpg.destroy_context()


def test_the_audio_lane_clears_the_control_lane(monkeypatch) -> None:
    """A tall control module used to grow straight down through the patch."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [300, 460] if item in RACK_RAILS[CONTROL_RAIL] else [300, 120],
        )

        _reflow_rail_lanes()

        control_y = CANVAS_INTERACTION.rail_y[CONTROL_RAIL]
        audio_y = CANVAS_INTERACTION.rail_y[AUDIO_RAIL]
        assert audio_y >= control_y + 460.0, "the lanes still overlap"
        assert SCALE_NODE in RACK_RAILS[CONTROL_RAIL]
    finally:
        dpg.destroy_context()
