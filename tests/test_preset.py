import json

import pytest
from pydantic import ValidationError

from noodler.app import build_runtime
from noodler.preset import (
    PATCH_EXTENSION,
    Point,
    RackNodePreset,
    RackViewPreset,
    capture_patch_preset,
    read_patch_preset,
    write_patch_preset,
)


def test_patch_preset_round_trips_as_readable_versioned_json(tmp_path) -> None:
    runtime = build_runtime()
    view = RackViewPreset(
        zoom=0.82,
        rails={"control": 24.0, "audio": 540.0},
        nodes=(
            RackNodePreset(
                node_id="wogglebug",
                position=Point(x=430.0, y=24.0),
                collapsed=True,
            ),
        ),
    )
    preset = capture_patch_preset(
        name="Hirajoshi Garden",
        patch=runtime.patch,
        master_gain=runtime.audio.master_gain,
        view=view,
    )

    destination = write_patch_preset(preset, tmp_path / "hirajoshi-garden")
    payload = json.loads(destination.read_text())

    assert destination.suffix == PATCH_EXTENSION
    assert payload["format"] == "noodler.patch"
    assert payload["format_version"] == 1
    assert payload["modules"][0]["parameters"]
    assert payload["cables"][0]["source"]["module_id"] == "utility"
    assert read_patch_preset(destination) == preset


def test_patch_preset_rejects_unknown_graph_references(tmp_path) -> None:
    path = tmp_path / "broken.noodler"
    path.write_text(
        json.dumps(
            {
                "format": "noodler.patch",
                "format_version": 1,
                "name": "Broken",
                "modules": [],
                "cables": [
                    {
                        "source": {"module_id": "ghost", "port_id": "out"},
                        "target": {"module_id": "void", "port_id": "in"},
                    }
                ],
            }
        )
    )

    with pytest.raises(ValidationError, match="unknown module"):
        read_patch_preset(path)


def test_patch_preset_rejects_future_format_versions(tmp_path) -> None:
    path = tmp_path / "future.noodler"
    path.write_text(
        json.dumps(
            {
                "format": "noodler.patch",
                "format_version": 2,
                "name": "Future",
                "modules": [],
            }
        )
    )

    with pytest.raises(ValidationError, match="format_version"):
        read_patch_preset(path)
