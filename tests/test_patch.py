import numpy as np
import pytest

from noodler.module_providers.builtin import (
    ComplexVCO,
    ComplexVCOParameters,
    FunctionUtility,
    FunctionUtilityParameters,
    PolarizingMixer,
    PolarizingMixerParameters,
    Reverb,
)
from noodler.patch import OutputChannel, PatchError, PatchGraph


def test_patch_routes_vco_through_polarizing_mixer_to_output() -> None:
    parameters = ComplexVCOParameters(frequency=100.0, amplitude=0.2)
    vco = ComplexVCO(parameters)
    mixer = PolarizingMixer(
        PolarizingMixerParameters(channels=2, gains=(0.5, 0.0))
    )
    patch = PatchGraph()
    patch.add_module("vco", vco)
    patch.add_module("mixer", mixer)
    cable = patch.connect("vco", "sine", "mixer", "input_1")
    tap = patch.connect_output("mixer", "output")

    expected_vco = ComplexVCO(parameters.model_copy(deep=True))
    expected = expected_vco.process(8, 800.0)["sine"] * 0.5
    output = patch.render(8, 800.0)

    np.testing.assert_allclose(output, expected)
    assert patch.processing_order == ("vco", "mixer")
    assert cable.model_dump() == {
        "source": {"module_id": "vco", "port_id": "sine"},
        "target": {"module_id": "mixer", "port_id": "input_1"},
    }
    assert tap.source.module_id == "mixer"


def test_only_one_cable_can_drive_an_input() -> None:
    patch = PatchGraph()
    patch.add_module("first", ComplexVCO())
    patch.add_module("second", ComplexVCO())
    patch.add_module("mixer", PolarizingMixer())
    patch.connect("first", "sine", "mixer", "input_1")

    with pytest.raises(PatchError, match="already has a cable"):
        patch.connect("second", "triangle", "mixer", "input_1")


def test_graph_routes_cv_into_the_vco_block_protocol() -> None:
    utility = FunctionUtility(
        FunctionUtilityParameters(channel_2_attenuverter=1.0)
    )
    vco = ComplexVCO(ComplexVCOParameters(frequency=100.0))
    patch = PatchGraph()
    patch.add_module("utility", utility)
    patch.add_module("vco", vco)
    patch.connect("utility", "channel_2", "vco", "pitch")
    patch.connect_output("vco", "sine")

    expected_vco = ComplexVCO(ComplexVCOParameters(frequency=100.0))
    expected = expected_vco.process(8, 800.0, pitch_cv=1.0)["sine"]

    np.testing.assert_allclose(patch.render(8, 800.0), expected)
    assert patch.processing_order == ("utility", "vco")


def test_incompatible_signal_types_are_rejected() -> None:
    patch = PatchGraph()
    patch.add_module("source", ComplexVCO())
    patch.add_module("target", ComplexVCO())

    with pytest.raises(PatchError, match="cannot be connected"):
        patch.connect("source", "sine", "target", "sync")


def test_feedback_requires_a_future_explicit_delay_module() -> None:
    patch = PatchGraph()
    patch.add_module("first", PolarizingMixer())
    patch.add_module("second", PolarizingMixer())
    patch.connect("first", "output", "second", "input_1")

    with pytest.raises(PatchError, match="feedback loops"):
        patch.connect("second", "output", "first", "input_1")

    assert len(patch.cables) == 1


def test_output_bus_accepts_continuous_cv() -> None:
    patch = PatchGraph()
    mixer = PolarizingMixer(
        PolarizingMixerParameters(channels=1, gains=(1.0,))
    )
    patch.add_module("mixer", mixer)
    patch.connect_output("mixer", "output", gain=0.25)

    output = patch.render(3, 48_000.0)

    np.testing.assert_allclose(output, 0.0)


def test_output_bus_preserves_explicit_stereo_channels() -> None:
    parameters = ComplexVCOParameters(frequency=100.0, amplitude=0.2)
    patch = PatchGraph()
    patch.add_module("vco", ComplexVCO(parameters))
    left = patch.connect_output(
        "vco",
        "sine",
        channel=OutputChannel.LEFT,
    )
    right = patch.connect_output(
        "vco",
        "triangle",
        channel=OutputChannel.RIGHT,
    )

    output = patch.render_stereo(8, 800.0)
    expected = ComplexVCO(parameters.model_copy(deep=True)).process(8, 800.0)

    np.testing.assert_allclose(output[:, 0], expected["sine"])
    np.testing.assert_allclose(output[:, 1], expected["triangle"])
    assert left.channel is OutputChannel.LEFT
    assert right.channel is OutputChannel.RIGHT


def test_cables_and_output_taps_can_be_disconnected() -> None:
    patch = PatchGraph()
    patch.add_module("vco", ComplexVCO())
    patch.add_module("mixer", PolarizingMixer())
    cable = patch.connect("vco", "sine", "mixer", "input_1")
    tap = patch.connect_output("mixer", "output")

    patch.disconnect(cable)
    patch.disconnect_output(tap)

    assert patch.cables == ()
    assert patch.output_taps == ()
    assert patch.processing_order == ("vco", "mixer")

    with pytest.raises(PatchError, match="not part of this patch"):
        patch.disconnect(cable)
    with pytest.raises(PatchError, match="not part of this patch"):
        patch.disconnect_output(tap)


def test_all_connections_can_be_disconnected_atomically() -> None:
    patch = PatchGraph()
    patch.add_module("vco", ComplexVCO())
    patch.add_module("mixer", PolarizingMixer())
    patch.connect("vco", "sine", "mixer", "input_1")
    patch.connect("vco", "triangle", "mixer", "input_2")
    patch.connect_output("mixer", "output", channel=OutputChannel.LEFT)
    patch.connect_output("mixer", "output", channel=OutputChannel.RIGHT)

    assert patch.disconnect_all() == 4
    assert patch.cables == ()
    assert patch.output_taps == ()
    assert patch.processing_order == ("vco", "mixer")
    assert patch.disconnect_all() == 0


def test_patch_prepares_stateful_modules() -> None:
    patch = PatchGraph()
    reverb = Reverb()
    patch.add_module("reverb", reverb)

    patch.prepare(48_000.0, 256)

    assert reverb.sample_rate == 48_000.0
