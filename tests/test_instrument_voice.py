"""A voice built from one of PyTheory's instruments."""

import numpy as np
import pytest
from pytheory import INSTRUMENTS

from noodler.module_providers.builtin import (
    INSTRUMENT_NAMES,
    BuiltinProvider,
    InstrumentVoice,
    InstrumentVoiceParameters,
    instrument_voice,
)


def _play(voice: InstrumentVoice, held: int, released: int) -> np.ndarray:
    """Hold a note, then let it go, and return everything that came out."""
    silence = np.zeros(256, dtype=np.float32)
    pitch = np.zeros(256, dtype=np.float32)
    rendered = []
    for gate in (np.ones(256, dtype=np.float32),) * held + (silence,) * released:
        rendered.append(
            voice.process(256, 48_000.0, {"pitch": pitch, "gate": gate})["audio"]
        )
    return np.concatenate(rendered)


def test_every_instrument_pytheory_knows_is_offered() -> None:
    assert len(INSTRUMENT_NAMES) == len(INSTRUMENTS) >= 80
    assert INSTRUMENT_NAMES == tuple(sorted(INSTRUMENTS))


def test_a_recipe_becomes_an_oscillator_and_a_contour() -> None:
    recipe = instrument_voice("celesta")

    assert recipe["shape"] in {"sine", "saw", "pulse", "fm"}
    assert recipe["envelope"] == INSTRUMENTS["celesta"]["envelope"]
    assert recipe["attack"] > 0.0 and recipe["release"] > 0.0
    assert recipe["cutoff"] > 0.0


def test_every_instrument_can_be_played(  # the whole catalogue, not a sample
) -> None:
    voice = InstrumentVoice()
    for name in INSTRUMENT_NAMES:
        voice.parameters.instrument = name
        rendered = _play(voice, held=4, released=1)
        assert np.all(np.isfinite(rendered)), name
        assert float(np.max(np.abs(rendered))) > 0.0, f"{name} was silent"
        assert float(np.max(np.abs(rendered))) <= 1.0, f"{name} clipped"


def test_letting_go_of_the_gate_silences_the_voice() -> None:
    voice = InstrumentVoice(
        InstrumentVoiceParameters(instrument="clean_guitar", level=0.8)
    )
    rendered = _play(voice, held=8, released=400)

    tail = rendered[-2_048:]
    assert float(np.max(np.abs(tail))) < 1e-3, "the note never let go"


def test_a_pad_takes_longer_to_arrive_than_a_mallet() -> None:
    """The contour is the instrument's, not a default."""
    def onset(name: str) -> float:
        voice = InstrumentVoice(InstrumentVoiceParameters(instrument=name))
        rendered = _play(voice, held=6, released=0)
        loud = np.abs(rendered) > 0.05
        return float(np.argmax(loud)) if loud.any() else float(len(rendered))

    assert onset("analog_pad") > onset("celesta")


def test_two_instruments_do_not_sound_the_same() -> None:
    first = _play(InstrumentVoice(InstrumentVoiceParameters(instrument="celesta")), 6, 2)
    second = _play(InstrumentVoice(InstrumentVoiceParameters(instrument="cello")), 6, 2)

    assert not np.allclose(first, second)


def test_an_unknown_instrument_settles_on_a_known_one() -> None:
    voice = InstrumentVoice(InstrumentVoiceParameters(instrument="tuba-shaped horn"))
    assert voice.parameters.instrument in INSTRUMENTS


def test_the_panel_offers_every_instrument_by_name() -> None:
    voice = BuiltinProvider().create("instrument_voice")
    assert voice.choices_for("instrument") == INSTRUMENT_NAMES
    assert voice.choices_for("level") == ()


def test_pitch_reaches_the_oscillator() -> None:
    voice = InstrumentVoice(InstrumentVoiceParameters(instrument="church_organ"))
    gate = np.ones(1_024, dtype=np.float32)

    def zero_crossings(octaves: float) -> int:
        played = InstrumentVoice(
            InstrumentVoiceParameters(instrument="church_organ")
        ).process(
            1_024,
            48_000.0,
            {"pitch": np.full(1_024, octaves, dtype=np.float32), "gate": gate},
        )["audio"]
        return int(np.count_nonzero(np.diff(np.signbit(played))))

    assert zero_crossings(1.0) > zero_crossings(0.0), "an octave up is faster"
