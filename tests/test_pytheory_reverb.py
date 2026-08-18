"""PyTheory's rooms, live."""

import time

import numpy as np
import pytest

from noodler.module_providers.builtin import BuiltinProvider, PyTheoryReverb, PyTheoryReverbParameters, REVERB_SPACES
from noodler.module_providers.builtin.pytheory_reverb import SCHROEDER, _Convolver, render_impulse

SR = 48_000.0
N = 256


def _burst(seconds: float = 3.0) -> np.ndarray:
    rng = np.random.default_rng(1)
    x = np.zeros(int(seconds * SR), dtype=np.float32)
    x[:2400] = (rng.standard_normal(2400) * np.exp(-np.arange(2400) / 500)).astype(np.float32) * 0.5
    return x


def _run(reverb: PyTheoryReverb, x: np.ndarray, block: int = N) -> tuple[np.ndarray, np.ndarray]:
    left, right = [], []
    for i in range(0, x.size - block + 1, block):
        out = reverb.process(block, SR, {"audio": x[i : i + block]})
        left.append(out["left"])
        right.append(out["right"])
    return np.concatenate(left), np.concatenate(right)


def test_the_partitioned_convolver_matches_a_direct_convolution() -> None:
    rng = np.random.default_rng(3)
    ir = (rng.standard_normal(1000) * np.exp(-np.arange(1000) / 300)).astype(np.float32)
    x = rng.standard_normal(4096).astype(np.float32)
    for block in (256, 64):
        convolver = _Convolver(ir, block)
        out = np.concatenate([convolver.process(x[i : i + block]) for i in range(0, x.size, block)])
        reference = np.convolve(x.astype(np.float64), ir.astype(np.float64))[: x.size]
        assert np.max(np.abs(out - reference)) < 1e-4


def test_every_room_builds_quickly_and_leaves_a_tail() -> None:
    assert SCHROEDER in REVERB_SPACES and len(REVERB_SPACES) >= 9
    for space in REVERB_SPACES:
        reverb = PyTheoryReverb(PyTheoryReverbParameters(space=space, mix=1.0, decay_seconds=2.0))
        started = time.perf_counter()
        reverb.prepare(SR, N)
        assert (time.perf_counter() - started) < 0.5, space
        left, right = _run(reverb, _burst(3.0))
        assert np.all(np.isfinite(left)) and np.all(np.isfinite(right)), space
        after_a_second = float(np.sqrt(np.mean(left[int(SR) : int(1.5 * SR)] ** 2)))
        assert after_a_second > 1e-4, f"{space} has no tail"


def test_a_room_is_stereo() -> None:
    reverb = PyTheoryReverb(PyTheoryReverbParameters(space="hall", mix=1.0, width=1.0))
    reverb.prepare(SR, N)
    left, right = _run(reverb, _burst())
    tail = slice(int(0.5 * SR), None)
    assert abs(np.corrcoef(left[tail], right[tail])[0, 1]) < 0.9


def test_width_zero_is_mono() -> None:
    reverb = PyTheoryReverb(PyTheoryReverbParameters(space="plate", mix=1.0, width=0.0))
    reverb.prepare(SR, N)
    left, right = _run(reverb, _burst())
    np.testing.assert_allclose(left, right, atol=1e-6)


def test_the_callback_never_renders_a_room() -> None:
    reverb = PyTheoryReverb(PyTheoryReverbParameters(space="taj_mahal", mix=1.0, decay_seconds=12.0))
    reverb.prepare(SR, N)
    x = _burst(1.0)
    _run(reverb, x)
    started = time.perf_counter()
    blocks = int(SR / N)
    for i in range(blocks):
        reverb.process(N, SR, {"audio": x[i * N : (i + 1) * N]})
    per_block = (time.perf_counter() - started) / blocks * 1_000
    assert per_block < 1.5, f"{per_block:.2f} ms a block for a twelve-second room"


def test_decay_shortens_an_impulse_and_the_schroeder_alike() -> None:
    short = render_impulse("cathedral", SR, 42, 0.5)
    long = render_impulse("cathedral", SR, 42, 4.0)
    assert short.size < long.size
    assert short.size == pytest.approx(0.5 * SR, rel=0.01)

    def tail_of(decay: float) -> float:
        reverb = PyTheoryReverb(PyTheoryReverbParameters(space=SCHROEDER, mix=1.0, decay_seconds=decay))
        reverb.prepare(SR, N)
        left, _right = _run(reverb, _burst(3.0))
        return float(np.sqrt(np.mean(left[int(2.0 * SR) : int(2.5 * SR)] ** 2)))

    assert tail_of(0.5) < tail_of(4.0)


def test_other_block_sizes_come_out_one_block_late_but_intact() -> None:
    reverb = PyTheoryReverb(PyTheoryReverbParameters(space="spring", mix=1.0))
    reverb.prepare(SR, 256)
    x = _burst(1.0)
    left, _right = _run(reverb, x, block=100)
    assert np.all(np.isfinite(left)) and float(np.max(np.abs(left))) > 0.0


def test_the_panel_offers_every_room_and_a_word_change_needs_a_refresh() -> None:
    reverb = BuiltinProvider().create("pytheory_reverb")
    reverb.prepare(SR, N)
    assert set(reverb.choices_for("space")) == set(REVERB_SPACES)
    assert reverb.ready
    reverb.parameters.space = "cave"
    assert not reverb.ready
    reverb.refresh()
    assert reverb.ready and "CAVE" in reverb.label
