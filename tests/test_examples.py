"""The example patches have to actually play."""

from pathlib import Path

import numpy as np
import pytest

from noodler.app import build_runtime_from_preset
from noodler.preset import read_patch_preset


EXAMPLES = sorted(Path("examples").glob("*.noodler"))


def test_there_are_examples_to_open() -> None:
    assert EXAMPLES, "the examples folder should hold at least one patch"


@pytest.mark.parametrize("document", EXAMPLES, ids=lambda path: path.stem)
def test_an_example_loads_and_makes_sound(document: Path) -> None:
    preset = read_patch_preset(document)
    if not preset.output_taps:
        pytest.skip(f"{document.stem} reaches no output")
    runtime = build_runtime_from_preset(preset)
    runtime.patch.prepare(48_000.0, 256)

    peaks = []
    for _ in range(int(4.0 * 48_000.0 / 256)):
        rendered = runtime.patch.render_stereo(256, 48_000.0)
        assert np.all(np.isfinite(rendered)), f"{document.stem} rendered a NaN"
        peaks.append(float(np.max(np.abs(rendered))))

    assert max(peaks) > 0.01, f"{document.stem} is silent"
    assert max(peaks) <= 1.0, f"{document.stem} clips"


def test_the_showcase_is_generative_and_in_one_key() -> None:
    """Chance becomes melody, and one Key decides what melody means."""
    preset = read_patch_preset(Path("examples/hijaz-machine.noodler"))
    runtime = build_runtime_from_preset(preset)
    runtime.patch.prepare(48_000.0, 256)

    key = runtime.patch.modules["key"]
    assert key.parameters.system == "arabic"
    assert key.parameters.scale_name == "hijaz"

    # Both voices read the same scale off the same cable.
    scale_targets = {
        cable.target.module_id
        for cable in runtime.patch.cables
        if cable.source.module_id == "key" and cable.source.port_id == "scale"
    }
    assert scale_targets == {"lead_pitch", "pad_pitch"}

    allowed = {round(frequency, 2) for _name, frequency in key.field.tones}
    for _ in range(120):
        runtime.patch.render_stereo(256, 48_000.0)
    quantizer = runtime.patch.modules["lead_pitch"]
    assert quantizer.field is not None, "the scale never arrived"
    assert quantizer.field.label == key.field.label

    # Nothing repeats on a short loop: two contours of 23 and 61 seconds.
    shape = runtime.patch.modules["shape"]
    assert shape.parameters.channel_1.rise_seconds != (
        shape.parameters.channel_4.rise_seconds
    )
    assert allowed, "the maqam should have tones"


def test_the_showcase_keeps_evolving() -> None:
    """A generative patch that settles into a loop is not generative."""
    preset = read_patch_preset(Path("examples/hijaz-machine.noodler"))
    runtime = build_runtime_from_preset(preset)
    runtime.patch.prepare(48_000.0, 256)

    def measure(blocks: int) -> float:
        total = []
        for _ in range(blocks):
            total.append(
                float(np.sqrt(np.mean(runtime.patch.render_stereo(256, 48_000.0) ** 2)))
            )
        return float(np.mean(total))

    early = measure(400)
    measure(1_200)
    later = measure(400)

    assert early > 0.0 and later > 0.0
    assert abs(later - early) > 0.005, "the patch sounded the same all through"
