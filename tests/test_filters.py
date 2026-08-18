import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import SignalType
from noodler.module_providers.builtin import (
    LADDER_FILTER_MANIFEST,
    STATE_VARIABLE_FILTER_MANIFEST,
    LadderFilter,
    LadderFilterParameters,
    StateVariableFilter,
    StateVariableFilterParameters,
)


def test_filter_manifests_expose_audio_cv_cross_patch_points() -> None:
    svf = {port.id: port for port in STATE_VARIABLE_FILTER_MANIFEST.ports}
    ladder = {port.id: port for port in LADDER_FILTER_MANIFEST.ports}

    assert svf["audio"].signal_type is SignalType.AUDIO
    assert svf["cutoff_cv"].signal_type is SignalType.CV
    assert ladder["low_24"].signal_type is SignalType.AUDIO


def test_state_variable_low_pass_rejects_more_high_than_low_frequency() -> None:
    sample_rate = 48_000.0
    time = np.arange(24_000) / sample_rate
    low_tone = np.sin(2.0 * np.pi * 100.0 * time)
    high_tone = np.sin(2.0 * np.pi * 8_000.0 * time)
    source = 0.5 * low_tone + 0.5 * high_tone
    filter_ = StateVariableFilter(
        StateVariableFilterParameters(cutoff_hz=800.0, resonance=0.1)
    )

    output = filter_.process(len(source), sample_rate, {"audio": source})["low"]
    spectrum = np.abs(np.fft.rfft(output[2_000:]))
    frequencies = np.fft.rfftfreq(len(output[2_000:]), 1.0 / sample_rate)
    low_energy = spectrum[np.argmin(np.abs(frequencies - 100.0))]
    high_energy = spectrum[np.argmin(np.abs(frequencies - 8_000.0))]

    assert low_energy > high_energy * 20.0


def test_ladder_filter_outputs_are_finite_and_block_boundary_stable() -> None:
    parameters = LadderFilterParameters(
        cutoff_hz=1_400.0,
        resonance=0.72,
        drive=2.5,
    )
    continuous = LadderFilter(parameters.model_copy())
    split = LadderFilter(parameters.model_copy())
    source = np.sin(np.linspace(0.0, 80.0 * np.pi, 2_000))
    cutoff_cv = np.linspace(-0.5, 1.0, 2_000)

    expected = continuous.process(
        2_000,
        48_000.0,
        {"audio": source, "cutoff_cv": cutoff_cv},
    )
    first = split.process(
        777,
        48_000.0,
        {"audio": source[:777], "cutoff_cv": cutoff_cv[:777]},
    )
    second = split.process(
        1_223,
        48_000.0,
        {"audio": source[777:], "cutoff_cv": cutoff_cv[777:]},
    )

    for name in expected:
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            expected[name],
            atol=1e-7,
        )
        assert np.all(np.isfinite(expected[name]))
        assert expected[name].dtype == np.float32


def test_filter_parameters_validate_assignment() -> None:
    parameters = StateVariableFilterParameters()

    with pytest.raises(ValidationError):
        parameters.resonance = 1.1

