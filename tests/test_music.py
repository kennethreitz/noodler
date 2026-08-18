"""Musical meaning, carried as itself."""

import numpy as np
import pytest

from noodler.module_providers.builtin import BuiltinProvider
from noodler.music import (
    SYSTEM_NAMES,
    build_scale,
    quantize,
    scale_names_for,
    tonics_for,
)
from noodler.patch import OutputChannel, PatchGraph


def test_every_tone_system_pytheory_knows_can_be_built() -> None:
    """Ten of sixteen systems were unreachable before this."""
    built = 0
    for system in SYSTEM_NAMES:
        tonics = tonics_for(system)
        assert tonics, f"{system} names no tones"
        modes = scale_names_for(system, tonics[0], 4)
        assert modes, f"{system} offers no modes"
        field = build_scale(system, tonics[0], 4, modes[-1])
        assert field is not None, f"{system} built nothing"
        assert field.tones
        built += 1
    assert built == len(SYSTEM_NAMES) >= 16


def test_a_system_keeps_its_own_vocabulary() -> None:
    """C is not an Arabic tonic, and Do is not a western one."""
    assert "C" in tonics_for("western")
    assert "C" not in tonics_for("arabic")
    assert "Do" in tonics_for("arabic")


def test_the_maqamat_and_ragas_are_reachable() -> None:
    assert "rast" in scale_names_for("arabic", "Do", 4)
    assert "hijaz" in scale_names_for("arabic", "Do", 4)
    assert "kalyani" in scale_names_for("carnatic", "Sa", 4)
    assert "hirajoshi" in scale_names_for("japanese", "A", 4)
    assert any("pelog" in name for name in scale_names_for("gamelan", "nem", 4))


def test_a_scale_repeats_at_its_own_period() -> None:
    """Bohlen-Pierce repeats at a tritave, not an octave."""
    western = build_scale("western", "C", 4, "major")
    assert western.period == pytest.approx(2.0)

    tonics = tonics_for("bohlen-pierce")
    bp = build_scale("bohlen-pierce", tonics[0], 4, "chromatic")
    assert bp.period == pytest.approx(3.0)

    lowest = min(bp.frequencies(span=1))
    assert any(
        abs(frequency - lowest * 3.0) < 1e-6 for frequency in bp.frequencies(span=1)
    )


def test_quantising_snaps_to_the_nearest_tone() -> None:
    field = build_scale("western", "C", 4, "major")
    table = field.pitch_table(261.63)

    wanted = np.array([0.0, 0.02, 0.9, -0.4])
    snapped = quantize(wanted, table)

    assert snapped.shape == wanted.shape
    for value in snapped:
        assert np.min(np.abs(table - value)) < 1e-9, "landed off the scale"
    assert np.all(np.abs(snapped - wanted) <= 0.5)


def test_quantising_without_a_scale_changes_nothing() -> None:
    wanted = np.array([0.3, -0.7])
    unchanged = quantize(wanted, np.zeros(0))
    np.testing.assert_array_equal(unchanged, wanted)


def test_a_random_voltage_becomes_a_melody_in_the_key() -> None:
    """The thesis: a scale travels, and a voltage arrives in that music."""
    provider = BuiltinProvider()
    key = provider.create("key")
    quantizer = provider.create("quantizer")
    key.parameters.system = "arabic"
    key.parameters.tonic = "Do"
    key.parameters.scale_name = "rast"

    allowed = {round(frequency, 3) for _name, frequency in key.field.tones}
    produced = set()
    for voltage in np.linspace(-0.2, 1.2, 40):
        rendered = quantizer.process(
            1,
            48_000.0,
            {"cv": np.array([voltage], dtype=np.float32), "scale": key.field},
        )
        produced.add(round(float(rendered["frequency"][0]), 3))

    in_one_period = {f for f in produced if min(allowed) <= f <= max(allowed)}
    assert in_one_period <= allowed, "a tone appeared that is not in the maqam"
    assert len(produced) > 5, "the voltage should reach several tones"


def test_the_scale_survives_the_journey_through_a_patch() -> None:
    provider = BuiltinProvider()
    key, quantizer, vco = (
        provider.create("key"),
        provider.create("quantizer"),
        provider.create("classic_vco"),
    )
    patch = PatchGraph()
    for name, module in (("key", key), ("quantizer", quantizer), ("vco", vco)):
        patch.add_module(name, module)
    patch.connect("key", "scale", "quantizer", "scale")
    patch.connect("quantizer", "pitch", "vco", "pitch")
    patch.connect_output("vco", "saw", channel=OutputChannel.BOTH)
    patch.prepare(48_000.0, 64)

    rendered = patch.render_stereo(64, 48_000.0)

    assert quantizer.field is not None, "the quantizer never received a scale"
    assert quantizer.field.label == key.field.label
    assert float(np.max(np.abs(rendered))) > 0.0


def test_changing_the_key_retunes_everything_downstream() -> None:
    provider = BuiltinProvider()
    key, quantizer = provider.create("key"), provider.create("quantizer")

    def sweep() -> set[float]:
        """What a voltage ramp is allowed to become in the current key."""
        produced = set()
        for voltage in np.linspace(0.0, 1.0, 60):
            rendered = quantizer.process(
                1,
                48_000.0,
                {"cv": np.array([voltage], dtype=np.float32), "scale": key.field},
            )
            produced.add(round(float(rendered["frequency"][0]), 2))
        return produced

    western = sweep()
    key.parameters.system = "japanese"
    key.parameters.scale_name = "hirajoshi"
    japanese = sweep()

    assert key.field.name == "hirajoshi"
    assert western != japanese, "the ramp should reach different tones"
    assert len(western) != len(japanese) or western ^ japanese


def test_an_impossible_key_is_settled_rather_than_refused() -> None:
    """A rack should keep playing while it is being retuned."""
    provider = BuiltinProvider()
    key = provider.create("key")

    key.parameters.system = "carnatic"

    assert key.parameters.tonic in tonics_for("carnatic")
    assert key.parameters.scale_name in scale_names_for(
        "carnatic", key.parameters.tonic, key.parameters.octave
    )
    assert key.field is not None


def test_a_module_offers_the_words_it_recognises() -> None:
    provider = BuiltinProvider()
    key = provider.create("key")

    assert set(key.choices_for("system")) == set(SYSTEM_NAMES)
    key.parameters.system = "arabic"
    assert "Do" in key.choices_for("tonic")
    assert "rast" in key.choices_for("scale_name")
    assert key.choices_for("octave") == ()
