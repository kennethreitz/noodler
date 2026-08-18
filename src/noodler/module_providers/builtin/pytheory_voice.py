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

One note is rendered per semitone, so a played pitch is read back at very near
the rate it was rendered at and PyTheory's own timbre survives. That is only
affordable because the cost of a note varies enormously between instruments —
a tenth of a millisecond for a music box, nine for a cello — so the resolution
is not fixed: notes are filled in for as long as a time budget allows, and an
instrument too expensive to cover finely keeps a coarse set and stays playable.
"""

from collections.abc import Mapping
import threading
import time

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
"""The coarse set, rendered first so an instrument is playable immediately."""

LOWEST_HZ = 55.0
SEMITONES = 61
"""Every semitone from 55 Hz to 1760 Hz, which is the range a rack reaches for."""

RENDER_BUDGET_MS = 260.0
"""How long filling in notes may take before changing instrument stops feeling
instant.

The cost of a note is not a property of the library, it is a property of the
instrument: a music box renders in a tenth of a millisecond and a cello in nine.
Rendering a fixed number would either leave the cheap instruments coarser than
they could be or freeze the app on the expensive ones, so the budget is time and
the resolution is whatever fits inside it.

The clock starts *after* the first note, because the first render of a synth
pays for compiling it — most of a second, once, for something that costs 0.8 ms
a note thereafter. Charging that to the budget would permanently punish an
instrument for being new rather than for being slow.
"""


def _spread(count: int) -> list[int]:
    """Order indices so that stopping early still covers the whole range.

    Filling in order would leave a partially rendered instrument accurate at
    the bottom and an octave out at the top. Bisecting means every note is as
    near a rendered one as the budget allows.
    """
    order: list[int] = []
    pending = [(0, count - 1)]
    seen = set()
    while pending:
        low, high = pending.pop(0)
        if low > high:
            continue
        middle = (low + high) // 2
        if middle not in seen:
            seen.add(middle)
            order.append(middle)
        pending.append((low, middle - 1))
        pending.append((middle + 1, high))
    return order

VOICE_OUTPUTS = ("audio", "envelope")
SYNTH_BY_NAME = {member.value: member for member in Synth}

LOOP_SECONDS = 0.35
"""How much of the end of a sustaining note is looped while the gate is held."""

LOOP_CROSSFADE_SECONDS = 0.06
"""The seam of the loop, crossfaded so repeating it is not a click."""

SUSTAINS_ABOVE = 0.15
"""A note still this loud at its end, relative to its peak, is a sustaining one.

PyTheory renders one second of every instrument. A plucked string has decayed
to almost nothing by then and should end; a bowed one or an organ is still at
full level and has only stopped because the render did. The two are told apart
by the render itself rather than by a table of which instruments are which, and
the threshold sits in a real gap: every guitar, piano and harp measures 0.13 or
below, everything blown, bowed or sustained 0.16 or above.

Long-ringing metal -- bells, glockenspiel, celesta -- lands on the sustaining
side, and holding one loops its ring, which is what a held mallet roll sounds
like. Letting go still releases it.
"""


def sustains(note: NDArray[np.float32]) -> bool:
    """Whether a rendered note is still sounding when it runs out."""
    if note.size < int(PYTHEORY_RATE * 0.5):
        return False
    tail = note[-int(PYTHEORY_RATE * 0.1) :]
    peak = float(np.max(np.abs(note)))
    return peak > 0.0 and float(np.sqrt(np.mean(tail * tail))) / peak >= SUSTAINS_ABOVE


def loop_region(note: NDArray[np.float32]) -> tuple[int, int] | None:
    """The stretch of a sustaining note that can be repeated while it is held.

    The last third of a second, seamed with a crossfade: the end of the region
    is faded into its beginning, so playback can jump from one to the other
    with nothing to hear at the join.
    """
    if not sustains(note):
        return None
    length = min(note.size, int(PYTHEORY_RATE * LOOP_SECONDS))
    fade = min(length // 2, int(PYTHEORY_RATE * LOOP_CROSSFADE_SECONDS))
    start = note.size - length
    return start, fade


def seam(note: NDArray[np.float32], region: tuple[int, int]) -> NDArray[np.float32]:
    """Return a copy of a note whose loop region has been crossfaded shut.

    The last `fade` samples of the region are blended toward the first `fade`
    samples, so that when playback wraps from the region's end to its start,
    the waveform it lands on is the one it was already fading into.
    """
    start, fade = region
    if fade <= 0:
        return note
    seamed = np.array(note, dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, fade, endpoint=False, dtype=np.float32)
    head = seamed[start : start + fade]
    tail = seamed[-fade:]
    seamed[-fade:] = tail * (1.0 - ramp) + head * ramp
    return seamed


def render_note(instrument: str, hertz: float) -> NDArray[np.float64]:
    """Ask PyTheory for one note, as floating point between -1 and 1."""
    spec = INSTRUMENTS.get(instrument) or INSTRUMENTS[DEFAULT_INSTRUMENT]
    synth = SYNTH_BY_NAME.get(str(spec.get("synth", "")))
    if synth is None:
        return np.zeros(0, dtype=np.float64)
    rendered = synth(float(hertz), **dict(spec.get("synth_kw") or {}))
    samples = np.asarray(rendered, dtype=np.float32)
    if not samples.size:
        return samples
    peak = float(np.max(np.abs(samples)))
    if peak > 0.0:
        samples = samples / peak
    # Trailing silence is most of a rendered note and none of the sound.
    loud = np.flatnonzero(np.abs(samples) > 1e-4)
    if loud.size:
        samples = samples[: int(loud[-1]) + 1]
    samples = np.asarray(samples, dtype=np.float32)
    region = loop_region(samples)
    return seam(samples, region) if region is not None else samples


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
        self._pending: list[float] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._generation = 0
        self._rendered_for: str | None = None
        self._sample_rate = 48_000.0
        self._note: NDArray[np.float64] | None = None
        self._loop: tuple[int, int] | None = None
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

    @property
    def resolution(self) -> str:
        """How closely the rendered notes cover the range, in words."""
        rendered = len(self._anchors)
        if rendered >= SEMITONES:
            return "every semitone"
        return f"{rendered} of {SEMITONES} pitches"

    @property
    def label(self) -> str:
        """What the status line says when this instrument is chosen.

        Which instrument it is, and how finely it got rendered — because that
        is decided by the budget rather than by the patch, and a player who
        cannot see it has no way to know why one instrument tracks pitch more
        closely than another.
        """
        spoken = self.parameters.instrument.replace("_", " ").upper()
        return f"{spoken}  ·  {self.resolution.upper()}"

    def refresh(
        self, budget_ms: float = RENDER_BUDGET_MS, *, in_background: bool = True
    ) -> None:
        """Render this instrument's notes. Control thread only — this is slow.

        The coarse set comes first, so the instrument plays straight away, and
        semitones are filled in for as long as the budget allows. An instrument
        that renders in a tenth of a millisecond gets all of them; one that
        takes most of a second keeps the coarse set and is still playable.
        """
        with self._lock:
            # Anything a previous instrument still owed is no longer wanted.
            self._generation += 1

        instrument = self.parameters.instrument
        wanted = [LOWEST_HZ * 2.0 ** (step / 12.0) for step in range(SEMITONES)]
        order = _spread(SEMITONES)

        # The first note pays whatever compiling this synth costs; the budget
        # measures the ones after it, which is what the resolution depends on.
        anchors = {wanted[order[0]]: render_note(instrument, wanted[order[0]])}
        started = time.perf_counter()
        for hertz in ANCHOR_HZ:
            anchors.setdefault(hertz, render_note(instrument, hertz))

        self._anchors = {hertz: note for hertz, note in anchors.items() if note.size}
        # Reversed, because pending is consumed from the end and the spread
        # puts the notes that improve coverage most at the front.
        self._pending = [wanted[index] for index in reversed(order[1:])]
        self._rendered_for = instrument
        self._spend(budget_ms, started)
        if in_background:
            self._finish_in_background()

    def _spend(self, budget_ms: float, started: float | None = None) -> bool:
        """Render pending notes until the budget runs out."""
        started = time.perf_counter() if started is None else started
        instrument = self._rendered_for or self.parameters.instrument
        # Built aside and swapped in whole: the audio callback reads this dict
        # from another thread, and growing one underneath a reader is a crash.
        anchors = dict(self._anchors)
        while self._pending:
            if (time.perf_counter() - started) * 1_000.0 >= budget_ms:
                break
            hertz = self._pending.pop()
            if any(abs(hertz - known) < 0.01 for known in anchors):
                continue
            note = render_note(instrument, hertz)
            if note.size:
                anchors[hertz] = note
        self._anchors = anchors
        return bool(self._pending)

    def _finish_in_background(self) -> None:
        """Render whatever the budget could not, off the interface's thread.

        The click can only afford so much, and the expensive instruments are
        exactly the ones that need the most notes. PyTheory's rendering gives
        up the interpreter lock while it works, so doing the rest on a worker
        costs the interface nothing measurable -- the instrument simply gets
        better at tracking pitch over the following second, while it plays.
        """
        with self._lock:
            if not self._pending or (
                self._worker is not None and self._worker.is_alive()
            ):
                return
            generation = self._generation
            self._worker = threading.Thread(
                target=self._fill_until_done,
                args=(generation,),
                name="noodler-render",
                daemon=True,
            )
            self._worker.start()

    def _fill_until_done(self, generation: int) -> None:
        """Render the remaining notes one at a time, abandoning stale work."""
        while True:
            with self._lock:
                if self._generation != generation or not self._pending:
                    return
                hertz = self._pending.pop()
                instrument = self._rendered_for or self.parameters.instrument
            # Rendering happens outside the lock: it is the slow part, and
            # nothing else needs to wait for it.
            note = render_note(instrument, hertz)
            with self._lock:
                if self._generation != generation:
                    return
                if note.size:
                    self._anchors = {**self._anchors, hertz: note}

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._sample_rate = float(sample_rate)
        if not self.ready:
            self.refresh()

    def _begin(self, hertz: float) -> None:
        """Choose the nearest rendered pitch and set the rate to read it at."""
        anchors = self._anchors
        if not anchors:
            return
        anchor = min(anchors, key=lambda candidate: abs(np.log2(hertz / candidate)))
        note = anchors[anchor]
        if note.size == 0:
            return
        self._note = note
        self._loop = loop_region(note)
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
            holding = self._gate_high or started
            if self._loop is not None and holding:
                # Held past the end of what was rendered: keep going round the
                # seamed loop, so a bowed or blown note lasts as long as the
                # gate does rather than as long as PyTheory's render did.
                start, _fade = self._loop
                length = note.size - 1 - start
                over = positions >= start
                positions = np.where(
                    over, start + np.mod(positions - start, length), positions
                )
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
    "LOOP_SECONDS",
    "loop_region",
    "sustains",
    "PYTHEORY_RATE",
    "PYTHEORY_VOICE_MANIFEST",
    "PyTheoryVoice",
    "PyTheoryVoiceParameters",
    "render_note",
]
