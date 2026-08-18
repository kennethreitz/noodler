"""How the rack responds: settling, momentum, ballistics, and the keyboard."""

import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    CONSOLE_MASTER_LEVEL,
    _console_band,
    AUDIO_RAIL,
    BOX_SELECTOR_FILL,
    CANVAS_INTERACTION,
    CONTROL_STATUS,
    DEFAULT_CONTROL_STATUS,
    INSTANCE_NODE_TAGS,
    KNOB_INTERACTION,
    METER_BALLISTICS,
    MIXER_LPG_LINK,
    MODULE_CLOSE_LAYER,
    MODULE_COLLAPSE,
    MODULE_SELECTOR,
    OUTPUT_METER,
    OUTPUT_NODE,
    RACK_NODES,
    REVERB_NODE,
    RACK_OUTLINE_BODY,
    RACK_RAILS,
    RACK,
    REVEAL_PATIENCE,
    RAIL_SPRINGS,
    TIDY_TARGETS,
    SAVE_PATCH_DIALOG,
    VCO_NODE,
    _add_selected_module,
    _begin_knob_drag,
    _capture_macos_scroll,
    _consume_scroll,
    _scroll_rack,
    _control_position,
    _delete_rack_selection,
    _end_knob_drag,
    _dismiss_rack_focus,
    _drag_knob,
    _frame_rack,
    _glide_rack,
    _module_close_at,
    _module_close_bounds,
    _rack_content_bounds,
    _queue_rack_zoom,
    _refresh_ui,
    _release_pan_momentum,
    _add_selected_module,
    _node_that_moved,
    _remove_module_node,
    _reveal_rack_once,
    _reveal_node,
    _settle_rack_rails,
    _tidy_rack,
    _module_depths,
    _settle_recenter,
    _settle_rack_zoom,
    _toggle_module_from_title,
    _translate_rack,
    build_ui,
)


def _descendants(item: int | str) -> tuple[int | str, ...]:
    children = tuple(
        child
        for slot in dpg.get_item_children(item).values()
        for child in slot
    )
    return children + tuple(
        descendant
        for child in children
        for descendant in _descendants(child)
    )





def test_zoom_springs_to_its_target_and_stops_there() -> None:
    dpg.create_context()
    try:
        build_ui()
        _queue_rack_zoom(1.4, screen_anchor=(400.0, 300.0))
        assert CANVAS_INTERACTION.zoom == 1.0

        _settle_rack_zoom(1.0 / 120.0)
        assert 1.0 < CANVAS_INTERACTION.zoom < 1.4

        for _ in range(400):
            _settle_rack_zoom(1.0 / 120.0)
        assert CANVAS_INTERACTION.zoom == pytest.approx(1.4, abs=1e-6)
    finally:
        dpg.destroy_context()


def test_a_released_pan_keeps_travelling() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        start_x = float(dpg.get_item_pos(VCO_NODE)[0])
        CANVAS_INTERACTION.pan_velocity_x = 900.0
        _release_pan_momentum()

        for _ in range(180):
            _glide_rack(1.0 / 60.0)

        travelled = float(dpg.get_item_pos(VCO_NODE)[0]) - start_x
        assert travelled > 100.0
        assert not CANVAS_INTERACTION.glide_x.moving, "momentum must come to rest"
    finally:
        dpg.destroy_context()


def test_a_press_on_the_rack_catches_a_gliding_canvas(monkeypatch) -> None:
    dpg.create_context()
    try:
        build_ui()
        CANVAS_INTERACTION.glide_x.release(900.0)
        assert CANVAS_INTERACTION.glide_x.moving
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (10.0, 10.0)
        )
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: False
        )

        _begin_knob_drag("test", None, KNOB_INTERACTION)

        assert not CANVAS_INTERACTION.glide_x.moving
    finally:
        dpg.destroy_context()


def test_the_output_meter_rises_instantly_and_falls_back() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        runtime.audio.last_peak = 0.8
        _refresh_ui(runtime, 1.0 / 60.0)
        assert dpg.get_value(OUTPUT_METER) == pytest.approx(0.8)

        runtime.audio.last_peak = 0.0
        for _ in range(60):
            _refresh_ui(runtime, 1.0 / 60.0)

        assert dpg.get_value(OUTPUT_METER) < 0.2
        assert METER_BALLISTICS.peak > dpg.get_value(OUTPUT_METER)
        # What is seen is the master dial's ring, lit as far round as the level.
        ring = dpg.get_item_configuration(f"{CONSOLE_MASTER_LEVEL}.meter")
        assert 1 < len(ring["points"]) < 30
    finally:
        dpg.destroy_context()


def test_delete_unpatches_a_selected_cable(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        link = dpg.get_alias_id(MIXER_LPG_LINK)
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [link])
        monkeypatch.setattr(dpg, "get_selected_nodes", lambda _rack: [])
        before = len(runtime.patch.cables)

        _delete_rack_selection("test", None, runtime)

        assert len(runtime.patch.cables) == before - 1
        assert not dpg.does_item_exist(MIXER_LPG_LINK)
    finally:
        dpg.destroy_context()


def test_delete_removes_a_selected_module_and_retains_its_panel_for_undo(
    monkeypatch,
) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [])
        monkeypatch.setattr(
            dpg, "get_selected_nodes", lambda _rack: [dpg.get_alias_id(VCO_NODE)]
        )

        _delete_rack_selection("test", None, runtime)

        assert "vco" not in runtime.patch.modules
        assert dpg.does_item_exist(VCO_NODE)
        assert not dpg.is_item_shown(VCO_NODE)
        assert VCO_NODE not in RACK_NODES
        assert VCO_NODE not in RACK_RAILS[AUDIO_RAIL]
        assert VCO_NODE not in RAIL_SPRINGS
        assert "vco" not in INSTANCE_NODE_TAGS
        # Every cable that touched the module went with it.
        assert all(
            "vco" not in (cable.source.module_id, cable.target.module_id)
            for cable in runtime.patch.cables
        )
        assert "REMOVED" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_the_system_output_cannot_be_deleted() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()

        assert _remove_module_node(OUTPUT_NODE, runtime) is False
        assert dpg.does_item_exist(OUTPUT_NODE)
        assert "CANNOT BE REMOVED" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_title_close_target_removes_a_module(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        node = INSTANCE_NODE_TAGS["classic_vco"]
        monkeypatch.setattr("noodler.app._module_close_at", lambda _point: node)

        _begin_knob_drag("test", None, (KNOB_INTERACTION, runtime))

        assert "classic_vco" not in runtime.patch.modules
        assert dpg.does_item_exist(node)
        assert not dpg.is_item_shown(node)
        assert dpg.does_item_exist(MODULE_CLOSE_LAYER)
    finally:
        dpg.destroy_context()


def test_title_close_is_at_the_right_edge_and_skips_system_output(
    monkeypatch,
) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        node = INSTANCE_NODE_TAGS["classic_vco"]
        monkeypatch.setattr(dpg, "get_item_rect_min", lambda _item: (10.0, 20.0))
        monkeypatch.setattr(dpg, "get_item_rect_max", lambda _item: (210.0, 320.0))

        bounds = _module_close_bounds(node)

        assert bounds is not None
        assert bounds[2] == pytest.approx(205.0)
        assert _module_close_at((200.0, 30.0)) == node
        assert _module_close_bounds(OUTPUT_NODE) is None
    finally:
        dpg.destroy_context()


def test_current_rack_tree_can_remove_an_unpatched_module() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        node = INSTANCE_NODE_TAGS["classic_vco"]
        remove_button = next(
            item
            for item in _descendants(RACK_OUTLINE_BODY)
            if dpg.get_item_type(item).endswith("mvButton")
            and dpg.get_item_configuration(item)["label"] == "×"
            and dpg.get_item_configuration(item)["user_data"][1]
            == "classic_vco"
        )
        configuration = dpg.get_item_configuration(remove_button)

        configuration["callback"](
            remove_button,
            None,
            configuration["user_data"],
        )

        assert "classic_vco" not in runtime.patch.modules
        assert dpg.does_item_exist(node)
        assert not dpg.is_item_shown(node)
    finally:
        dpg.destroy_context()


def test_delete_is_ignored_while_the_module_browser_is_open(monkeypatch) -> None:
    """Most Mac keyboards send Backspace for Delete, so the search field wins."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        monkeypatch.setattr("noodler.app._keyboard_is_captured", lambda: True)
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [])
        monkeypatch.setattr(
            dpg, "get_selected_nodes", lambda _rack: [dpg.get_alias_id(VCO_NODE)]
        )

        _delete_rack_selection("test", None, runtime)

        assert "vco" in runtime.patch.modules
    finally:
        dpg.destroy_context()


def test_delete_with_an_empty_selection_says_so(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [])
        monkeypatch.setattr(dpg, "get_selected_nodes", lambda _rack: [])

        _delete_rack_selection("test", None, runtime)

        assert "NOTHING SELECTED" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_escape_clears_the_selection(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        cleared: list[int] = []
        monkeypatch.setattr(
            "noodler.app._clear_rack_selection", lambda: cleared.append(1)
        )

        _dismiss_rack_focus("test", None, runtime)

        assert cleared == [1]
        assert dpg.is_item_shown(MODULE_SELECTOR), "the library is not a dialog"
    finally:
        dpg.destroy_context()

def test_double_clicking_a_control_restores_its_default(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        configuration = dpg.get_item_configuration(knob)
        binding = configuration["user_data"]
        configuration["callback"](
            knob,
            _control_position(880.0, 1.0, 20_000.0, True),
            binding,
        )
        assert runtime.vco.parameters.frequency == pytest.approx(880.0)

        # A double-click over a control resolves to the control, not the title.
        monkeypatch.setattr("noodler.app._hovered_knob", lambda: (knob, binding))
        _toggle_module_from_title("test", None, runtime)

        assert runtime.vco.parameters.frequency == pytest.approx(220.0)
        assert "RESET" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def _settle_camera(frames: int = 400) -> None:
    for _ in range(frames):
        _settle_recenter(1.0 / 120.0)


def test_framing_brings_a_flung_rack_back(monkeypatch) -> None:
    """Momentum can send the rack out of the window, so it needs a way home."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [900, 600] if item == RACK else [90, 110],
        )
        before = _rack_content_bounds()
        assert before is not None

        _translate_rack(-4_000.0, -2_500.0)
        flung = _rack_content_bounds()
        assert flung[0] < -3_000.0

        _frame_rack("test", None, runtime)
        _settle_camera()

        # Centred in the part of the canvas above the console, not the whole.
        framed = _rack_content_bounds()
        centre_x = (framed[0] + framed[2]) * 0.5
        centre_y = (framed[1] + framed[3]) * 0.5
        assert centre_x == pytest.approx(450.0, abs=2.0)
        assert centre_y == pytest.approx((600.0 - _console_band()) * 0.5, abs=2.0)
    finally:
        dpg.destroy_context()


def test_framing_an_empty_rack_says_so() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        for node in tuple(RACK_NODES):
            if dpg.does_item_exist(node):
                dpg.delete_item(node)
                RACK_NODES.remove(node)

        _frame_rack("test", None, runtime)

        assert "NOTHING TO FRAME" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_a_press_cancels_a_framing_move_in_progress(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [900, 600] if item == RACK else [90, 110],
        )
        _translate_rack(-2_000.0, 0.0)
        _frame_rack("test", None, runtime)
        _settle_recenter(1.0 / 120.0)
        assert not CANVAS_INTERACTION.recenter_x.settled

        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (10.0, 10.0)
        )
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: False
        )
        _begin_knob_drag("test", None, KNOB_INTERACTION)

        assert CANVAS_INTERACTION.recenter_x.settled
        assert CANVAS_INTERACTION.recenter_x.target == 0.0
    finally:
        dpg.destroy_context()


def test_the_rack_keyboard_stands_down_for_the_save_dialog(monkeypatch) -> None:
    """Typing a patch name must not delete modules with Backspace."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        dpg.show_item(SAVE_PATCH_DIALOG)
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [])
        monkeypatch.setattr(
            dpg, "get_selected_nodes", lambda _rack: [dpg.get_alias_id(VCO_NODE)]
        )

        _delete_rack_selection("test", None, runtime)

        assert "vco" in runtime.patch.modules
    finally:
        dpg.destroy_context()


def _sized(rack_size, node_size):
    """Report one size for the editor viewport and another for every node."""
    return lambda item: list(rack_size) if item == RACK else list(node_size)


def test_a_module_added_off_screen_is_brought_into_view(monkeypatch) -> None:
    """An add that lands outside the window reads as nothing having happened."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg, "get_item_rect_size", _sized((900, 600), (200, 150))
        )
        dpg.set_item_pos(VCO_NODE, [2_400.0, 300.0])

        assert _reveal_node(VCO_NODE) is True
        _settle_camera()

        node_x = float(dpg.get_item_pos(VCO_NODE)[0])
        assert node_x >= 56.0 - 1.0
        assert node_x + 200.0 <= 900.0 - 56.0 + 1.0
    finally:
        dpg.destroy_context()


def test_a_module_already_in_view_does_not_move_the_camera(monkeypatch) -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg, "get_item_rect_size", _sized((900, 600), (200, 150))
        )
        # Well inside the part of the canvas above the console band.
        dpg.set_item_pos(VCO_NODE, [300.0, 120.0])

        assert _reveal_node(VCO_NODE) is False
        assert CANVAS_INTERACTION.recenter_x.target == 0.0
        assert CANVAS_INTERACTION.recenter_y.target == 0.0
    finally:
        dpg.destroy_context()


def test_a_held_background_drag_pans_for_its_whole_travel(monkeypatch) -> None:
    """Dear PyGui repeats the mouse-down callback for every held frame.

    Beginning the pan again on each of those frames moved its origin to the
    current pointer, so the drag had nothing left to travel and the rack sat
    still under the editor's own selection marquee.
    """
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        pointer = [300.0, 240.0]
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: tuple(pointer)
        )
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: True
        )
        monkeypatch.setattr(
            "noodler.app._point_is_over_rack_background", lambda _position: True
        )
        monkeypatch.setattr("noodler.app._module_close_at", lambda _position: None)
        start = tuple(dpg.get_item_pos(VCO_NODE))

        _begin_knob_drag("test", None, KNOB_INTERACTION)
        for step in ((350.0, 260.0), (410.0, 300.0), (440.0, 290.0)):
            pointer[0], pointer[1] = step
            _begin_knob_drag("test", None, KNOB_INTERACTION)
            _drag_knob("test", None, KNOB_INTERACTION)

        moved = tuple(dpg.get_item_pos(VCO_NODE))
        assert moved[0] - start[0] == pytest.approx(140.0)
        assert moved[1] - start[1] == pytest.approx(50.0)
    finally:
        dpg.destroy_context()


def test_the_marquee_is_hidden_for_panning_and_shown_for_selecting(
    monkeypatch,
) -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (300.0, 240.0)
        )
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: True
        )
        monkeypatch.setattr("noodler.app._module_close_at", lambda _position: None)

        monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
        _begin_knob_drag("test", None, KNOB_INTERACTION)
        assert CANVAS_INTERACTION.panning is True
        assert dpg.get_value(BOX_SELECTOR_FILL) == [0.0, 0.0, 0.0, 0.0]
        _end_knob_drag("test", None, KNOB_INTERACTION)

        # Shift hands the gesture back to the editor, which needs to show it.
        monkeypatch.setattr(
            dpg, "is_key_down", lambda key: key == dpg.mvKey_LShift
        )
        _begin_knob_drag("test", None, KNOB_INTERACTION)
        assert CANVAS_INTERACTION.panning is False
        assert dpg.get_value(BOX_SELECTOR_FILL)[3] > 0.0

        _end_knob_drag("test", None, KNOB_INTERACTION)
        assert dpg.get_value(BOX_SELECTOR_FILL) == [0.0, 0.0, 0.0, 0.0]
    finally:
        dpg.destroy_context()


def test_closing_a_module_does_not_slide_into_a_pan(monkeypatch) -> None:
    """The mouse-down callback repeats, so a spent press must stay spent."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        pointer = [300.0, 240.0]
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: tuple(pointer)
        )
        monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: True
        )
        monkeypatch.setattr(
            "noodler.app._point_is_over_rack_background", lambda _position: True
        )
        monkeypatch.setattr(
            "noodler.app._module_close_at",
            lambda _position: VCO_NODE if dpg.does_item_exist(VCO_NODE) else None,
        )
        start = tuple(dpg.get_item_pos(REVERB_NODE))

        _begin_knob_drag("test", None, (KNOB_INTERACTION, runtime))
        assert "vco" not in runtime.patch.modules

        # The finger is still down and drifting; the rack must not follow.
        for step in ((360.0, 280.0), (420.0, 300.0)):
            pointer[0], pointer[1] = step
            _begin_knob_drag("test", None, (KNOB_INTERACTION, runtime))
            _drag_knob("test", None, KNOB_INTERACTION)

        assert CANVAS_INTERACTION.panning is False
        assert tuple(dpg.get_item_pos(REVERB_NODE)) == start

        _end_knob_drag("test", None, KNOB_INTERACTION)
        assert CANVAS_INTERACTION.press_consumed is False
    finally:
        dpg.destroy_context()








class _RecordingCursor:
    def __init__(self) -> None:
        self.events: list[str] = []

    def grab(self) -> bool:
        self.events.append("grab")
        return True

    def reset(self) -> bool:
        self.events.append("reset")
        return True


def test_a_background_drag_also_takes_the_pointer(monkeypatch) -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        cursor = _RecordingCursor()
        monkeypatch.setattr("noodler.app.RACK_CURSOR", cursor)
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (300.0, 240.0)
        )
        monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: True
        )
        monkeypatch.setattr("noodler.app._module_close_at", lambda _position: None)

        _begin_knob_drag("test", None, KNOB_INTERACTION)
        assert cursor.events == ["grab"]

        _end_knob_drag("test", None, KNOB_INTERACTION)
        assert cursor.events[-1] == "reset"
    finally:
        dpg.destroy_context()




def test_module_depth_follows_the_cables() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        depths = _module_depths(runtime.patch)

        assert depths["vco"] < depths["mixer"] < depths["low_pass_gate"]
        assert depths["low_pass_gate"] < depths["reverb"]
        assert depths["wogglebug"] == 0, "a source starts at the beginning"
    finally:
        dpg.destroy_context()


def test_tidy_leaves_an_unpatched_rack_alone() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        before = list(RACK_RAILS[AUDIO_RAIL])

        _tidy_rack("test", None, runtime)

        assert RACK_RAILS[AUDIO_RAIL] == before
    finally:
        dpg.destroy_context()



def test_space_and_a_click_drag_pans_rather_than_selects(monkeypatch) -> None:
    """Space plus a drag is the reach people already have; it must pan.

    The press also has to be claimed, or the editor spends it on a box select —
    and it has to work from over a module, not just from empty background.
    """
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        pointer = [300.0, 240.0]
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: tuple(pointer)
        )
        monkeypatch.setattr(
            dpg, "is_key_down", lambda key: key == dpg.mvKey_Spacebar
        )
        monkeypatch.setattr(dpg, "is_mouse_button_down", lambda _button: True)
        monkeypatch.setattr("noodler.app._mouse_is_over_rack", lambda: True)
        monkeypatch.setattr("noodler.app._keyboard_is_captured", lambda: False)
        monkeypatch.setattr("noodler.app._module_close_at", lambda _position: None)
        # The press lands on a module, not on empty canvas.
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: False
        )
        monkeypatch.setattr(
            "noodler.app._point_is_over_rack_background", lambda _position: False
        )
        cleared: list[int] = []
        monkeypatch.setattr(
            "noodler.app._clear_rack_selection", lambda: cleared.append(1)
        )
        start = tuple(dpg.get_item_pos(VCO_NODE))

        _begin_knob_drag("test", None, (KNOB_INTERACTION, runtime))
        assert CANVAS_INTERACTION.panning is True

        for step in ((360.0, 280.0), (430.0, 310.0)):
            pointer[0], pointer[1] = step
            _begin_knob_drag("test", None, (KNOB_INTERACTION, runtime))
            _drag_knob("test", None, KNOB_INTERACTION)

        moved = tuple(dpg.get_item_pos(VCO_NODE))
        assert moved[0] - start[0] == pytest.approx(130.0)
        assert moved[1] - start[1] == pytest.approx(70.0)
        assert cleared, "the editor keeps trying to select; keep clearing"
    finally:
        dpg.destroy_context()


def test_scrolling_moves_the_rack_rather_than_zooming() -> None:
    """A gesture that means two things means neither reliably."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        start = tuple(dpg.get_item_pos(VCO_NODE))
        zoom = CANVAS_INTERACTION.zoom

        _capture_macos_scroll(-40.0, -120.0)
        _consume_scroll()

        moved = tuple(dpg.get_item_pos(VCO_NODE))
        assert moved[0] - start[0] == pytest.approx(-40.0)
        assert moved[1] - start[1] == pytest.approx(-120.0)
        assert CANVAS_INTERACTION.zoom == zoom, "scrolling must not zoom"
    finally:
        dpg.destroy_context()


def test_sideways_scrolling_is_carried_too() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        start = float(dpg.get_item_pos(VCO_NODE)[0])

        _capture_macos_scroll(90.0, 0.0)
        _consume_scroll()

        assert float(dpg.get_item_pos(VCO_NODE)[0]) - start == pytest.approx(90.0)
    finally:
        dpg.destroy_context()


def test_the_wheel_stands_down_when_the_platform_reports_scrolling(
    monkeypatch,
) -> None:
    """Both paths firing would scroll the rack twice for one gesture."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        monkeypatch.setattr("noodler.app._mouse_is_over_rack", lambda: True)
        CANVAS_INTERACTION.native_scroll = True

        _scroll_rack("test", 3.0)

        assert CANVAS_INTERACTION.pending_scroll_y == 0.0

        CANVAS_INTERACTION.native_scroll = False
        _scroll_rack("test", 3.0)
        assert CANVAS_INTERACTION.pending_scroll_y > 0.0
    finally:
        dpg.destroy_context()


def test_a_module_drag_cannot_turn_into_a_pan_partway(monkeypatch) -> None:
    """The rack can move under a drag; the drag must not change its mind.

    Whether a gesture began over empty background was re-tested every frame
    against node rectangles that had moved since — a scroll, a glide, or a
    neighbour settling was enough to make a module drag start panning instead,
    leaving the module behind.
    """
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (400.0, 300.0)
        )
        monkeypatch.setattr(
            dpg, "get_mouse_drag_delta", lambda **_kwargs: (10.0, 5.0)
        )
        monkeypatch.setattr("noodler.app._module_close_at", lambda _p: None)
        monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
        # The press lands on a module.
        monkeypatch.setattr(
            "noodler.app._point_is_over_rack_background", lambda _p: False
        )
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: False
        )

        _begin_knob_drag("test", None, (KNOB_INTERACTION, None))
        _drag_knob("test", None, KNOB_INTERACTION)
        assert CANVAS_INTERACTION.panning is False

        # Now the rack shifts, so that same origin is over background.
        monkeypatch.setattr(
            "noodler.app._point_is_over_rack_background", lambda _p: True
        )
        for _ in range(5):
            _drag_knob("test", None, KNOB_INTERACTION)

        assert CANVAS_INTERACTION.panning is False, "the drag changed its mind"

        # A fresh press over background still pans.
        _end_knob_drag("test", None, KNOB_INTERACTION)
        monkeypatch.setattr(
            "noodler.app._mouse_is_over_rack_background", lambda: True
        )
        _begin_knob_drag("test", None, (KNOB_INTERACTION, None))
        _drag_knob("test", None, KNOB_INTERACTION)
        assert CANVAS_INTERACTION.panning is True
    finally:
        dpg.destroy_context()


def _add_one_module(runtime, module_id: str = "classic_vco") -> str:
    """Put one ordinary module in the rack and return its node."""
    _add_selected_module("test", None, (runtime, module_id))
    return INSTANCE_NODE_TAGS[
        next(
            instance_id
            for instance_id in runtime.patch.modules
            if instance_id != "master"
        )
    ]


def test_the_rack_is_centred_only_once_it_can_be_measured(monkeypatch) -> None:
    """A panel has no size until it has been drawn once.

    Centring before then centres a one-by-one point rather than a rack, which
    lands the panel wherever its own corner falls — off the edge, as often as
    not.
    """
    dpg.create_context()
    try:
        runtime = build_ui()
        # The master is pinned, so centring has to be judged on a module the
        # camera actually carries.
        node = _add_one_module(runtime)
        placed = tuple(dpg.get_item_pos(node))

        # The editor is laid out; the panel has not been drawn yet.
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [950, 700] if item == RACK else [0, 0],
        )
        _reveal_rack_once()
        assert CANVAS_INTERACTION.pending_reveal is True
        assert tuple(dpg.get_item_pos(node)) == placed, "moved too early"

        # Now it has a real size.
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [950, 700] if item == RACK else [232, 300],
        )
        _reveal_rack_once()

        x, y = (float(value) for value in dpg.get_item_pos(node))
        assert x + 116.0 == pytest.approx(475.0, abs=1.0)
        assert y + 150.0 == pytest.approx((700.0 - _console_band()) * 0.5, abs=1.0)
        assert CANVAS_INTERACTION.pending_reveal is False

        # And it never moves the rack again.
        _reveal_rack_once()
        assert float(dpg.get_item_pos(node)[0]) == pytest.approx(x)
    finally:
        dpg.destroy_context()


def test_centring_gives_up_waiting_rather_than_never_happening(monkeypatch) -> None:
    """A panel that never reports a size must not strand the rack off-screen."""
    dpg.create_context()
    try:
        build_ui()
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [950, 700] if item == RACK else [0, 0],
        )

        for _ in range(REVEAL_PATIENCE + 1):
            _reveal_rack_once()

        assert CANVAS_INTERACTION.pending_reveal is False
    finally:
        dpg.destroy_context()


def test_a_barely_laid_out_viewport_is_not_believed(monkeypatch) -> None:
    """A viewport reports a small non-zero size for its first frames.

    Centring against two pixels moves the rack almost exactly as far left as
    the panel started, which is how the system output kept arriving clipped by
    the left edge.
    """
    dpg.create_context()
    try:
        runtime = build_ui()
        node = _add_one_module(runtime)
        placed = tuple(dpg.get_item_pos(node))
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [2, 2] if item == RACK else [232, 300],
        )

        for _ in range(20):
            _reveal_rack_once()

        assert tuple(dpg.get_item_pos(node)) == placed
        assert CANVAS_INTERACTION.pending_reveal is True, "still waiting"

        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [950, 700] if item == RACK else [232, 300],
        )
        _reveal_rack_once()

        x, y = (float(value) for value in dpg.get_item_pos(node))
        assert x + 116.0 == pytest.approx(475.0, abs=1.0)
        assert y + 150.0 == pytest.approx((700.0 - _console_band()) * 0.5, abs=1.0)
    finally:
        dpg.destroy_context()


def test_double_clicking_a_cable_unpatches_it(monkeypatch) -> None:
    """A node editor gives no way to pull a plug back out of its jack."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        before = len(runtime.patch.cables)
        link = dpg.get_alias_id(MIXER_LPG_LINK)
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [link])
        monkeypatch.setattr("noodler.app._hovered_knob", lambda: None)

        _toggle_module_from_title("test", None, runtime)

        assert len(runtime.patch.cables) == before - 1
        assert not dpg.does_item_exist(MIXER_LPG_LINK)
    finally:
        dpg.destroy_context()


def test_a_double_click_elsewhere_still_folds_a_module(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [])
        monkeypatch.setattr("noodler.app._hovered_knob", lambda: None)
        monkeypatch.setattr(
            "noodler.app._module_title_at", lambda _position: VCO_NODE
        )

        _toggle_module_from_title("test", None, runtime)

        assert MODULE_COLLAPSE.is_collapsed(VCO_NODE)
    finally:
        dpg.destroy_context()



def _tidied_offset(frame_rate: float, seconds: float) -> float:
    """How far a tidied module still has to travel after some wall-clock time."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _tidy_rack("test", None, runtime)
        target = TIDY_TARGETS.get(VCO_NODE)
        assert target is not None
        remaining = seconds
        step = 1.0 / frame_rate
        while remaining > 0.0:
            _settle_rack_rails(min(step, remaining))
            remaining -= step
        return float(dpg.get_item_pos(VCO_NODE)[0]) - target[0]
    finally:
        dpg.destroy_context()


def test_tidying_settles_identically_at_60_and_240_hz() -> None:
    """The rack must not rearrange twice as fast on a ProMotion panel."""
    slow = _tidied_offset(60.0, seconds=0.05)
    fast = _tidied_offset(240.0, seconds=0.05)
    assert slow == pytest.approx(fast, abs=1.5)


def test_a_tidied_module_lands_exactly_where_it_was_sent() -> None:
    assert _tidied_offset(120.0, seconds=1.5) == pytest.approx(0.0, abs=0.5)


def test_tidy_orders_the_rack_by_the_way_signal_flows() -> None:
    """The patch already knows left-to-right; tidying just reads it."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)

        _tidy_rack("test", None, runtime)

        placed = {node: target for node, target in TIDY_TARGETS.items()}
        order = [INSTANCE_NODE_TAGS[m] for m in ("vco", "mixer", "low_pass_gate", "reverb")]
        positions = [placed[node] for node in order if node in placed]
        assert positions == sorted(positions), "signal order, left to right"
        assert "TIDIED" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_a_module_left_alone_is_never_moved() -> None:
    """The rails kept having opinions after the hand had let go."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        placed = tuple(dpg.get_item_pos(VCO_NODE))
        dpg.set_item_pos(VCO_NODE, [placed[0] + 260.0, placed[1] + 130.0])
        moved = tuple(dpg.get_item_pos(VCO_NODE))

        for _ in range(600):
            _settle_rack_rails(1 / 120)

        assert tuple(dpg.get_item_pos(VCO_NODE)) == moved
    finally:
        dpg.destroy_context()


def test_a_module_dragged_during_a_tidy_is_left_alone(monkeypatch) -> None:
    """Tidying must let go the moment the user takes hold of something.

    The dragged module is found by the panel that has left the spring driving
    it, which is evidence rather than the guesswork that hover and geometry
    turned out to be.
    """
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _tidy_rack("test", None, runtime)
        _settle_rack_rails(1 / 120)

        monkeypatch.setattr(
            dpg, "is_mouse_button_dragging", lambda button, threshold: True
        )
        monkeypatch.setattr(dpg, "get_item_state", lambda _item: {})
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (-5_000.0, -5_000.0)
        )
        assert _node_that_moved() is None, "nothing has been picked up"

        grabbed = tuple(dpg.get_item_pos(VCO_NODE))
        dpg.set_item_pos(VCO_NODE, [grabbed[0] - 180.0, grabbed[1]])
        assert _node_that_moved() == VCO_NODE

        for _ in range(120):
            _settle_rack_rails(1 / 120)
        assert float(dpg.get_item_pos(VCO_NODE)[0]) == pytest.approx(
            grabbed[0] - 180.0, abs=2.0
        )
        assert VCO_NODE not in TIDY_TARGETS, "the tidy let go of it"
    finally:
        dpg.destroy_context()
