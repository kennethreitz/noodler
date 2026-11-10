"""Build the two guitar patches: DADGAD Chapel, and Open G with a capo on 2.

Run from the repository root:  uv run python examples/build_guitar_patches.py

Both are ordinary patches. The chapel is a phrase in D over the open strings
of DADGAD. The hymn is an A major arpeggio — which is what open G with a capo
on the second fret already is — under a guitar that strums that tuning.
"""

from pathlib import Path

from noodler.studio import Patch


ROOT = Path(__file__).resolve().parent


def chapel() -> Patch:
    patch = Patch("DADGAD Chapel").at(bpm=72, gain=0.9)
    patch.module(
        "key", "key",
        system="western", tonic="D", octave=3, scale_name="major",
        reference_frequency_hz=220.0, at=(40, 40),
    )
    patch.module(
        "melody", "sequencer",
        steps="0 2 4 3  4 2 0 4  5 4 2 1  0 . 4 .",
        division="1/8", octave=1, gate_length=0.55, at=(380, 40),
    )
    patch.module(
        "board", "fretboard",
        tuning="dadgad", capo=0, strum="down", division="1/4",
        strum_ms=16, gate_ms=180, at=(760, 40),
    )
    patch.module(
        "box", "pytheory_voice",
        instrument="kalimba", level=0.55, release_ms=520,
        reference_frequency_hz=220.0, at=(380, 380),
    )
    patch.module(
        "guitar", "pytheory_voice",
        instrument="acoustic_guitar", level=0.4, release_ms=340,
        reference_frequency_hz=220.0, at=(760, 380),
    )
    patch.module(
        "room", "reverb",
        mix=1.0, decay_seconds=5.2, damping=0.46, diffusion=0.84,
        pre_delay_ms=28.0, at=(1140, 380),
    )
    patch.module("midi", "midi_out", channel=1, velocity=88, at=(40, 380))
    patch.cable("key.scale", "melody.scale")
    patch.cable("melody.pitch", "box.pitch")
    patch.cable("melody.gate", "box.gate")
    patch.cable("melody.pitch", "midi.pitch")
    patch.cable("melody.gate", "midi.gate")
    patch.cable("board.pitch", "guitar.pitch")
    patch.cable("board.gate", "guitar.gate")
    patch.hear("box.audio", level=0.7, pan=-0.22, send_b=0.4)
    patch.hear("guitar.audio", level=0.52, pan=0.28, send_b=0.5)
    patch.cable("master.send_b", "room.audio")
    patch.cable("room.left", "master.return_b_left")
    patch.cable("room.right", "master.return_b_right")
    patch.master.set_return_level("b", 0.52)
    return patch


def hymn() -> Patch:
    """Open G, capo 2, is an A major chord. The arpeggio plays that A."""
    patch = Patch("Open G, Capo 2").at(bpm=84, gain=0.9)
    patch.module("clock", "clock", at=(40, 40))
    patch.module("chord", "chord", name="A", octave=3, at=(360, 40))
    patch.module(
        "arp", "arpeggio_brain",
        pattern="up / down", octave_range=2, gate_length=0.45, at=(700, 40),
    )
    patch.module(
        "board", "fretboard",
        tuning="open g", capo=2, strum="down", division="1/2",
        strum_ms=20, gate_ms=240, at=(1080, 40),
    )
    patch.module(
        "box", "pytheory_voice",
        instrument="music_box", level=0.42, release_ms=760,
        reference_frequency_hz=220.0, at=(360, 400),
    )
    patch.module(
        "guitar", "pytheory_voice",
        instrument="clean_guitar", level=0.4, release_ms=420,
        reference_frequency_hz=220.0, at=(1080, 400),
    )
    patch.module(
        "room", "reverb",
        mix=1.0, decay_seconds=4.2, damping=0.4, diffusion=0.82,
        pre_delay_ms=22.0, at=(720, 400),
    )
    patch.module("midi", "midi_out", channel=1, velocity=92, at=(40, 400))
    for voice in range(1, 5):
        patch.cable(f"chord.voice_{voice}", f"arp.voice_{voice}")
    patch.cable("clock.eighth", "arp.clock")
    patch.cable("arp.pitch", "box.pitch")
    patch.cable("arp.gate", "box.gate")
    patch.cable("arp.pitch", "midi.pitch")
    patch.cable("arp.gate", "midi.gate")
    patch.cable("board.pitch", "guitar.pitch")
    patch.cable("board.gate", "guitar.gate")
    patch.hear("box.audio", level=0.6, pan=-0.18, send_b=0.34)
    patch.hear("guitar.audio", level=0.5, pan=0.24, send_b=0.46)
    patch.cable("master.send_b", "room.audio")
    patch.cable("room.left", "master.return_b_left")
    patch.cable("room.right", "master.return_b_right")
    patch.master.set_return_level("b", 0.5)
    return patch


def main() -> None:
    written = [
        chapel().save(ROOT / "dadgad-chapel.noodler"),
        hymn().save(ROOT / "open-g-hymn.noodler"),
        hymn().save(ROOT / "open-g-hymn.toml"),
    ]
    for path in written:
        print(path.relative_to(ROOT.parent))


if __name__ == "__main__":
    main()
