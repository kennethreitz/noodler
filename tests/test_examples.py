"""The example patches have to actually play."""

from pathlib import Path

import numpy as np
import pytest

from noodler.app import build_runtime_from_preset
from noodler.preset import read_patch_preset
from noodler.transport import Transport


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


TONE_SYSTEM_SET = {
    "bohlen-pierce-chapel": "bohlen-pierce",
    "carnatic-loom": "carnatic",
    "makam-divan": "makam",
    "nineteen": "19-tet",
    "pelog-bell-garden": "pelog",
    "shruti-drone": "shruti",
    "slendro-rain": "slendro",
}


@pytest.mark.parametrize("stem,system", sorted(TONE_SYSTEM_SET.items()))
def test_each_patch_in_the_set_is_in_the_system_its_name_says(stem, system) -> None:
    preset = read_patch_preset(Path("examples") / f"{stem}.noodler")
    runtime = build_runtime_from_preset(preset)
    key = runtime.patch.modules["key"]
    assert key.parameters.system == system

    # Every voice is PyTheory's own synthesis, and every quantizer reads the Key.
    voices = [m for m in runtime.patch.modules.values() if m.manifest.id == "pytheory_voice"]
    quantizers = {
        instance_id
        for instance_id, m in runtime.patch.modules.items()
        if m.manifest.id == "quantizer"
    }
    fed = {
        cable.target.module_id
        for cable in runtime.patch.cables
        if cable.source.module_id == "key" and cable.source.port_id == "scale"
    }
    assert voices, "no PyTheory voice"
    assert quantizers and fed == quantizers, "a quantizer is not reading the Key"


@pytest.mark.parametrize("stem", sorted(TONE_SYSTEM_SET))
def test_each_patch_in_the_set_is_not_twelve_tone(stem) -> None:
    """The point of the set. A tuning indistinguishable from a piano is not one."""
    preset = read_patch_preset(Path("examples") / f"{stem}.noodler")
    key = build_runtime_from_preset(preset).patch.modules["key"]
    tones = sorted(frequency for _name, frequency in key.field.tones)
    steps = [1_200.0 * np.log2(b / a) for a, b in zip(tones, tones[1:])]
    assert steps
    assert not all(abs(step - 100.0) < 3.0 for step in steps), f"{stem} is 12-TET"


def test_the_set_leaves_headroom() -> None:
    """Every patch sits in the same loudness range and none approaches clipping."""
    levels = {}
    for stem in TONE_SYSTEM_SET:
        runtime = build_runtime_from_preset(
            read_patch_preset(Path("examples") / f"{stem}.noodler")
        )
        runtime.patch.prepare(48_000.0, 256)
        audio = np.concatenate(
            [runtime.patch.render_stereo(256, 48_000.0) for _ in range(1_500)]
        )
        peak = float(np.max(np.abs(audio)))
        assert peak < 0.85, f"{stem} peaks at {peak:.2f}"
        levels[stem] = float(np.sqrt(np.mean(audio**2)))
    loudest, quietest = max(levels.values()), min(levels.values())
    assert loudest / quietest < 4.0, levels


def _strongest_period(audio: np.ndarray, low: float = 0.2, high: float = 6.0) -> float:
    """The period, in seconds, that the loudness of a passage most repeats at."""
    envelope = np.convolve(np.abs(audio).mean(axis=1), np.ones(2_400) / 2_400, mode="same")
    spectrum = np.abs(np.fft.rfft(envelope - envelope.mean()))
    frequencies = np.fft.rfftfreq(envelope.size, 1.0 / 48_000.0)
    band = (frequencies > low) & (frequencies < high)
    return float(1.0 / frequencies[band][np.argmax(spectrum[band])])


def test_the_highlife_example_keeps_time_with_the_transport() -> None:
    """Drums, chords, arpeggio, melody and bass all follow the menu-bar clock."""
    preset = read_patch_preset(Path("examples/highlife-kalimba.noodler"))
    assert preset.transport.bpm == 108.0
    runtime = build_runtime_from_preset(preset)
    runtime.patch.prepare(48_000.0, 256)

    def play(bpm: float, seconds: float) -> np.ndarray:
        transport = Transport(bpm=bpm)
        blocks = []
        for _ in range(int(seconds * 48_000 / 256)):
            runtime.patch.transport = transport.tick(256, 48_000.0)
            blocks.append(runtime.patch.render_stereo(256, 48_000.0))
        return np.concatenate(blocks)

    at_108 = play(108.0, 16.0)
    at_150 = play(150.0, 12.0)

    # The loudest repetition is the beat or a simple division of it -- the
    # eighths and the beat are close in energy -- and it moves with the tempo.
    def beats_per_period(audio: np.ndarray, bpm: float) -> float:
        return _strongest_period(audio) * bpm / 60.0

    for audio, bpm in ((at_108, 108.0), (at_150, 150.0)):
        ratio = beats_per_period(audio, bpm)
        assert any(abs(ratio - simple) < 0.03 for simple in (0.5, 1.0, 2.0)), ratio
    assert float(np.max(np.abs(at_108))) < 0.9

    clocked = [
        m for m in runtime.patch.modules.values() if getattr(m, "uses_transport", False)
    ]
    assert {m.manifest.id for m in clocked} == {"clock", "pytheory_beats"}
