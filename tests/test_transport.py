"""One clock the whole rack agrees on."""

import pytest

from noodler.transport import (
    CHOICES,
    DIVISIONS,
    FREE,
    MAX_BPM,
    MIN_BPM,
    Transport,
    is_rate_field,
)


def test_a_quarter_note_is_one_beat() -> None:
    clock = Transport(bpm=120.0)
    assert clock.hz_for("1/4") == pytest.approx(2.0)
    assert clock.hz_for("1/8") == pytest.approx(4.0)
    assert clock.hz_for("1/16") == pytest.approx(8.0)
    assert clock.hz_for("1/2") == pytest.approx(1.0)


def test_a_longer_division_is_a_slower_rate() -> None:
    clock = Transport(bpm=120.0)  # a 4/4 bar is four quarters, so two seconds
    assert clock.hz_for("1 bar") == pytest.approx(0.5)
    assert clock.hz_for("4 bars") == pytest.approx(0.125)
    assert clock.hz_for("1/4") > clock.hz_for("1/2") > clock.hz_for("1 bar")


def test_a_bar_is_as_long_as_the_signature_says() -> None:
    """A bar cannot be tabulated: 7/8 is not 4/4."""
    clock = Transport(bpm=120.0)
    assert clock.quarters_per_bar == pytest.approx(4.0)

    clock.set_signature(7, 8)
    assert clock.signature == "7/8"
    assert clock.quarters_per_bar == pytest.approx(3.5)
    assert clock.hz_for("1 bar") == pytest.approx(2.0 / 3.5)

    clock.set_signature(5, 4)
    assert clock.hz_for("1 bar") == pytest.approx(0.4)


def test_the_signature_does_not_change_what_a_note_is() -> None:
    """Tempo counts quarter notes whatever the signature says."""
    common, odd = Transport(bpm=120.0), Transport(bpm=120.0)
    odd.set_signature(7, 8)
    for name in ("1/4", "1/8", "1/16T", "1/8."):
        assert odd.hz_for(name) == pytest.approx(common.hz_for(name))


def test_a_signature_is_kept_usable() -> None:
    clock = Transport()
    assert clock.set_signature(0, 4) == "1/4", "a bar holds at least one beat"
    assert clock.set_signature(99, 4).startswith("32/")
    assert clock.set_signature(3, 7) == "3/8", "snapped to a real note value"
    assert clock.set_signature(6, 8) == "6/8"


def test_the_bar_counts_the_beats_the_signature_names() -> None:
    clock = Transport(bpm=120.0)
    clock.set_signature(7, 8)  # seven eighths = 3.5 quarters = 1.75s
    clock.advance(0.25)
    assert clock.beat == 2
    clock.advance(1.5)
    assert clock.phase == pytest.approx(0.0, abs=1e-9)
    assert clock.beat == 1


def test_dotted_and_triplet_divisions_are_musical() -> None:
    clock = Transport(bpm=120.0)
    assert clock.hz_for("1/8.") == pytest.approx(clock.hz_for("1/8") * 2 / 3)
    assert clock.hz_for("1/8T") == pytest.approx(clock.hz_for("1/8") * 1.5)


def test_tempo_scales_every_division_together() -> None:
    slow, fast = Transport(bpm=60.0), Transport(bpm=180.0)
    for name in DIVISIONS:
        assert fast.hz_for(name) == pytest.approx(slow.hz_for(name) * 3.0)


def test_free_running_asks_the_clock_for_nothing() -> None:
    clock = Transport()
    assert clock.hz_for(FREE) is None
    assert clock.hz_for("nonsense") is None
    assert CHOICES[0] == FREE


def test_the_tempo_stays_inside_a_usable_range() -> None:
    clock = Transport()
    assert clock.set_bpm(1.0) == MIN_BPM
    assert clock.set_bpm(10_000.0) == MAX_BPM
    assert clock.set_bpm(96.0) == pytest.approx(96.0)


def test_the_clock_runs_through_the_bar() -> None:
    clock = Transport(bpm=120.0)  # a bar is two seconds
    clock.advance(0.5)
    assert clock.phase == pytest.approx(0.25)
    assert clock.beat == 2

    clock.advance(1.75)
    assert clock.phase == pytest.approx(0.125), "the bar wrapped"
    assert clock.beat == 1


def test_a_stopped_clock_stays_where_it_is() -> None:
    clock = Transport(running=False)
    clock.advance(1.0)
    assert clock.phase == 0.0


def test_the_clock_flashes_on_the_beat() -> None:
    clock = Transport(bpm=120.0)
    assert clock.on_beat() is True
    clock.advance(0.25)  # half a beat in
    assert clock.on_beat() is False


def test_only_repeat_rates_belong_to_the_clock() -> None:
    """Pitch is a frequency too, and a reference frequency is a tuning."""
    assert is_rate_field("rate_hz")
    assert is_rate_field("clock_rate_hz")
    assert not is_rate_field("frequency")
    assert not is_rate_field("reference_frequency_hz")
    assert not is_rate_field("cutoff_hz")


def test_a_synced_rate_follows_the_clock_through_the_real_model() -> None:
    """The DSP never learns about tempo; it is handed the hertz it knows."""
    import dearpygui.dearpygui as dpg

    from noodler.app import (
        RATE_SYNCS,
        TRANSPORT,
        _add_selected_module,
        _apply_transport_sync,
        build_ui,
    )

    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "wogglebug"))
        module = runtime.patch.modules["wogglebug"]

        knob, sync = next(
            (knob, sync)
            for knob, sync in RATE_SYNCS.items()
            if sync.module is module
        )
        assert sync.division == FREE

        TRANSPORT.set_bpm(120.0)
        sync.division = "1/4"
        _apply_transport_sync()
        assert module.parameters.clock_rate_hz == pytest.approx(2.0)

        sync.division = "1/8"
        _apply_transport_sync()
        assert module.parameters.clock_rate_hz == pytest.approx(4.0)

        TRANSPORT.set_bpm(60.0)
        _apply_transport_sync()
        assert module.parameters.clock_rate_hz == pytest.approx(2.0)

        # Free running is left entirely alone.
        sync.division = FREE
        module.parameters.clock_rate_hz = 7.0
        _apply_transport_sync()
        assert module.parameters.clock_rate_hz == pytest.approx(7.0)
    finally:
        TRANSPORT.set_bpm(120.0)
        dpg.destroy_context()


def test_only_rate_controls_are_offered_to_the_clock() -> None:
    import dearpygui.dearpygui as dpg

    from noodler.app import RATE_SYNCS, _add_selected_module, build_ui

    dpg.create_context()
    try:
        runtime = build_ui()
        _add_selected_module("test", None, (runtime, "scale_generator"))
        module = runtime.patch.modules["scale_generator"]

        paths = {
            sync.path[-1] for sync in RATE_SYNCS.values() if sync.module is module
        }
        assert paths == {"rate_hz"}, "tuning is not a tempo"
    finally:
        dpg.destroy_context()


def test_the_clock_menu_comes_after_view_and_edit() -> None:
    import dearpygui.dearpygui as dpg

    from noodler.app import RACK_MENU_BAR, build_ui

    dpg.create_context()
    try:
        build_ui()
        menus = [
            dpg.get_item_configuration(child)["label"]
            for child in dpg.get_item_children(RACK_MENU_BAR, 1)
            if dpg.get_item_type(child).endswith("mvMenu")
        ]
        assert menus == ["File", "View", "Edit", "Clock"]
    finally:
        dpg.destroy_context()


def test_the_signature_controls_drive_the_clock() -> None:
    import dearpygui.dearpygui as dpg

    from noodler.app import (
        CLOCK_BEATS_INPUT,
        CLOCK_READOUT,
        CLOCK_UNIT_INPUT,
        TRANSPORT,
        _refresh_clock,
        _set_clock_signature,
        build_ui,
    )

    dpg.create_context()
    try:
        build_ui()
        dpg.set_value(CLOCK_BEATS_INPUT, 7)
        dpg.set_value(CLOCK_UNIT_INPUT, "8")
        _set_clock_signature("test", None, None)

        assert TRANSPORT.signature == "7/8"
        assert TRANSPORT.quarters_per_bar == pytest.approx(3.5)

        _refresh_clock(1 / 60)
        readout = dpg.get_value(CLOCK_READOUT)
        assert "BPM" in readout and "7/8" in readout and "BEAT" in readout
    finally:
        TRANSPORT.set_signature(4, 4)
        dpg.destroy_context()


def test_the_readout_is_pushed_to_the_right_edge(monkeypatch) -> None:
    import dearpygui.dearpygui as dpg

    from noodler.app import (
        CLOCK_MARGIN,
        CLOCK_READOUT,
        CLOCK_SPACER,
        _refresh_clock,
        build_ui,
    )

    dpg.create_context()
    try:
        build_ui()
        monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: 1400)
        monkeypatch.setattr(dpg, "get_item_rect_size", lambda _item: [220, 18])
        monkeypatch.setattr(dpg, "get_item_rect_min", lambda _item: [300, 4])

        _refresh_clock(1 / 60)

        # Wanted left edge is 1400 - 220 - margin; it was measured at 300.
        gap = float(dpg.get_item_configuration(CLOCK_SPACER)["width"])
        assert gap == pytest.approx(1.0 + (1400 - 220 - CLOCK_MARGIN - 300), abs=1.0)
    finally:
        dpg.destroy_context()
