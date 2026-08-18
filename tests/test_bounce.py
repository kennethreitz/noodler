"""Rendering a patch to a file."""

import time
from pathlib import Path

import dearpygui.dearpygui as dpg
import numpy as np
import pytest

from noodler.app import (
    EXPORT_MENU,
    EXPORT_MESSAGES,
    _export_dialog,
    _show_export_messages,
    build_ui,
    default_rack_preset,
)
from noodler.bounce import bounce, read_wav, write_wav
from noodler.preset import read_patch_preset


def test_a_bounce_is_so_many_bars_and_a_tail_at_the_document_tempo() -> None:
    preset = read_patch_preset(Path("examples/highlife-kalimba.noodler"))
    reported = []
    audio = bounce(preset, bars=2, tail_seconds=1.0, progress=lambda done, total: reported.append((done, total)))
    bar = 4 * 60.0 / preset.transport.bpm
    assert audio.shape[1] == 2
    assert audio.shape[0] == pytest.approx((2 * bar + 1.0) * 48_000, abs=512)
    assert float(np.max(np.abs(audio))) > 0.01
    assert float(np.max(np.abs(audio))) <= 1.0
    assert reported and reported[-1] == (2, 2)


def test_a_wav_reads_back_as_it_was_written(tmp_path) -> None:
    rng = np.random.default_rng(1)
    audio = np.clip(rng.standard_normal((4_800, 2)) * 0.3, -1.0, 1.0).astype(np.float32)
    written = write_wav(tmp_path / "take", audio, 48_000.0)
    assert written.suffix == ".wav"
    back, rate = read_wav(written)
    assert rate == 48_000
    assert back.shape == audio.shape
    assert np.max(np.abs(back - audio)) < 1e-4


def test_export_from_the_menu_writes_the_file_and_says_so(tmp_path) -> None:
    dpg.create_context()
    try:
        runtime = build_ui(preset=default_rack_preset())
        assert dpg.does_item_exist(EXPORT_MENU)
        EXPORT_MESSAGES.clear()
        from noodler.app import EXPORT_BARS
        EXPORT_BARS[:] = [1]

        _export_dialog("test", {"file_path_name": str(tmp_path / "bounce.wav")}, runtime)

        deadline = time.time() + 60.0
        while time.time() < deadline and not (tmp_path / "bounce.wav").exists():
            time.sleep(0.05)
        while time.time() < deadline and not any("EXPORTED" in m or "ERROR" in m for m, _e in EXPORT_MESSAGES):
            time.sleep(0.05)
        assert any("EXPORTED" in m for m, _e in EXPORT_MESSAGES), EXPORT_MESSAGES
        _show_export_messages()
        back, rate = read_wav(tmp_path / "bounce.wav")
        assert rate == 48_000 and back.shape[0] > 48_000
    finally:
        dpg.destroy_context()
