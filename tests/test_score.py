"""A written phrase, played on the clock."""

import numpy as np
import pytest

from noodler.module_providers.builtin import BuiltinProvider, PyTheoryScore, PyTheoryScoreParameters, parse_phrase
from noodler.module_providers.builtin.score import PhraseError, parse_duration
from noodler.transport import Transport

SR, N = 48_000.0, 256


def _edges(x: np.ndarray) -> np.ndarray:
    return np.flatnonzero(np.diff(np.concatenate([[0], (x > 0.0).astype(int)])) > 0)


def _play(module, seconds: float, bpm: float = 120.0):
    transport = Transport(bpm=bpm)
    outs = {}
    for _ in range(int(seconds * SR / N)):
        out = module.process(N, SR, {"transport": transport.tick(N, SR)})
        for k, v in out.items():
            outs.setdefault(k, []).append(v)
    return {k: np.concatenate(v) for k, v in outs.items()}


def test_durations_are_letters_dots_triplets_or_beats() -> None:
    assert parse_duration("q") == 1.0
    assert parse_duration("e.") == 0.75
    assert parse_duration("qt") == pytest.approx(2 / 3)
    assert parse_duration("1.5") == 1.5
    with pytest.raises(PhraseError):
        parse_duration("x")


def test_pytheory_reads_the_note_names() -> None:
    steps = parse_phrase("C4:q F#3:e Bb2:h r:q [A3,C4,E4]:w*5")
    assert [s.midis for s in steps] == [(60,), (54,), (46,), (), (57, 60, 64)]
    assert [s.beats for s in steps] == [1.0, 0.5, 2.0, 1.0, 4.0]
    assert steps[-1].velocity == pytest.approx(5 / 9)


def test_a_bad_phrase_is_a_fault_not_a_crash() -> None:
    with pytest.raises(PhraseError):
        parse_phrase("E5 D5")
    with pytest.raises(PhraseError):
        parse_phrase("H9:q")
    module = PyTheoryScore(PyTheoryScoreParameters(phrase="E5 D5"))
    module.prepare(SR, N)
    assert "FAULT" in module.label
    out = module.process(N, SR, {})
    assert out["gate"].shape == (N,)


def test_the_phrase_plays_on_the_clock_and_loops() -> None:
    module = PyTheoryScore(PyTheoryScoreParameters(phrase="A3:q C4:q E4:q A4:q"))
    module.prepare(SR, N)
    out = _play(module, 4.5)
    onsets = _edges(out["trigger"]) / SR
    assert np.allclose(onsets[:8], np.arange(8) * 0.5, atol=1e-3)
    pitches = [round(float(out["pitch"][i + 2]), 3) for i in _edges(out["trigger"])[:4]]
    assert pitches == [0.0, 0.25, 0.583, 1.0]
    assert np.allclose(np.diff(_edges(out["phrase"])) / SR, 2.0, atol=1e-3), "four beats round"
    assert float(np.mean(out["gate"] > 0)) == pytest.approx(0.7, abs=0.02)


def test_chords_come_out_on_four_voices_and_rests_close_the_gate() -> None:
    module = PyTheoryScore(PyTheoryScoreParameters(phrase="[A3,C4,E4,A4]:h r:h"))
    module.prepare(SR, N)
    out = _play(module, 2.0)
    first = _edges(out["trigger"])[0] + 2
    assert [round(float(out[v][first]), 3) for v in ("pitch", "voice_2", "voice_3", "voice_4")] == [0.0, 0.25, 0.583, 1.0]
    # Second half of the bar is a rest: the gate is down.
    assert float(np.max(out["gate"][int(1.1 * SR) : int(1.9 * SR)])) == 0.0


def test_transpose_shifts_every_voice() -> None:
    module = PyTheoryScore(PyTheoryScoreParameters(phrase="A3:w"))
    module.prepare(SR, N)
    transport = Transport(bpm=120.0)
    out = module.process(N, SR, {"transport": transport.tick(N, SR), "transpose": np.full(N, 1.0, np.float32)})
    assert float(out["pitch"][-1]) == pytest.approx(1.0)


def test_it_follows_a_tempo_change_and_runs_free_without_a_clock() -> None:
    module = PyTheoryScore(PyTheoryScoreParameters(phrase="C4:q D4:q", follow_clock=False, rate_hz=4.0))
    module.prepare(SR, N)
    outs = [module.process(N, SR, {})["trigger"] for _ in range(int(2 * SR / N))]
    onsets = _edges(np.concatenate(outs)) / SR
    assert np.allclose(np.diff(onsets), 0.25, atol=1e-3)


def test_the_panel_offers_a_phrase_field() -> None:
    module = BuiltinProvider().create("pytheory_score")
    assert isinstance(module.parameters.phrase, str)
    module.parameters.phrase = "G4:e"
    module.prepare(SR, N)
    assert "1 STEPS" in module.label
