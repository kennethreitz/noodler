import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import ConnectionDisposition, SignalType, assess_connection
from noodler.module_providers.builtin import COMPLEX_VCO_MANIFEST
from noodler.module_providers.builtin.reverb import (
    REVERB_MANIFEST,
    Reverb,
    ReverbParameters,
)


def test_manifest_exposes_modulation_and_separate_wet_output() -> None:
    ports = {port.id: port for port in REVERB_MANIFEST.ports}

    assert set(ports) == {
        "audio",
        "mix_cv",
        "decay_cv",
        "freeze",
        "wet_left",
        "wet_right",
        "left",
        "right",
    }
    assert ports["audio"].signal_type is SignalType.AUDIO
    assert ports["mix_cv"].signal_type is SignalType.CV
    assert ports["freeze"].signal_type is SignalType.GATE


def test_impulse_produces_a_delayed_dense_tail() -> None:
    reverb = Reverb(ReverbParameters(mix=1.0))
    impulse = np.zeros(12_000)
    impulse[0] = 1.0

    outputs = reverb.process(12_000, 48_000.0, {"audio": impulse})
    wet_left = outputs["wet_left"]
    wet_right = outputs["wet_right"]

    assert np.count_nonzero(wet_left[:800]) == 0
    assert np.count_nonzero(wet_left[1_500:]) > 500
    assert float(np.sum(np.square(wet_left))) > 0.01
    assert float(np.sum(np.square(wet_right))) > 0.01
    assert not np.array_equal(wet_left, wet_right)


def test_zero_mix_is_exactly_dry() -> None:
    reverb = Reverb(ReverbParameters(mix=0.0))
    signal = np.linspace(-0.5, 0.5, 8_192)

    outputs = reverb.process(8_192, 48_000.0, {"audio": signal})

    np.testing.assert_allclose(outputs["left"], signal, atol=1e-7)
    np.testing.assert_allclose(outputs["right"], signal, atol=1e-7)


def test_split_blocks_match_one_continuous_render() -> None:
    parameters = ReverbParameters(
        mix=0.45,
        decay_seconds=4.2,
        damping=0.3,
        diffusion=0.8,
        pre_delay_ms=11.0,
    )
    continuous = Reverb(parameters.model_copy())
    split = Reverb(parameters.model_copy())
    signal = np.zeros(10_000)
    signal[0] = 0.8
    signal[4_000] = -0.3

    expected = continuous.process(10_000, 48_000.0, {"audio": signal})
    first = split.process(3_333, 48_000.0, {"audio": signal[:3_333]})
    second = split.process(6_667, 48_000.0, {"audio": signal[3_333:]})

    for name, block in expected.items():
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            block,
            atol=1e-7,
        )


def test_reset_clears_the_prepared_room() -> None:
    reverb = Reverb(ReverbParameters(mix=1.0, pre_delay_ms=0.0))
    impulse = np.zeros(8_000)
    impulse[0] = 1.0
    reverb.process(8_000, 48_000.0, {"audio": impulse})

    reverb.reset()
    outputs = reverb.process(4_000, 48_000.0)

    np.testing.assert_allclose(outputs["wet_left"], 0.0)
    np.testing.assert_allclose(outputs["wet_right"], 0.0)


def test_audio_cv_cross_linking_is_explicit() -> None:
    vco_ports = {port.id: port for port in COMPLEX_VCO_MANIFEST.ports}
    reverb_ports = {port.id: port for port in REVERB_MANIFEST.ports}

    assessment = assess_connection(vco_ports["sine"], reverb_ports["mix_cv"])

    assert assessment.compatible is True
    assert assessment.disposition is ConnectionDisposition.CROSS_SIGNAL


def test_control_blocks_must_match_the_audio_block_size() -> None:
    with pytest.raises(ValueError, match="mix_cv must be scalar"):
        Reverb().process(8, 48_000.0, {"mix_cv": np.zeros(7)})


def test_parameters_validate_assignment() -> None:
    parameters = ReverbParameters()

    with pytest.raises(ValidationError):
        parameters.decay_seconds = 31.0
