"""The commands that do not open the rack.

``noodler`` on its own still opens the window. These are the ones you run
when you want the patch as a file: check it, render it, or write the MIDI.

::

    noodler check examples/dadgad-chapel.noodler
    noodler render examples/dadgad-chapel.noodler -o chapel.wav
    noodler midi examples/open-g-hymn.noodler -o hymn.mid
    noodler modules
"""

from argparse import ArgumentParser, Namespace
from pathlib import Path

from noodler.module_providers.builtin import BUILTIN_PROVIDER_MANIFEST
from noodler.preset import read_patch_preset


def main(argv: list[str]) -> None:
    parser = ArgumentParser(prog="noodler", description="Check, render, or list a Noodler patch.")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate a patch and print what is in it")
    check.add_argument("patch", type=Path)

    render = commands.add_parser("render", help="bounce a patch to a WAV file")
    render.add_argument("patch", type=Path)
    render.add_argument("-o", "--output", type=Path, required=True)
    render.add_argument("--bars", type=int, default=8)
    render.add_argument("--tail", type=float, default=2.0)

    midi = commands.add_parser("midi", help="write the MIDI a patch's MIDI Out modules played")
    midi.add_argument("patch", type=Path)
    midi.add_argument("-o", "--output", type=Path, required=True)
    midi.add_argument("--bars", type=int, default=8)

    commands.add_parser("modules", help="list the modules that ship with Noodler")

    args = parser.parse_args(argv)
    if args.command == "check":
        _check(args)
    elif args.command == "render":
        _render(args)
    elif args.command == "midi":
        _midi(args)
    elif args.command == "modules":
        _modules()


def _load(path: Path):
    try:
        return read_patch_preset(path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"noodler: could not open {path}: {exc}") from exc


def _check(args: Namespace) -> None:
    preset = _load(args.patch)
    print(f"{preset.name}")
    print(
        f"{preset.transport.bpm:g} BPM  ·  "
        f"{preset.transport.beats_per_bar}/{preset.transport.beat_unit}  ·  "
        f"{len(preset.modules)} modules  ·  {len(preset.cables)} cables"
    )
    for module in preset.modules:
        print(f"  {module.instance_id:<16} {module.module_type}")


def _render(args: Namespace) -> None:
    from noodler.bounce import bounce, write_wav

    if args.bars <= 0:
        raise SystemExit("noodler: --bars must be positive")
    preset = _load(args.patch)
    audio = bounce(preset, bars=args.bars, tail_seconds=args.tail)
    destination = write_wav(args.output, audio)
    seconds = audio.shape[0] / 48_000
    print(f"wrote {destination}  ({seconds:.1f}s)")


def _midi(args: Namespace) -> None:
    from noodler.bounce import perform
    from noodler.midi import write_midi

    if args.bars <= 0:
        raise SystemExit("noodler: --bars must be positive")
    preset = _load(args.patch)
    _audio, events = perform(preset, bars=args.bars, tail_seconds=0.0)
    notes = [event for event in events if event.on]
    if not notes:
        raise SystemExit("noodler: that patch has no MIDI notes to write")
    destination = write_midi(args.output, events, bpm=preset.transport.bpm)
    print(f"wrote {destination}  ({len(notes)} notes)")


def _modules() -> None:
    shelves: dict[str, list[str]] = {}
    for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
        shelves.setdefault(manifest.category, []).append(manifest.name)
    for category, names in shelves.items():
        print(category)
        for name in names:
            print(f"  {name}")


__all__ = ["main"]
