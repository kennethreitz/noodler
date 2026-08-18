"""Collapsing the module library, and the pane that holds it."""

import dearpygui.dearpygui as dpg

from noodler.app import (
    CONTROL_STATUS,
    LIBRARY_PANE_BUTTON,
    MODULE_LIBRARY_HEADER,
    MODULE_SELECTOR,
    MODULE_SELECTOR_SEARCH,
    _keyboard_is_captured,
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


def test_a_focused_search_box_does_not_hold_every_shortcut(monkeypatch) -> None:
    """Dear PyGui calls a field focused whenever its window is.

    Treating that as "the user is typing" handed the whole keyboard to the
    search box for the rest of the session, so L stopped bringing the library
    back — after the status line had promised that it would.
    """
    dpg.create_context()
    try:
        build_ui()
        monkeypatch.setattr(dpg, "is_item_focused", lambda _item: True)
        monkeypatch.setattr(dpg, "is_item_active", lambda _item: False)

        assert _keyboard_is_captured() is False

        _toggle_library_pane()
        assert dpg.is_item_shown(MODULE_SELECTOR) is False
        _toggle_library_pane()
        assert dpg.is_item_shown(MODULE_SELECTOR) is True
    finally:
        dpg.destroy_context()


def test_actually_typing_still_holds_the_keyboard(monkeypatch) -> None:
    dpg.create_context()
    try:
        build_ui()
        monkeypatch.setattr(dpg, "is_item_active", lambda item: item == MODULE_SELECTOR_SEARCH)

        assert _keyboard_is_captured() is True

        _toggle_library_pane()
        assert dpg.is_item_shown(MODULE_SELECTOR) is True, "L must not fire mid-word"
    finally:
        dpg.destroy_context()


def test_a_hidden_search_box_never_holds_the_keyboard(monkeypatch) -> None:
    dpg.create_context()
    try:
        build_ui()
        _toggle_library_pane()
        monkeypatch.setattr(dpg, "is_item_active", lambda _item: True)

        assert _keyboard_is_captured() is False
    finally:
        dpg.destroy_context()
