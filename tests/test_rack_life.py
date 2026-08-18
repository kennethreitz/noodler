"""The rack is alive: jacks glow with signal, knobs answer the pointer, and a
module can be asked things with a right-click."""

import types

import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    OUTPUT_NODE,
    SPACE_TAP,
    TRANSPORT,
    _patch_link_created,
    _space_pressed,
    _space_released,
    CABLE_SOURCES,
    CABLE_STEPS,
    CONTROL_STATUS,
    INSTANCE_NODE_TAGS,
    _add_selected_module,
    _duplicate_module,
    _has_unsaved_changes,
    _record_knob_turn,
    _set_knob_position,
    _set_knob_value,
    EMPTY_RACK_STATUS,
    KNOB_ARC,
    KNOB_INTERACTION,
    KNOB_STATES,
    PINNED_NODES,
    PORT_STEPS,
    PORT_TEXTS,
    RACK_HISTORY,
    TEXT,
    VCO_NODE,
    _consume_pending_open,
    _context_menu_tag,
    _control_position,
    _knobs_in_node,
    _new_patch,
    _refresh_jack_activity,
    _refresh_knob_hover,
    _reset_module_controls,
    _unplug_module,
    build_ui,
)


def _play(runtime, blocks: int = 4) -> None:
    runtime.patch.prepare(48_000.0, 256)
    for _ in range(blocks):
        runtime.patch.render_stereo(256, 48_000.0)
    runtime.audio._stream = types.SimpleNamespace(active=True)


def test_every_output_jack_is_indexed_and_the_console_is_not() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _refresh_jack_activity(runtime)
        assert ("vco", "saw") in PORT_TEXTS
        assert ("master", "send_a") in PORT_TEXTS, "the master's sends are outputs"
        assert ("master", "channel_1") not in PORT_TEXTS, "inputs are not lit"
        assert ("vco", "pitch") not in PORT_TEXTS
    finally:
        dpg.destroy_context()


def test_jacks_light_with_signal_and_go_dark_when_audio_stops() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _play(runtime)
        _refresh_jack_activity(runtime)
        assert PORT_STEPS[("vco", "saw")] > 0
        lit = sum(1 for step in PORT_STEPS.values() if step > 0)
        assert lit > 10

        runtime.audio._stream = None
        for _ in range(60):
            _refresh_jack_activity(runtime)
        assert all(step == 0 for step in PORT_STEPS.values())
    finally:
        dpg.destroy_context()


def test_a_silent_jack_is_dim_not_dark() -> None:
    """A jack that is patched but quiet still shows what colour it is."""
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _refresh_jack_activity(runtime)
        text, _signal = PORT_TEXTS[("vco", "saw")]
        colour = dpg.get_item_configuration(text)["color"]
        assert any(channel > 0.12 for channel in colour[:3])
    finally:
        dpg.destroy_context()


def test_the_knob_under_the_pointer_brightens_and_the_one_turning_more(monkeypatch) -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        art = KNOB_INTERACTION.art[knob]

        _refresh_knob_hover()
        idle = tuple(dpg.get_item_configuration(art.arc)["color"])

        monkeypatch.setattr(dpg, "is_item_hovered", lambda item: item == knob)
        _refresh_knob_hover()
        hover = tuple(dpg.get_item_configuration(art.arc)["color"])
        assert KNOB_STATES[knob] == "hover"
        assert sum(hover[:3]) > sum(idle[:3])

        KNOB_INTERACTION.active_knob = knob
        _refresh_knob_hover()
        active = tuple(dpg.get_item_configuration(art.arc)["color"])
        assert KNOB_STATES[knob] == "active"
        assert sum(active[:3]) > sum(hover[:3])

        KNOB_INTERACTION.active_knob = None
        monkeypatch.setattr(dpg, "is_item_hovered", lambda item: False)
        _refresh_knob_hover()
        assert KNOB_STATES[knob] == "idle"
        assert tuple(dpg.get_item_configuration(art.arc)["color"]) == idle
    finally:
        dpg.destroy_context()


def test_every_module_has_a_context_menu_and_the_console_does_not() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        assert dpg.does_item_exist(_context_menu_tag(VCO_NODE))
        for node in PINNED_NODES:
            assert not dpg.does_item_exist(_context_menu_tag(node))
    finally:
        dpg.destroy_context()


def test_reset_controls_puts_every_knob_on_the_panel_back() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        configuration = dpg.get_item_configuration(knob)
        configuration["callback"](
            knob, _control_position(880.0, 1.0, 20_000.0, True), configuration["user_data"]
        )
        assert runtime.vco.parameters.frequency == pytest.approx(880.0)
        assert len(_knobs_in_node(VCO_NODE)) >= 6

        _reset_module_controls(VCO_NODE)

        assert runtime.vco.parameters.frequency == pytest.approx(220.0)
        assert "RESET" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_unplugging_one_module_is_one_undoable_edit() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        before = len(runtime.patch.cables)

        _unplug_module(VCO_NODE, runtime)
        assert len(runtime.patch.cables) < before
        assert not any(
            "vco" in (c.source.module_id, c.target.module_id) for c in runtime.patch.cables
        )

        RACK_HISTORY.undo()
        assert len(runtime.patch.cables) == before
    finally:
        dpg.destroy_context()


def test_an_empty_rack_says_what_to_do_with_itself() -> None:
    dpg.create_context()
    try:
        build_ui()
        assert dpg.get_value(CONTROL_STATUS) == EMPTY_RACK_STATUS
    finally:
        dpg.destroy_context()


def test_a_new_rack_comes_with_its_sends_patched() -> None:
    from noodler.app import default_rack_preset

    preset = default_rack_preset()
    routes = {(c.source.module_id, c.source.port_id, c.target.module_id, c.target.port_id) for c in preset.cables}
    assert ("master", "send_a", "delay", "audio") in routes
    assert ("master", "send_b", "reverb", "audio") in routes
    assert ("delay", "output", "master", "return_a_left") in routes
    assert ("reverb", "wet_left", "master", "return_b_left") in routes
    assert ("reverb", "wet_right", "master", "return_b_right") in routes
    parameters = {m.instance_id: m.parameters for m in preset.modules}
    assert parameters["delay"]["mix"] == 1.0 and parameters["reverb"]["mix"] == 1.0
    assert parameters["reverb"]["space"] == "hall"


def test_cables_glow_with_the_jack_that_feeds_them() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _play(runtime)
        _refresh_jack_activity(runtime)
        assert CABLE_SOURCES, "every drawn cable knows its source"
        assert sum(1 for step in CABLE_STEPS.values() if step > 0) > 5
        # A cable's glow is its source jack's step, exactly.
        for link, (module_id, port_id, _signal) in CABLE_SOURCES.items():
            assert CABLE_STEPS[link] == PORT_STEPS.get((module_id, port_id), 0)
    finally:
        dpg.destroy_context()


def test_a_whole_knob_turn_is_one_undoable_edit() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        binding = KNOB_INTERACTION.bindings[knob]
        assert not _has_unsaved_changes()

        before = KNOB_INTERACTION.positions[knob]
        after = _control_position(880.0, 1.0, 20_000.0, True)
        _set_knob_position(knob, after)
        _set_knob_value(str(knob), after, binding)
        _record_knob_turn(knob, before, after)

        assert runtime.vco.parameters.frequency == pytest.approx(880.0)
        assert _has_unsaved_changes()
        assert RACK_HISTORY.done[-1].description == "TURN FREQUENCY"
        RACK_HISTORY.undo()
        assert runtime.vco.parameters.frequency == pytest.approx(220.0)
        RACK_HISTORY.redo()
        assert runtime.vco.parameters.frequency == pytest.approx(880.0)
    finally:
        dpg.destroy_context()


def test_a_turn_that_went_nowhere_is_not_an_edit() -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        position = KNOB_INTERACTION.positions[knob]
        _record_knob_turn(knob, position, position)
        assert not RACK_HISTORY.can_undo
    finally:
        dpg.destroy_context()


def test_duplicate_copies_the_settings_and_not_the_cables() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "pytheory_voice"))
        original = runtime.patch.modules["pytheory_voice"]
        original.parameters.instrument = "sitar"
        original.parameters.level = 0.31
        cables_before = len(runtime.patch.cables)

        _duplicate_module(INSTANCE_NODE_TAGS["pytheory_voice"], runtime)

        copy = runtime.patch.modules["pytheory_voice_2"]
        assert copy is not original
        assert copy.parameters.instrument == "sitar"
        assert copy.parameters.level == pytest.approx(0.31)
        assert len(runtime.patch.cables) == cables_before
        RACK_HISTORY.undo()
        assert "pytheory_voice_2" not in runtime.patch.modules
    finally:
        dpg.destroy_context()


def test_a_send_into_an_effect_makes_it_fully_wet() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "reverb"))
        reverb = runtime.patch.modules["reverb"]
        node = INSTANCE_NODE_TAGS["reverb"]
        assert reverb.parameters.mix < 1.0
        assert dpg.does_item_exist(f"{node}.control.mix"), "generic knobs are addressable"

        _patch_link_created("test", (f"{OUTPUT_NODE}.send_a", f"{node}.audio"), runtime)

        assert reverb.parameters.mix == pytest.approx(1.0)
        assert "FULLY WET" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_an_ordinary_cable_into_an_effect_leaves_its_mix_alone() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        _add_selected_module("test", None, (runtime, "reverb"))
        reverb = runtime.patch.modules["reverb"]
        before = reverb.parameters.mix
        _patch_link_created(
            "test",
            (f"{INSTANCE_NODE_TAGS['classic_vco']}.saw", f"{INSTANCE_NODE_TAGS['reverb']}.audio"),
            runtime,
        )
        assert reverb.parameters.mix == pytest.approx(before)
    finally:
        dpg.destroy_context()


def test_a_tap_of_space_toggles_playback_and_a_pan_does_not(monkeypatch) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        toggled = []
        monkeypatch.setattr("noodler.app._toggle_playback", lambda *a, **k: toggled.append(1))
        monkeypatch.setattr("noodler.app._keyboard_is_captured", lambda: False)

        _space_pressed("k", None, runtime)
        _space_released("k", None, runtime)
        assert toggled == [1], "a tap plays"

        _space_pressed("k", None, runtime)
        SPACE_TAP["panned"] = True
        _space_released("k", None, runtime)
        assert toggled == [1], "a space that panned was not a tap"

        _space_pressed("k", None, runtime)
        SPACE_TAP["down_at"] -= 1.0
        _space_released("k", None, runtime)
        assert toggled == [1], "a long hold is not a tap"
    finally:
        dpg.destroy_context()


def test_a_musical_output_lights_its_jack_instead_of_crashing() -> None:
    """The Key's scale is an object on a cable, not a number: it is simply lit."""
    from noodler.preset import read_patch_preset
    from pathlib import Path

    dpg.create_context()
    try:
        runtime = build_ui(preset=read_patch_preset(Path("examples/pelog-bell-garden.noodler")))
        _play(runtime)
        _refresh_jack_activity(runtime)
        assert PORT_STEPS[("key", "scale")] > 0
    finally:
        dpg.destroy_context()


def test_one_bad_frame_does_not_stop_the_heartbeat(monkeypatch) -> None:
    from noodler.app import _refresh_frame, LAST_FRAME_ERROR

    dpg.create_context()
    try:
        runtime = build_ui()
        scheduled = []
        monkeypatch.setattr(dpg, "set_frame_callback", lambda *a, **k: scheduled.append(a))
        monkeypatch.setattr("noodler.app._refresh_knob_hover", lambda: 1 / 0)

        _refresh_frame("frame", None, runtime)

        assert scheduled, "the next frame was still scheduled"
        assert "ZeroDivisionError" in LAST_FRAME_ERROR[0]
        assert "FRAME ERROR" in dpg.get_value(CONTROL_STATUS)
    finally:
        LAST_FRAME_ERROR[0] = ""
        dpg.destroy_context()


def test_scrolling_over_a_knob_turns_it_and_not_the_rack(monkeypatch) -> None:
    from noodler.app import CANVAS_INTERACTION, _consume_scroll, _close_scroll_turn

    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        knob = f"{VCO_NODE}.control.frequency"
        binding = KNOB_INTERACTION.bindings[knob]
        monkeypatch.setattr("noodler.app._hovered_knob", lambda: (knob, binding))
        placed = tuple(dpg.get_item_pos(VCO_NODE))
        before = runtime.vco.parameters.frequency

        for _ in range(5):
            CANVAS_INTERACTION.pending_scroll_y = 48.0
            _consume_scroll()

        assert runtime.vco.parameters.frequency > before, "up is more"
        assert tuple(dpg.get_item_pos(VCO_NODE)) == placed, "the rack did not move"
        _close_scroll_turn(force=True)
        assert RACK_HISTORY.done[-1].description == "TURN FREQUENCY"
        assert len(RACK_HISTORY.done) == 1, "five wheel clicks are one edit"
    finally:
        dpg.destroy_context()


def test_scrolling_elsewhere_still_pans() -> None:
    from noodler.app import CANVAS_INTERACTION, _consume_scroll

    dpg.create_context()
    try:
        build_ui(starter_patch=True)
        placed = tuple(dpg.get_item_pos(VCO_NODE))
        CANVAS_INTERACTION.pending_scroll_y = 48.0
        _consume_scroll()
        assert tuple(dpg.get_item_pos(VCO_NODE)) != placed
    finally:
        dpg.destroy_context()


def test_quit_new_and_open_ask_before_losing_unsaved_work() -> None:
    from noodler.app import (
        PENDING_OPEN,
        UNSAVED_DIALOG,
        _exit_noodler,
        _new_patch,
        _unsaved_cancel,
        _unsaved_discard,
    )
    import noodler.app as app

    dpg.create_context()
    try:
        runtime = build_ui()
        _new_patch()
        assert PENDING_OPEN, "nothing unsaved: New just happens"
        PENDING_OPEN.clear()

        _add_selected_module("test", None, (runtime, "classic_vco"))
        _new_patch()
        assert not PENDING_OPEN, "unsaved: New waits for an answer"
        assert dpg.is_item_shown(UNSAVED_DIALOG)
        _unsaved_cancel()
        assert not PENDING_OPEN and not dpg.is_item_shown(UNSAVED_DIALOG)

        _new_patch()
        _unsaved_discard()
        assert PENDING_OPEN, "don't save: it happens"
        PENDING_OPEN.clear()

        stopped = []
        app.dpg.stop_dearpygui = lambda: stopped.append(1)
        try:
            _exit_noodler()
            assert stopped, "just discarded, so nothing is unsaved: quit just quits"
        finally:
            del app.dpg.stop_dearpygui
    finally:
        dpg.destroy_context()


def test_saving_and_opening_feed_the_recent_list(tmp_path) -> None:
    from noodler.app import RECENT_MENU, _recent_documents, _save_patch_to

    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        _save_patch_to(runtime, tmp_path / "first.noodler")
        _save_patch_to(runtime, tmp_path / "second.noodler")

        assert [p.name for p in _recent_documents()] == ["second.noodler", "first.noodler"]
        labels = [
            dpg.get_item_configuration(item)["label"]
            for item in dpg.get_item_children(RECENT_MENU, slot=1)
        ]
        assert labels == ["second", "first"]
    finally:
        dpg.destroy_context()


def test_a_polarizing_gain_runs_from_minus_one_to_one_with_zero_up() -> None:
    """The panel reads a tuple item's constraints, and a bipolar knob rests at zero."""
    import math
    from noodler.app import _knob_geometry, _knobs_in_node

    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "polarizing_mixer"))
        node = INSTANCE_NODE_TAGS["polarizing_mixer"]
        knob = next(k for k in _knobs_in_node(node) if KNOB_INTERACTION.bindings[k].label == "1")
        binding = KNOB_INTERACTION.bindings[knob]
        assert (binding.minimum, binding.maximum) == (-1.0, 1.0)

        _centre, _radius, angle, arc = _knob_geometry(knob, binding.size)
        assert angle == pytest.approx(1.5 * math.pi), "zero is straight up"
        assert len(arc) <= 3, "nothing is lit at rest"
    finally:
        dpg.destroy_context()


def test_the_app_opens_with_play_showing_not_stop() -> None:
    from noodler.app import TRANSPORT_BUTTON, _refresh_transport_button

    dpg.create_context()
    try:
        runtime = build_ui()
        _refresh_transport_button(runtime)
        assert not runtime.audio.is_running
        assert "PLAY" in dpg.get_item_configuration(TRANSPORT_BUTTON)["label"]
    finally:
        dpg.destroy_context()
