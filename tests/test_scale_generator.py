import math

import numpy as np
import pytest
from pydantic import ValidationError
from pytheory import Tone

from noodler.module_providers import PortDirection, SignalType
from noodler.module_providers.builtin.scale_generator import (
    SCALE_GENERATOR_MANIFEST,
    SUPPORTED_SCALE_SYSTEMS,
    ScaleGenerator,
    ScaleGeneratorParameters,
    SequencePattern,
    scale_names,
)


def test_manifest_exposes_musical_cv_and_timing_outputs() -> None:
    ports = {port.id: port for port in SCALE_GENERATOR_MANIFEST.ports}

    assert set(ports) == {
        "clock",
        "reset",
        "transpose",
        "note",
        "pitch",
        "frequency",
        "degree",
        "gate",
        "trigger",
    }
    assert ports["clock"].direction is PortDirection.INPUT
    assert ports["note"].signal_type is SignalType.MUSICAL
    assert ports["pitch"].signal_type is SignalType.CV
    assert ports["gate"].signal_type is SignalType.GATE


def test_default_sequence_is_prepared_from_c_dorian() -> None:
    generator = ScaleGenerator()
    c4 = Tone.from_string("C4")

    outputs = generator.process(4, 48_000.0, {"clock": 0.0})

    assert generator.scale_label == "C dorian · western"
    assert generator.current_note == "C4"
    assert generator.degree_count == 8
    np.testing.assert_allclose(outputs["frequency"], c4.frequency)
    np.testing.assert_allclose(outputs["note"], c4.midi)
    np.testing.assert_allclose(
        outputs["pitch"],
        math.log2(c4.frequency / 220.0),
    )


def test_external_clock_advances_scale_and_reset_returns_to_tonic() -> None:
    generator = ScaleGenerator(
        ScaleGeneratorParameters(pattern=SequencePattern.UP)
    )
    clock = [0.0, 1.0, 1.0, 0.0, 1.0, 0.0]
    reset = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

    outputs = generator.process(
        6,
        100.0,
        {"clock": clock, "reset": reset},
    )

    np.testing.assert_allclose(outputs["gate"], clock)
    np.testing.assert_allclose(outputs["trigger"], [0, 1, 0, 0, 1, 1])
    assert outputs["note"][0] == 60.0
    assert outputs["note"][1] == 62.0
    assert outputs["note"][4] == 63.0
    assert outputs["note"][5] == 60.0
    assert generator.current_note == "C4"


def test_configure_rebuilds_a_given_pytheory_scale() -> None:
    generator = ScaleGenerator()

    generator.configure(
        system="blues",
        tonic="E",
        octave=2,
        scale_name="minor pentatonic",
    )

    assert generator.scale_label == "E minor pentatonic · blues"
    assert generator.current_note == "E2"
    assert generator.degree_count == 6
    assert generator.current_frequency == pytest.approx(
        Tone.from_string("E2", system="blues").frequency
    )


def test_all_exposed_systems_and_scale_lists_come_from_pytheory() -> None:
    for system in SUPPORTED_SCALE_SYSTEMS:
        names = scale_names(system)
        assert names
        generator = ScaleGenerator(
            ScaleGeneratorParameters(system=system, scale_name=names[0])
        )
        assert generator.degree_count >= 1


def test_transpose_changes_frequency_pitch_and_musical_note_together() -> None:
    generator = ScaleGenerator()

    outputs = generator.process(2, 48_000.0, {"transpose": 1.0})

    assert outputs["frequency"][0] == pytest.approx(
        Tone.from_string("C5").frequency
    )
    assert outputs["note"][0] == 72.0
    assert outputs["pitch"][0] == pytest.approx(
        math.log2(Tone.from_string("C5").frequency / 220.0)
    )


def test_random_pattern_is_deterministic_across_block_boundaries() -> None:
    parameters = ScaleGeneratorParameters(
        pattern=SequencePattern.RANDOM,
        seed=777,
    )
    continuous = ScaleGenerator(parameters.model_copy())
    split = ScaleGenerator(parameters.model_copy())
    clock = np.tile([0.0, 1.0], 20)

    expected = continuous.process(40, 100.0, {"clock": clock})
    first = split.process(17, 100.0, {"clock": clock[:17]})
    second = split.process(23, 100.0, {"clock": clock[17:]})

    for name, block in expected.items():
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            block,
        )


def test_melodic_wander_is_seeded_and_returns_to_phrase_tonics() -> None:
    parameters = ScaleGeneratorParameters(
        system="japanese",
        tonic="A",
        octave=3,
        scale_name="hirajoshi",
        pattern=SequencePattern.WANDER,
        seed=777,
    )
    continuous = ScaleGenerator(parameters.model_copy())
    split = ScaleGenerator(parameters.model_copy())
    clock = np.tile([0.0, 1.0], 16)

    expected = continuous.process(32, 100.0, {"clock": clock})
    first = split.process(13, 100.0, {"clock": clock[:13]})
    second = split.process(19, 100.0, {"clock": clock[13:]})

    for name, block in expected.items():
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            block,
        )
    assert expected["degree"][15] == pytest.approx(1.0)
    assert expected["degree"][31] == pytest.approx(0.0)


def test_control_blocks_must_match_the_audio_block_size() -> None:
    with pytest.raises(ValueError, match="transpose must be scalar"):
        ScaleGenerator().process(8, 48_000.0, {"transpose": np.zeros(7)})


def test_invalid_scale_selection_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not a western scale"):
        ScaleGeneratorParameters(scale_name="minor pentatonic")
