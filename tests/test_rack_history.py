"""Undoing rack edits: cables, bulk unplugs, and whole modules."""

import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    AUDIO_RAIL,
    CONTROL_STATUS,
    INSTANCE_NODE_TAGS,
    MIXER_LPG_LINK,
    RACK,
    RACK_HISTORY,
    RACK_NODES,
    RACK_RAILS,
    VCO_NODE,
    _delete_rack_selection,
    _press_once,
    _release_stale_key_latches,
    _remove_module_node,
    _undo_or_redo_rack_edit,
    _unplug_all,
    build_ui,
)


def _drawn_cables() -> int:
    return len(dpg.get_item_children(RACK).get(0, ()))


def _vco_cables(runtime) -> int:
    return sum(
        1
        for cable in runtime.patch.cables
        if "vco" in (cable.source.module_id, cable.target.module_id)
    )


def test_a_rebuilt_rack_starts_with_no_history() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        assert not RACK_HISTORY.can_undo
        assert not RACK_HISTORY.can_redo
    finally:
        dpg.destroy_context()


def test_undo_puts_a_removed_module_back_with_its_cables() -> None:
    """One keypress can take a module and a dozen cables; one takes it back."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        cables_before = len(runtime.patch.cables)
        drawn_before = _drawn_cables()
        vco_cables = _vco_cables(runtime)
        assert vco_cables >= 3, "the starter patch should wire the VCO up well"

        assert _remove_module_node(VCO_NODE, runtime) is True
        assert "vco" not in runtime.patch.modules
        assert len(runtime.patch.cables) == cables_before - vco_cables

        assert RACK_HISTORY.undo() is not None

        assert "vco" in runtime.patch.modules
        assert len(runtime.patch.cables) == cables_before
        assert _drawn_cables() == drawn_before
        assert dpg.is_item_shown(VCO_NODE)
        assert VCO_NODE in RACK_NODES
        assert VCO_NODE in RACK_RAILS[AUDIO_RAIL]
        assert INSTANCE_NODE_TAGS["vco"] == VCO_NODE
    finally:
        dpg.destroy_context()


def test_the_restored_module_is_the_same_panel_not_a_rebuilt_one() -> None:
    """Undo must not cost a module the controls its own builder gave it."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        configuration = dpg.get_item_configuration(knob)
        binding = configuration["user_data"]
        configuration["callback"](knob, 0.5, binding)
        tuned = runtime.vco.parameters.frequency

        _remove_module_node(VCO_NODE, runtime)
        RACK_HISTORY.undo()

        assert dpg.does_item_exist(knob)
        assert runtime.patch.modules["vco"] is runtime.vco
        assert runtime.vco.parameters.frequency == pytest.approx(tuned)
    finally:
        dpg.destroy_context()


def test_redo_removes_the_module_again() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _remove_module_node(VCO_NODE, runtime)
        RACK_HISTORY.undo()
        assert "vco" in runtime.patch.modules

        assert RACK_HISTORY.redo() is not None

        assert "vco" not in runtime.patch.modules
        assert not dpg.is_item_shown(VCO_NODE)
        assert VCO_NODE not in RACK_NODES
    finally:
        dpg.destroy_context()


def test_undo_restores_one_unpatched_cable(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        cables_before = len(runtime.patch.cables)
        monkeypatch.setattr(
            dpg, "get_selected_links", lambda _rack: [dpg.get_alias_id(MIXER_LPG_LINK)]
        )
        monkeypatch.setattr(dpg, "get_selected_nodes", lambda _rack: [])
        _delete_rack_selection("test", None, runtime)
        assert len(runtime.patch.cables) == cables_before - 1

        RACK_HISTORY.undo()

        assert len(runtime.patch.cables) == cables_before
        assert any(
            cable.source.module_id == "mixer"
            and cable.target.module_id == "low_pass_gate"
            for cable in runtime.patch.cables
        )
    finally:
        dpg.destroy_context()


def test_undo_restores_everything_an_unplug_all_took() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        cables_before = len(runtime.patch.cables)
        taps_before = len(runtime.patch.output_taps)
        drawn_before = _drawn_cables()

        _unplug_all("test", None, runtime)
        assert runtime.patch.cables == ()
        assert runtime.patch.output_taps == ()

        RACK_HISTORY.undo()

        assert len(runtime.patch.cables) == cables_before
        assert len(runtime.patch.output_taps) == taps_before
        assert _drawn_cables() == drawn_before
    finally:
        dpg.destroy_context()


def test_a_fresh_edit_abandons_the_redo_branch() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _remove_module_node(VCO_NODE, runtime)
        RACK_HISTORY.undo()
        assert RACK_HISTORY.can_redo

        _unplug_all("test", None, runtime)

        assert not RACK_HISTORY.can_redo
    finally:
        dpg.destroy_context()


def test_the_undo_chord_needs_its_modifier(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _remove_module_node(VCO_NODE, runtime)

        monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
        _undo_or_redo_rack_edit("test", None, runtime)
        assert "vco" not in runtime.patch.modules, "a bare Z must not undo"

        monkeypatch.setattr(
            dpg, "is_key_down", lambda key: key != dpg.mvKey_ModShift
        )
        _undo_or_redo_rack_edit("test", None, runtime)

        assert "vco" in runtime.patch.modules
        assert "UNDID" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_the_shifted_chord_redoes(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _remove_module_node(VCO_NODE, runtime)
        monkeypatch.setattr(
            dpg, "is_key_down", lambda key: key != dpg.mvKey_ModShift
        )
        _undo_or_redo_rack_edit("test", None, runtime)
        assert "vco" in runtime.patch.modules

        monkeypatch.setattr(dpg, "is_key_down", lambda _key: True)
        _undo_or_redo_rack_edit("test", None, runtime)

        assert "vco" not in runtime.patch.modules
        assert "REDID" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_an_empty_history_says_so(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        monkeypatch.setattr(
            dpg, "is_key_down", lambda key: key != dpg.mvKey_ModShift
        )

        _undo_or_redo_rack_edit("test", None, runtime)

        assert "NOTHING TO UNDO" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_holding_undo_does_not_unwind_the_whole_history(monkeypatch) -> None:
    """A key repeat should not cost the user every edit they made."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _remove_module_node(VCO_NODE, runtime)
        _unplug_all("test", None, runtime)
        assert len(RACK_HISTORY.done) == 2

        # Command down, Shift up: an undo chord, repeating while held.
        monkeypatch.setattr(
            dpg, "is_key_down", lambda key: key != dpg.mvKey_ModShift
        )
        held = _press_once(dpg.mvKey_Z, _undo_or_redo_rack_edit)
        for _ in range(12):
            held("test", None, runtime)
            _release_stale_key_latches()

        assert len(RACK_HISTORY.done) == 1, "one press, one undo"
        assert "vco" not in runtime.patch.modules, "the earlier edit stands"
    finally:
        dpg.destroy_context()


def test_releasing_the_key_arms_the_next_press(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _remove_module_node(VCO_NODE, runtime)
        _unplug_all("test", None, runtime)
        held = _press_once(dpg.mvKey_Z, _undo_or_redo_rack_edit)

        def _press_and_release() -> None:
            monkeypatch.setattr(
                dpg, "is_key_down", lambda key: key != dpg.mvKey_ModShift
            )
            held("test", None, runtime)
            monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
            _release_stale_key_latches()

        _press_and_release()
        _press_and_release()

        assert not RACK_HISTORY.can_undo
        assert "vco" in runtime.patch.modules, "both edits came back"
    finally:
        dpg.destroy_context()
