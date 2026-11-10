"""The human patch API, the new theory modules, and text documents."""

from pathlib import Path

import numpy as np
import pytheory
import pytest
from pytheory import Fretboard

from noodler.cli import main as cli_main
from noodler.midi import read_midi_notes, write_midi
from noodler.module_providers.builtin import BuiltinProvider
from noodler.module_providers.builtin.chord import ChordModule, ChordParameters
from noodler.module_providers.builtin.fretboard import FretboardVoice, FretboardParameters
from noodler.module_providers.builtin.sequencer import Sequencer, SequencerParameters, parse_steps
from noodler.music import build_scale, hz_to_volts
from noodler.patch import PatchGraph
from noodler.preset import read_patch_preset, write_patch_preset
from noodler.studio import Patch
from noodler.transport import Transport


SR = 48_000.0


def test_pytheory_is_the_release_with_guitar_tunings() -> None:
    assert pytheory.__version__.startswith("0.58")
    board = Fretboard.guitar("open g", capo=2)
    assert [tone.full_name for tone in board.tones] == ["E2", "A2", "E3", "A3", "C#4", "E4"]


def test_fretboard_module_is_the_pytheory_guitar() -> None:
    voice = FretboardVoice(FretboardParameters(tuning="dadgad", capo=0))
    rendered = voice.process(64, SR)
    board = Fretboard.guitar("dadgad")
    expected = [hz_to_volts(tone.frequency, 220.0) for tone in board.tones]
    for index, volts in enumerate(expected, start=1):
        assert float(rendered[f"string_{index}"][0]) == pytest.approx(volts)
    assert "D2" in voice.label and "dadgad" in voice.label

    capo = FretboardVoice(FretboardParameters(tuning="open g", capo=2))
    capo.process(8, SR)
    assert "C#4" in capo.label


def test_a_named_chord_is_fretted_on_that_tuning() -> None:
    voice = FretboardVoice(FretboardParameters(tuning="standard", chord="G"))
    voice.process(8, SR)
    assert "G2" in voice.label and "B2" in voice.label


def test_sequencer_degrees_follow_the_patched_scale() -> None:
    assert parse_steps("0 2 . 4 rest") == (0, 2, None, 4, None)
    scale = build_scale("western", "D", 3, "major")
    assert scale is not None
    sequencer = Sequencer(
        SequencerParameters(steps="0 1 2", division="1/4", rate_hz=2.0, gate_length=0.5)
    )
    # One second at 2 quarters/second is two quarter notes: degrees 0 then 1.
    rendered = sequencer.process(int(SR), SR, {"scale": scale})
    assert rendered["pitch"].shape == (int(SR),)
    assert float(rendered["pitch"][0]) == pytest.approx(hz_to_volts(scale.tones[0][1], 220.0))
    # The second step lands half a second in, which is the next degree.
    assert float(rendered["pitch"][int(SR * 0.6)]) == pytest.approx(
        hz_to_volts(scale.tones[1][1], 220.0)
    )
    assert float(np.max(rendered["gate"])) == 1.0


def test_chord_module_voices_a_name_for_the_arpeggiator() -> None:
    chord = ChordModule(ChordParameters(name="Am7", octave=3))
    rendered = chord.process(16, SR)
    assert rendered["voice_1"].shape == (16,)
    assert "A" in chord.label
    # Four voices, and they are not all the same pitch.
    pitches = [float(rendered[f"voice_{index}"][0]) for index in range(1, 5)]
    assert len(set(round(pitch, 4) for pitch in pitches)) >= 3
    unknown = ChordModule(ChordParameters(name="not-a-chord"))
    assert "unrecognised" in unknown.label


def test_a_patch_round_trips_through_toml_and_json(tmp_path: Path) -> None:
    patch = Patch("Round Trip").at(bpm=100)
    patch.module("melody", "sequencer", steps="0 4 7 .", division="1/4")
    patch.module("board", "fretboard", tuning="drop d", capo=2)
    patch.cable("melody.gate", "board.strum")
    document = patch.preset()
    json_path = write_patch_preset(document, tmp_path / "trip.noodler")
    toml_path = write_patch_preset(document, tmp_path / "trip.toml")
    assert json_path.suffix == ".noodler"
    assert toml_path.suffix == ".toml"
    assert "drop d" in toml_path.read_text()
    assert "[[modules]]" in toml_path.read_text()
    restored = read_patch_preset(toml_path)
    assert restored.name == "Round Trip"
    assert restored.transport.bpm == 100
    types = {module.instance_id: module.module_type for module in restored.modules}
    assert types["board"] == "fretboard"
    assert types["melody"] == "sequencer"
    assert read_patch_preset(json_path).name == restored.name


def test_midi_out_writes_the_notes_a_phrase_played(tmp_path: Path) -> None:
    provider = BuiltinProvider()
    graph = PatchGraph()
    graph.add_module("melody", provider.create("sequencer", {"steps": "0 2 4 7", "division": "1/4", "rate_hz": 2.0}))
    graph.add_module("midi", provider.create("midi_out"))
    graph.connect("melody", "pitch", "midi", "pitch")
    graph.connect("melody", "gate", "midi", "gate")
    transport = Transport(bpm=120, running=True)
    for _ in range(int(2 * SR / 256)):
        graph.transport = transport.tick(256, SR)
        graph.render_stereo(256, SR)
    events = graph.modules["midi"].midi_events
    assert any(event.on for event in events)
    path = write_midi(tmp_path / "phrase.mid", events, bpm=120)
    notes = [note for _tick, note, on in read_midi_notes(path) if on]
    assert len(notes) >= 4
    assert notes == sorted(notes) or len(set(notes)) >= 3


def test_cli_checks_renders_and_lists(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    patch = Patch("CLI Bell").at(bpm=120, gain=0.8)
    patch.module("tone", "classic_vco", frequency=220.0, amplitude=0.2)
    patch.module("melody", "sequencer", steps="0 7 12 7", division="1/4", rate_hz=2.0)
    patch.module("midi", "midi_out")
    patch.cable("melody.pitch", "tone.pitch")
    patch.cable("melody.pitch", "midi.pitch")
    patch.cable("melody.gate", "midi.gate")
    patch.hear("tone.sine", level=0.4)
    document = patch.save(tmp_path / "bell.noodler")

    cli_main(["check", str(document)])
    checked = capsys.readouterr().out
    assert "CLI Bell" in checked
    assert "sequencer" in checked

    wav = tmp_path / "bell.wav"
    cli_main(["render", str(document), "-o", str(wav), "--bars", "1", "--tail", "0.2"])
    assert wav.stat().st_size > 44
    assert "wrote" in capsys.readouterr().out

    mid = tmp_path / "bell.mid"
    cli_main(["midi", str(document), "-o", str(mid), "--bars", "1"])
    assert read_midi_notes(mid)
    cli_main(["modules"])
    listed = capsys.readouterr().out
    assert "Fretboard" in listed
    assert "Sequencer" in listed
    assert "MIDI Out" in listed


def test_shipped_guitar_patches_are_the_documents_the_builder_writes() -> None:
    chapel = read_patch_preset(Path("examples/dadgad-chapel.noodler"))
    hymn = read_patch_preset(Path("examples/open-g-hymn.noodler"))
    hymn_toml = read_patch_preset(Path("examples/open-g-hymn.toml"))
    assert chapel.name == "DADGAD Chapel"
    assert chapel.transport.bpm == 72
    assert {module.module_type for module in chapel.modules} >= {"key", "sequencer", "fretboard", "pytheory_voice", "midi_out"}
    board = next(module for module in chapel.modules if module.instance_id == "board")
    assert board.parameters["tuning"] == "dadgad"
    assert hymn.name == "Open G, Capo 2"
    fret = next(module for module in hymn.modules if module.instance_id == "board")
    assert fret.parameters["tuning"] == "open g"
    assert fret.parameters["capo"] == 2
    assert hymn_toml.name == hymn.name
    assert hymn_toml.transport.bpm == hymn.transport.bpm
