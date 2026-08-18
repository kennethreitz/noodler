"""The rack is alive: jacks glow with signal, knobs answer the pointer, and a
module can be asked things with a right-click."""

import types

import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    CONTROL_STATUS,
    EMPTY_RACK_STATUS,
    KNOB_ARC,
    KNOB_INTERACTION,
    KNOB_STATES,
    OUTPUT_NODE,
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
        _new_patch()
        _consume_pending_open()
        assert dpg.get_value(CONTROL_STATUS) == EMPTY_RACK_STATUS
    finally:
        dpg.destroy_context()
