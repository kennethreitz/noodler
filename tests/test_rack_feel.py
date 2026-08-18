"""How the rack responds: settling, momentum, ballistics, and the keyboard."""

import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    AUDIO_RAIL,
    CANVAS_INTERACTION,
    CONTROL_STATUS,
    DEFAULT_CONTROL_STATUS,
    INSTANCE_NODE_TAGS,
    KNOB_INTERACTION,
    METER_BALLISTICS,
    MIXER_LPG_LINK,
    MODULE_CLOSE_LAYER,
    MODULE_SELECTOR,
    OUTPUT_METER,
    OUTPUT_NODE,
    RACK_NODES,
    RACK_OUTLINE_BODY,
    RACK_RAILS,
    RACK,
    RAIL_SPRINGS,
    SAVE_PATCH_DIALOG,
    VCO_NODE,
    _add_selected_module,
    _begin_knob_drag,
    _control_position,
    _delete_rack_selection,
    _dismiss_rack_focus,
    _frame_rack,
    _glide_rack,
    _module_close_at,
    _module_close_bounds,
    _rack_content_bounds,
    _queue_rack_zoom,
    _refresh_ui,
    _release_pan_momentum,
    _remove_module_node,
    _reveal_node,
    _settle_rack_rails,
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


def _displaced_rail_offset(frame_rate: float, seconds: float) -> float:
    """Lift a module off its rail and report how far it has fallen back."""
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        node_x = float(dpg.get_item_pos(VCO_NODE)[0])
        rail_y = CANVAS_INTERACTION.rail_y[AUDIO_RAIL]
        dpg.set_item_pos(VCO_NODE, [node_x, rail_y + 220.0])
        RAIL_SPRINGS.clear()

        remaining = seconds
        step = 1.0 / frame_rate
        while remaining > 0.0:
            _settle_rack_rails(min(step, remaining))
            remaining -= step
        return float(dpg.get_item_pos(VCO_NODE)[1]) - rail_y
    finally:
        dpg.destroy_context()


def test_rail_settling_is_identical_at_60_and_240_hz() -> None:
    """The rack must not animate twice as fast on a ProMotion panel."""
    slow = _displaced_rail_offset(60.0, seconds=0.05)
    fast = _displaced_rail_offset(240.0, seconds=0.05)
    assert slow == pytest.approx(fast, abs=1.0)
    assert 0.0 < fast < 220.0, "the module should be mid-flight, not parked"


def test_a_settled_module_lands_exactly_on_its_rail() -> None:
    """A spring arrives, so no snap threshold has to pop the last pixel."""
    assert _displaced_rail_offset(120.0, seconds=1.0) == 0.0


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
        assert "PK" in dpg.get_item_configuration(OUTPUT_METER)["overlay"]
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


def test_delete_removes_a_selected_module_and_forgets_it(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        monkeypatch.setattr(dpg, "get_selected_links", lambda _rack: [])
        monkeypatch.setattr(
            dpg, "get_selected_nodes", lambda _rack: [dpg.get_alias_id(VCO_NODE)]
        )

        _delete_rack_selection("test", None, runtime)

        assert "vco" not in runtime.patch.modules
        assert not dpg.does_item_exist(VCO_NODE)
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
        assert not dpg.does_item_exist(node)
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
        assert not dpg.does_item_exist(node)
    finally:
        dpg.destroy_context()


def test_delete_is_ignored_while_the_module_browser_is_open(monkeypatch) -> None:
    """Most Mac keyboards send Backspace for Delete, so the search field wins."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        dpg.show_item(MODULE_SELECTOR)
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


def test_escape_closes_the_browser_before_clearing_the_selection() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        dpg.show_item(MODULE_SELECTOR)

        _dismiss_rack_focus("test", None, runtime)
        assert not dpg.is_item_shown(MODULE_SELECTOR)

        _dismiss_rack_focus("test", None, runtime)
        assert dpg.get_value(CONTROL_STATUS) == DEFAULT_CONTROL_STATUS
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
            dpg, "get_item_rect_size", lambda item: [900, 600]
        )
        before = _rack_content_bounds()
        assert before is not None

        _translate_rack(-4_000.0, -2_500.0)
        flung = _rack_content_bounds()
        assert flung[0] < -3_000.0

        _frame_rack("test", None, runtime)
        _settle_camera()

        framed = _rack_content_bounds()
        centre_x = (framed[0] + framed[2]) * 0.5
        centre_y = (framed[1] + framed[3]) * 0.5
        assert centre_x == pytest.approx(450.0, abs=2.0)
        assert centre_y == pytest.approx(300.0, abs=2.0)
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
        monkeypatch.setattr(dpg, "get_item_rect_size", lambda item: [900, 600])
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
        dpg.set_item_pos(VCO_NODE, [300.0, 200.0])

        assert _reveal_node(VCO_NODE) is False
        assert CANVAS_INTERACTION.recenter_x.target == 0.0
        assert CANVAS_INTERACTION.recenter_y.target == 0.0
    finally:
        dpg.destroy_context()
