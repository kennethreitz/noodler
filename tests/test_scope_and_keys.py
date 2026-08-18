"""The scope that draws a signal, and the keys that play the rack."""

import numpy as np
import pytest

from noodler.module_providers.builtin.keys import KEY_ROW, Keys, KeysParameters, semitone_for_letter
from noodler.module_providers.builtin.scope import Scope, ScopeParameters

SR = 48_000.0


def test_the_scope_holds_a_periodic_wave_still_and_passes_it_through() -> None:
    scope = Scope(ScopeParameters(window_ms=10.0))
    scope.prepare(SR)
    t = np.arange(4800) / SR
    saw = (((t * 440.0) % 1.0) * 2.0 - 1.0).astype(np.float32)
    for start in range(0, 4800, 256):
        out = scope.process(min(256, 4800 - start), SR, {"signal": saw[start : start + 256]})
    assert np.allclose(out["through"], saw[4608:4800]), "unchanged on the way through"
    assert 0.9 < float(out["peak"][0]) <= 1.0
    first = scope.trace(200)
    for start in range(0, 4800, 256):
        scope.process(min(256, 4800 - start), SR, {"signal": saw[start : start + 256]})
    again = scope.trace(200)
    assert first.shape == (200,) and np.allclose(first, again, atol=0.02), "triggered: the same picture each time"
    assert -0.1 < float(first[0]) < 0.15, "starting at the rising crossing"
    scope.parameters.mode = "roll"
    rolled = scope.trace(200)
    assert rolled.shape == (200,)
    assert "10 ms" in scope.label and "TRIGGER" not in scope.label and "ROLL" in scope.label


def test_the_scope_takes_an_external_trigger_and_survives_silence() -> None:
    scope = Scope(ScopeParameters(window_ms=5.0))
    scope.prepare(SR)
    signal = np.random.default_rng(1).standard_normal(2048).astype(np.float32) * 0.1
    trigger = np.zeros(2048, dtype=np.float32)
    trigger[100] = 1.0
    trigger[1200] = 1.0
    scope.process(2048, SR, {"signal": signal, "trigger": trigger})
    trace = scope.trace(50)
    # The window starts at the last trigger that leaves a whole window after it.
    assert np.allclose(trace[0], signal[1200], atol=1e-6)
    quiet = Scope()
    quiet.prepare(SR)
    quiet.process(512, SR)
    assert np.allclose(quiet.trace(64), 0.0)


def test_the_keys_map_the_home_row_to_a_keyboard_and_play_last_note_priority() -> None:
    assert semitone_for_letter("a") == 0 and semitone_for_letter("W") == 1 and semitone_for_letter(";") == 16
    assert semitone_for_letter("q") is None
    assert len(KEY_ROW) == 18
    keys = Keys(KeysParameters(octave=3))
    keys.prepare(SR)
    out = keys.process(512, SR)
    assert float(out["gate"][0]) == 0.0
    keys.press(0)  # C3
    out = keys.process(512, SR)
    assert float(out["gate"][0]) == 1.0 and float(out["trigger"][0]) == 1.0
    assert round(float(out["pitch"][0]) * 12 + 57) == 48
    assert keys.label == "C3"
    keys.press(7)  # G3 on top: last note wins
    out = keys.process(512, SR)
    assert round(float(out["pitch"][0]) * 12 + 57) == 55 and float(out["velocity"][0]) == 0.5
    keys.release(7)
    out = keys.process(512, SR)
    assert round(float(out["pitch"][0]) * 12 + 57) == 48, "back to the note still held"
    assert float(out["trigger"].max()) == 0.0, "letting go is not a press"
    keys.octave_up()
    keys.press(0)
    out = keys.process(512, SR)
    assert round(float(out["pitch"][0]) * 12 + 57) == 60, "C4 an octave up"
    keys.release_all()
    out = keys.process(512, SR)
    assert float(out["gate"][0]) == 0.0
    keys.parameters.glide_ms = 200.0
    keys.press(12)
    out = keys.process(int(SR * 0.05), SR)
    assert out["pitch"][0] < out["pitch"][-1] < keys._target, "sliding up, not there yet"


def test_the_panels_carry_a_trace_and_a_keybed_and_arming_takes_the_letters(monkeypatch) -> None:
    import dearpygui.dearpygui as dpg

    from noodler.app import (
        INSTANCE_NODE_TAGS,
        KEYS_ARMED,
        MODULE_DISPLAYS,
        _disarm_keys,
        _keybed_at,
        _keyboard_is_captured,
        _keys_key_pressed,
        _keys_key_released,
        _mount_new_module,
        _refresh_module_displays,
        _toggle_keys_armed,
        build_ui,
    )

    dpg.create_context()
    try:
        runtime = build_ui()
        scope_node = _mount_new_module(runtime, "scope")
        keys_node = _mount_new_module(runtime, "keys")
        assert MODULE_DISPLAYS[scope_node]["kind"] == "scope" and dpg.does_item_exist(f"{scope_node}.scope.trace")
        assert MODULE_DISPLAYS[keys_node]["kind"] == "keys" and dpg.does_item_exist(f"{keys_node}.keys.bed")
        keys = runtime.patch.modules[next(i for i, n in INSTANCE_NODE_TAGS.items() if n == keys_node)]
        # Arm: the letters play; the app's letter shortcuts stand aside; command chords do not.
        assert not _keyboard_is_captured()
        _toggle_keys_armed(0, None, (keys, keys_node))
        assert KEYS_ARMED and keys.armed
        monkeypatch.setattr(dpg, "is_key_down", lambda key: False)
        assert _keyboard_is_captured()
        _keys_key_pressed(0, dpg.mvKey_A, None)
        _keys_key_pressed(0, dpg.mvKey_H, None)
        assert keys.held() == (0, 9)
        _keys_key_pressed(0, dpg.mvKey_X, None)
        assert keys.parameters.octave == 4, "X takes the octave up"
        _keys_key_released(0, dpg.mvKey_A, None)
        assert keys.held() == (9,)
        _refresh_module_displays(runtime)  # draws the keybed with the held note lit
        assert dpg.get_value(f"{keys_node}.keys.note") == "A4"
        # The keybed knows which key is under a point: mock its rectangle.
        display = MODULE_DISPLAYS[keys_node]
        monkeypatch.setattr(dpg, "get_item_rect_min", lambda item: [100.0, 200.0] if item == display["canvas"] else [0.0, 0.0])
        w, h = display["size"]
        hit = _keybed_at((100.0 + 2.0, 200.0 + h - 2.0))
        assert hit is not None and hit[0] is keys and hit[1] == 0, "the bottom-left corner is the C"
        assert _keybed_at((100.0 + w + 5.0, 200.0)) is None
        _disarm_keys()
        assert not KEYS_ARMED and not keys.armed and keys.held() == ()
        assert not _keyboard_is_captured()
    finally:
        KEYS_ARMED.clear()
        dpg.destroy_context()
