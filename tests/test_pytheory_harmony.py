"""PyTheory's progressions, maqamat, chord ear and negative harmony in the rack."""

import math

import numpy as np
import pytest

from noodler.module_providers.builtin import BuiltinProvider
from noodler.module_providers.builtin.chord_ear import ChordEar, name_chord
from noodler.module_providers.builtin.maqam import MAQAM_NAMES, MaqamParameters, MaqamVoice
from noodler.module_providers.builtin.negative_harmony import NegativeHarmony, NegativeHarmonyParameters, mirror_midi
from noodler.module_providers.builtin.progression import (
    PROGRESSION_NAMES,
    ProgressionError,
    ProgressionParameters,
    PyTheoryProgression,
    parse_numerals,
)
from noodler.transport import Transport

SR = 48_000.0


def midi_of(volts: float, reference: float = 220.0) -> int:
    return int(round(69 + 12 * math.log2(reference * 2.0 ** volts / 440.0)))


# ---- progression --------------------------------------------------------------


def test_the_progression_walks_its_chords_on_its_own_rate_and_voices_them_low_to_high() -> None:
    voice = PyTheoryProgression(ProgressionParameters(follow_clock=False, rate_hz=4.0))
    voice.prepare(SR)
    out = voice.process(int(SR), SR)
    # Four chords a second: the first at once, three changes after.
    assert int((np.diff(out["change"]) > 0).sum()) == 3
    assert "I-V-vi-IV" in PROGRESSION_NAMES and "custom" in PROGRESSION_NAMES
    v = [midi_of(float(out[f"voice_{i}"][100])) for i in range(1, 5)]
    assert v == sorted(v) and v[0] >= 60, "voiced low to high, in the fourth octave"
    assert midi_of(float(out["root"][100])) < v[0], "the root below the voices"
    assert out["gate"].mean() == pytest.approx(0.9, abs=0.02)
    assert "C MAJOR" in voice.label


def test_the_progression_changes_a_chord_every_bar_of_the_transport() -> None:
    voice = PyTheoryProgression(ProgressionParameters(progression="Pachelbel", tonic="D", bars_per_chord=1))
    voice.prepare(SR)
    transport = Transport(bpm=120.0)
    changes = 0
    labels = []
    block = 4800
    for _ in range(int(SR * 4.5 / block)):  # four and a half seconds: two bars and a bit at 120
        frame = transport.tick(block, SR)
        out = voice.process(block, SR, {"transport": frame})
        changes += int((np.diff(out["change"]) > 0).sum() + (out["change"][0] > 0))
        labels.append(voice.label)
    assert changes >= 3, "the first chord, then one per bar"
    assert labels[0].startswith("D MAJOR") and any(l.startswith("A MAJOR") for l in labels), "I then V, in D"


def test_the_progression_steps_on_a_trigger_and_wanders_when_asked() -> None:
    voice = PyTheoryProgression(ProgressionParameters(progression="Andalusian", tonic="A", mode="minor"))
    voice.prepare(SR)
    step = np.zeros(1000, dtype=np.float32)
    step[10] = 1.0
    seen = []
    for _ in range(4):
        voice.process(1000, SR, {"step": step})
        seen.append(voice.label.split("  ·  ")[0])
    assert seen == ["A MINOR", "G MAJOR", "F MAJOR", "E MAJOR"], seen
    wander = PyTheoryProgression(ProgressionParameters(style="wander", follow_clock=False, rate_hz=10.0, seed=1))
    wander.prepare(SR)
    names = set()
    for _ in range(30):
        wander.process(4800, SR)
        names.add(str(wander._current))
    assert len(names) >= 3, "wandering visits more than a loop of one"


def test_custom_numerals_are_read_and_a_bad_one_is_a_fault_not_a_crash() -> None:
    assert parse_numerals("I - V | vi, IV") == ("I", "V", "vi", "IV")
    with pytest.raises(ProgressionError):
        parse_numerals("   ")
    voice = PyTheoryProgression(ProgressionParameters(progression="custom", custom="ii V7 I", follow_clock=False))
    voice.prepare(SR)
    voice.process(256, SR)
    assert voice.label.startswith("D MINOR")
    broken = PyTheoryProgression(ProgressionParameters(progression="custom", custom="I nope"))
    broken.prepare(SR)
    out = broken.process(256, SR)
    assert "FAULT" in broken.label and float(out["gate"].max()) == 0.0


# ---- maqam ------------------------------------------------------------------


def test_the_maqam_is_tuned_justly_from_pytheory_with_its_quarter_tones() -> None:
    assert "Rast" in MAQAM_NAMES and "Bayati" in MAQAM_NAMES
    voice = MaqamVoice(MaqamParameters(maqam="Rast", tonic="D3", rate_hz=8.0))
    voice.prepare(SR)
    ladder = voice._ladder
    assert len(ladder) == 8 and ladder[-1] == pytest.approx(ladder[0] * 2.0, rel=1e-6), "tonic to octave"
    # Rast's third is neutral: 27/22 above the tonic, between minor and major.
    assert ladder[2] / ladder[0] == pytest.approx(27 / 22, rel=1e-6)
    out = voice.process(int(SR), SR)
    assert int((np.diff(out["trigger"]) > 0).sum()) >= 4
    assert 0.0 <= float(out["degree"].max()) <= 1.0
    assert "RAST" in voice.label and "QUARTER-TONES" in voice.label


def test_the_maqam_goes_up_and_down_its_ladder_when_asked_and_resets_to_the_tonic() -> None:
    voice = MaqamVoice(MaqamParameters(maqam="Hijaz", tonic="D3", style="up down", density=1.0))
    voice.prepare(SR)
    clock = np.zeros(2400, dtype=np.float32)
    clock[::240] = 1.0  # ten steps
    out = voice.process(2400, SR, {"clock": clock})
    heard = sorted(set(round(float(f), 1) for f in out["frequency"]))
    assert len(heard) >= 7, "up the ladder, degree by degree"
    reset = np.zeros(2400, dtype=np.float32)
    reset[0] = 1.0
    out = voice.process(2400, SR, {"clock": np.zeros(2400, dtype=np.float32), "reset": reset})
    assert float(out["frequency"][-1]) == pytest.approx(voice._ladder[0], rel=1e-6)


# ---- chord ear ----------------------------------------------------------------


def test_the_ear_names_the_chord_on_its_inputs_and_says_when_it_changes() -> None:
    assert name_chord([60, 64, 67, 70])[0] == "C dominant 7th"
    assert name_chord([64, 67, 72])[0] == "C major" and name_chord([64, 67, 72])[1] == 60
    assert name_chord([60])[0] is None
    ear = ChordEar()
    ear.prepare(SR)

    def held(*midis):
        return {f"pitch_{i + 1}": np.full(256, (m - 57) / 12.0, dtype=np.float32) for i, m in enumerate(midis)}

    out = ear.process(256, SR, held(60, 64, 67))
    assert ear.label == "C MAJOR"
    assert midi_of(float(out["root"][0])) == 60 and float(out["known"][0]) == 1.0
    assert float(out["changed"].max()) == 1.0
    out = ear.process(256, SR, held(60, 64, 67))
    assert int((np.diff(out["changed"]) > 0).sum()) == 0, "the same chord is not a change"
    out = ear.process(256, SR, held(62, 65, 69, 72))
    assert ear.label == "D MINOR 7TH" and float(out["changed"].max()) == 1.0
    assert float(out["dissonance"][0]) > 0.5, "a seventh chord is more dissonant than a triad"
    # Listening only on a trigger: no trigger, no new name.
    listen = np.zeros(256, dtype=np.float32)
    out = ear.process(256, SR, {**held(60, 63, 67), "listen": listen})
    assert ear.label == "D MINOR 7TH"
    listen[100] = 1.0
    out = ear.process(256, SR, {**held(60, 63, 67), "listen": listen})
    assert ear.label == "C MINOR" and float(out["changed"][100]) == 1.0


# ---- negative harmony ---------------------------------------------------------


def test_negative_harmony_mirrors_about_the_axis_the_way_pytheory_does() -> None:
    # C major's axis is between E flat and E: C <-> G, E <-> Eb, D <-> F, B <-> Ab.
    assert mirror_midi(60, 0) == 55 and mirror_midi(64, 0) == 63 and mirror_midi(67, 0) == 72
    assert mirror_midi(62, 0) == 65 and mirror_midi(71, 0) == 68
    module = NegativeHarmony(NegativeHarmonyParameters(tonic="C"))
    module.prepare(SR)
    pitch = np.array([(m - 57) / 12.0 for m in (60, 64, 67, 62, 71)], dtype=np.float32)
    out = module.process(5, SR, {"pitch": pitch})
    assert [midi_of(float(v)) for v in out["out"]] == [55, 63, 72, 65, 68]
    assert np.allclose(out["straight"], pitch)
    assert "AXIS Eb/E" in module.label
    # A gate decides when patched; the switch when not.
    gate = np.array([1, 0, 1, 0, 1], dtype=np.float32)
    out = module.process(5, SR, {"pitch": pitch, "mirror": gate})
    assert [midi_of(float(v)) for v in out["out"]] == [55, 64, 72, 62, 68]
    module.parameters.mirror = False
    out = module.process(5, SR, {"pitch": pitch})
    assert np.allclose(out["out"], pitch) and "STRAIGHT" in module.label


def test_the_four_are_built_in_and_carry_their_choices() -> None:
    provider = BuiltinProvider()
    progression = provider.create("pytheory_progression")
    assert "Pachelbel" in progression.choices_for("progression") and "dorian" in progression.choices_for("mode")
    maqam = provider.create("pytheory_maqam")
    assert set(maqam.choices_for("maqam")) == set(MAQAM_NAMES)
    assert provider.create("pytheory_chord_ear").manifest.category == "Musical Brains"
    assert provider.create("pytheory_negative_harmony").choices_for("tonic")[0] == "C"
