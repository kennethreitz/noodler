"""A Standard MIDI file, written from notes a patch played.

The rack's MIDI output is a file any DAW can open. Live ports need a native
backend this program does not carry; a ``.mid`` does not. Events are quarter
notes on the patch's clock, so the tempo in the file is the tempo of the patch.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MidiEvent:
    """One note-on or note-off, in quarter notes from the start of the take."""

    quarters: float
    note: int
    velocity: int
    on: bool
    channel: int = 1


def _varlen(value: int) -> bytes:
    buffer = bytearray([value & 0x7F])
    value >>= 7
    while value:
        buffer.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(buffer))


def write_midi(
    path: str | Path,
    events: tuple[MidiEvent, ...] | list[MidiEvent],
    *,
    bpm: float = 120.0,
    ticks_per_quarter: int = 480,
) -> Path:
    """Write a format-0 MIDI file and return its path."""
    destination = Path(path)
    if destination.suffix.lower() != ".mid":
        destination = destination.with_suffix(".mid")
    destination.parent.mkdir(parents=True, exist_ok=True)

    ordered = sorted(events, key=lambda event: (event.quarters, event.on))
    tempo = int(round(60_000_000 / bpm)) if bpm > 0 else 500_000
    track = bytearray()
    track += _varlen(0) + bytes((0xFF, 0x51, 0x03)) + tempo.to_bytes(3, "big")
    last = 0
    for event in ordered:
        tick = max(0, int(round(event.quarters * ticks_per_quarter)))
        delta = max(0, tick - last)
        last = max(last, tick)
        status = 0x90 if event.on else 0x80
        channel = (max(1, min(16, event.channel)) - 1) & 0x0F
        velocity = event.velocity if event.on else 0
        track += _varlen(delta) + bytes(
            (status | channel, event.note & 0x7F, max(0, min(127, velocity)))
        )
    track += _varlen(0) + bytes((0xFF, 0x2F, 0x00))

    header = b"MThd" + (6).to_bytes(4, "big")
    header += (0).to_bytes(2, "big") + (1).to_bytes(2, "big")
    header += int(ticks_per_quarter).to_bytes(2, "big")
    destination.write_bytes(header + b"MTrk" + len(track).to_bytes(4, "big") + track)
    return destination


def read_midi_notes(path: str | Path) -> list[tuple[int, int, bool]]:
    """Read ``(tick, note, on)`` back out of a format-0 file, for tests."""
    data = Path(path).read_bytes()
    if data[:4] != b"MThd":
        raise ValueError("not a MIDI file")
    # One track, sitting right after the 14-byte header a format-0 file uses.
    body = data[22:]
    notes: list[tuple[int, int, bool]] = []
    tick = 0
    index = 0
    running = 0

    def take_varlen() -> int:
        nonlocal index
        value = 0
        while True:
            byte = body[index]
            index += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value

    while index < len(body):
        tick += take_varlen()
        status = body[index]
        index += 1
        if status == 0xFF:
            kind = body[index]
            index += 1
            length = take_varlen()
            index += length
            if kind == 0x2F:
                break
            continue
        if status & 0x80:
            running = status
        else:
            # Running status: this byte was already the first data byte.
            index -= 1
        command = running & 0xF0
        note = body[index]
        index += 1
        index += 1  # velocity
        if command == 0x90:
            notes.append((tick, note, True))
        elif command == 0x80:
            notes.append((tick, note, False))
    return notes


__all__ = ["MidiEvent", "read_midi_notes", "write_midi"]
