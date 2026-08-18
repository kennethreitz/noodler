from pathlib import Path
from types import SimpleNamespace

import dearpygui.dearpygui as dpg
import numpy as np
import pytest

import noodler.app as app
from noodler.app import (
    CANVAS_INTERACTION,
    CONTROL_STATUS,
    INSTANCE_NODE_TAGS,
    OUTPUT_NODE,
    RACK,
    RACK_HISTORY,
    RACK_OUTLINE_BODY,
    _parse_cli_args,
    build_runtime_from_preset,
    build_ui,
)
from noodler.preset import read_patch_preset


EXAMPLE_PATCH = Path(__file__).parents[1] / "examples" / "somesound.noodler"


def _tree_labels(item: int | str) -> list[str]:
    labels: list[str] = []
    for children in dpg.get_item_children(item).values():
        for child in children:
            label = dpg.get_item_label(child)
            if label:
                labels.append(label)
            labels.extend(_tree_labels(child))
    return labels


def test_example_patch_builds_an_executable_stereo_graph() -> None:
    preset = read_patch_preset(EXAMPLE_PATCH)
    runtime = build_runtime_from_preset(preset)

    assert tuple(runtime.patch.modules) == ("classic_vco", "reverb")
    assert runtime.patch.modules["classic_vco"].parameters.frequency == 110.0
    assert len(runtime.patch.cables) == 1
    assert len(runtime.patch.output_taps) == 2
    assert runtime.audio.master_gain == pytest.approx(0.65)

    rendered = runtime.patch.render_stereo(512, 48_000.0)
    assert rendered.shape == (512, 2)
    assert np.max(np.abs(rendered)) > 0.0


def test_example_patch_restores_panels_cables_and_view() -> None:
    dpg.create_context()
    try:
        preset = read_patch_preset(EXAMPLE_PATCH)
        runtime = build_ui(preset=preset)

        vco_node = INSTANCE_NODE_TAGS["classic_vco"]
        reverb_node = INSTANCE_NODE_TAGS["reverb"]
        assert runtime.patch.modules["reverb"].parameters.decay_seconds == 5.8
        assert dpg.get_item_pos(vco_node) == [60, 250]
        assert dpg.get_item_pos(reverb_node) == [430, 250]
        assert dpg.get_item_pos(OUTPUT_NODE) == [820, 250]
        assert len(dpg.get_item_children(RACK).get(0, ())) == 3
        assert CANVAS_INTERACTION.zoom == pytest.approx(0.85)
        assert "SOME SOUND" in dpg.get_value(CONTROL_STATUS)
        reverb_branches = [
            label
            for label in _tree_labels(RACK_OUTLINE_BODY)
            if label.startswith("SPACE REVERB  [reverb]")
        ]
        assert reverb_branches == [
            "SPACE REVERB  [reverb]  ·  left  →  left  ·  right  →  right"
        ]
        assert not RACK_HISTORY.can_undo
    finally:
        dpg.destroy_context()


def test_cli_accepts_a_patch_document_path() -> None:
    args = _parse_cli_args([str(EXAMPLE_PATCH)])
    assert args.patch == EXAMPLE_PATCH


def test_main_opens_the_cli_document(monkeypatch) -> None:
    opened = []
    closed = []

    class GestureMonitor:
        def __init__(self, _callback) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monkeypatch.setattr(app, "MacMagnifyMonitor", GestureMonitor)
    monkeypatch.setattr(
        app,
        "build_ui",
        lambda *, preset: (
            opened.append(preset)
            or SimpleNamespace(audio=SimpleNamespace(close=lambda: closed.append(True)))
        ),
    )
    for function in (
        "create_context",
        "create_viewport",
        "setup_dearpygui",
        "set_primary_window",
        "show_viewport",
        "set_frame_callback",
        "start_dearpygui",
        "destroy_context",
    ):
        monkeypatch.setattr(app.dpg, function, lambda *args, **kwargs: None)

    app.main([str(EXAMPLE_PATCH)])

    assert [preset.name for preset in opened] == ["Some Sound"]
    assert closed == [True]


def test_main_reports_a_missing_document_before_opening_the_ui(tmp_path) -> None:
    missing = tmp_path / "missing.noodler"
    with pytest.raises(SystemExit, match="could not open"):
        app.main([str(missing)])
