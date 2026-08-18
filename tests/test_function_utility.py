import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import ConnectionDisposition, assess_connection
from noodler.module_providers.builtin import (
    COMPLEX_VCO_MANIFEST,
    FUNCTION_UTILITY_MANIFEST,
    MAX_FUNCTION_STAGE_SECONDS,
    MIN_FUNCTION_STAGE_SECONDS,
    FunctionChannelParameters,
    FunctionUtility,
    FunctionUtilityParameters,
)


def test_timing_range_reaches_audio_rate_and_twenty_five_minute_cycles() -> None:
    fastest = FunctionChannelParameters(
        rise_seconds=MIN_FUNCTION_STAGE_SECONDS,
        fall_seconds=MIN_FUNCTION_STAGE_SECONDS,
    )
    slowest = FunctionChannelParameters(
        rise_seconds=MAX_FUNCTION_STAGE_SECONDS,
        fall_seconds=MAX_FUNCTION_STAGE_SECONDS,
    )

    assert fastest.rise_seconds + fastest.fall_seconds == pytest.approx(0.001)
    assert slowest.rise_seconds + slowest.fall_seconds == pytest.approx(25 * 60)

    utility = FunctionUtility(
        FunctionUtilityParameters(
            channel_1=fastest.model_copy(update={"cycle": True}),
        )
    )
    output = utility.process(frame_count=96, sample_rate=48_000.0)[
        "channel_1_unity"
    ]

    assert output[23] == pytest.approx(1.0)
    assert output[47] == pytest.approx(0.0)
    assert output[71] == pytest.approx(1.0)


def test_function_times_reject_values_outside_the_supported_range() -> None:
    with pytest.raises(ValidationError):
        FunctionChannelParameters(rise_seconds=MIN_FUNCTION_STAGE_SECONDS / 2)
    with pytest.raises(ValidationError):
        FunctionChannelParameters(fall_seconds=MAX_FUNCTION_STAGE_SECONDS * 2)


def test_middle_channels_supply_normalized_offsets_when_unpatched() -> None:
    utility = FunctionUtility(
        FunctionUtilityParameters(
            channel_2_attenuverter=1.0,
            channel_3_attenuverter=-1.0,
        )
    )

    outputs = utility.process(frame_count=3, sample_rate=48_000.0)

    np.testing.assert_allclose(outputs["channel_2"], 1.0)
    np.testing.assert_allclose(outputs["channel_3"], -0.5)
    np.testing.assert_allclose(outputs["sum"], 0.5)
    np.testing.assert_allclose(outputs["inverse"], -0.5)
    np.testing.assert_allclose(outputs["or"], 1.0)


def test_sum_inverse_and_non_negative_analog_or() -> None:
    utility = FunctionUtility(
        FunctionUtilityParameters(
            channel_1=FunctionChannelParameters(attenuverter=0.0),
            channel_2_attenuverter=1.0,
            channel_3_attenuverter=-1.0,
            channel_4=FunctionChannelParameters(attenuverter=0.0),
        )
    )

    outputs = utility.process(
        frame_count=2,
        sample_rate=48_000.0,
        inputs={
            "channel_2_signal": [-1.0, 0.2],
            "channel_3_signal": [0.5, -0.5],
        },
    )

    np.testing.assert_allclose(outputs["sum"], [-1.5, 0.7])
    np.testing.assert_allclose(outputs["inverse"], [1.5, -0.7])
    np.testing.assert_allclose(outputs["or"], [0.0, 0.5])


def test_triggered_function_rises_and_falls_with_endpoint_gates() -> None:
    utility = FunctionUtility(
        FunctionUtilityParameters(
            channel_1=FunctionChannelParameters(
                rise_seconds=0.5,
                fall_seconds=0.5,
                curve=0.0,
            )
        )
    )

    outputs = utility.process(
        frame_count=4,
        sample_rate=4.0,
        inputs={"channel_1_trigger": [1.0, 0.0, 0.0, 0.0]},
    )

    np.testing.assert_allclose(outputs["channel_1_unity"], [0.5, 1.0, 0.5, 0.0])
    np.testing.assert_allclose(outputs["channel_1_eor"], [0.0, 1.0, 1.0, 0.0])


def test_cycle_mode_generates_a_repeating_function() -> None:
    utility = FunctionUtility(
        FunctionUtilityParameters(
            channel_4=FunctionChannelParameters(
                rise_seconds=0.25,
                fall_seconds=0.25,
                cycle=True,
            )
        )
    )

    outputs = utility.process(frame_count=4, sample_rate=4.0)

    np.testing.assert_allclose(outputs["channel_4_unity"], [1.0, 0.0, 1.0, 0.0])
    np.testing.assert_allclose(outputs["channel_4_eoc"], [0.0, 1.0, 0.0, 1.0])


def test_signal_input_uses_separate_linear_rise_and_fall_slew() -> None:
    utility = FunctionUtility(
        FunctionUtilityParameters(
            channel_1=FunctionChannelParameters(
                rise_seconds=0.5,
                fall_seconds=0.5,
                curve=0.0,
            )
        )
    )

    output = utility.process(
        frame_count=4,
        sample_rate=4.0,
        inputs={"channel_1_signal": [1.0, 1.0, 0.0, 0.0]},
    )["channel_1_unity"]

    np.testing.assert_allclose(output, [0.5, 1.0, 0.5, 0.0])


def test_curve_control_changes_function_shape() -> None:
    logarithmic = FunctionUtility(
        FunctionUtilityParameters(
            channel_1=FunctionChannelParameters(
                rise_seconds=1.0,
                fall_seconds=1.0,
                curve=-1.0,
            )
        )
    )
    exponential = FunctionUtility(
        FunctionUtilityParameters(
            channel_1=FunctionChannelParameters(
                rise_seconds=1.0,
                fall_seconds=1.0,
                curve=1.0,
            )
        )
    )

    log_output = logarithmic.process(
        2,
        4.0,
        {"channel_1_trigger": [1.0, 0.0]},
    )["channel_1_unity"]
    exp_output = exponential.process(
        2,
        4.0,
        {"channel_1_trigger": [1.0, 0.0]},
    )["channel_1_unity"]

    assert log_output[0] > exp_output[0]


def test_function_parameters_validate_assignment() -> None:
    parameters = FunctionChannelParameters()

    with pytest.raises(ValidationError):
        parameters.curve = 1.1


def test_audio_can_patch_into_a_function_signal_input() -> None:
    vco_ports = {port.id: port for port in COMPLEX_VCO_MANIFEST.ports}
    utility_ports = {port.id: port for port in FUNCTION_UTILITY_MANIFEST.ports}

    assessment = assess_connection(
        vco_ports["sine"],
        utility_ports["channel_1_signal"],
    )

    assert assessment.compatible is True
    assert assessment.disposition is ConnectionDisposition.CROSS_SIGNAL
