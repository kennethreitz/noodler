"""PyTheory's effects, ragas and tone rows, in the rack."""

import numpy as np
import pytest

from noodler.module_providers.builtin import (
    FX_EFFECTS,
    RAGA_NAMES,
    BuiltinProvider,
    PyTheoryFX,
    PyTheoryFXParameters,
    RagaVoice,
    RagaVoiceParameters,
    ToneRowParameters,
    ToneRowVoice,
    parse_row,
)
from noodler.module_providers.builtin.raga import swara_octave
from noodler.module_providers.builtin.tone_row import RowError

SR, N = 48_000.0, 256


def _tone(seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _run(module, x: np.ndarray, port: str = "audio_out", inputs=None):
    out = []
    for i in range(0, x.size - N + 1, N):
        out.append(module.process(N, SR, {"audio": x[i : i + N], **(inputs or {})})[port])
    return np.concatenate(out)


# ------------------------------------------------------------------ effects


def test_every_effect_colours_the_signal_and_stays_finite() -> None:
    x = _tone()
    for effect in FX_EFFECTS:
        fx = PyTheoryFX(PyTheoryFXParameters(effect=effect, mix=1.0, depth=0.6, drive=4.0))
        fx.prepare(SR, N)
        y = _run(fx, x)
        assert np.all(np.isfinite(y)), effect
        assert float(np.sqrt(np.mean((y - x[: y.size]) ** 2))) > 0.02, f"{effect} did nothing"


def test_mix_zero_is_the_dry_signal() -> None:
    x = _tone(0.5)
    for effect in FX_EFFECTS:
        fx = PyTheoryFX(PyTheoryFXParameters(effect=effect, mix=0.0))
        fx.prepare(SR, N)
        y = _run(fx, x)
        np.testing.assert_allclose(y, x[: y.size], atol=1e-6, err_msg=effect)


def test_the_tremolo_lfo_carries_its_phase_across_blocks() -> None:
    fx = PyTheoryFX(PyTheoryFXParameters(effect="tremolo", mix=1.0, depth=1.0, rate_hz=2.0))
    fx.prepare(SR, N)
    y = _run(fx, np.ones(int(SR), dtype=np.float32))
    # A two-hertz tremolo on DC is a two-hertz wave: no discontinuities at
    # block edges, and one full cycle every half second.
    assert float(np.max(np.abs(np.diff(y)))) < 0.01
    troughs = np.flatnonzero((y[1:-1] < y[:-2]) & (y[1:-1] < y[2:]) & (y[1:-1] < 0.05)) + 1
    assert troughs.size >= 1
    if troughs.size >= 2:
        assert np.allclose(np.diff(troughs) / SR, 0.5, atol=0.02)


def test_the_distortion_gets_louder_with_drive_and_the_saturation_adds_even_harmonics() -> None:
    x = _tone(0.5)
    soft = _run(PyTheoryFX(PyTheoryFXParameters(effect="distortion", mix=1.0, drive=1.0)), x)
    hard = _run(PyTheoryFX(PyTheoryFXParameters(effect="distortion", mix=1.0, drive=8.0)), x)
    assert float(np.sqrt(np.mean(hard**2))) > float(np.sqrt(np.mean(soft**2)))
    sat = _run(PyTheoryFX(PyTheoryFXParameters(effect="saturation", mix=1.0, depth=1.0)), x)
    length = (sat.size // N) * N
    spectrum = np.abs(np.fft.rfft(sat[:length] * np.hanning(length)))
    freqs = np.fft.rfftfreq(length, 1 / SR)
    second = spectrum[np.argmin(np.abs(freqs - 440.0))]
    fundamental = spectrum[np.argmin(np.abs(freqs - 220.0))]
    assert second > fundamental * 0.05, "a second harmonic appeared"


def test_the_panel_offers_every_effect() -> None:
    fx = BuiltinProvider().create("pytheory_fx")
    assert set(fx.choices_for("effect")) == set(FX_EFFECTS)


# -------------------------------------------------------------------- ragas


def test_swaras_are_read_the_way_pytheory_writes_them() -> None:
    assert swara_octave("N.") == ("N", -1)
    assert swara_octave("S'") == ("S", 1)
    assert swara_octave("g") == ("g", 0)


def test_a_raga_climbs_by_the_aroha_and_is_justly_tuned() -> None:
    assert len(RAGA_NAMES) >= 50
    voice = RagaVoice(RagaVoiceParameters(raga="Yaman", sa="C3", style="aroha avaroha", rate_hz=8.0, density=1.0))
    voice.prepare(SR, N)
    freq, trig = [], []
    for _ in range(int(3 * SR / N)):
        out = voice.process(N, SR, {})
        freq.append(out["frequency"])
        trig.append(out["trigger"])
    freq, trig = np.concatenate(freq), np.concatenate(trig)
    onsets = np.flatnonzero(np.diff(np.concatenate([[0], (trig > 0).astype(int)])) > 0)
    notes = [float(freq[i + 2]) for i in onsets]
    sa = 130.81
    ratios = [round(n / sa, 3) for n in notes[:8]]
    # Yaman's aroha from N. below: 15/16, 9/8, 5/4, 45/32, 5/3, 15/8, 2 -- just.
    assert ratios[:7] == pytest.approx([0.9375, 1.125, 1.25, 1.40625, 1.6667, 1.875, 2.0], rel=0.002)


def test_a_raga_can_be_clocked_and_reset() -> None:
    voice = RagaVoice(RagaVoiceParameters(raga="Bhupali", sa="D3", style="walk", density=1.0))
    voice.prepare(SR, N)
    clock = np.zeros(N, np.float32)
    clock[0] = 1.0
    steps = 0
    for _ in range(40):
        out = voice.process(N, SR, {"clock": clock})
        steps += int(out["trigger"][0] > 0)
    assert steps == 40, "one note per clock"
    silent = voice.process(N, SR, {"clock": np.zeros(N, np.float32)})
    assert float(silent["trigger"].max()) == 0.0


def test_the_pakad_style_plays_the_pakad() -> None:
    voice = RagaVoice(RagaVoiceParameters(raga="Yaman", sa="C3", style="pakad", rate_hz=8.0, density=1.0))
    voice.prepare(SR, N)
    phrase = np.concatenate([voice.process(N, SR, {})["phrase"] for _ in range(int(2 * SR / N))])
    assert float(phrase.max()) > 0.0


def test_the_raga_panel_offers_every_raga_and_says_what_it_is() -> None:
    voice = BuiltinProvider().create("pytheory_raga")
    assert set(voice.choices_for("raga")) == set(RAGA_NAMES)
    assert "YAMAN" in voice.label and "THAAT" in voice.label


# ---------------------------------------------------------------- tone rows


def test_a_row_is_twelve_pitch_classes_each_once() -> None:
    row = parse_row("0 11 7 8 3 1 2 10 6 5 4 9")
    assert sorted(row.form("P0")) == list(range(12))
    assert parse_row("C Db D Eb E F Gb G Ab A Bb B").form("P0") == list(range(12))
    with pytest.raises(RowError):
        parse_row("0 1 2")
    with pytest.raises(RowError):
        parse_row("0 0 1 2 3 4 5 6 7 8 9 10")


def test_forms_come_from_pytheory_and_the_row_loops() -> None:
    voice = ToneRowVoice(ToneRowParameters(row="0 11 7 8 3 1 2 10 6 5 4 9", form="I", transposition=2, rate_hz=8.0))
    voice.prepare(SR, N)
    assert voice.label.startswith("I2")
    row_start, pitch = [], []
    for _ in range(int(3.2 * SR / N)):
        out = voice.process(N, SR, {})
        row_start.append(out["row_start"])
        pitch.append(out["pitch"])
    starts = np.flatnonzero(np.diff(np.concatenate([[0], (np.concatenate(row_start) > 0).astype(int)])) > 0)
    assert len(starts) >= 2 and np.allclose(np.diff(starts) / SR, 12 / 8.0, atol=0.01), "twelve notes round"


def test_a_row_that_is_not_a_row_is_a_fault_not_a_crash() -> None:
    voice = ToneRowVoice(ToneRowParameters(row="0 1 2"))
    voice.prepare(SR, N)
    assert "FAULT" in voice.label
    voice.process(N, SR, {})
