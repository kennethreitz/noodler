import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import ConnectionDisposition, assess_connection
from noodler.module_providers.builtin import (
    COMPLEX_VCO_MANIFEST,
    PolarizingMixer,
    PolarizingMixerParameters,
    polarizing_mixer_manifest,
)


def test_channel_count_shapes_the_instance_manifest() -> None:
    mixer = PolarizingMixer(PolarizingMixerParameters(channels=7))

    assert mixer.manifest.name == "7-Channel Polarizing Mixer"
    assert [port.id for port in mixer.manifest.ports] == [
        "input_1",
        "input_2",
        "input_3",
        "input_4",
        "input_5",
        "input_6",
        "input_7",
        "output",
    ]


def test_each_channel_can_attenuate_or_invert_before_summing() -> None:
    mixer = PolarizingMixer(
        PolarizingMixerParameters(channels=3, gains=(1.0, -0.5, 0.25))
    )

    output = mixer.process(
        frame_count=3,
        sample_rate=48_000.0,
        inputs={
            "input_1": [1.0, 2.0, 3.0],
            "input_2": 2.0,
            "input_3": [-4.0, 0.0, 4.0],
        },
    )["output"]

    np.testing.assert_allclose(output, [-1.0, 1.0, 3.0])


def test_mixer_does_not_clip_audio_or_cv_sums() -> None:
    mixer = PolarizingMixer(
        PolarizingMixerParameters(channels=2, gains=(1.0, 1.0))
    )

    output = mixer.process(
        frame_count=2,
        sample_rate=48_000.0,
        inputs={"input_1": 1.0, "input_2": 1.0},
    )["output"]

    np.testing.assert_allclose(output, [2.0, 2.0])


def test_gain_updates_replace_the_parameter_snapshot() -> None:
    mixer = PolarizingMixer(PolarizingMixerParameters(channels=2))

    mixer.set_gain(2, -0.75)

    assert mixer.parameters.gains == (0.0, -0.75)


def test_gain_count_and_range_are_validated() -> None:
    with pytest.raises(ValidationError, match="exactly one value"):
        PolarizingMixerParameters(channels=3, gains=(1.0, 1.0))

    with pytest.raises(ValidationError, match="between -1 and 1|less than or equal to 1|greater than or equal to -1"):
        PolarizingMixerParameters(channels=1, gains=(1.1,))


def test_manifest_factory_validates_channel_count() -> None:
    with pytest.raises(ValidationError):
        polarizing_mixer_manifest(0)


def test_vco_audio_can_patch_into_mixer_cv_input() -> None:
    vco_ports = {port.id: port for port in COMPLEX_VCO_MANIFEST.ports}
    mixer_ports = {port.id: port for port in polarizing_mixer_manifest(2).ports}

    assessment = assess_connection(vco_ports["triangle"], mixer_ports["input_1"])

    assert assessment.compatible is True
    assert assessment.disposition is ConnectionDisposition.CROSS_SIGNAL

