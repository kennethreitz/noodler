"""Notes leaving the rack as MIDI.

Pitch and gate go in, the way they go into a voice. What comes out is a list
of note-ons and note-offs on the module, which a render can write to a
``.mid`` file. The audio callback only appends to that list; it does not open
a port or a file.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field

from noodler.midi import MidiEvent
from noodler.module_providers import ModuleManifest, PortDirection, SignalType
from noodler.transport import TransportFrame, block_clock

from ._dsp import FloatBlock, block, empty_outputs, port


NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MIDI_OUTPUTS = ("thru",)


def note_number(volts: float, reference_hz: float) -> int:
    """The MIDI note a one-volt-per-octave pitch sounds as."""
    hertz = reference_hz * 2.0 ** float(np.clip(volts, -8.0, 8.0))
    if hertz <= 0.0:
        return 0
    midi = 69.0 + 12.0 * math.log2(hertz / 440.0)
    return int(np.clip(round(midi), 0, 127))


def spell(note: int) -> str:
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


class MidiOutParameters(BaseModel):
    """Which channel, how hard, and what zero volts means."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    channel: int = Field(default=1, ge=1, le=16)
    velocity: int = Field(default=96, ge=1, le=127)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)


MIDI_OUT_MANIFEST = ModuleManifest(
    id="midi_out",
    name="MIDI Out",
    category="Outputs",
    description=(
        "Turn a pitch and a gate into MIDI notes. A render writes them to a "
        ".mid file; the notes are what the cable carried."
    ),
    ports=(
        port("pitch", "1 V/oct", PortDirection.INPUT, SignalType.CV, "The note, against the reference."),
        port("gate", "Gate", PortDirection.INPUT, SignalType.GATE, "A rising edge is a note-on; letting go is a note-off."),
        port("velocity", "Velocity", PortDirection.INPUT, SignalType.CV, "Zero to one, when you want the panel velocity overwritten."),
        port("thru", "Thru", PortDirection.OUTPUT, SignalType.GATE, "The gate, passed through so the cable can continue."),
    ),
)


class MidiOut:
    """Record note-ons and note-offs from a pitch and a gate."""

    manifest = MIDI_OUT_MANIFEST
    uses_transport = True
    readout = True

    def __init__(self, parameters: MidiOutParameters | None = None) -> None:
        self.parameters = parameters or MidiOutParameters()
        self.midi_events: list[MidiEvent] = []
        self._held: int | None = None
        self._high = False
        self._free_quarters = 0.0
        self._last = "—"

    @property
    def label(self) -> str:
        count = sum(1 for event in self.midi_events if event.on)
        return f"ch {self.parameters.channel} · {self._last} · {count} notes"

    def _event(self, quarters: float, note: int, velocity: int, on: bool) -> None:
        self.midi_events.append(
            MidiEvent(
                quarters=quarters,
                note=note,
                velocity=velocity,
                on=on,
                channel=self.parameters.channel,
            )
        )

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if frame_count == 0:
            return empty_outputs(MIDI_OUTPUTS)

        inputs = inputs or {}
        pitch = block("pitch", inputs, frame_count)
        gate = block("gate", inputs, frame_count)
        velocity_cv = block("velocity", inputs, frame_count) if "velocity" in inputs else None
        transport = inputs.get("transport")
        if not isinstance(transport, TransportFrame):
            transport = None
        start, per_sample, _per_bar, _running, self._free_quarters = block_clock(
            transport,
            free_quarters=self._free_quarters,
            rate_hz=2.0,
            frame_count=frame_count,
            sample_rate=sample_rate,
        )
        reference = self.parameters.reference_frequency_hz
        high = self._high
        held = self._held
        for index in range(frame_count):
            is_high = float(gate[index]) > 0.0
            note = note_number(float(pitch[index]), reference)
            rising = is_high and not high
            falling = high and not is_high
            changed = is_high and held is not None and note != held
            if falling or changed:
                if held is not None:
                    self._event(start + index * per_sample, held, 0, False)
                    held = None
            if rising or changed:
                velocity = self.parameters.velocity
                if velocity_cv is not None:
                    velocity = int(np.clip(round(float(velocity_cv[index]) * 127.0), 1, 127))
                self._event(start + index * per_sample, note, velocity, True)
                held = note
                self._last = spell(note)
            high = is_high
        self._high = high
        self._held = held
        return {"thru": np.asarray(gate, dtype=np.float32)}


__all__ = [
    "MIDI_OUT_MANIFEST",
    "MidiOut",
    "MidiOutParameters",
    "note_number",
]
