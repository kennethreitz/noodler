import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import ConnectionDisposition, assess_connection
from noodler.module_providers.builtin import (
    COMPLEX_VCO_MANIFEST,
    ComplexVCO,
    ComplexVCOParameters,
    WaveB,
)


def test_all_outputs_are_derived_from_one_triangle_core() -> None:
    vco = ComplexVCO(
        ComplexVCOParameters(
            frequency=1.0,
            amplitude=1.0,
            pulse_width=0.5,
            morph=0.0,
        )
    )

    outputs = vco.process(frame_count=4, sample_rate=4.0)

    np.testing.assert_allclose(outputs["triangle"], [-1.0, 0.0, 1.0, 0.0])
    np.testing.assert_allclose(outputs["sine"], [0.0, 1.0, 0.0, -1.0], atol=1e-6)
    np.testing.assert_allclose(outputs["saw"], [-1.0, -0.5, 0.0, 0.5])
    np.testing.assert_allclose(outputs["pulse"], [1.0, 1.0, -1.0, -1.0])
    np.testing.assert_allclose(outputs["morph"], outputs["sine"], atol=1e-6)
    assert vco.phase == pytest.approx(0.0)


def test_separate_blocks_match_one_continuous_block() -> None:
    parameters = ComplexVCOParameters(
        frequency=3.0,
        amplitude=0.75,
        frequency_cv_1_amount=0.25,
        linear_fm_amount=0.2,
        morph=0.3,
    )
    split = ComplexVCO(parameters.model_copy())
    continuous = ComplexVCO(parameters.model_copy())

    cv = np.linspace(-0.5, 0.5, 12)
    split_blocks = [
        split.process(
            frame_count=5,
            sample_rate=32.0,
            frequency_cv_1=cv[:5],
            linear_fm=cv[:5],
        ),
        split.process(
            frame_count=7,
            sample_rate=32.0,
            frequency_cv_1=cv[5:],
            linear_fm=cv[5:],
        ),
    ]
    continuous_outputs = continuous.process(
        frame_count=12,
        sample_rate=32.0,
        frequency_cv_1=cv,
        linear_fm=cv,
    )

    for output_name in continuous_outputs:
        split_output = np.concatenate([block[output_name] for block in split_blocks])
        np.testing.assert_allclose(
            split_output,
            continuous_outputs[output_name],
            atol=1e-6,
        )
    assert split.phase == pytest.approx(continuous.phase)


def test_one_volt_per_octave_input_doubles_frequency() -> None:
    vco = ComplexVCO(ComplexVCOParameters(frequency=1.0, amplitude=1.0))

    outputs = vco.process(frame_count=4, sample_rate=8.0, pitch_cv=1.0)

    np.testing.assert_allclose(outputs["sine"], [0.0, 1.0, 0.0, -1.0], atol=1e-6)


def test_processed_frequency_inputs_are_bipolar_and_exponential() -> None:
    positive = ComplexVCO(
        ComplexVCOParameters(frequency=1.0, amplitude=1.0, frequency_cv_1_amount=1.0)
    )
    inverted = ComplexVCO(
        ComplexVCOParameters(frequency=1.0, amplitude=1.0, frequency_cv_1_amount=-1.0)
    )

    positive_output = positive.process(4, 8.0, frequency_cv_1=1.0)["sine"]
    inverted_output = inverted.process(4, 8.0, frequency_cv_1=1.0)["sine"]

    np.testing.assert_allclose(positive_output, [0.0, 1.0, 0.0, -1.0], atol=1e-6)
    np.testing.assert_allclose(
        inverted_output,
        [
            0.0,
            np.sin(np.pi / 8.0),
            np.sin(np.pi / 4.0),
            np.sin(3.0 * np.pi / 8.0),
        ],
        atol=1e-6,
    )


def test_linear_fm_changes_frequency_without_exponential_conversion() -> None:
    vco = ComplexVCO(
        ComplexVCOParameters(frequency=1.0, amplitude=1.0, linear_fm_amount=1.0)
    )

    output = vco.process(4, 8.0, linear_fm=1.0)["sine"]

    np.testing.assert_allclose(output, [0.0, 1.0, 0.0, -1.0], atol=1e-6)


def test_pwm_changes_pulse_duty_cycle() -> None:
    vco = ComplexVCO(
        ComplexVCOParameters(frequency=1.0, amplitude=1.0, pulse_width=0.5)
    )

    narrow = vco.process(8, 8.0, pwm=-0.75)["pulse"]

    assert np.count_nonzero(narrow > 0.0) < np.count_nonzero(narrow < 0.0)


@pytest.mark.parametrize(
    ("wave_b", "target_output"),
    [(WaveB.SAW, "saw"), (WaveB.PULSE, "pulse")],
)
def test_morph_moves_from_sine_to_selected_wave_b(
    wave_b: WaveB,
    target_output: str,
) -> None:
    sine_end = ComplexVCO(
        ComplexVCOParameters(frequency=1.0, amplitude=1.0, morph=0.0, wave_b=wave_b)
    ).process(8, 8.0)
    wave_b_end = ComplexVCO(
        ComplexVCOParameters(frequency=1.0, amplitude=1.0, morph=1.0, wave_b=wave_b)
    ).process(8, 8.0)

    np.testing.assert_allclose(sine_end["morph"], sine_end["sine"], atol=1e-6)
    np.testing.assert_allclose(
        wave_b_end["morph"],
        wave_b_end[target_output],
        atol=1e-6,
    )


def test_rising_sync_edge_resets_triangle_core() -> None:
    vco = ComplexVCO(ComplexVCOParameters(frequency=1.0, amplitude=1.0))
    vco.reset(phase=0.25)

    output = vco.process(4, 4.0, sync=[0.0, 1.0, 1.0, 0.0])["triangle"]

    np.testing.assert_allclose(output, [0.0, -1.0, 0.0, 1.0])


def test_outputs_are_bounded_float32_blocks() -> None:
    vco = ComplexVCO(
        ComplexVCOParameters(
            frequency=440.0,
            amplitude=0.4,
            pulse_width=0.2,
            morph=0.65,
            wave_b=WaveB.PULSE,
        )
    )

    outputs = vco.process(
        frame_count=128,
        sample_rate=48_000.0,
        linear_fm=np.linspace(-1.0, 1.0, 128),
        morph_cv=np.linspace(-0.25, 0.25, 128),
    )

    assert set(outputs) == {"sine", "triangle", "saw", "pulse", "morph"}
    for block in outputs.values():
        assert block.shape == (128,)
        assert block.dtype == np.float32
        assert float(np.max(np.abs(block))) <= 0.400001


def test_control_blocks_must_match_the_audio_block_size() -> None:
    vco = ComplexVCO()

    with pytest.raises(ValueError, match="linear_fm must be scalar"):
        vco.process(8, 48_000.0, linear_fm=np.zeros(7))


def test_parameters_validate_assignment() -> None:
    parameters = ComplexVCOParameters()

    with pytest.raises(ValidationError):
        parameters.pulse_width = 1.0


def test_vco_explicitly_supports_audio_cv_cross_linking() -> None:
    ports = {port.id: port for port in COMPLEX_VCO_MANIFEST.ports}

    assessment = assess_connection(ports["morph"], ports["linear_fm"])

    assert assessment.compatible is True
    assert assessment.disposition is ConnectionDisposition.CROSS_SIGNAL
