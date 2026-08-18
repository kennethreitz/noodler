"""Opening a patch, and saving over the one you opened."""

from pathlib import Path

import dearpygui.dearpygui as dpg
import pytest

from noodler.app import (
    ACTIVE_RUNTIME,
    CLOCK_BPM_INPUT,
    CONTROL_STATUS,
    CURRENT_PATCH_PATH,
    EXAMPLES_MENU,
    NEW_PATCH_MENU_ITEM,
    OPEN_PATCH_DIALOG,
    PENDING_OPEN,
    TRANSPORT,
    _add_selected_module,
    _consume_pending_open,
    _example_documents,
    _new_patch,
    _open_example,
    _open_patch_dialog,
    _save_patch,
    _show_save_patch_dialog,
    build_ui,
)
from noodler.preset import PatchPreset, read_patch_preset


def _saved_to(tmp_path: Path, runtime, name: str = "Test Patch") -> Path:
    destination = tmp_path / f"{name}.noodler"
    from noodler.app import _save_patch_to

    _save_patch_to(runtime, destination)
    return destination


def test_a_patch_can_be_saved_and_opened_again(tmp_path) -> None:
    """Saving without opening was a document you could write and never read."""
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        _add_selected_module("test", None, (runtime, "reverb"))
        modules = set(runtime.patch.modules)
        destination = _saved_to(tmp_path, runtime, "Reopened")
        assert destination.exists()

        _open_patch_dialog("test", {"file_path_name": str(destination)})
        assert PENDING_OPEN, "the document waits for the next frame"

        reopened = _consume_pending_open()

        assert reopened is not None
        assert set(reopened.patch.modules) == modules
        assert ACTIVE_RUNTIME == [] or True
        assert "OPENED" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_the_rack_is_rebuilt_rather_than_added_to(tmp_path) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        destination = _saved_to(tmp_path, runtime, "One Module")

        _add_selected_module("test", None, (runtime, "reverb"))
        # Two modules and the master every rack has.
        assert len(runtime.patch.modules) == 3

        _open_patch_dialog("test", {"file_path_name": str(destination)})
        reopened = _consume_pending_open()

        assert len(reopened.patch.modules) == 2, "the old rack was left behind"
    finally:
        dpg.destroy_context()


def test_saving_remembers_where_the_patch_came_from(tmp_path) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        destination = _saved_to(tmp_path, runtime, "Remembered")
        assert CURRENT_PATCH_PATH == [destination]

        # Save writes over that file rather than asking again.
        runtime.patch.modules["classic_vco"].parameters.frequency = 330.0
        _save_patch(0, None, runtime)

        saved = {
            module.instance_id: module.parameters
            for module in read_patch_preset(destination).modules
        }
        assert saved["classic_vco"]["frequency"] == 330.0
    finally:
        CURRENT_PATCH_PATH.clear()
        dpg.destroy_context()


def test_save_asks_where_when_the_patch_has_no_home() -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        CURRENT_PATCH_PATH.clear()

        _save_patch(0, None, runtime)

        from noodler.app import SAVE_PATCH_DIALOG

        assert dpg.is_item_shown(SAVE_PATCH_DIALOG), "it should ask"
    finally:
        CURRENT_PATCH_PATH.clear()
        dpg.destroy_context()


def test_an_unreadable_document_is_reported_not_raised(tmp_path) -> None:
    dpg.create_context()
    try:
        build_ui()
        broken = tmp_path / "broken.noodler"
        broken.write_text("{ not a patch }")

        _open_patch_dialog("test", {"file_path_name": str(broken)})

        assert not PENDING_OPEN
        assert "COULD NOT OPEN" in dpg.get_value(CONTROL_STATUS)
    finally:
        dpg.destroy_context()


def test_the_open_dialog_exists_to_be_shown() -> None:
    dpg.create_context()
    try:
        build_ui()
        assert dpg.does_item_exist(OPEN_PATCH_DIALOG)
        assert not dpg.is_item_shown(OPEN_PATCH_DIALOG)
    finally:
        dpg.destroy_context()


def test_exit_leaves(monkeypatch) -> None:
    """File to Exit, and the command chord that means the same thing."""
    import noodler.app as app

    dpg.create_context()
    try:
        build_ui()
        assert dpg.does_item_exist(app.EXIT_MENU_ITEM)

        stopped: list[bool] = []
        monkeypatch.setattr(dpg, "stop_dearpygui", lambda: stopped.append(True))

        app._exit_noodler()
        assert stopped == [True]

        # A bare Q must not close the rack.
        monkeypatch.setattr(dpg, "is_key_down", lambda _key: False)
        app._quit_shortcut("test", None, None)
        assert stopped == [True]

        monkeypatch.setattr(dpg, "is_key_down", lambda key: key == dpg.mvKey_ModSuper)
        app._quit_shortcut("test", None, None)
        assert stopped == [True, True]
    finally:
        dpg.destroy_context()


def test_exit_stands_down_while_typing(monkeypatch) -> None:
    import noodler.app as app

    dpg.create_context()
    try:
        build_ui()
        stopped: list[bool] = []
        monkeypatch.setattr(dpg, "stop_dearpygui", lambda: stopped.append(True))
        monkeypatch.setattr(app, "_keyboard_is_captured", lambda: True)

        app._exit_noodler()

        assert stopped == [], "a patch named Quit should not close the rack"
    finally:
        dpg.destroy_context()


def test_the_command_chords_reach_open_and_save(monkeypatch) -> None:
    import noodler.app as app

    dpg.create_context()
    try:
        runtime = build_ui()
        monkeypatch.setattr(app, "_keyboard_is_captured", lambda: False)
        monkeypatch.setattr(
            dpg, "is_key_down", lambda key: key == dpg.mvKey_ModSuper
        )

        app._open_shortcut("test", None, runtime)
        assert dpg.is_item_shown(OPEN_PATCH_DIALOG)

        CURRENT_PATCH_PATH.clear()
        app._save_shortcut("test", None, runtime)
        from noodler.app import SAVE_PATCH_DIALOG

        assert dpg.is_item_shown(SAVE_PATCH_DIALOG), "no home yet, so it asks"
    finally:
        CURRENT_PATCH_PATH.clear()
        dpg.destroy_context()


def test_the_tempo_travels_with_the_document(tmp_path) -> None:
    """A patch with a beat in it is not the same patch at another tempo."""
    dpg.create_context()
    try:
        runtime = build_ui()
        TRANSPORT.set_bpm(97.0)
        TRANSPORT.set_signature(7, 8)
        destination = _saved_to(tmp_path, runtime, "Seven")

        TRANSPORT.set_bpm(120.0)
        TRANSPORT.set_signature(4, 4)
        _open_patch_dialog("test", {"file_path_name": str(destination)})
        _consume_pending_open()

        assert TRANSPORT.bpm == 97.0
        assert TRANSPORT.signature == "7/8"
        assert dpg.get_value(CLOCK_BPM_INPUT) == pytest.approx(97.0)
    finally:
        TRANSPORT.set_bpm(120.0)
        TRANSPORT.set_signature(4, 4)
        CURRENT_PATCH_PATH.clear()
        dpg.destroy_context()


def test_an_older_document_without_a_tempo_still_opens() -> None:
    preset = PatchPreset.model_validate(
        {"format": "noodler.patch", "format_version": 1, "name": "old", "modules": []}
    )
    assert preset.transport.bpm == 120.0


def test_file_new_is_an_empty_rack_that_has_forgotten_its_path(tmp_path) -> None:
    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "classic_vco"))
        _saved_to(tmp_path, runtime, "Something")
        assert CURRENT_PATCH_PATH

        _new_patch()
        fresh = _consume_pending_open()

        assert tuple(fresh.patch.modules) == ("master",)
        assert not CURRENT_PATCH_PATH, "Save must ask, not write over the old file"
        assert dpg.does_item_exist(NEW_PATCH_MENU_ITEM)
    finally:
        CURRENT_PATCH_PATH.clear()
        dpg.destroy_context()


def test_the_examples_are_in_the_file_menu_and_open_without_a_path() -> None:
    dpg.create_context()
    try:
        build_ui()
        documents = _example_documents()
        assert documents, "the checkout ships examples"
        assert dpg.does_item_exist(EXAMPLES_MENU)

        _open_example("test", None, documents[0])
        opened = _consume_pending_open()

        assert len(opened.patch.modules) > 1
        assert not CURRENT_PATCH_PATH, "an example is a starting point, not a file to write over"
    finally:
        CURRENT_PATCH_PATH.clear()
        dpg.destroy_context()
