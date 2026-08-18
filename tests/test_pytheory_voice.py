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
from noodler.module_providers.builtin.pytheory_voice import (
    ANCHOR_HZ,
    LOWEST_HZ,
    SEMITONES,
    loop_region,
    sustains,
)


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


def test_a_cheap_instrument_gets_every_semitone() -> None:
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="music_box"))
    voice.prepare(48_000.0, 256)

    assert voice.ready
    assert len(voice._anchors) == SEMITONES
    assert voice.resolution == "every semitone"
    assert all(note.size > 0 for note in voice._anchors.values())


def test_the_budget_stops_an_expensive_instrument_short() -> None:
    """A budget that cannot be spent is not a budget."""
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="cello"))
    voice.refresh(budget_ms=0.0, in_background=False)

    assert voice.ready, "it must still be playable"
    # The coarse set is not optional, and neither is the unbudgeted first note.
    assert set(ANCHOR_HZ) <= set(voice._anchors)
    assert len(voice._anchors) == len(ANCHOR_HZ) + 1
    assert "of" in voice.resolution


def test_the_first_note_is_not_charged_to_the_budget() -> None:
    """Compiling a synth is a one-off, not evidence the instrument is slow."""
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="granular_pad"))
    voice.refresh(in_background=False)
    first = len(voice._anchors)

    voice.refresh(in_background=False)
    assert len(voice._anchors) == first == SEMITONES


def test_what_the_click_cannot_afford_is_finished_in_the_background() -> None:
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="piano"))
    voice.refresh(budget_ms=0.0)
    assert len(voice._anchors) < SEMITONES, "the click should not have covered it"

    voice._worker.join(timeout=60.0)
    assert not voice._worker.is_alive()
    assert len(voice._anchors) == SEMITONES
    assert voice.resolution == "every semitone"


def test_changing_instrument_abandons_the_previous_one() -> None:
    """A worker still rendering a cello must not fill a piano with cello notes."""
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="cello"))
    voice.refresh(budget_ms=0.0)
    stale = voice._worker

    voice.parameters.instrument = "music_box"
    voice.refresh(in_background=False)
    stale.join(timeout=60.0)

    assert voice._rendered_for == "music_box"
    reference = render_note("music_box", 440.0)
    played = voice._anchors[min(voice._anchors, key=lambda hz: abs(hz - 440.0))]
    assert np.array_equal(played[: reference.size], reference)


def test_the_background_worker_is_never_the_audio_thread_s_problem() -> None:
    """Notes appear by swapping the whole dict, never by growing it."""
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="piano"))
    voice.refresh(budget_ms=0.0)

    # Reading anchors while the worker fills them must not raise.
    for _ in range(2_000):
        anchors = voice._anchors
        assert min(anchors, key=lambda hz: abs(hz - 440.0)) in anchors
    voice._worker.join(timeout=60.0)


def test_rendered_pitches_are_spread_rather_than_bunched() -> None:
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="cello"))
    voice.refresh(budget_ms=0.0, in_background=False)

    rendered = sorted(voice._anchors)
    assert rendered[0] == pytest.approx(LOWEST_HZ), "the bottom is covered"
    assert rendered[-1] > 1_000.0, "so is the top"


def test_a_note_is_played_near_the_rate_it_was_rendered_at() -> None:
    """The point of per-semitone rendering: barely any resampling."""
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="music_box"))
    voice.prepare(44_100.0, 256)
    voice._begin(440.0)

    assert voice._step == pytest.approx(1.0, abs=0.03)


def test_the_status_line_says_how_finely_it_rendered() -> None:
    voice = PyTheoryVoice(PyTheoryVoiceParameters(instrument="music_box"))
    voice.prepare(48_000.0, 256)

    assert "MUSIC BOX" in voice.label
    assert "EVERY SEMITONE" in voice.label


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


def _held(name: str, seconds: float, release_ms: float = 200.0) -> np.ndarray:
    voice = PyTheoryVoice(
        PyTheoryVoiceParameters(instrument=name, release_ms=release_ms)
    )
    voice.prepare(48_000.0, 256)
    held = int(seconds * 48_000)
    gate = np.concatenate(
        [np.ones(held, dtype=np.float32), np.zeros(48_000, dtype=np.float32)]
    )
    return _blocks(voice, gate[: len(gate) // 256 * 256])


def test_the_render_says_whether_an_instrument_sustains() -> None:
    """Told apart by the sound, not by a table of names."""
    assert sustains(render_note("harmonium", 220.0))
    assert sustains(render_note("cello", 220.0))
    assert sustains(render_note("flute", 220.0))
    assert not sustains(render_note("piano", 220.0))
    assert not sustains(render_note("koto", 220.0))
    assert not sustains(render_note("kalimba", 220.0))


def test_a_sustaining_note_lasts_as_long_as_the_gate() -> None:
    """PyTheory renders one second; a held organ note is not one second."""
    played = _held("harmonium", 4.0)
    by_second = [
        float(np.sqrt(np.mean(played[i * 48_000 : (i + 1) * 48_000] ** 2)))
        for i in range(4)
    ]
    assert all(level > 0.1 for level in by_second), by_second
    # Steady, not decaying: within a fifth of the first second all the way.
    assert min(by_second) > by_second[0] * 0.8


def test_a_struck_note_ends_when_it_ends() -> None:
    played = _held("piano", 4.0)
    third_second = played[2 * 48_000 : 3 * 48_000]
    assert float(np.max(np.abs(third_second))) < 1e-3, "a piano does not sustain"


def test_looping_does_not_add_a_click() -> None:
    """The seam is crossfaded: repeating it is no rougher than the render."""
    raw = render_note("theremin", 220.0)
    played = _held("theremin", 3.0)
    looping = played[48_000 + 4_800 : 3 * 48_000 - 4_800]

    assert float(np.max(np.abs(np.diff(looping)))) <= float(
        np.max(np.abs(np.diff(raw)))
    )


def test_a_loop_region_is_at_the_end_of_the_note() -> None:
    note = render_note("string_ensemble", 220.0)
    region = loop_region(note)
    assert region is not None
    start, fade = region
    assert 0 < start < note.size
    assert 0 < fade < note.size - start
    assert loop_region(render_note("piano", 220.0)) is None


def test_releasing_a_held_note_still_lets_go() -> None:
    played = _held("harmonium", 2.0, release_ms=100.0)
    assert float(np.max(np.abs(played[-24_000:]))) < 1e-3
