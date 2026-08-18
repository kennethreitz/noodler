"""Collapsing the module library, and the pane that holds it."""

import dearpygui.dearpygui as dpg

from noodler.app import (
    CONTROL_STATUS,
    LIBRARY_PANE_BUTTON,
    MODULE_LIBRARY_HEADER,
    MODULE_SELECTOR,
    MODULE_SELECTOR_SEARCH,
    _show_module_selector,
    _toggle_library_pane,
    build_ui,
)


def _button_label() -> str:
    return dpg.get_item_configuration(LIBRARY_PANE_BUTTON)["label"]


def test_the_library_section_starts_open_and_can_be_collapsed() -> None:
    dpg.create_context()
    try:
        build_ui()

        assert dpg.does_item_exist(MODULE_LIBRARY_HEADER)
        assert dpg.get_value(MODULE_LIBRARY_HEADER) is True

        dpg.set_value(MODULE_LIBRARY_HEADER, False)
        assert dpg.get_value(MODULE_LIBRARY_HEADER) is False
        # Collapsing the section leaves the pane, and the rack outline, in place.
        assert dpg.is_item_shown(MODULE_SELECTOR)
    finally:
        dpg.destroy_context()


def test_the_whole_pane_collapses_and_says_which_way_it_goes() -> None:
    dpg.create_context()
    try:
        build_ui()
        assert dpg.is_item_shown(MODULE_SELECTOR)
        assert _button_label() == "HIDE LIBRARY"

        _toggle_library_pane()

        assert dpg.is_item_shown(MODULE_SELECTOR) is False
        assert _button_label() == "SHOW LIBRARY"
        assert "LIBRARY HIDDEN" in dpg.get_value(CONTROL_STATUS)

        _toggle_library_pane()

        assert dpg.is_item_shown(MODULE_SELECTOR) is True
        assert _button_label() == "HIDE LIBRARY"
    finally:
        dpg.destroy_context()


def test_reaching_for_a_module_reveals_whatever_is_hiding_it() -> None:
    """A hidden pane must not make the add shortcut look broken."""
    dpg.create_context()
    try:
        runtime = build_ui()
        _toggle_library_pane()
        dpg.set_value(MODULE_LIBRARY_HEADER, False)
        assert not dpg.is_item_shown(MODULE_SELECTOR)

        _show_module_selector("test", None, runtime)

        assert dpg.is_item_shown(MODULE_SELECTOR)
        assert dpg.get_value(MODULE_LIBRARY_HEADER) is True
        assert dpg.get_value(MODULE_SELECTOR_SEARCH) == ""
    finally:
        dpg.destroy_context()


def test_the_pane_toggle_stands_down_for_a_text_field(monkeypatch) -> None:
    """L is a character before it is a shortcut."""
    dpg.create_context()
    try:
        build_ui()
        monkeypatch.setattr("noodler.app._keyboard_is_captured", lambda: True)

        _toggle_library_pane()

        assert dpg.is_item_shown(MODULE_SELECTOR) is True
    finally:
        dpg.destroy_context()
