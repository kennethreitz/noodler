"""A panel is derived from the module, so it cannot drift from it."""

import pytest

from noodler.module_providers.builtin import (
    BUILTIN_PROVIDER_MANIFEST,
    BuiltinProvider,
    ComplexVCO,
)
from noodler.ui.panel import (
    COLUMN_CHARS,
    CONTROL_COLUMNS,
    describe,
    fit,
    label_and_unit,
    panel_value,
    set_panel_value,
)


def test_a_field_name_becomes_a_label_and_a_unit() -> None:
    assert label_and_unit("fine_tune_cents") == ("FINE TUNE", "ct")
    assert label_and_unit("frequency_cv_1_amount") == ("FREQ CV 1", "")
    assert label_and_unit("decay_seconds") == ("DECAY", "s")
    assert label_and_unit("cutoff_hz") == ("CUTOFF", "Hz")
    assert label_and_unit("morph") == ("MORPH", "")


def test_every_cell_is_one_column_wide() -> None:
    assert len(fit("MORPH")) == COLUMN_CHARS
    assert len(fit("0.200 Hz")) == COLUMN_CHARS
    assert fit("A VERY LONG PARAMETER NAME").endswith("…")


def test_every_built_in_module_derives_a_usable_panel() -> None:
    """A module should get a correct panel simply by existing."""
    provider = BuiltinProvider()
    for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
        spec = describe(provider.create(manifest.id))

        assert spec.title, manifest.id
        assert spec.controls, f"{manifest.id} has no controls"
        assert spec.inputs or spec.outputs, f"{manifest.id} has no jacks"
        assert spec.width > 0 and spec.height > 0
        for control in spec.controls:
            assert control.label.strip(), f"{manifest.id} has a blank label"
            if control.kind == "knob":
                assert control.minimum < control.maximum, control.label


def test_a_knob_reads_its_bounds_from_the_schema() -> None:
    spec = describe(ComplexVCO())
    frequency = next(c for c in spec.controls if c.label == "FREQ")

    assert frequency.kind == "knob"
    assert frequency.maximum == 20_000.0
    assert frequency.minimum == pytest.approx(2.0), "four decades of usable travel"
    assert frequency.logarithmic, "a three-decade range is not linear to the hand"


def test_choices_and_toggles_are_recognised() -> None:
    spec = describe(ComplexVCO())
    wave = next(c for c in spec.controls if c.kind == "choice")

    assert "saw" in wave.choices
    assert wave.value in wave.choices


def test_a_panel_is_measured_before_it_is_drawn() -> None:
    """The rack cannot lay out what it cannot measure."""
    spec = describe(ComplexVCO())
    rows = -(-len(spec.controls) // CONTROL_COLUMNS)

    assert spec.height > rows * 50.0
    assert spec.width >= (len(spec.title) + 2) * 8.0 - 1


def test_a_control_reads_and_writes_the_real_parameters() -> None:
    vco = ComplexVCO()
    spec = describe(vco)
    frequency = next(c for c in spec.controls if c.label == "FREQ")

    assert panel_value(vco.parameters, frequency.path) == pytest.approx(
        vco.parameters.frequency
    )
    set_panel_value(vco.parameters, frequency.path, 440.0)
    assert vco.parameters.frequency == pytest.approx(440.0)


def test_writing_out_of_range_is_refused_by_the_model() -> None:
    vco = ComplexVCO()
    with pytest.raises(Exception):
        set_panel_value(vco.parameters, ("frequency",), -5.0)


def test_a_sequence_parameter_says_who_owns_it() -> None:
    from noodler.module_providers.builtin import PolarizingMixer

    mixer = PolarizingMixer()
    with pytest.raises(TypeError, match="owning module"):
        set_panel_value(mixer.parameters, ("gains", 0), 0.5)
