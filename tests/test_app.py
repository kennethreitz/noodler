import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    ADD_MODULE_BUTTON,
    APP_FONT,
    APP_THEME,
    AUDIO_RAIL,
    CANVAS_INTERACTION,
    CONTROL_STATUS,
    FUNCTION_NODE,
    LPG_NODE,
    LPG_REVERB_LINK,
    MIXER_NODE,
    MODULE_SELECTOR,
    MODULE_SELECTOR_SEARCH,
    MODULE_SELECTOR_STATUS,
    MODULE_COLLAPSE,
    MIXER_LPG_LINK,
    OUTPUT_NODE,
    PINNED_NODES,
    OUTPUT_METER,
    PRIMARY_WINDOW,
    RACK,
    RACK_NODES,
    RACK_OUTLINE_BODY,
    RACK_OUTLINE_STATUS,
    RACK_RAILS,
    RACK_WORKSPACE,
    REVERB_LEFT_OUTPUT_LINK,
    REVERB_NODE,
    REVERB_RIGHT_OUTPUT_LINK,
    SCALE_NODE,
    SCALE_NAME_CONTROL,
    SCALE_NOTE_STATUS,
    SCALE_SYSTEM_CONTROL,
    SCALE_LPG_LINK,
    SCALE_VCO_LINK,
    OPEN_PATCH_MENU_ITEM,
    SAVE_AS_MENU_ITEM,
    SAVE_PATCH_MENU_ITEM,
    SAVE_PATCH_DIALOG,
    UTILITY_REVERB_LINK,
    UTILITY_VCO_LINK,
    UNPLUG_ALL_BUTTON,
    VCO_NODE,
    VCO_MIXER_LINK,
    VCO_TRIANGLE_MIXER_LINK,
    WOGGLE_NODE,
    WOGGLE_MIXER_LINK,
    WOGGLE_REVERB_LINK,
    WOGGLE_SCALE_LINK,
    WOGGLE_VCO_LINK,
    ZOOM_IN_BUTTON,
    ZOOM_RESET_BUTTON,
    INPUT_HANDLERS,
    INSTANCE_NODE_TAGS,
    KNOB_INTERACTION,
    _control_position,
    _capture_current_preset,
    _add_selected_module,
    _begin_knob_drag,
    _drag_knob,
    _end_knob_drag,
    _filter_module_selector,
    _module_library_category_tag,
    _module_library_section_tag,
    _mouse_is_over_rack_background,
    _node_attributes,
    _pan_rack,
    _patch_link_created,
    _point_is_over_rack_background,
    _queue_rack_zoom,
    _rack_font_tag,
    _rail_x_targets,
    _set_rack_zoom,
    _set_module_collapsed,
    _set_dynamic_parameter,
    _save_patch_dialog,
    _settle_rack_zoom,
    _knob_bounds,
    _zoomed_position,
    build_ui,
)
from noodler.module_providers.builtin import BUILTIN_PROVIDER_MANIFEST
from noodler.motion import KnobDrag
from noodler.patch import OutputChannel
from noodler.preset import read_patch_preset


def _descendant_labels(item: int | str) -> set[str]:
    labels: set[str] = set()
    for children in dpg.get_item_children(item).values():
        for child in children:
            label = dpg.get_item_label(child)
            if label:
                labels.add(label)
            if dpg.get_item_type(child).endswith("mvText"):
                labels.add(str(dpg.get_value(child)))
            labels.update(_descendant_labels(child))
    return labels


def test_default_rack_starts_quiet_with_only_the_master() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()

        # The rack is empty of anything the user did not put there, but the
        # master is always present and already reaching the speakers.
        assert tuple(runtime.patch.modules) == ("master",)
        assert runtime.patch.cables == ()
        assert {tap.channel.value for tap in runtime.patch.output_taps} == {
            "left",
            "right",
        }
        # The console: eight strips and the master, and nothing else.
        # Eight strips, two returns, the master, and twelve jack posts.
        assert set(RACK_NODES) == set(PINNED_NODES)
        assert len(PINNED_NODES) == 23
        assert dpg.does_item_exist(OUTPUT_NODE)
        assert not dpg.does_item_exist(VCO_NODE)
        assert not dpg.does_item_exist(WOGGLE_NODE)
        # Adding a module is the library pane's job, and saving is the File
        # menu's; neither needs a permanent seat on the toolbar.
        assert not dpg.does_item_exist(ADD_MODULE_BUTTON)
        assert dpg.does_item_exist(OPEN_PATCH_MENU_ITEM)
        assert dpg.does_item_exist(SAVE_PATCH_MENU_ITEM)
        assert dpg.does_item_exist(SAVE_AS_MENU_ITEM)
        assert dpg.get_value(RACK_OUTLINE_STATUS) == "1 PANEL  ·  0 CABLES"
        outline = _descendant_labels(RACK_OUTLINE_BODY)
        assert {"SIGNAL FLOW", "CONSOLE", "NO SIGNAL CONNECTED"} <= (
            outline
        )

        # The master is saved like any module -- its levels are worth keeping
        # -- and restored into the one every rack already has.
        captured = _capture_current_preset(runtime, "Untitled Patch")
        assert [module.instance_id for module in captured.modules] == ["master"]
        assert captured.cables == ()
        assert {tap.channel.value for tap in captured.output_taps} == {
            "left",
            "right",
        }
        assert [node.node_id for node in captured.view.nodes] == ["master"]
    finally:
        dpg.destroy_context()


@pytest.mark.parametrize("starter_patch", [False, True])
def test_patch_status_is_a_footer_below_the_rack(starter_patch: bool) -> None:
    dpg.create_context()
    try:
        build_ui(starter_patch=starter_patch)

        window_items = dpg.get_item_children(PRIMARY_WINDOW).get(1, ())
        workspace = dpg.get_alias_id(RACK_WORKSPACE)
        status = dpg.get_alias_id(CONTROL_STATUS)
        rack_parent = dpg.get_item_parent(RACK)
        if rack_parent not in {RACK_WORKSPACE, workspace}:
            rack_parent = dpg.get_item_parent(rack_parent)
        assert rack_parent in {RACK_WORKSPACE, workspace}
        # The footer now carries a trace beside the words, so the status sits
        # in a row of its own; that row is what belongs to the window.
        status_parent = dpg.get_item_parent(CONTROL_STATUS)
        if status_parent not in {PRIMARY_WINDOW, dpg.get_alias_id(PRIMARY_WINDOW)}:
            status_parent = dpg.get_item_parent(status_parent)
        assert status_parent in {
            PRIMARY_WINDOW,
            dpg.get_alias_id(PRIMARY_WINDOW),
        }
        # Ordering is checked on the footer row, which is what the window holds.
        footer = dpg.get_item_parent(CONTROL_STATUS)
        if footer in {PRIMARY_WINDOW, dpg.get_alias_id(PRIMARY_WINDOW)}:
            footer = status
        assert window_items.index(workspace) < window_items.index(footer)
    finally:
        dpg.destroy_context()


def test_starter_patch_ui_tracks_the_mixer_channel_count() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(mixer_channels=6, starter_patch=True)

        for item in (
            PRIMARY_WINDOW,
            RACK,
            VCO_NODE,
            MIXER_NODE,
            FUNCTION_NODE,
            OUTPUT_NODE,
            WOGGLE_NODE,
            SCALE_NODE,
            LPG_NODE,
            REVERB_NODE,
            SCALE_SYSTEM_CONTROL,
            SCALE_NAME_CONTROL,
            SCALE_NOTE_STATUS,
            WOGGLE_VCO_LINK,
            WOGGLE_SCALE_LINK,
            SCALE_VCO_LINK,
            SCALE_LPG_LINK,
            UTILITY_VCO_LINK,
            UTILITY_REVERB_LINK,
            VCO_MIXER_LINK,
            VCO_TRIANGLE_MIXER_LINK,
            WOGGLE_MIXER_LINK,
            MIXER_LPG_LINK,
            LPG_REVERB_LINK,
            WOGGLE_REVERB_LINK,
            REVERB_LEFT_OUTPUT_LINK,
            REVERB_RIGHT_OUTPUT_LINK,
            OUTPUT_METER,
            INPUT_HANDLERS,
        ):
            assert dpg.does_item_exist(item)
        assert runtime.mixer.parameters.channels == 6
        assert runtime.mixer.parameters.gains[:3] == (0.48, 0.14, 0.12)
        assert runtime.utility.parameters.channel_1.cycle is True
        assert runtime.utility.parameters.channel_1.rise_seconds == 11.0
        assert runtime.utility.parameters.channel_1.fall_seconds == 17.0
        assert runtime.utility.parameters.channel_4.cycle is True
        assert dpg.does_item_exist(APP_FONT)
        assert dpg.does_item_exist(APP_THEME)
        assert dpg.does_item_exist(f"{MIXER_NODE}.input_6")
        frequency_control = f"{VCO_NODE}.control.frequency"
        assert dpg.get_item_type(frequency_control).endswith("mvDrawlist")
        configuration = dpg.get_item_configuration(frequency_control)
        binding = configuration["user_data"]
        configuration["callback"](
            frequency_control,
            _control_position(440.0, 1.0, 20_000.0, True),
            binding,
        )
        assert runtime.vco.parameters.frequency == pytest.approx(440.0)
        assert runtime.vco.parameters.frequency_cv_2_amount == pytest.approx(0.018)
        rate_control = f"{WOGGLE_NODE}.control.rate"
        rate_configuration = dpg.get_item_configuration(rate_control)
        rate_configuration["callback"](
            rate_control,
            0.0,
            rate_configuration["user_data"],
        )
        assert runtime.wogglebug.parameters.clock_rate_hz == pytest.approx(0.01)
        system_control = dpg.get_item_configuration(SCALE_SYSTEM_CONTROL)
        system_control["callback"](
            SCALE_SYSTEM_CONTROL,
            "blues",
            system_control["user_data"],
        )
        scale_control = dpg.get_item_configuration(SCALE_NAME_CONTROL)
        scale_control["callback"](
            SCALE_NAME_CONTROL,
            "minor pentatonic",
            scale_control["user_data"],
        )
        assert runtime.scale_generator.parameters.system == "blues"
        assert runtime.scale_generator.parameters.scale_name == "minor pentatonic"
        start = _control_position(440.0, 1.0, 20_000.0, True)
        minimum, maximum = _knob_bounds(binding)

        def _sweep(delta_y: float, *, fine: bool) -> float:
            drag = KnobDrag(minimum=minimum, maximum=maximum)
            drag.begin(start)
            return drag.advance(delta_y, 1.0 / 60.0, fine=fine)

        coarse = _sweep(-45.0, fine=False)
        fine = _sweep(-45.0, fine=True)
        assert coarse > fine > start
        # There is no hint tooltip on a knob any more: the status bar says
        # what the value is while it turns, and nothing covers the panel.
        KNOB_INTERACTION.active_knob = frequency_control
        _end_knob_drag("test", None, KNOB_INTERACTION)
        assert KNOB_INTERACTION.active_knob is None
        assert dpg.get_item_configuration(
            f"{FUNCTION_NODE}.channel_1"
        )["show"] is True
        assert dpg.get_item_configuration(
            f"{FUNCTION_NODE}.channel_1_signal"
        )["show"] is True
        assert dpg.get_item_configuration(
            f"{FUNCTION_NODE}.channel_4_eoc"
        )["show"] is True
        assert runtime.patch.processing_order[:-1] == (
            "utility",
            "wogglebug",
            "scale_generator",
            "vco",
            "mixer",
            "low_pass_gate",
            "reverb",
        )
        assert [
            (
                cable.source.module_id,
                cable.source.port_id,
                cable.target.module_id,
                cable.target.port_id,
            )
            for cable in runtime.patch.cables
        ] == [
            ("utility", "channel_1", "vco", "morph_cv"),
            ("wogglebug", "woggle", "vco", "frequency_cv_2"),
            ("wogglebug", "clock", "scale_generator", "clock"),
            ("scale_generator", "pitch", "vco", "pitch"),
            ("vco", "morph", "mixer", "input_1"),
            ("vco", "triangle", "mixer", "input_2"),
            ("wogglebug", "ring_mod", "mixer", "input_3"),
            ("mixer", "output", "low_pass_gate", "audio"),
            ("scale_generator", "trigger", "low_pass_gate", "strike"),
            ("utility", "channel_4", "reverb", "decay_cv"),
            ("low_pass_gate", "output", "reverb", "audio"),
            ("wogglebug", "burst", "reverb", "freeze"),
            # The starter reaches the speakers through the master, on channels
            # that can be turned down, rather than by tapping the output.
            ("reverb", "left", "master", "channel_1"),
            ("reverb", "right", "master", "channel_2"),
        ]
        assert len(runtime.patch.output_taps) == 2
        assert [tap.source.module_id for tap in runtime.patch.output_taps] == [
            "master",
            "master",
        ]
        assert [tap.channel for tap in runtime.patch.output_taps] == [
            OutputChannel.LEFT,
            OutputChannel.RIGHT,
        ]
        assert runtime.wogglebug is runtime.patch.modules["wogglebug"]
        assert runtime.scale_generator is runtime.patch.modules["scale_generator"]
        assert runtime.low_pass_gate is runtime.patch.modules["low_pass_gate"]
        assert runtime.reverb is runtime.patch.modules["reverb"]
    finally:
        dpg.destroy_context()


def test_module_selector_exposes_every_builtin_module() -> None:
    dpg.create_context()
    try:
        build_ui()

        assert dpg.does_item_exist(MODULE_SELECTOR)
        assert dpg.does_item_exist(MODULE_SELECTOR)
        assert dpg.does_item_exist(MODULE_SELECTOR_SEARCH)
        assert dpg.get_item_type(MODULE_SELECTOR).endswith("mvChildWindow")
        assert dpg.is_item_shown(MODULE_SELECTOR)
        assert dpg.get_value(MODULE_SELECTOR_STATUS) == (
            f"{len(BUILTIN_PROVIDER_MANIFEST.modules)} MODULES"
        )
        for section in (
            "COMPOSE & MODULATE",
            "GENERATE",
            "SHAPE & CONTROL",
            "MIX & SPACE",
        ):
            assert dpg.does_item_exist(_module_library_section_tag(section))
        for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
            assert dpg.does_item_exist(
                _module_library_category_tag(manifest.category)
            )
            assert dpg.does_item_exist(
                f"noodler.module_selector.item.{manifest.id}"
            )
    finally:
        dpg.destroy_context()


def test_module_selector_adds_unique_executable_instances_to_the_rack() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()

        for module_id in (
            "classic_vco",
            "state_variable_filter",
            "polarizing_mixer",
        ):
            _add_selected_module("test", None, (runtime, module_id))

        assert dpg.is_item_shown(MODULE_SELECTOR)
        assert dpg.get_value(RACK_OUTLINE_STATUS) == "4 PANELS  ·  0 CABLES"
        assert "UNPATCHED" in _descendant_labels(RACK_OUTLINE_BODY)
        instance_id = "state_variable_filter"
        node = INSTANCE_NODE_TAGS[instance_id]
        assert instance_id in runtime.patch.modules
        assert dpg.does_item_exist(node)
        assert node in RACK_NODES
        assert node in RACK_RAILS[AUDIO_RAIL]
        assert dpg.does_item_exist(f"{node}.audio")
        assert dpg.does_item_exist(f"{node}.low")

        _patch_link_created(
            "test",
            (
                f"{INSTANCE_NODE_TAGS['classic_vco']}.saw",
                f"{node}.audio",
            ),
            runtime,
        )
        _patch_link_created(
            "test",
            (
                f"{node}.low",
                f"{INSTANCE_NODE_TAGS['polarizing_mixer']}.input_1",
            ),
            runtime,
        )
        _patch_link_created(
            "test",
            (
                f"{INSTANCE_NODE_TAGS['polarizing_mixer']}.output",
                f"{OUTPUT_NODE}.channel_1",
            ),
            runtime,
        )
        assert any(
            cable.source.module_id == "state_variable_filter"
            for cable in runtime.patch.cables
        )
        # It reaches the speakers by being in the master, not by having its
        # own tap: the only taps are the master's own.
        assert any(
            cable.source.module_id == "polarizing_mixer"
            and cable.target.module_id == "master"
            for cable in runtime.patch.cables
        )
        assert dpg.get_value(RACK_OUTLINE_STATUS) == "4 PANELS  ·  3 CABLES"
        outline = _descendant_labels(RACK_OUTLINE_BODY)
        assert "UNPATCHED" not in outline
        assert any("POLARIZING MIXER" in label for label in outline)
        assert any("STATE VARIABLE FILTER" in label for label in outline)
        assert any("CLASSIC VCO" in label for label in outline)
        assert dpg.get_item_configuration(f"{node}.audio")["show"] is True
        assert dpg.get_item_configuration(f"{node}.low")["show"] is True
        rendered = runtime.patch.render(64, 48_000.0)
        assert rendered.shape == (64,)

        _add_selected_module(
            "test",
            None,
            (runtime, "state_variable_filter"),
        )
        assert "state_variable_filter_2" in runtime.patch.modules
        assert dpg.does_item_exist(
            INSTANCE_NODE_TAGS["state_variable_filter_2"]
        )

        captured = _capture_current_preset(runtime, "Expanded Palette")
        assert {module.instance_id for module in captured.modules} >= {
            "state_variable_filter",
            "state_variable_filter_2",
        }
        assert {node.node_id for node in captured.view.nodes} >= {
            "state_variable_filter",
            "state_variable_filter_2",
        }
    finally:
        dpg.destroy_context()


def test_module_selector_search_filters_names_categories_and_descriptions() -> None:
    dpg.create_context()
    try:
        build_ui()

        _filter_module_selector("test", "filter", None)

        assert dpg.get_item_configuration(
            "noodler.module_selector.item.state_variable_filter"
        )["show"] is True
        assert dpg.get_item_configuration(
            "noodler.module_selector.item.melody_brain"
        )["show"] is False
        assert dpg.get_item_configuration(
            _module_library_category_tag("Filters")
        )["show"] is True
        assert dpg.get_value(_module_library_category_tag("Filters")) is True
        assert dpg.get_item_configuration(
            _module_library_category_tag("Musical Brains")
        )["show"] is False
        # Counted from the catalogue rather than restated, so adding a module
        # that happens to mention filtering does not fail this test.
        matching = sum(
            "filter" in f"{m.name} {m.category} {m.description}".lower()
            for m in BUILTIN_PROVIDER_MANIFEST.modules
        )
        assert dpg.get_value(MODULE_SELECTOR_STATUS) == f"{matching} MODULES"
    finally:
        dpg.destroy_context()


def test_current_rack_module_expands_to_live_port_states() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        node = INSTANCE_NODE_TAGS["classic_vco"]

        outline = _descendant_labels(RACK_OUTLINE_BODY)
        assert "PORTS  ·  0/9 PATCHED" in outline
        assert "INPUTS" in outline
        assert "OUTPUTS" in outline
        assert "○  Saw  ·  AUDIO  ·  OPEN" in outline

        _patch_link_created(
            "test",
            (f"{node}.saw", f"{OUTPUT_NODE}.channel_1"),
            runtime,
        )

        outline = _descendant_labels(RACK_OUTLINE_BODY)
        assert "PORTS  ·  1/9 PATCHED" in outline
        assert "●  Saw  ·  AUDIO  ·  PATCHED" in outline
    finally:
        dpg.destroy_context()


def test_generated_module_controls_update_validated_parameters() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "function_utility"))
        utility = runtime.patch.modules["function_utility"]

        _set_dynamic_parameter(
            utility,
            ("channel_1", "rise_seconds"),
            3.5,
        )

        assert utility.parameters.channel_1.rise_seconds == pytest.approx(3.5)
    finally:
        dpg.destroy_context()


def test_generated_float_parameters_are_packed_three_across() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        existing = set(KNOB_INTERACTION.bindings)

        _add_selected_module("test", None, (runtime, "classic_vco"))

        knobs = [
            knob
            for knob in KNOB_INTERACTION.bindings
            if knob not in existing
        ]
        row_parents = [
            dpg.get_item_parent(dpg.get_item_parent(knob))
            for knob in knobs
        ]
        assert len(knobs) == 5
        assert len(set(row_parents[:3])) == 1
        assert len(set(row_parents[3:])) == 1
        assert len(set(row_parents)) == 2
    finally:
        dpg.destroy_context()


def test_patch_bays_show_every_port_until_open_jacks_are_hidden() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)

        assert dpg.get_value(f"{VCO_NODE}.patch_bay.status") == (
            "SIGNAL PATH  ·  3 IN  →  2 OUT"
        )
        assert dpg.get_item_configuration(f"{VCO_NODE}.morph_cv")["show"]
        assert dpg.get_item_configuration(f"{VCO_NODE}.pitch")["show"]
        assert dpg.get_item_configuration(
            f"{VCO_NODE}.frequency_cv_2"
        )["show"]
        assert dpg.get_item_configuration(f"{VCO_NODE}.morph")["show"]
        assert dpg.get_item_configuration(f"{VCO_NODE}.sine")["show"]
        assert dpg.get_value(f"{WOGGLE_NODE}.patch_bay.status") == (
            "SIGNAL PATH  ·  4 OUT"
        )
        assert dpg.get_value(f"{REVERB_NODE}.patch_bay.status") == (
            "SIGNAL PATH  ·  3 IN  →  2 OUT"
        )
        assert dpg.get_value(f"{LPG_NODE}.patch_bay.status") == (
            "SIGNAL PATH  ·  2 IN  →  1 OUT"
        )
        assert dpg.get_item_configuration(f"{MIXER_NODE}.input_2")["show"]
        assert dpg.get_item_configuration(f"{MIXER_NODE}.input_4")["show"]

        # There is no HIDE OPEN toggle: collapsing a module hides its open jacks.
        assert not dpg.does_item_exist(f"{VCO_NODE}.patch_bay.hide_open")
        _set_module_collapsed(VCO_NODE, True, runtime)
        assert not dpg.get_item_configuration(f"{VCO_NODE}.sine")["show"]
        assert not dpg.get_item_configuration(f"{VCO_NODE}.sync")["show"]
        assert dpg.get_item_configuration(f"{VCO_NODE}.morph")["show"]
        _set_module_collapsed(VCO_NODE, False, runtime)
        assert dpg.get_item_configuration(f"{VCO_NODE}.sine")["show"]
    finally:
        dpg.destroy_context()


def test_module_title_collapse_shows_the_title_and_the_patched_jacks() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        attributes = _node_attributes(VCO_NODE)
        cable_count = len(runtime.patch.cables)
        title = dpg.get_item_configuration(VCO_NODE)["label"]

        _set_module_collapsed(VCO_NODE, True, runtime)

        assert MODULE_COLLAPSE.is_collapsed(VCO_NODE) is True
        assert dpg.get_item_configuration(VCO_NODE)["label"] == title, "the title stays"
        patched = {
            f"{VCO_NODE}.{end.port_id}"
            for cable in runtime.patch.cables
            for end in (cable.source, cable.target)
            if end.module_id == "vco"
        }
        for attribute in attributes:
            shown = dpg.get_item_configuration(attribute)["show"]
            alias = dpg.get_item_alias(attribute) or attribute
            kind = dpg.get_item_configuration(attribute).get("attribute_type")
            if kind == dpg.mvNode_Attr_Static:
                assert shown is False, "controls are put away"
            else:
                assert shown is (alias in patched), alias
        assert dpg.get_item_configuration(VCO_MIXER_LINK)["show"] is True
        assert len(runtime.patch.cables) == cable_count

        _set_module_collapsed(VCO_NODE, False, runtime)

        assert MODULE_COLLAPSE.is_collapsed(VCO_NODE) is False
        assert all(
            dpg.get_item_configuration(attribute)["show"] for attribute in attributes
        ), "open means every control and every jack"
        assert len(runtime.patch.cables) == cable_count
    finally:
        dpg.destroy_context()


def test_save_patch_dialog_writes_current_graph_controls_and_rack_view(
    tmp_path,
) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        _set_module_collapsed(WOGGLE_NODE, True, runtime)
        dpg.set_item_pos(VCO_NODE, [444.0, 666.0])
        destination = tmp_path / "Moon Garden"

        _save_patch_dialog(
            "test",
            {"file_path_name": str(destination)},
            runtime,
        )

        saved = read_patch_preset(tmp_path / "Moon Garden.noodler")
        assert dpg.does_item_exist(SAVE_PATCH_MENU_ITEM)
        assert dpg.does_item_exist(SAVE_PATCH_DIALOG)
        assert saved.name == "Moon Garden"
        assert saved.cables == runtime.patch.cables
        assert saved.output_taps == runtime.patch.output_taps
        assert saved.system_output.master_gain == runtime.audio.master_gain
        node_views = {node.node_id: node for node in saved.view.nodes}
        assert node_views["wogglebug"].collapsed is True
        assert node_views["vco"].position.x == 444.0
        assert node_views["vco"].position.y == 666.0

        captured = _capture_current_preset(runtime, "Moon Garden")
        assert captured.modules == saved.modules
    finally:
        dpg.destroy_context()


def test_trackpad_zoom_queues_fractional_motion_and_eases() -> None:
    dpg.create_context()
    try:
        build_ui()

        _queue_rack_zoom(1.06, screen_anchor=(400.0, 300.0))

        assert CANVAS_INTERACTION.zoom == 1.0
        assert CANVAS_INTERACTION.zoom_target == pytest.approx(1.06)
        _settle_rack_zoom()
        assert 1.0 < CANVAS_INTERACTION.zoom < 1.06
        assert CANVAS_INTERACTION.zoom_target == pytest.approx(1.06)
    finally:
        dpg.destroy_context()


def test_rack_zoom_scales_the_hierarchy_and_has_visible_controls() -> None:
    assert _zoomed_position((200.0, 100.0), (50.0, 25.0), 0.5) == (
        125.0,
        62.5,
    )

    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        module_node = INSTANCE_NODE_TAGS["classic_vco"]
        # The console is pinned along the bottom, so it is not part of what zooms.
        original = {
            node: tuple(dpg.get_item_pos(node))
            for node in RACK_NODES
            if node != OUTPUT_NODE
        }
        pinned = tuple(dpg.get_item_pos(OUTPUT_NODE))
        assert dpg.get_global_font_scale() == pytest.approx(1.0)

        _set_rack_zoom(1.12, screen_anchor=(0.0, 0.0))

        assert CANVAS_INTERACTION.zoom == pytest.approx(1.12)
        for node, (original_x, original_y) in original.items():
            node_x, node_y = dpg.get_item_pos(node)
            assert node_x == pytest.approx(original_x * 1.12, abs=1.0)
            assert node_y == pytest.approx(original_y * 1.12, abs=1.0)
        assert dpg.get_global_font_scale() == pytest.approx(1.0)
        # Modules take the zoomed font; the console does not zoom at all.
        assert dpg.get_item_font(module_node) == _rack_font_tag(1.12)
        assert not dpg.get_item_info(OUTPUT_NODE)["font"], "the console keeps its own"
        assert tuple(dpg.get_item_pos(OUTPUT_NODE)) == pinned
        assert dpg.get_item_configuration(ZOOM_RESET_BUTTON)["label"] == "112%"

        zoom_in = dpg.get_item_configuration(ZOOM_IN_BUTTON)
        zoom_in["callback"](
            ZOOM_IN_BUTTON,
            None,
            zoom_in["user_data"],
        )
        assert CANVAS_INTERACTION.zoom > 1.12
    finally:
        dpg.destroy_context()


def test_rail_layout_makes_room_without_moving_what_fits() -> None:
    """A drag has to mean a position, so the rail only resolves overlap."""
    positions = (20.0, 180.0, 430.0)
    widths = (200.0, 180.0, 220.0)

    # Nothing is being dragged: later modules are pushed clear, no further.
    assert _rail_x_targets(
        positions,
        widths,
        active_index=None,
        gap=40.0,
    ) == (20.0, 260.0, 480.0)

    # The dragged module keeps its position and the rest part around it.
    assert _rail_x_targets(
        positions,
        widths,
        active_index=1,
        gap=40.0,
    ) == (-60.0, 180.0, 430.0)


def test_rail_layout_leaves_a_roomy_row_untouched() -> None:
    positions = (20.0, 400.0, 900.0)
    widths = (200.0, 180.0, 220.0)

    assert _rail_x_targets(
        positions,
        widths,
        active_index=None,
        gap=40.0,
    ) == positions
    assert _rail_x_targets((), (), active_index=None, gap=20.0) == ()


def test_node_editor_repatches_the_live_graph() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        editor = dpg.get_item_configuration(RACK)
        link = editor["callback"]
        delink = editor["delink_callback"]
        user_data = editor["user_data"]

        assert dpg.get_item_user_data(VCO_MIXER_LINK) == runtime.patch.cables[4]
        assert dpg.get_item_user_data(WOGGLE_SCALE_LINK) == runtime.patch.cables[2]
        assert dpg.get_item_user_data(SCALE_VCO_LINK) == runtime.patch.cables[3]
        assert dpg.get_item_user_data(MIXER_LPG_LINK) == runtime.patch.cables[7]
        assert dpg.get_item_user_data(LPG_REVERB_LINK) == runtime.patch.cables[10]
        assert dpg.get_item_user_data(REVERB_LEFT_OUTPUT_LINK) == next(
            cable
            for cable in runtime.patch.cables
            if cable.target.port_id == "channel_1"
        )
        assert dpg.get_item_user_data(REVERB_RIGHT_OUTPUT_LINK) == next(
            cable
            for cable in runtime.patch.cables
            if cable.target.port_id == "channel_2"
        )

        delink(RACK, VCO_MIXER_LINK, user_data)
        assert not dpg.does_item_exist(VCO_MIXER_LINK)
        assert len(runtime.patch.cables) == 13
        assert dpg.get_item_configuration(f"{VCO_NODE}.morph")["show"]
        assert dpg.get_item_configuration(f"{MIXER_NODE}.input_1")["show"]

        # Dear PyGui reports numeric item IDs and users may drag input-to-output.
        link(
            RACK,
            (
                dpg.get_alias_id(f"{MIXER_NODE}.input_1"),
                dpg.get_alias_id(f"{VCO_NODE}.triangle"),
            ),
            user_data,
        )
        assert runtime.patch.cables[-1].source.port_id == "triangle"
        assert runtime.patch.cables[-1].target.port_id == "input_1"
        assert dpg.get_item_configuration(f"{VCO_NODE}.triangle")["show"]
        assert dpg.get_item_configuration(f"{MIXER_NODE}.input_1")["show"]

        # Unpatching the master's channels silences the rack but does not
        # disconnect the speakers: the bus is not something you can unplug.
        delink(RACK, REVERB_LEFT_OUTPUT_LINK, user_data)
        delink(RACK, REVERB_RIGHT_OUTPUT_LINK, user_data)
        assert [tap.source.module_id for tap in runtime.patch.output_taps] == [
            "master",
            "master",
        ]
        assert not any(
            cable.target.module_id == "master" for cable in runtime.patch.cables
        )
        link(
            RACK,
            (
                dpg.get_alias_id(f"{OUTPUT_NODE}.channel_1"),
                dpg.get_alias_id(f"{VCO_NODE}.sine"),
            ),
            user_data,
        )
        patched = runtime.patch.cables[-1]
        assert patched.source.module_id == "vco"
        assert patched.source.port_id == "sine"
        assert patched.target.module_id == "master"

        cable_count = len(runtime.patch.cables)
        link(
            RACK,
            (
                dpg.get_alias_id(f"{VCO_NODE}.saw"),
                dpg.get_alias_id(f"{MIXER_NODE}.input_1"),
            ),
            user_data,
        )
        assert len(runtime.patch.cables) == cable_count
        assert dpg.get_value(CONTROL_STATUS).startswith("CAN'T PATCH:")

        delink(RACK, UTILITY_VCO_LINK, user_data)
        link(
            RACK,
            (
                dpg.get_alias_id(f"{WOGGLE_NODE}.stepped"),
                dpg.get_alias_id(f"{VCO_NODE}.morph_cv"),
            ),
            user_data,
        )
        assert runtime.patch.cables[-1].source.module_id == "wogglebug"
        assert runtime.patch.cables[-1].source.port_id == "stepped"
        assert runtime.patch.cables[-1].target.port_id == "morph_cv"
    finally:
        dpg.destroy_context()


def test_unplug_all_button_clears_visual_and_executable_cables() -> None:
    dpg.create_context()
    try:
        runtime = build_ui(starter_patch=True)
        # Everything patched, which is every cable; the master's own bus to the
        # speakers was never patched and is never unplugged.
        initial_count = len(runtime.patch.cables)
        button = dpg.get_item_configuration(UNPLUG_ALL_BUTTON)

        button["callback"](
            UNPLUG_ALL_BUTTON,
            None,
            button["user_data"],
        )

        assert initial_count > 0
        assert runtime.patch.cables == ()
        assert [tap.source.module_id for tap in runtime.patch.output_taps] == [
            "master",
            "master",
        ], "the speakers stay connected"
        assert dpg.get_item_children(RACK).get(0, []) == []
        assert dpg.get_item_configuration(f"{VCO_NODE}.morph_cv")["show"]
        assert dpg.get_value(CONTROL_STATUS) == (
            f"UNPLUGGED ALL  ·  {initial_count} CABLES REMOVED"
        )

        button["callback"](
            UNPLUG_ALL_BUTTON,
            None,
            button["user_data"],
        )
        assert dpg.get_value(CONTROL_STATUS) == "NO CABLES TO UNPLUG"
    finally:
        dpg.destroy_context()
