import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import PortDirection, SignalType
from noodler.module_providers.builtin import (
    WOGGLEBUG_MANIFEST,
    Wogglebug,
    WogglebugParameters,
)


def test_manifest_exposes_the_complete_uncertainty_instrument() -> None:
    ports = {port.id: port for port in WOGGLEBUG_MANIFEST.ports}

    assert set(ports) == {
        "external_clock",
        "clock_cv",
        "ego",
        "influence",
        "stepped",
        "smooth",
        "woggle",
        "clock",
        "burst",
        "smooth_vco",
        "woggle_vco",
        "ring_mod",
    }
    assert ports["external_clock"].direction is PortDirection.INPUT
    assert ports["clock"].signal_type is SignalType.GATE
    assert ports["stepped"].signal_type is SignalType.CV
    assert ports["ring_mod"].signal_type is SignalType.AUDIO


def test_external_clock_samples_and_holds_new_random_values() -> None:
    bug = Wogglebug(WogglebugParameters(clock_rate_hz=0.01, seed=7))
    clock = np.array([0.0, 1.0, 1.0, 0.0, 1.0, 1.0])

    outputs = bug.process(6, 100.0, {"external_clock": clock})

    np.testing.assert_allclose(outputs["clock"], clock)
    assert outputs["stepped"][0] == 0.0
    assert outputs["stepped"][1] != 0.0
    assert outputs["stepped"][1] == outputs["stepped"][2]
    assert outputs["stepped"][2] == outputs["stepped"][3]
    assert outputs["stepped"][4] != outputs["stepped"][3]


def test_ego_input_can_become_the_sample_source() -> None:
    bug = Wogglebug(
        WogglebugParameters(
            clock_rate_hz=0.01,
            chaos=0.0,
            ego_id_balance=0.0,
        )
    )
    bug.disturb()

    stepped = bug.process(3, 100.0, {"ego": 0.75})["stepped"]

    np.testing.assert_allclose(stepped, 0.75)


def test_disturb_forces_an_immediate_random_event() -> None:
    bug = Wogglebug(WogglebugParameters(clock_rate_hz=0.01, seed=11))
    before = bug.process(4, 100.0)["stepped"]
    bug.disturb()
    after = bug.process(4, 100.0)["stepped"]

    np.testing.assert_allclose(before, 0.0)
    assert after[0] != 0.0
    assert after[0] == after[-1]


def test_split_blocks_are_identical_to_one_continuous_block() -> None:
    parameters = WogglebugParameters(
        clock_rate_hz=23.0,
        chaos=0.8,
        ego_id_balance=0.4,
        woggle=0.3,
        seed=2026,
    )
    continuous = Wogglebug(parameters.model_copy())
    split = Wogglebug(parameters.model_copy())
    influence = np.linspace(-0.5, 0.5, 257)
    clock_cv = np.sin(np.linspace(0.0, 3.0, 257)) * 0.1

    expected = continuous.process(
        257,
        1_000.0,
        {"influence": influence, "clock_cv": clock_cv},
    )
    first = split.process(
        91,
        1_000.0,
        {"influence": influence[:91], "clock_cv": clock_cv[:91]},
    )
    second = split.process(
        166,
        1_000.0,
        {"influence": influence[91:], "clock_cv": clock_cv[91:]},
    )

    for name, block in expected.items():
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            block,
            atol=1e-7,
        )


def test_outputs_use_normalized_ranges_and_float32_blocks() -> None:
    bug = Wogglebug(WogglebugParameters(audio_level=0.25, seed=4))
    bug.disturb()

    outputs = bug.process(1_024, 48_000.0)

    assert set(outputs) == {
        "stepped",
        "smooth",
        "woggle",
        "clock",
        "burst",
        "smooth_vco",
        "woggle_vco",
        "ring_mod",
    }
    for block in outputs.values():
        assert block.shape == (1_024,)
        assert block.dtype == np.float32
    for name in ("stepped", "smooth", "woggle"):
        assert float(np.max(np.abs(outputs[name]))) <= 1.0
    for name in ("smooth_vco", "woggle_vco", "ring_mod"):
        assert float(np.max(np.abs(outputs[name]))) <= 0.250001
    assert set(np.unique(outputs["clock"])).issubset({0.0, 1.0})
    assert set(np.unique(outputs["burst"])).issubset({0.0, 1.0})


def test_influence_audio_replaces_the_internal_ring_mod_source() -> None:
    bug = Wogglebug(WogglebugParameters(audio_level=0.25))

    ring = bug.process(64, 48_000.0, {"influence": 0.0})["ring_mod"]

    np.testing.assert_allclose(ring, 0.0)


def test_control_blocks_must_match_the_audio_block_size() -> None:
    with pytest.raises(ValueError, match="influence must be scalar"):
        Wogglebug().process(8, 48_000.0, {"influence": np.zeros(7)})


def test_parameters_validate_assignment() -> None:
    parameters = WogglebugParameters()

    with pytest.raises(ValidationError):
        parameters.chaos = 1.1
