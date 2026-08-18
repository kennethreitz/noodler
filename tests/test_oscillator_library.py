import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers.builtin import (
    ClassicVCO,
    ClassicVCOParameters,
    FMVoice,
    FMVoiceParameters,
    NoiseSource,
    NoiseSourceParameters,
    SupersawOscillator,
    SupersawParameters,
)


def test_classic_vco_produces_the_usual_wave_family_and_sub_octave() -> None:
    vco = ClassicVCO(
        ClassicVCOParameters(frequency=1.0, amplitude=1.0)
    )

    outputs = vco.process(4, 4.0)

    np.testing.assert_allclose(outputs["sine"], [0.0, 1.0, 0.0, -1.0], atol=1e-6)
    np.testing.assert_allclose(outputs["triangle"], [-1.0, 0.0, 1.0, 0.0])
    np.testing.assert_allclose(outputs["saw"], [-1.0, -0.5, 0.0, 0.5])
    np.testing.assert_allclose(outputs["pulse"], [1.0, 1.0, -1.0, -1.0])
    np.testing.assert_allclose(outputs["sub"], [1.0, 1.0, 1.0, 1.0])


def test_fm_voice_is_phase_continuous_across_blocks() -> None:
    parameters = FMVoiceParameters(frequency=123.0, ratio=1.5, index=3.2)
    continuous = FMVoice(parameters.model_copy())
    split = FMVoice(parameters.model_copy())
    pitch = np.linspace(-0.2, 0.3, 300)

    expected = continuous.process(300, 8_000.0, {"pitch": pitch})
    first = split.process(113, 8_000.0, {"pitch": pitch[:113]})
    second = split.process(187, 8_000.0, {"pitch": pitch[113:]})

    for name in expected:
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            expected[name],
            atol=1e-7,
        )
    assert not np.array_equal(expected["output"], expected["carrier"])


def test_supersaw_cluster_differs_from_center_voice() -> None:
    oscillator = SupersawOscillator(
        SupersawParameters(frequency=220.0, detune_cents=15.0, amplitude=0.3)
    )

    outputs = oscillator.process(2_048, 48_000.0)

    assert not np.array_equal(outputs["cluster"], outputs["center"])
    for output in outputs.values():
        assert output.dtype == np.float32
        assert float(np.max(np.abs(output))) <= 0.300001


def test_noise_colors_are_seeded_and_block_boundary_stable() -> None:
    parameters = NoiseSourceParameters(seed=777, level=0.4)
    continuous = NoiseSource(parameters.model_copy())
    split = NoiseSource(parameters.model_copy())
    clock = np.tile([0.0, 0.0, 1.0, 1.0], 100)

    expected = continuous.process(400, 4_000.0, {"clock": clock})
    first = split.process(137, 4_000.0, {"clock": clock[:137]})
    second = split.process(263, 4_000.0, {"clock": clock[137:]})

    for name in expected:
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            expected[name],
        )
        assert float(np.max(np.abs(expected[name]))) <= 0.400001
    held = expected["sample_hold"]
    assert np.all(held[2:6] == held[2])


def test_oscillator_parameters_are_assignment_validated() -> None:
    parameters = SupersawParameters()

    with pytest.raises(ValidationError):
        parameters.detune_cents = 75.0

