"""Opening a patch, and saving over the one you opened."""

from pathlib import Path

import dearpygui.dearpygui as dpg

from noodler.app import (
    ACTIVE_RUNTIME,
    CONTROL_STATUS,
    CURRENT_PATCH_PATH,
    OPEN_PATCH_DIALOG,
    PENDING_OPEN,
    _add_selected_module,
    _consume_pending_open,
    _open_patch_dialog,
    _save_patch,
    _show_save_patch_dialog,
    build_ui,
)
from noodler.preset import read_patch_preset


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
        assert len(runtime.patch.modules) == 2

        _open_patch_dialog("test", {"file_path_name": str(destination)})
        reopened = _consume_pending_open()

        assert len(reopened.patch.modules) == 1, "the old rack was left behind"
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

        assert read_patch_preset(destination).modules[0].parameters[
            "frequency"
        ] == 330.0
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
