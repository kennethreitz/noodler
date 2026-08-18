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


def test_a_feedback_patch_is_allowed_to_exist() -> None:
    """A rack feeds back. Refusing it made a family of patches unbuildable."""
    patch = PatchGraph()
    patch.add_module("first", PolarizingMixer())
    patch.add_module("second", PolarizingMixer())
    patch.connect("first", "output", "second", "input_1")
    patch.connect("second", "output", "first", "input_1")

    assert len(patch.cables) == 2
    assert len(patch.processing_order) == 2
    assert len(patch.feedback_cables) == 1

    closing = next(iter(patch.feedback_cables))
    assert closing.source.module_id == "second", "the newest cable closes the loop"


def test_a_loop_reads_the_previous_block_not_the_current_one() -> None:
    """One block of delay is what makes a loop a signal path, not an equation."""
    patch = PatchGraph()
    source = ComplexVCO(ComplexVCOParameters(frequency=100.0, amplitude=0.5))
    passthrough = PolarizingMixer(
        PolarizingMixerParameters(channels=2, gains=(1.0, 1.0))
    )
    patch.add_module("vco", source)
    patch.add_module("mixer", passthrough)
    patch.connect("vco", "sine", "mixer", "input_1")
    patch.connect("mixer", "output", "mixer", "input_2")
    patch.connect_output("mixer", "output")

    assert len(patch.feedback_cables) == 1

    first = np.array(patch.render(4, 800.0))
    second = np.array(patch.render(4, 800.0))

    # The first block cannot hear itself; the second carries the first back in.
    assert np.any(second != 0.0)
    assert not np.allclose(first, second)


def test_a_module_can_be_patched_into_itself() -> None:
    patch = PatchGraph()
    patch.add_module("mixer", PolarizingMixer())
    patch.connect("mixer", "output", "mixer", "input_1")

    assert patch.processing_order == ("mixer",)
    assert len(patch.feedback_cables) == 1
    patch.render(4, 48_000.0)  # renders rather than raising


def test_a_patch_without_loops_has_no_feedback_cables() -> None:
    patch = PatchGraph()
    patch.add_module("first", PolarizingMixer())
    patch.add_module("second", PolarizingMixer())
    patch.connect("first", "output", "second", "input_1")

    assert patch.feedback_cables == frozenset()
    assert patch.processing_order == ("first", "second")


def test_removing_the_loop_restores_a_plain_order() -> None:
    patch = PatchGraph()
    patch.add_module("first", PolarizingMixer())
    patch.add_module("second", PolarizingMixer())
    patch.connect("first", "output", "second", "input_1")
    closing = patch.connect("second", "output", "first", "input_1")
    assert patch.feedback_cables

    patch.disconnect(closing)

    assert patch.feedback_cables == frozenset()
    assert patch.processing_order == ("first", "second")


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


def test_removing_a_module_takes_its_cables_and_taps_with_it() -> None:
    vco = ComplexVCO(ComplexVCOParameters(frequency=100.0, amplitude=0.2))
    mixer = PolarizingMixer(
        PolarizingMixerParameters(channels=2, gains=(0.5, 0.0))
    )
    patch = PatchGraph()
    patch.add_module("vco", vco)
    patch.add_module("mixer", mixer)
    patch.connect("vco", "sine", "mixer", "input_1")
    patch.connect_output("mixer", "output")
    patch.connect_output("vco", "sine")

    removed = patch.remove_module("mixer")

    assert removed == 2
    assert "mixer" not in patch.modules
    assert patch.cables == ()
    assert [tap.source.module_id for tap in patch.output_taps] == ["vco"]
    assert patch.processing_order == ("vco",)
    # The surviving graph still renders.
    assert patch.render(8, 800.0).shape == (8,)


def test_removing_an_unknown_module_is_rejected() -> None:
    patch = PatchGraph()
    with pytest.raises(PatchError, match="unknown module instance"):
        patch.remove_module("nothing")
