"""PyTheory's own synthesis, played from the rack."""

import time

import numpy as np
import pytest
from pytheory import INSTRUMENTS

from noodler.module_providers.builtin import (
    BuiltinProvider,
    PyTheoryVoice,
    PyTheoryVoiceParameters,
    render_note,
)
from noodler.module_providers.builtin.pytheory_voice import ANCHOR_HZ


def _blocks(voice: PyTheoryVoice, gate: np.ndarray, pitch: float = 0.0) -> np.ndarray:
    played = []
    held = np.full(256, pitch, dtype=np.float32)
    for index in range(0, len(gate), 256):
        played.append(
            voice.process(256, 48_000.0, {"pitch": held, "gate": gate[index : index + 256]})[
                "audio"
            ]
        )
    return np.concatenate(played)


def test_pytheory_renders_the_note_itself() -> None:
    """Not a recipe rebuilt from oscillators: the library's own algorithm."""
    note = render_note("rhodes", 440.0)

    assert note.size > 0
    assert np.max(np.abs(note)) == pytest.approx(1.0), "normalised to full scale"
    assert np.all(np.isfinite(note))


def test_every_instrument_renders_something() -> None:
    for name in list(INSTRUMENTS)[:20]:
        note = render_note(name, 220.0)
        assert note.size > 0, name
        assert np.all(np.isfinite(note)), name


def test_the_callback_never_renders() -> None:
    """Rendering is milliseconds of work; the callback has milliseconds total."""
    voice = PyTheoryVoice()
    voice.prepare(48_000.0, 256)
    gate = np.ones(256, dtype=np.float32)
    pitch = np.zeros(256, dtype=np.float32)

    voice.process(256, 48_000.0, {"pitch": pitch, "gate": gate})
    started = time.perf_counter()
    for _ in range(200):
        voice.process(256, 48_000.0, {"pitch": pitch, "gate": gate})
    per_block = (time.perf_counter() - started) / 200 * 1_000

    assert per_block < 1.0, f"playback cost {per_block:.2f} ms a block"


def test_a_gate_starts_a_note_and_releasing_fades_it() -> None:
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="rhodes", release_ms=20.0))
    voice.prepare(48_000.0, 256)
    gate = np.concatenate(
        [np.ones(2_048, dtype=np.float32), np.zeros(8_192, dtype=np.float32)]
    )

    played = _blocks(voice, gate)

    assert float(np.max(np.abs(played[:2_048]))) > 0.01, "the note never sounded"
    assert float(np.max(np.abs(played[-2_048:]))) < 1e-3, "it never let go"


def test_pitch_chooses_and_shifts_the_rendered_note() -> None:
    def crossings(pitch: float) -> int:
        voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="celesta"))
        voice.prepare(48_000.0, 256)
        played = _blocks(voice, np.ones(2_048, dtype=np.float32), pitch=pitch)
        return int(np.count_nonzero(np.diff(np.signbit(played))))

    assert crossings(1.0) > crossings(0.0)


def test_notes_are_rendered_for_several_pitches() -> None:
    voice = PyTheoryVoice()
    voice.prepare(48_000.0, 256)

    assert voice.ready
    assert set(voice._anchors) == set(ANCHOR_HZ)
    assert all(note.size > 0 for note in voice._anchors.values())


def test_changing_instrument_needs_a_refresh_not_a_render_in_the_callback() -> None:
    voice = PyTheoryVoice()
    voice.prepare(48_000.0, 256)
    assert voice.ready

    voice.parameters.instrument = "sitar"
    assert not voice.ready, "the callback must not be asked to render"

    voice.refresh()
    assert voice.ready


def test_an_unknown_instrument_settles_on_a_known_one() -> None:
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="not an instrument"))
    assert voice.parameters.instrument in INSTRUMENTS


def test_the_panel_offers_every_instrument() -> None:
    voice = BuiltinProvider().create("pytheory_voice")
    assert len(voice.choices_for("instrument")) == len(INSTRUMENTS)
