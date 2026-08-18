import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers.builtin import (
    ADSREnvelope,
    ADSRParameters,
    EchoDelay,
    EchoDelayParameters,
    EnvelopeStage,
    VCA,
    VCAParameters,
    VCAResponse,
)


def test_adsr_reaches_sustain_then_releases_and_pulses_end() -> None:
    envelope = ADSREnvelope(
        ADSRParameters(
            attack_seconds=0.01,
            decay_seconds=0.02,
            sustain=0.4,
            release_seconds=0.03,
            curve=0.0,
        )
    )
    gate = np.concatenate((np.ones(60), np.zeros(50)))

    output = envelope.process(len(gate), 1_000.0, {"gate": gate})

    assert output["envelope"][9] == pytest.approx(1.0)
    assert output["envelope"][29] == pytest.approx(0.4)
    assert output["envelope"][59] == pytest.approx(0.4)
    assert np.count_nonzero(output["end"]) == 1
    assert envelope.stage is EnvelopeStage.IDLE


def test_vca_supports_linear_and_exponential_gain_laws() -> None:
    cv = np.array([0.0, 0.25, 0.5, 1.0])
    linear = VCA(VCAParameters(response=VCAResponse.LINEAR))
    exponential = VCA(VCAParameters(response=VCAResponse.EXPONENTIAL))

    linear_output = linear.process(4, 48_000.0, {"signal": 0.5, "level_cv": cv})
    exponential_output = exponential.process(
        4,
        48_000.0,
        {"signal": 0.5, "level_cv": cv},
    )

    np.testing.assert_allclose(linear_output["gain"], cv)
    np.testing.assert_allclose(exponential_output["gain"], cv * cv)
    assert exponential_output["output"][1] < linear_output["output"][1]


def test_echo_places_impulse_at_delay_time_and_creates_feedback_repeat() -> None:
    delay = EchoDelay(
        EchoDelayParameters(
            time_seconds=0.01,
            feedback=0.5,
            mix=1.0,
            damping=0.0,
            drive=1.0,
        )
    )
    impulse = np.zeros(40)
    impulse[0] = 1.0

    wet = delay.process(40, 1_000.0, {"audio": impulse})["wet"]

    assert wet[10] > 0.7
    assert wet[20] > 0.2
    assert np.count_nonzero(wet[:10]) == 0


def test_echo_is_stable_across_audio_block_boundaries() -> None:
    parameters = EchoDelayParameters(
        time_seconds=0.027,
        feedback=-0.45,
        mix=0.6,
        damping=0.3,
    )
    continuous = EchoDelay(parameters.model_copy())
    split = EchoDelay(parameters.model_copy())
    source = np.zeros(1_000)
    source[[0, 233, 701]] = [1.0, -0.4, 0.2]

    expected = continuous.process(1_000, 4_000.0, {"audio": source})
    first = split.process(377, 4_000.0, {"audio": source[:377]})
    second = split.process(623, 4_000.0, {"audio": source[377:]})

    for name in expected:
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            expected[name],
            atol=1e-7,
        )


def test_dynamics_parameters_validate_assignment() -> None:
    parameters = ADSRParameters()

    with pytest.raises(ValidationError):
        parameters.sustain = -0.1

