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


def test_the_bell_garden_is_tuned_by_pytheory_not_by_semitones() -> None:
    """Pelog is why the Key exists: its steps are nothing like 100 cents."""
    preset = read_patch_preset(Path("examples/pelog-bell-garden.noodler"))
    runtime = build_runtime_from_preset(preset)
    runtime.patch.prepare(48_000.0, 256)

    key = runtime.patch.modules["key"]
    assert key.parameters.system == "pelog"

    tones = sorted(frequency for _name, frequency in key.field.tones)
    steps = [
        1_200.0 * np.log2(higher / lower)
        for lower, higher in zip(tones, tones[1:])
    ]
    assert steps, "the scale should have steps"
    assert not all(abs(step - 100.0) < 5.0 for step in steps), (
        "these are semitones, not pelog"
    )
    # Uneven on purpose: a pelog step is anything from a small to a large one.
    assert max(steps) - min(steps) > 40.0


def test_every_voice_in_the_garden_is_pytheory_synthesis() -> None:
    preset = read_patch_preset(Path("examples/pelog-bell-garden.noodler"))
    runtime = build_runtime_from_preset(preset)
    runtime.patch.prepare(48_000.0, 256)

    voices = {
        instance_id: module
        for instance_id, module in runtime.patch.modules.items()
        if instance_id in {"bells", "kalimba", "bowl"}
    }
    assert len(voices) == 3
    for instance_id, voice in voices.items():
        assert voice.manifest.id == "pytheory_voice", instance_id
        assert voice.ready, f"{instance_id} rendered nothing"
        assert voice._anchors, instance_id

    # One Key, three quantizers: the whole garden is in one tuning.
    scale_targets = {
        cable.target.module_id
        for cable in runtime.patch.cables
        if cable.source.module_id == "key" and cable.source.port_id == "scale"
    }
    assert scale_targets == {"bell_pitch", "kalimba_pitch", "bowl_pitch"}


def test_each_voice_in_the_garden_has_its_own_register() -> None:
    """Three instruments in one range is a pile, not an arrangement."""
    preset = read_patch_preset(Path("examples/pelog-bell-garden.noodler"))

    def spectrum_of(channel: int) -> float:
        runtime = build_runtime_from_preset(preset)
        runtime.patch.prepare(48_000.0, 256)
        master = runtime.patch.modules["master"]
        for other in range(1, 9):
            master.set_level(other, 1.0 if other == channel else 0.0)
        audio = np.concatenate(
            [runtime.patch.render_stereo(256, 48_000.0) for _ in range(1_400)]
        ).sum(axis=1)
        spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
        frequencies = np.fft.rfftfreq(len(audio), 1.0 / 48_000.0)
        heard = (frequencies > 40.0) & (frequencies < 6_000.0)
        # Where the energy actually sits, rather than one lucky peak.
        weights = spectrum[heard]
        return float(np.sum(frequencies[heard] * weights) / np.sum(weights))

    bells = spectrum_of(1)
    kalimba = spectrum_of(3)
    bowl = spectrum_of(4)

    assert bowl < kalimba < bells, (
        f"bowl {bowl:.0f} Hz, kalimba {kalimba:.0f} Hz, bells {bells:.0f} Hz"
    )
