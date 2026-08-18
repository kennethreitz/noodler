"""Where the rack comes out."""

import numpy as np
import pytest

from noodler.module_providers.builtin import (
    MASTER_CHANNELS,
    MasterMixer,
    MasterMixerParameters,
)


def _steady(value: float = 1.0, frames: int = 8) -> np.ndarray:
    return np.full(frames, value, dtype=np.float32)


def test_an_unpatched_mixer_is_silent() -> None:
    rendered = MasterMixer().process(8, 48_000.0)

    assert set(rendered) == {"left", "right", "sum", "send_a", "send_b"}
    for channel in rendered.values():
        np.testing.assert_allclose(channel, 0.0)


def test_a_patched_channel_is_audible_on_both_sides() -> None:
    mixer = MasterMixer(MasterMixerParameters(master=1.0))
    rendered = mixer.process(8, 48_000.0, {"channel_1": _steady()})

    assert float(rendered["left"][0]) > 0.0
    assert float(rendered["left"][0]) == pytest.approx(
        float(rendered["right"][0])
    ), "centred means even"


def test_panning_moves_a_channel_without_changing_its_loudness() -> None:
    """Equal power: moving a channel across changes where it is, not how loud."""
    mixer = MasterMixer(MasterMixerParameters(master=1.0))
    centred = mixer.process(8, 48_000.0, {"channel_1": _steady()})
    middle = float(
        np.hypot(centred["left"][0], centred["right"][0])
    )

    mixer.set_pan(1, -1.0)
    left = mixer.process(8, 48_000.0, {"channel_1": _steady()})
    assert float(left["right"][0]) == pytest.approx(0.0, abs=1e-6)
    assert float(np.hypot(left["left"][0], left["right"][0])) == pytest.approx(
        middle, rel=1e-5
    )

    mixer.set_pan(1, 1.0)
    right = mixer.process(8, 48_000.0, {"channel_1": _steady()})
    assert float(right["left"][0]) == pytest.approx(0.0, abs=1e-6)


def test_channels_sum() -> None:
    mixer = MasterMixer(MasterMixerParameters(master=1.0))
    one = mixer.process(8, 48_000.0, {"channel_1": _steady()})["left"][0]
    both = mixer.process(
        8, 48_000.0, {"channel_1": _steady(), "channel_2": _steady()}
    )["left"][0]

    assert float(both) == pytest.approx(float(one) * 2.0, rel=1e-5)


def test_a_level_of_zero_mutes_only_that_channel() -> None:
    mixer = MasterMixer(MasterMixerParameters(master=1.0))
    mixer.set_level(1, 0.0)

    rendered = mixer.process(
        8, 48_000.0, {"channel_1": _steady(), "channel_2": _steady(0.5)}
    )

    assert float(rendered["left"][0]) > 0.0, "channel two still plays"
    only_two = MasterMixer(MasterMixerParameters(master=1.0)).process(
        8, 48_000.0, {"channel_2": _steady(0.5)}
    )
    assert float(rendered["left"][0]) == pytest.approx(
        float(only_two["left"][0]), rel=1e-5
    )


def test_the_sum_is_the_mono_fold_down() -> None:
    mixer = MasterMixer(MasterMixerParameters(master=1.0))
    mixer.set_pan(1, -1.0)
    rendered = mixer.process(8, 48_000.0, {"channel_1": _steady()})

    expected = (rendered["left"] + rendered["right"]) * 0.5
    np.testing.assert_allclose(rendered["sum"], expected, rtol=1e-6)


def test_every_channel_has_a_jack() -> None:
    inputs = [
        port for port in MasterMixer.manifest.ports if port.direction.value == "input"
    ]
    assert len(inputs) == MASTER_CHANNELS
    assert {port.signal_type.value for port in inputs} == {"audio"}


def test_a_channel_outside_the_mixer_is_refused() -> None:
    mixer = MasterMixer()
    with pytest.raises(ValueError, match="between 1 and"):
        mixer.set_level(0, 0.5)
    with pytest.raises(ValueError, match="between 1 and"):
        mixer.set_pan(MASTER_CHANNELS + 1, 0.5)


def test_a_wrongly_sized_set_of_levels_is_refused() -> None:
    with pytest.raises(ValueError, match="entries"):
        MasterMixerParameters(levels=(1.0, 1.0))


def test_sends_are_post_fader_and_summed_across_channels() -> None:
    mixer = MasterMixer()
    one = np.ones(4, dtype=np.float32)
    mixer.set_level(1, 0.5)
    mixer.set_level(2, 1.0)
    mixer.set_send("a", 1, 1.0)
    mixer.set_send("a", 2, 0.5)
    mixer.set_send("b", 2, 1.0)

    rendered = mixer.process(4, 48_000.0, {"channel_1": one, "channel_2": one})

    # A: channel one at 0.5 x 1.0, channel two at 1.0 x 0.5.
    np.testing.assert_allclose(rendered["send_a"], 1.0, atol=1e-6)
    # B: only channel two, at its level.
    np.testing.assert_allclose(rendered["send_b"], 1.0, atol=1e-6)


def test_a_send_is_not_affected_by_pan_or_master() -> None:
    mixer = MasterMixer()
    one = np.ones(4, dtype=np.float32)
    mixer.set_level(1, 1.0)
    mixer.set_pan(1, -1.0)
    mixer.set_send("a", 1, 1.0)
    mixer.parameters.master = 0.0

    rendered = mixer.process(4, 48_000.0, {"channel_1": one})

    np.testing.assert_allclose(rendered["send_a"], 1.0, atol=1e-6)
    np.testing.assert_allclose(rendered["left"], 0.0)


def test_a_send_must_name_a_real_bus() -> None:
    with pytest.raises(ValueError):
        MasterMixer().set_send("c", 1, 0.5)
