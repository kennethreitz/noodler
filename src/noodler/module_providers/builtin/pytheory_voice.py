"""PyTheory's own synthesis, played from the rack.

The Instrument Voice module reads a PyTheory instrument as a recipe and rebuilds
it out of Noodler's oscillators. This module does the other thing: it runs
PyTheory's actual synthesis — `Synth.RHODES`, `Synth.CELLO`, `Synth.SITAR` — and
plays what comes back.

That cannot happen inside the audio callback. PyTheory renders a whole note at
once, about five milliseconds of work for one second of sound, against a
callback that must finish in five milliseconds *total*. So the note is rendered
on the control thread, before it is needed, and the callback only reads it: a
sampler whose samples are made by the algorithm rather than recorded from one.

A handful of pitches are rendered per instrument and the nearest is resampled to
the pitch actually asked for. Rendering one note per semitone would be truer and
is the obvious next step; an octave apart is close enough that the shift is
small, and it keeps changing instrument to a fifth of a second.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pytheory import INSTRUMENTS, Synth

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port
from .instrument import DEFAULT_INSTRUMENT, INSTRUMENT_NAMES


PYTHEORY_RATE = 44_100.0
"""The rate PyTheory renders at, whatever the audio device is doing."""

ANCHOR_HZ: tuple[float, ...] = (55.0, 110.0, 220.0, 440.0, 880.0, 1760.0)
"""Pitches rendered per instrument; everything else is resampled from these."""

VOICE_OUTPUTS = ("audio", "envelope")
SYNTH_BY_NAME = {member.value: member for member in Synth}


def render_note(instrument: str, hertz: float) -> NDArray[np.float64]:
    """Ask PyTheory for one note, as floating point between -1 and 1."""
    spec = INSTRUMENTS.get(instrument) or INSTRUMENTS[DEFAULT_INSTRUMENT]
    synth = SYNTH_BY_NAME.get(str(spec.get("synth", "")))
    if synth is None:
        return np.zeros(0, dtype=np.float64)
    rendered = synth(float(hertz), **dict(spec.get("synth_kw") or {}))
    samples = np.asarray(rendered, dtype=np.float64)
    if not samples.size:
        return samples
    peak = float(np.max(np.abs(samples)))
    return samples / peak if peak > 0.0 else samples


class PyTheoryVoiceParameters(BaseModel):
    """Which instrument to render, and how it is played back."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    instrument: str = DEFAULT_INSTRUMENT
    level: float = Field(default=0.5, ge=0.0, le=1.0)
    release_ms: float = Field(default=120.0, ge=1.0, le=4_000.0)
    reference_frequency_hz: float = Field(default=220.0, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def known(self) -> "PyTheoryVoiceParameters":
        if self.instrument not in INSTRUMENTS:
            object.__setattr__(self, "instrument", DEFAULT_INSTRUMENT)
        return self


PYTHEORY_VOICE_MANIFEST = ModuleManifest(
    id="pytheory_voice",
    name="PyTheory Voice",
    category="Oscillators",
    description=(
        "PyTheory's own synthesis, played from the rack. Notes are rendered by "
        "the library on the control thread and read back in real time."
    ),
    ports=(
        port("pitch", "1 V/oct", PortDirection.INPUT, SignalType.CV, "Pitch, against the reference."),
        port("gate", "Gate", PortDirection.INPUT, SignalType.GATE, "A rising edge starts the note."),
        port("audio", "Out", PortDirection.OUTPUT, SignalType.AUDIO, "What PyTheory rendered."),
        port("envelope", "Env", PortDirection.OUTPUT, SignalType.CV, "The playback gain, including its release."),
    ),
)


class PyTheoryVoice:
    """Play notes that PyTheory synthesised."""

    manifest = PYTHEORY_VOICE_MANIFEST

    def __init__(self, parameters: PyTheoryVoiceParameters | None = None) -> None:
        self.parameters = parameters or PyTheoryVoiceParameters()
        self._anchors: dict[float, NDArray[np.float64]] = {}
        self._rendered_for: str | None = None
        self._sample_rate = 48_000.0
        self._note: NDArray[np.float64] | None = None
        self._position = 0.0
        self._step = 1.0
        self._gain = 0.0
        self._gate_high = False

    @property
    def ready(self) -> bool:
        """Whether the notes for the current instrument have been rendered."""
        return self._rendered_for == self.parameters.instrument

    def choices_for(self, field: str) -> tuple[str, ...]:
        return INSTRUMENT_NAMES if field == "instrument" else ()

    def refresh(self) -> None:
        """Render this instrument's notes. Control thread only — this is slow."""
        instrument = self.parameters.instrument
        self._anchors = {
            hertz: render_note(instrument, hertz) for hertz in ANCHOR_HZ
        }
        self._rendered_for = instrument

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._sample_rate = float(sample_rate)
        if not self.ready:
            self.refresh()

    def _begin(self, hertz: float) -> None:
        """Choose the nearest rendered pitch and set the rate to read it at."""
        if not self._anchors:
            return
        anchor = min(self._anchors, key=lambda candidate: abs(np.log2(hertz / candidate)))
        note = self._anchors[anchor]
        if note.size == 0:
            return
        self._note = note
        self._position = 0.0
        self._step = (hertz / anchor) * (PYTHEORY_RATE / self._sample_rate)
        self._gain = 1.0

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
            return empty_outputs(VOICE_OUTPUTS)
        if self._sample_rate != float(sample_rate):
            self._sample_rate = float(sample_rate)

        inputs = inputs or {}
        pitch = np.asarray(block("pitch", inputs, frame_count), dtype=np.float64)
        gate = np.asarray(block("gate", inputs, frame_count), dtype=np.float64)

        # A note begins on the first rising edge in the block. Sub-block timing
        # would need a render mid-callback, which is the one thing this cannot do.
        high = gate > 0.0
        started = bool(high.any() and not self._gate_high)
        if started:
            index = int(np.argmax(high))
            frequency = float(
                self.parameters.reference_frequency_hz
                * 2.0 ** float(np.clip(pitch[index], -8.0, 8.0))
            )
            self._begin(frequency)
        self._gate_high = bool(high[-1])

        audio = np.zeros(frame_count, dtype=np.float64)
        envelope = np.zeros(frame_count, dtype=np.float64)
        note = self._note
        if note is not None and note.size and self._gain > 0.0:
            positions = self._position + np.arange(frame_count) * self._step
            inside = positions < note.size - 1
            lower = np.clip(positions.astype(np.int64), 0, max(0, note.size - 2))
            fraction = positions - lower
            played = (
                note[lower] * (1.0 - fraction) + note[lower + 1] * fraction
            ) * inside

            if self._gate_high or started:
                gain = np.full(frame_count, self._gain)
            else:
                # Released: fade rather than cut, so letting go is not a click.
                per_sample = 1.0 / max(1.0, self.parameters.release_ms * sample_rate / 1_000.0)
                gain = np.clip(
                    self._gain - per_sample * np.arange(1, frame_count + 1), 0.0, 1.0
                )
                self._gain = float(gain[-1])
            audio = played * gain * self.parameters.level
            envelope = gain * inside
            self._position = float(positions[-1] + self._step)
            if self._position >= note.size - 1:
                self._note = None

        return {
            "audio": np.asarray(audio, dtype=np.float32),
            "envelope": np.asarray(envelope, dtype=np.float32),
        }


__all__ = [
    "ANCHOR_HZ",
    "PYTHEORY_RATE",
    "PYTHEORY_VOICE_MANIFEST",
    "PyTheoryVoice",
    "PyTheoryVoiceParameters",
    "render_note",
]
