from typing import Any

import numpy as np
import pytest

from noodler.engine import SystemAudioEngine
from noodler.module_providers.builtin import (
    ComplexVCO,
    PolarizingMixer,
    PolarizingMixerParameters,
    Reverb,
)
from noodler.patch import OutputChannel, PatchGraph


class FakeOutputStream:
    def __init__(self, **configuration: Any) -> None:
        self.configuration = configuration
        self.samplerate = configuration["samplerate"] or 44_100.0
        self.active = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.stopped = True
        self.active = False

    def close(self) -> None:
        self.closed = True


def audible_patch() -> PatchGraph:
    patch = PatchGraph()
    vco = ComplexVCO()
    mixer = PolarizingMixer(
        PolarizingMixerParameters(channels=1, gains=(0.5,))
    )
    patch.add_module("vco", vco)
    patch.add_module("mixer", mixer)
    patch.connect("vco", "sine", "mixer", "input_1")
    patch.connect_output("mixer", "output")
    return patch


def test_engine_uses_device_rate_and_duplicates_mono_to_stereo() -> None:
    streams: list[FakeOutputStream] = []

    def stream_factory(**configuration: Any) -> FakeOutputStream:
        stream = FakeOutputStream(**configuration)
        streams.append(stream)
        return stream

    engine = SystemAudioEngine(
        audible_patch(),
        master_gain=0.5,
        stream_factory=stream_factory,
    )
    engine.start()
    stream = streams[0]
    output = np.empty((64, 2), dtype=np.float32)
    stream.configuration["callback"](output, 64, None, None)

    assert engine.is_running is True
    assert engine.sample_rate == 44_100.0
    assert stream.configuration["dtype"] == "float32"
    np.testing.assert_allclose(output[:, 0], output[:, 1])
    assert np.max(np.abs(output)) <= 0.05 + 1e-6
    assert np.any(output != 0.0)
    assert engine.last_peak == pytest.approx(float(np.max(np.abs(output))))

    engine.stop()
    assert engine.is_running is False
    assert stream.stopped is True
    assert stream.closed is True
    assert engine.last_peak == 0.0


def test_engine_start_and_stop_are_idempotent() -> None:
    streams: list[FakeOutputStream] = []

    def stream_factory(**configuration: Any) -> FakeOutputStream:
        stream = FakeOutputStream(**configuration)
        streams.append(stream)
        return stream

    engine = SystemAudioEngine(audible_patch(), stream_factory=stream_factory)

    engine.start()
    engine.start()
    engine.stop()
    engine.stop()

    assert len(streams) == 1


def test_engine_prepares_stateful_modules_at_the_device_rate() -> None:
    reverb = Reverb()
    patch = PatchGraph()
    patch.add_module("reverb", reverb)
    patch.connect_output("reverb", "left", channel=OutputChannel.LEFT)
    patch.connect_output("reverb", "right", channel=OutputChannel.RIGHT)
    engine = SystemAudioEngine(patch, stream_factory=FakeOutputStream)

    engine.start()

    assert reverb.sample_rate == 44_100.0
    engine.stop()


def test_engine_preserves_stereo_patch_routing() -> None:
    patch = PatchGraph()
    patch.add_module("vco", ComplexVCO())
    patch.connect_output("vco", "sine", channel=OutputChannel.LEFT)
    patch.connect_output("vco", "triangle", channel=OutputChannel.RIGHT)
    engine = SystemAudioEngine(patch, stream_factory=FakeOutputStream)
    engine.start()
    output = np.empty((64, 2), dtype=np.float32)

    engine._stream.configuration["callback"](output, 64, None, None)

    assert np.any(output[:, 0] != output[:, 1])
    engine.stop()


def test_master_gain_is_bounded_for_system_output() -> None:
    engine = SystemAudioEngine(audible_patch())

    with pytest.raises(ValueError, match="between 0 and 1"):
        engine.master_gain = 1.1
