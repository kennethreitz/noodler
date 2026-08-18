"""The master mixer, which every rack has and none can remove.

It replaced the system output: a node with three jacks and no mixer behind
them, which had to be found before anything could be heard and could be panned
off the edge of the window while you looked for it.
"""

import dearpygui.dearpygui as dpg
import numpy as np
import pytest

from noodler.app import (
    CANVAS_INTERACTION,
    INSTANCE_NODE_TAGS,
    MASTER_ID,
    OUTPUT_NODE,
    RACK,
    _add_selected_module,
    _patch_link_created,
    _remove_module_node,
    _settle_console,
    _translate_rack,
    adopt_output_taps,
    build_ui,
    ensure_master,
)
from noodler.module_providers.builtin import BuiltinProvider, MASTER_CHANNELS, MasterMixer
from noodler.patch import OutputChannel, PatchGraph


def test_every_rack_has_a_master_already_reaching_the_speakers() -> None:
    patch = PatchGraph()
    master = ensure_master(patch)

    assert isinstance(master, MasterMixer)
    assert patch.modules[MASTER_ID] is master
    assert {tap.channel for tap in patch.output_taps} == {
        OutputChannel.LEFT,
        OutputChannel.RIGHT,
    }
    assert all(tap.source.module_id == MASTER_ID for tap in patch.output_taps)


def test_asking_twice_does_not_wire_it_twice() -> None:
    patch = PatchGraph()
    first = ensure_master(patch)
    second = ensure_master(patch)

    assert first is second
    assert len(patch.output_taps) == 2


def test_patching_a_channel_is_all_it_takes_to_be_heard() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        vco = INSTANCE_NODE_TAGS["classic_vco"]

        silent = runtime.patch.render_stereo(256, 48_000.0)
        _patch_link_created(
            "test", (f"{vco}.saw", f"{OUTPUT_NODE}.channel_1"), runtime
        )
        heard = runtime.patch.render_stereo(256, 48_000.0)

        assert float(np.max(np.abs(silent))) == 0.0
        assert float(np.max(np.abs(heard))) > 0.0
    finally:
        dpg.destroy_context()


def test_the_camera_does_not_carry_the_console() -> None:
    from noodler.app import CONSOLE_STRIP

    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        vco = INSTANCE_NODE_TAGS["classic_vco"]
        strip = CONSOLE_STRIP.format(channel=1)
        pinned = tuple(dpg.get_item_pos(strip))
        moved = tuple(dpg.get_item_pos(vco))

        _translate_rack(-140.0, 60.0)

        assert tuple(dpg.get_item_pos(strip)) == pinned
        assert tuple(dpg.get_item_pos(vco)) == (moved[0] - 140, moved[1] + 60)
    finally:
        dpg.destroy_context()


def test_the_console_settles_along_the_bottom_edge(monkeypatch) -> None:
    from noodler.app import CONSOLE_STRIP

    dpg.create_context()
    try:
        build_ui()
        strip = CONSOLE_STRIP.format(channel=1)
        dpg.set_item_pos(strip, [10.0, 40.0])
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [950, 700] if item == RACK else [232, 300],
        )

        _settle_console()

        x, y = (float(value) for value in dpg.get_item_pos(strip))
        assert y + 300.0 == pytest.approx(700.0 - 14.0, abs=1.0), "along the bottom"
        assert x >= 14.0, "and in from the left edge"
    finally:
        dpg.destroy_context()


def test_a_barely_laid_out_viewport_does_not_move_the_console(monkeypatch) -> None:
    from noodler.app import CONSOLE_STRIP

    dpg.create_context()
    try:
        build_ui()
        strip = CONSOLE_STRIP.format(channel=1)
        placed = tuple(dpg.get_item_pos(strip))
        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [2, 2] if item == RACK else [232, 300],
        )

        _settle_console()

        assert tuple(dpg.get_item_pos(strip)) == placed
    finally:
        dpg.destroy_context()


def test_the_console_cannot_be_removed() -> None:
    from noodler.app import CONSOLE_STRIP

    dpg.create_context()
    try:
        runtime = build_ui()

        assert _remove_module_node(CONSOLE_STRIP.format(channel=1), runtime) is False
        assert _remove_module_node(OUTPUT_NODE, runtime) is False
        assert MASTER_ID in runtime.patch.modules
        assert len(runtime.patch.output_taps) == 2
    finally:
        dpg.destroy_context()


def test_a_patch_that_predates_the_master_keeps_its_sound() -> None:
    """Old documents tapped the output directly. Those taps become channels."""
    provider = BuiltinProvider()
    patch = PatchGraph()
    patch.add_module("reverb", provider.create("reverb"))
    patch.connect_output("reverb", "left", channel=OutputChannel.LEFT)
    patch.connect_output("reverb", "right", channel=OutputChannel.RIGHT)

    adopt_output_taps(patch)

    assert [
        (cable.source.port_id, cable.target.module_id, cable.target.port_id)
        for cable in patch.cables
    ] == [
        ("left", MASTER_ID, "channel_1"),
        ("right", MASTER_ID, "channel_2"),
    ]
    assert all(tap.source.module_id == MASTER_ID for tap in patch.output_taps)
    # Where a tap was becomes where its channel is panned: the same statement.
    master = patch.modules[MASTER_ID]
    assert master.parameters.pans[0] == -1.0
    assert master.parameters.pans[1] == 1.0


def test_a_patch_with_more_taps_than_channels_keeps_what_it_can() -> None:
    provider = BuiltinProvider()
    patch = PatchGraph()
    for index in range(MASTER_CHANNELS + 2):
        patch.add_module(f"vco_{index}", provider.create("classic_vco"))
        patch.connect_output(f"vco_{index}", "saw", channel=OutputChannel.BOTH)

    adopt_output_taps(patch)

    assert len(patch.cables) == MASTER_CHANNELS
    assert all(tap.source.module_id == MASTER_ID for tap in patch.output_taps)


def test_nothing_to_adopt_leaves_a_patch_alone() -> None:
    patch = PatchGraph()
    adopt_output_taps(patch)

    assert patch.modules == {}
    assert patch.output_taps == ()


def test_each_strip_has_a_jack_post_standing_above_its_middle(monkeypatch) -> None:
    """The jack is a separate, invisible node whose pin is at the strip's top centre."""
    from noodler.app import CONSOLE_POST, CONSOLE_STRIP, JACK_POST_LIFT, POST_ANCHORS

    dpg.create_context()
    try:
        build_ui()
        assert len(POST_ANCHORS) == 14  # eight channels; a send out and L/R in per effect
        strip = CONSOLE_STRIP.format(channel=3)
        post = CONSOLE_POST.format(name="channel_3")
        assert dpg.does_item_exist(f"{OUTPUT_NODE}.channel_3")
        parent = dpg.get_item_parent(f"{OUTPUT_NODE}.channel_3")
        assert parent in (post, dpg.get_alias_id(post))

        monkeypatch.setattr(
            dpg,
            "get_item_rect_size",
            lambda item: [950, 700] if item == RACK else ([8, 22] if item in POST_ANCHORS else [78, 118]),
        )
        _settle_console()

        strip_x, strip_y = dpg.get_item_pos(strip)
        post_x, post_y = dpg.get_item_pos(post)
        assert post_x == pytest.approx(strip_x + 39.0, abs=1.0), "the pin at the middle"
        assert post_y == pytest.approx(strip_y - JACK_POST_LIFT, abs=1.0), "standing above the top edge"
    finally:
        dpg.destroy_context()


def test_a_cable_to_the_console_is_drawn_by_hand_and_enters_from_above() -> None:
    from noodler.app import (
        CONSOLE_CABLE_PATHS,
        CONSOLE_LINK_HIDDEN_THEME,
        _console_cable_points,
        _is_console_route,
    )

    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        vco = INSTANCE_NODE_TAGS["classic_vco"]
        _patch_link_created("test", (f"{vco}.saw", f"{OUTPUT_NODE}.channel_1"), runtime)
        link = dpg.get_item_children(RACK).get(0, [])[0]
        route = dpg.get_item_user_data(link)
        assert _is_console_route(route)
        # imnodes' own copy of the link is invisible; the drawn one is what shows.
        assert dpg.get_item_alias(dpg.get_item_info(link)["theme"]) == CONSOLE_LINK_HIDDEN_THEME

        points = _console_cable_points((900.0, 400.0), (460.0, 630.0))
        assert points[1][1] == points[0][1], "leaves the module horizontally"
        assert points[2][0] == points[3][0], "and arrives at the jack vertically"
        assert points[2][1] < points[3][1], "from above"
    finally:
        dpg.destroy_context()
