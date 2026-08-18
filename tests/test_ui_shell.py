"""The gestures the new rack answers to, and what they do to the patch."""

import dearpygui.dearpygui as dpg
import pytest

from noodler.ui import rack as rack_view
from noodler.ui import shell as sh


def _shell():
    shell = sh.create()
    sh.build(shell)
    return shell


def test_a_new_rack_holds_only_the_system_output() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        assert shell.rack.order == [rack_view.OUTPUT_ID]
        assert dpg.does_item_exist(rack_view.node_tag(rack_view.OUTPUT_ID))
        assert dpg.get_value(sh.SUMMARY) == "EMPTY RACK"
    finally:
        dpg.destroy_context()


def test_adding_a_module_builds_its_panel_before_the_output() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        instance = sh.add_module(shell, "complex_vco")

        assert instance == "complex_vco"
        assert shell.rack.order == ["complex_vco", rack_view.OUTPUT_ID]
        assert dpg.does_item_exist(rack_view.node_tag(instance))
        assert instance in shell.rack.patch.modules
        assert "1 MODULE" in dpg.get_value(sh.SUMMARY)
    finally:
        dpg.destroy_context()


def test_repeated_adds_make_distinct_instances() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        first = sh.add_module(shell, "classic_vco")
        second = sh.add_module(shell, "classic_vco")

        assert first != second
        assert {first, second} <= set(shell.rack.patch.modules)
    finally:
        dpg.destroy_context()


def test_every_module_in_the_library_can_be_added() -> None:
    """A module should reach the rack simply by existing in the catalog."""
    from noodler.module_providers.builtin import BUILTIN_PROVIDER_MANIFEST

    dpg.create_context()
    try:
        shell = _shell()
        for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
            assert sh.add_module(shell, manifest.id) is not None, manifest.id
        assert len(shell.rack.patch.modules) == len(
            BUILTIN_PROVIDER_MANIFEST.modules
        )
        # And they all fit somewhere, on some row.
        assert len(rack_view.placements(shell.rack)) == len(shell.rack.order)
    finally:
        dpg.destroy_context()


def test_dragging_a_title_moves_a_module_through_the_order(monkeypatch) -> None:
    """A horizontal drag means order, and order is all it means."""
    dpg.create_context()
    try:
        shell = _shell()
        for module_id in ("classic_vco", "state_variable_filter", "reverb"):
            sh.add_module(shell, module_id)
        before = list(shell.rack.order)

        monkeypatch.setattr(
            sh, "_module_title_at", lambda _shell, _x, _y: "classic_vco"
        )
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (10.0, 10.0)
        )
        monkeypatch.setattr(sh, "_editor_origin", lambda: (0.0, 0.0))
        sh.on_press("test", None, shell)
        assert shell.grabbed == "classic_vco"

        # Carry it far to the right of everything else.
        monkeypatch.setattr(
            dpg, "get_mouse_pos", lambda *, local=False: (5_000.0, 20.0)
        )
        sh.on_drag("test", None, shell)
        sh.on_release("test", None, shell)

        assert shell.rack.order != before
        assert shell.rack.order.index("classic_vco") > shell.rack.order.index(
            "state_variable_filter"
        )
        assert set(shell.rack.order) == set(before), "nothing was lost"
    finally:
        dpg.destroy_context()


def test_patching_a_cable_changes_the_executable_graph() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        sh.add_module(shell, "classic_vco")
        rack = shell.rack

        rack_view.link_created(
            rack_view.EDITOR,
            (
                rack_view.port_tag("classic_vco", "saw"),
                rack_view.port_tag(rack_view.OUTPUT_ID, "mono"),
            ),
            rack,
        )

        assert len(rack.patch.output_taps) == 1
        assert rack.patch.output_taps[0].source.module_id == "classic_vco"
        assert "1 CABLE" in dpg.get_value(sh.SUMMARY)
    finally:
        dpg.destroy_context()


def test_an_impossible_cable_is_refused_and_explained() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        sh.add_module(shell, "classic_vco")

        rack_view.link_created(
            rack_view.EDITOR,
            (
                rack_view.port_tag("classic_vco", "pitch"),
                rack_view.port_tag("classic_vco", "sync"),
            ),
            shell.rack,
        )

        assert shell.rack.patch.cables == ()
        assert "CAN'T PATCH" in dpg.get_value(sh.STATUS)
    finally:
        dpg.destroy_context()


def test_removing_a_module_takes_its_cables_with_it() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        sh.add_module(shell, "classic_vco")
        rack = shell.rack
        rack_view.link_created(
            rack_view.EDITOR,
            (
                rack_view.port_tag("classic_vco", "saw"),
                rack_view.port_tag(rack_view.OUTPUT_ID, "mono"),
            ),
            rack,
        )

        assert rack_view.remove_module(rack, "classic_vco") is True

        assert "classic_vco" not in rack.patch.modules
        assert rack.patch.output_taps == ()
        assert not dpg.does_item_exist(rack_view.node_tag("classic_vco"))
        assert "classic_vco" not in rack.order
    finally:
        dpg.destroy_context()


def test_the_system_output_cannot_be_removed() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        assert rack_view.remove_module(shell.rack, rack_view.OUTPUT_ID) is False
        assert rack_view.OUTPUT_ID in shell.rack.order
    finally:
        dpg.destroy_context()


def test_adding_a_module_can_be_undone_and_redone() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        sh.add_module(shell, "reverb")
        assert "reverb" in shell.rack.patch.modules

        shell.history.undo()
        assert "reverb" not in shell.rack.patch.modules

        shell.history.redo()
        assert "reverb" in shell.rack.patch.modules
    finally:
        dpg.destroy_context()


def test_a_knob_drag_moves_the_real_parameter(monkeypatch) -> None:
    dpg.create_context()
    try:
        shell = _shell()
        sh.add_module(shell, "classic_vco")
        module = shell.rack.patch.modules["classic_vco"]
        knob, binding = next(
            (knob, bound)
            for knob, bound in shell.rack.knobs.items()
            if bound.control.label == "FREQ"
        )
        before = module.parameters.frequency

        monkeypatch.setattr(dpg, "is_item_hovered", lambda item: item == knob)
        monkeypatch.setattr(dpg, "get_mouse_pos", lambda *, local=False: (0.0, 400.0))
        monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
        sh.on_press("test", None, shell)
        assert shell.active_knob == knob

        # Upward movement raises the value.
        monkeypatch.setattr(dpg, "get_mouse_pos", lambda *, local=False: (0.0, 250.0))
        sh.on_drag("test", None, shell)
        sh.on_release("test", None, shell)

        assert module.parameters.frequency > before
        assert dpg.get_value(binding.readout).strip()
    finally:
        dpg.destroy_context()


def test_searching_hides_what_does_not_match() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        sh._filter_library("test", "reverb", shell)

        assert dpg.get_item_configuration("noodler.ui.library.reverb")["show"]
        assert not dpg.get_item_configuration(
            "noodler.ui.library.classic_vco"
        )["show"]

        sh._filter_library("test", "", shell)
        assert dpg.get_item_configuration("noodler.ui.library.classic_vco")["show"]
    finally:
        dpg.destroy_context()


def test_the_rack_scrolls_rather_than_pans() -> None:
    dpg.create_context()
    try:
        shell = _shell()
        for module_id in ("reverb", "classic_vco", "echo_delay"):
            sh.add_module(shell, module_id)

        sh.on_wheel("test", -3.0, shell)
        assert shell.rack.scroll > 0.0

        rack_view.settle(shell.rack, 1 / 120)
        sh.on_wheel("test", 50.0, shell)
        rack_view.settle(shell.rack, 1 / 120)
        assert shell.rack.scroll == pytest.approx(0.0), "the rack has a top"
    finally:
        dpg.destroy_context()
