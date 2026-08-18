import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import SignalType
from noodler.module_providers.builtin import (
    ARPEGGIO_BRAIN_MANIFEST,
    HARMONY_BRAIN_MANIFEST,
    MELODY_BRAIN_MANIFEST,
    ArpeggioBrain,
    ArpeggioBrainParameters,
    ArpeggioPattern,
    HarmonicStyle,
    HarmonyBrain,
    HarmonyBrainParameters,
    MelodyBrain,
    MelodyBrainParameters,
    MelodyStyle,
)


def test_brain_manifests_keep_musical_pitch_and_timing_distinct() -> None:
    melody = {port.id: port for port in MELODY_BRAIN_MANIFEST.ports}
    harmony = {port.id: port for port in HARMONY_BRAIN_MANIFEST.ports}
    arpeggio = {port.id: port for port in ARPEGGIO_BRAIN_MANIFEST.ports}

    assert melody["note"].signal_type is SignalType.MUSICAL
    assert melody["pitch"].signal_type is SignalType.CV
    assert melody["phrase"].signal_type is SignalType.TRIGGER
    assert harmony["chord"].signal_type is SignalType.MUSICAL
    assert harmony["voice_4"].signal_type is SignalType.CV
    assert arpeggio["clock"].signal_type is SignalType.GATE


def test_melody_brain_prepares_a_seeded_phrase_with_rests_and_cadence() -> None:
    parameters = MelodyBrainParameters(
        system="japanese",
        tonic="A",
        octave=3,
        scale_name="hirajoshi",
        style=MelodyStyle.WANDER,
        phrase_length=16,
        density=0.65,
        seed=777,
    )

    first = MelodyBrain(parameters.model_copy())
    second = MelodyBrain(parameters.model_copy())

    assert first.phrase == second.phrase
    assert first.phrase[0] == 0
    assert first.phrase[-1] == 0
    assert any(step is None for step in first.phrase)


def test_melody_brain_is_deterministic_across_block_boundaries() -> None:
    parameters = MelodyBrainParameters(seed=42, density=0.72)
    continuous = MelodyBrain(parameters.model_copy())
    split = MelodyBrain(parameters.model_copy())
    clock = np.tile([0.0, 1.0, 1.0, 0.0], 20)
    density = np.linspace(-0.2, 0.15, len(clock))

    expected = continuous.process(
        len(clock),
        100.0,
        {"clock": clock, "density_cv": density},
    )
    first = split.process(
        31,
        100.0,
        {"clock": clock[:31], "density_cv": density[:31]},
    )
    second = split.process(
        len(clock) - 31,
        100.0,
        {"clock": clock[31:], "density_cv": density[31:]},
    )

    for name in expected:
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            expected[name],
        )


def test_mutation_changes_one_dense_phrase_without_leaving_scale_range() -> None:
    brain = MelodyBrain(MelodyBrainParameters(density=1.0, seed=12))
    original = brain.phrase

    brain.process(3, 100.0, {"mutate": [0.0, 1.0, 0.0]})

    assert brain.phrase != original
    assert all(step is not None and step >= 0 for step in brain.phrase)


def test_harmony_brain_uses_pytheory_progression_and_cached_voicings() -> None:
    brain = HarmonyBrain(
        HarmonyBrainParameters(
            tonic="C",
            mode="major",
            style=HarmonicStyle.JOURNEY,
            length=4,
        )
    )
    clock = np.tile([0.0, 1.0], 4)

    outputs = brain.process(len(clock), 100.0, {"clock": clock})
    edges = [1, 3, 5, 7]

    assert brain.chord_symbols == ("C", "Am", "F", "G")
    np.testing.assert_allclose(outputs["chord"][edges], [60.0, 69.0, 65.0, 67.0])
    assert outputs["function"][edges].tolist() == pytest.approx([0.0, 0.0, 0.5, 1.0])
    for edge in edges:
        voices = [outputs[f"voice_{voice}"][edge] for voice in range(1, 5)]
        assert voices == sorted(voices)


def test_functional_harmony_is_seeded() -> None:
    parameters = HarmonyBrainParameters(
        style=HarmonicStyle.FUNCTIONAL,
        length=12,
        seed=777,
    )

    assert HarmonyBrain(parameters.model_copy()).chord_symbols == (
        HarmonyBrain(parameters.model_copy()).chord_symbols
    )


def test_arpeggio_brain_serializes_four_harmony_voices() -> None:
    brain = ArpeggioBrain(
        ArpeggioBrainParameters(
            pattern=ArpeggioPattern.UP,
            octave_range=1,
        )
    )
    clock = np.tile([0.0, 1.0], 4)
    inputs = {
        "clock": clock,
        "voice_1": 0.0,
        "voice_2": 0.25,
        "voice_3": 7 / 12,
        "voice_4": 1.0,
    }

    outputs = brain.process(len(clock), 100.0, inputs)

    np.testing.assert_allclose(
        outputs["pitch"][[1, 3, 5, 7]],
        [0.0, 0.25, 7 / 12, 1.0],
    )
    np.testing.assert_allclose(outputs["trigger"][[1, 3, 5, 7]], 1.0)


def test_brain_parameter_models_reject_invalid_musical_selections() -> None:
    with pytest.raises(ValidationError, match="not a western scale"):
        MelodyBrainParameters(scale_name="hirajoshi")
    with pytest.raises(ValidationError, match="major or minor"):
        HarmonyBrainParameters(mode="dorian")

