"""The LFO: one phase, every shape."""

import numpy as np
import pytest

from noodler.module_providers.builtin import BuiltinProvider
from noodler.module_providers.builtin.lfo import LFO, LFOParameters, SHAPES

SR = 48_000.0


def test_every_shape_comes_out_at_once_and_the_chosen_one_is_the_main_output() -> None:
    lfo = LFO(LFOParameters(rate_hz=2.0))
    lfo.prepare(SR)
    out = lfo.process(int(SR), SR)
    assert set(out) == {"out", "sine", "triangle", "saw", "square", "random", "cycle"}
    assert np.allclose(out["out"], out["sine"]), "the main output is the chosen shape"
    for name in ("sine", "triangle", "saw", "square"):
        assert float(out[name].min()) == pytest.approx(-1.0, abs=1e-3)
        assert float(out[name].max()) == pytest.approx(1.0, abs=1e-3)
    assert abs(float(out["sine"].mean())) < 0.01 and abs(float(out["square"].mean())) < 0.01
    # Two hertz for a second: two tops of the cycle after the first sample.
    assert int((np.diff(out["cycle"]) > 0).sum()) >= 1
    assert "SINE" in lfo.label and "2.00 Hz" in lfo.label
    assert lfo.choices_for("shape") == SHAPES


def test_depth_offset_and_unipolar_scale_the_output_where_a_control_wants_it() -> None:
    lfo = LFO(LFOParameters(rate_hz=1.0, shape="triangle", depth=0.5, offset=0.25))
    lfo.prepare(SR)
    out = lfo.process(int(SR), SR)
    assert float(out["out"].min()) == pytest.approx(-0.25, abs=1e-3)
    assert float(out["out"].max()) == pytest.approx(0.75, abs=1e-3)
    uni = LFO(LFOParameters(rate_hz=1.0, shape="triangle", unipolar=True))
    uni.prepare(SR)
    out = uni.process(int(SR), SR)
    assert float(out["out"].min()) == pytest.approx(0.0, abs=1e-3)
    assert float(out["out"].max()) == pytest.approx(1.0, abs=1e-3)
    assert float(out["sine"].min()) >= 0.0, "every jack follows the polarity"
    assert "0..1" in uni.label


def test_the_rate_cv_doubles_per_volt_and_a_reset_restarts_from_the_phase_knob() -> None:
    lfo = LFO(LFOParameters(rate_hz=1.0, phase=0.25))
    lfo.prepare(SR)
    faster = lfo.process(int(SR), SR, {"rate_cv": np.ones(int(SR), dtype=np.float32)})
    assert int((np.diff(faster["cycle"]) > 0).sum()) >= 1, "two hertz now"
    lfo = LFO(LFOParameters(rate_hz=1.0, phase=0.25))
    lfo.prepare(SR)
    reset = np.zeros(4800, dtype=np.float32)
    reset[1000] = 1.0
    out = lfo.process(4800, SR, {"reset": reset})
    assert float(out["sine"][1000]) == pytest.approx(1.0, abs=1e-3), "a quarter turn in: the top of the sine"
    assert float(out["cycle"][1000]) == 1.0, "a reset is the top of a cycle"
    assert float(out["cycle"][999]) == 0.0


def test_sample_and_hold_steps_once_a_cycle_and_the_walk_is_smooth() -> None:
    held = LFO(LFOParameters(rate_hz=4.0, shape="sample & hold", seed=3))
    held.prepare(SR)
    out = held.process(int(SR), SR)
    values = sorted(set(np.round(out["out"], 4).tolist()))
    assert 3 <= len(values) <= 6, "a new value each cycle, four cycles in a second"
    walk = LFO(LFOParameters(rate_hz=4.0, shape="smooth random", seed=3))
    walk.prepare(SR)
    out = walk.process(int(SR), SR)
    assert float(np.abs(np.diff(out["out"])).max()) < 0.01, "no steps in the walk"
    assert -1.0 <= float(out["out"].min()) and float(out["out"].max()) <= 1.0


def test_the_lfo_is_built_in_and_keeps_its_phase_across_blocks() -> None:
    lfo = BuiltinProvider().create("lfo")
    lfo.parameters.rate_hz = 5.0
    lfo.prepare(SR)
    first = lfo.process(2400, SR)["saw"]
    second = lfo.process(2400, SR)["saw"]
    # A quarter of a cycle per block: the saw keeps falling across the seam.
    assert float(second[0]) < float(first[-1]) and float(second[0]) == pytest.approx(float(first[-1]) - 2.0 * 5.0 / SR, abs=1e-4)
