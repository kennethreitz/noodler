"""Modules that keep time with the rack's one clock."""

import numpy as np
import pytest

from noodler.engine import SystemAudioEngine
from noodler.module_providers.builtin import (
    BuiltinProvider,
    Clock,
    ClockParameters,
    PATTERN_NAMES,
    PyTheoryBeats,
    PyTheoryBeatsParameters,
)
from noodler.module_providers.builtin.clocked import _steps_in_block, render_hit
from noodler.patch import PatchGraph
from noodler.transport import Transport, TransportFrame
from pytheory import DrumSound

SR = 48_000.0
N = 256


def _edges(signal: np.ndarray) -> np.ndarray:
    """Rising edges, counting one that is already high at sample zero."""
    high = (signal > 0.0).astype(int)
    return np.flatnonzero(np.diff(np.concatenate([[0], high])) > 0)


def _run(module, transport: Transport | None, seconds: float, extra=None):
    outputs = {}
    for _ in range(int(seconds * SR / N)):
        inputs = dict(extra or {})
        if transport is not None:
            inputs["transport"] = transport.tick(N, SR)
        out = module.process(N, SR, inputs)
        for name, value in out.items():
            outputs.setdefault(name, []).append(value)
    return {name: np.concatenate(values) for name, values in outputs.items()}


# ---------------------------------------------------------------- transport


def test_the_transport_ticks_on_the_sample_clock_and_reports_block_start() -> None:
    transport = Transport(bpm=120.0)
    frame = transport.tick(N, SR)
    assert isinstance(frame, TransportFrame)
    assert frame.phase == 0.0 and frame.bars == 0, "the frame is where the block began"
    # 256 samples at 48k = 5.33 ms; a bar at 120 in 4/4 is 2 s.
    assert transport.phase == pytest.approx(N / SR / 2.0)


def test_bars_are_counted_so_long_patterns_know_where_they_are() -> None:
    transport = Transport(bpm=120.0)
    for _ in range(int(5.0 * SR / N)):
        transport.tick(N, SR)
    assert transport.bars == 2
    assert transport.frame().quarters == pytest.approx(10.0, abs=0.05)


def test_a_stopped_transport_does_not_move() -> None:
    transport = Transport(bpm=120.0, running=False)
    for _ in range(50):
        transport.tick(N, SR)
    assert transport.phase == 0.0 and transport.bars == 0


def test_the_engine_hands_the_graph_a_frame_per_block() -> None:
    patch = PatchGraph()
    transport = Transport(bpm=100.0)
    engine = SystemAudioEngine(patch, transport=transport)
    engine._active_sample_rate = SR
    out = np.zeros((N, 2), dtype=np.float32)
    engine._audio_callback(out, N, None, None)
    assert isinstance(patch.transport, TransportFrame)
    assert patch.transport.bpm == 100.0
    assert transport.phase > 0.0, "the callback advanced the clock"


def test_only_a_module_that_asks_gets_the_clock() -> None:
    patch = PatchGraph()
    seen = {}

    class Listens:
        manifest = Clock.manifest
        uses_transport = True
        def process(self, n, sr, inputs=None):
            seen["listens"] = (inputs or {}).get("transport")
            return {"beat": np.zeros(n, np.float32)}

    class Ignores:
        manifest = Clock.manifest
        def process(self, n, sr, inputs=None):
            seen["ignores"] = "transport" in (inputs or {})
            return {"beat": np.zeros(n, np.float32)}

    patch.add_module("a", Listens())
    patch.add_module("b", Ignores())
    patch.transport = Transport().frame()
    patch.render_stereo(N, SR)
    assert isinstance(seen["listens"], TransportFrame)
    assert seen["ignores"] is False


# --------------------------------------------------------------- arithmetic


def test_steps_land_once_and_only_once_across_block_edges() -> None:
    """A beat exactly on a block boundary must fire in one block, not both."""
    per_sample = 2.0 / SR  # 120 BPM
    fired = []
    start = 0.0
    for block_index in range(400):
        for index in _steps_in_block(start, per_sample, N, 1.0):
            fired.append(block_index * N + index)
        start += N * per_sample
    spacing = np.diff(fired)
    assert len(fired) == pytest.approx(400 * N * per_sample, abs=1)
    assert np.all(np.abs(spacing - SR / 2.0) <= 1.0), "beats are half a second apart"


# ------------------------------------------------------------------- clock


def test_the_clock_module_follows_tempo_and_signature() -> None:
    clock = Clock()
    clock.prepare(SR, N)
    out = _run(clock, Transport(bpm=90.0, beats_per_bar=3), 6.0)
    beats = _edges(out["beat"])
    bars = _edges(out["bar"])
    assert np.mean(np.diff(beats)) / SR == pytest.approx(60.0 / 90.0, abs=1e-3)
    assert np.mean(np.diff(bars)) / SR == pytest.approx(2.0, abs=1e-3)
    assert out["phase"].min() >= 0.0 and out["phase"].max() <= 1.0
    assert np.all(out["run"] == 1.0)


def test_the_clock_module_runs_free_without_a_transport() -> None:
    clock = Clock(ClockParameters(rate_hz=4.0))
    clock.prepare(SR, N)
    out = _run(clock, None, 3.0)
    assert np.mean(np.diff(_edges(out["beat"]))) / SR == pytest.approx(0.25, abs=1e-3)


def test_the_clock_module_goes_quiet_when_the_transport_stops() -> None:
    clock = Clock()
    clock.prepare(SR, N)
    out = _run(clock, Transport(running=False), 2.0)
    assert not _edges(out["beat"]).size
    assert np.all(out["run"] == 0.0)


# ------------------------------------------------------------------- beats


def test_pytheory_synthesises_the_drums() -> None:
    kick = render_hit(DrumSound.KICK)
    hat = render_hit(DrumSound.CLOSED_HAT)
    assert kick.size > 1_000 and hat.size > 100
    assert np.max(np.abs(kick)) == pytest.approx(1.0)
    # A kick is low and a hat is not: the two spectra should not agree.
    def centroid(x):
        s = np.abs(np.fft.rfft(x)); f = np.fft.rfftfreq(x.size, 1 / 44_100)
        return float(np.sum(f * s) / np.sum(s))
    assert centroid(kick) < centroid(hat) / 2


def test_every_preset_loads_and_plays() -> None:
    assert len(PATTERN_NAMES) >= 100
    for name in PATTERN_NAMES[::7]:  # a sample, so the suite stays quick
        beats = PyTheoryBeats(PyTheoryBeatsParameters(pattern=name))
        beats.prepare(SR, N)
        assert beats.ready, name
        out = _run(beats, Transport(bpm=110.0), 4.0)
        assert np.all(np.isfinite(out["audio"])), name
        assert float(np.max(np.abs(out["audio"]))) > 0.05, f"{name} is silent"


def test_beat_one_is_beat_one() -> None:
    """The first hit of a rock beat is a kick on the downbeat: sample zero."""
    beats = PyTheoryBeats(PyTheoryBeatsParameters(pattern="rock"))
    beats.prepare(SR, N)
    out = _run(beats, Transport(bpm=120.0), 4.5)
    first = int(np.flatnonzero(np.abs(out["audio"]) > 0.01)[0])
    # A kick begins with a click whose first sample or two may be quiet, so
    # "on the downbeat" is within a fraction of a millisecond of it.
    assert first <= 8
    downbeats = _edges(out["downbeat"])
    # A four-beat pattern at 120 comes round every two seconds.
    assert np.allclose(np.diff(downbeats) / SR, 2.0, atol=1e-3)


def test_the_pattern_follows_a_tempo_change() -> None:
    beats = PyTheoryBeats(PyTheoryBeatsParameters(pattern="rock"))
    beats.prepare(SR, N)
    transport = Transport(bpm=60.0)
    slow = _run(beats, transport, 4.0)
    transport.set_bpm(180.0)
    fast = _run(beats, transport, 4.0)
    assert len(_edges(fast["trigger"])) > 2 * len(_edges(slow["trigger"]))


def test_stopping_the_transport_stops_the_drums() -> None:
    beats = PyTheoryBeats(PyTheoryBeatsParameters(pattern="rock"))
    beats.prepare(SR, N)
    transport = Transport(bpm=120.0)
    _run(beats, transport, 2.0)
    transport.running = False
    quiet = _run(beats, transport, 2.0)
    assert float(np.max(np.abs(quiet["audio"][-int(SR):]))) < 1e-4
    assert not _edges(quiet["trigger"][int(SR):]).size


def test_a_pattern_can_run_free_and_be_reset() -> None:
    beats = PyTheoryBeats(
        PyTheoryBeatsParameters(pattern="rock", follow_clock=False, rate_hz=2.0)
    )
    beats.prepare(SR, N)
    out = _run(beats, Transport(bpm=30.0), 4.0)  # transport present but ignored
    assert np.allclose(np.diff(_edges(out["downbeat"])) / SR, 2.0, atol=1e-3)
    # Reset pulls it back to the top mid-pattern.
    _run(beats, None, 0.7)
    reset = np.zeros(N, np.float32); reset[0] = 1.0
    out = beats.process(N, SR, {"reset": reset})
    assert out["downbeat"][0] == 1.0


def test_swing_leans_the_off_beats_late() -> None:
    def hat_offsets(swing: float) -> np.ndarray:
        beats = PyTheoryBeats(PyTheoryBeatsParameters(pattern="rock", swing=swing))
        beats.prepare(SR, N)
        out = _run(beats, Transport(bpm=120.0), 2.0)
        return _edges(out["trigger"]) / SR

    straight, swung = hat_offsets(0.0), hat_offsets(1.0)
    # The off-beat eighths (0.25 s, 0.75 s, ...) move later; the beats do not.
    assert 0.25 in np.round(straight, 3)
    assert 0.25 not in np.round(swung, 3)
    assert 0.0 in np.round(swung, 3) and 0.5 in np.round(swung, 3)


def test_the_callback_never_renders_a_drum() -> None:
    beats = PyTheoryBeats(PyTheoryBeatsParameters(pattern="samba"))
    beats.prepare(SR, N)
    import time
    transport = Transport(bpm=140.0)
    started = time.perf_counter()
    blocks = int(4 * SR / N)
    for _ in range(blocks):
        beats.process(N, SR, {"transport": transport.tick(N, SR)})
    per_block = (time.perf_counter() - started) / blocks * 1_000
    assert per_block < 0.5, f"{per_block:.3f} ms a block"


def test_changing_the_pattern_needs_a_refresh_and_offers_them_all() -> None:
    beats = BuiltinProvider().create("pytheory_beats")
    beats.prepare(SR, N)
    assert beats.ready
    beats.parameters.pattern = "teental"
    assert not beats.ready
    beats.refresh()
    assert beats.ready and "TEENTAL" in beats.label
    assert set(beats.choices_for("pattern")) == set(PATTERN_NAMES)
