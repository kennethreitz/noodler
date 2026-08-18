"""One clock the whole rack can agree on.

Modules that repeat — clocks, sequencers, arpeggiators, random sources — each
carry their own rate in hertz, which is the honest unit for a voltage but the
wrong one for music. Nothing in a patch lines up unless every rate is set by
hand to the same arithmetic, and changing the tempo means changing all of them.

A rate can instead be given as a division of a beat. The transport owns the
tempo; a division turns it into the hertz the module already understands, so
nothing in the DSP has to learn about music, and a module is never forced to
sync — free-running is still a division called "free".
"""

from dataclasses import dataclass


FREE = "free"
"""A rate the transport does not drive."""

NOTE_DIVISIONS: dict[str, float] = {
    "1/2": 2.0,
    "1/2.": 3.0,
    "1/4": 1.0,
    "1/4.": 1.5,
    "1/4T": 2.0 / 3.0,
    "1/8": 0.5,
    "1/8.": 0.75,
    "1/8T": 1.0 / 3.0,
    "1/16": 0.25,
    "1/16T": 1.0 / 6.0,
    "1/32": 0.125,
}
"""Note lengths, measured in quarter notes.

Dotted divisions are half again as long; triplets are two thirds.
"""

BAR_DIVISIONS: dict[str, float] = {"8 bars": 8.0, "4 bars": 4.0, "2 bars": 2.0, "1 bar": 1.0}
"""Bar lengths, measured in bars.

A bar cannot be tabulated in quarter notes because its length is the time
signature's to decide: a bar of 7/8 is not a bar of 4/4.
"""

DIVISIONS: dict[str, float] = {**BAR_DIVISIONS, **NOTE_DIVISIONS}

CHOICES: tuple[str, ...] = (FREE, *DIVISIONS)

MIN_BPM = 20.0
MAX_BPM = 300.0
MAX_BEATS_PER_BAR = 32
BEAT_UNITS: tuple[int, ...] = (1, 2, 4, 8, 16)
"""Note values a signature can count in: whole through sixteenth."""


@dataclass(frozen=True, slots=True)
class TransportFrame:
    """Where the clock stood when an audio block began.

    This is how tempo reaches the DSP without the DSP learning about music:
    a module that asks for it is handed one of these per block, sample-exact,
    and everything else never sees it. It is a snapshot, so a module can read
    it freely while the clock moves on underneath.
    """

    bpm: float
    phase: float
    """Position within the bar at the first sample of the block, zero to one."""
    bars: int
    """How many whole bars have gone by since the clock last started at zero."""
    beats_per_bar: int
    quarters_per_bar: float
    running: bool

    @property
    def quarters(self) -> float:
        """Absolute position in quarter notes, which is what patterns count in."""
        return (self.bars + self.phase) * self.quarters_per_bar

    @property
    def quarters_per_second(self) -> float:
        return self.bpm / 60.0


@dataclass(slots=True)
class Transport:
    """The rack's tempo, and where it currently is in the bar."""

    bpm: float = 120.0
    running: bool = True
    phase: float = 0.0
    """Position within a bar, from zero to one."""

    bars: int = 0
    """Whole bars elapsed, so patterns longer than a bar know where they are."""

    beats_per_bar: int = 4
    """The signature's upper number: how many beats a bar holds."""

    beat_unit: int = 4
    """The signature's lower number: which note gets the beat."""

    @property
    def quarters_per_bar(self) -> float:
        """A bar's length in quarter notes, which is what tempo counts."""
        return self.beats_per_bar * (4.0 / self.beat_unit)

    @property
    def signature(self) -> str:
        return f"{self.beats_per_bar}/{self.beat_unit}"

    def set_signature(self, beats: int, unit: int) -> str:
        """Set the time signature, keeping both halves usable.

        Tempo is counted in quarter notes whatever the signature says, so 6/8
        at 120 is six eighth-note beats in the time of three quarters — the
        denominator changes what a beat *is*, not how fast the clock runs.
        """
        self.beats_per_bar = max(1, min(MAX_BEATS_PER_BAR, int(beats)))
        self.beat_unit = min(
            BEAT_UNITS, key=lambda unit_: abs(unit_ - int(unit))
        )
        self.phase = min(self.phase, 0.999999)
        return self.signature

    def set_bpm(self, bpm: float) -> float:
        """Set the tempo, held inside a range a rack can actually use."""
        self.bpm = min(MAX_BPM, max(MIN_BPM, float(bpm)))
        return self.bpm

    def quarters_for(self, division: str) -> float | None:
        """How many quarter notes one cycle of a division lasts."""
        bars = BAR_DIVISIONS.get(division)
        if bars is not None:
            return bars * self.quarters_per_bar
        return NOTE_DIVISIONS.get(division)

    def hz_for(self, division: str) -> float | None:
        """The rate a division asks for, or None if it asks for nothing.

        A division names how *long* one cycle is, so a longer division is a
        slower rate: a bar at 120 BPM in 4/4 is one cycle every two seconds.
        """
        quarters = self.quarters_for(division)
        if quarters is None or quarters <= 0.0:
            return None
        return (self.bpm / 60.0) / quarters

    def seconds_for(self, division: str) -> float | None:
        """How long one cycle of a division lasts, in seconds.

        The other face of hz_for: a delay time, a decay, a pre-delay are
        lengths, and a length synced to the clock is a division of the beat.
        """
        hertz = self.hz_for(division)
        return None if hertz is None or hertz <= 0.0 else 1.0 / hertz

    def advance(self, dt: float) -> float:
        """Move the clock on by one frame and return the position in the bar."""
        if self.running and dt > 0.0:
            bar_seconds = self.quarters_per_bar * 60.0 / max(1e-6, self.bpm)
            moved = self.phase + dt / bar_seconds
            self.bars += int(moved)
            self.phase = moved % 1.0
        return self.phase

    def frame(self) -> TransportFrame:
        """A snapshot of the clock, for a module to read this block."""
        return TransportFrame(
            bpm=self.bpm,
            phase=self.phase,
            bars=self.bars,
            beats_per_bar=self.beats_per_bar,
            quarters_per_bar=self.quarters_per_bar,
            running=self.running,
        )

    def tick(self, frame_count: int, sample_rate: float) -> TransportFrame:
        """Advance by one audio block and return where the block *began*.

        Called from the audio callback, so the clock runs on the sample clock
        rather than the frame rate: a beat lands on the sample it should, not
        within sixteen milliseconds of it.
        """
        frame = self.frame()
        if sample_rate > 0.0:
            self.advance(frame_count / float(sample_rate))
        return frame

    def rewind(self) -> None:
        """Back to the top of bar one."""
        self.phase = 0.0
        self.bars = 0

    @property
    def beat(self) -> int:
        """Which beat of the bar the clock is on, counting from one."""
        return int(self.phase * self.beats_per_bar) + 1

    def on_beat(self, width: float = 0.12) -> bool:
        """Whether the clock is close enough to a beat to flash for it."""
        within = (self.phase * self.beats_per_bar) % 1.0
        return within < width


def is_rate_field(field_name: str) -> bool:
    """Whether a parameter names a repeat rate the transport could drive.

    Pitch is a frequency too, and a reference frequency is a tuning, so neither
    belongs to the clock. Only rates do.
    """
    return field_name.endswith("rate_hz")


def is_time_field(field_name: str) -> bool:
    """Whether a parameter names a length of time the transport could set.

    A delay time, a decay, a pre-delay, an attack: any of them can be a
    division of the beat. Names say the unit -- seconds or milliseconds -- so
    the sync knows what to write.
    """
    return field_name.endswith("_seconds") or field_name.endswith("_ms")


def clock_kind(field_name: str) -> str | None:
    """'rate', 'seconds', 'ms', or None if the clock has nothing to say."""
    if is_rate_field(field_name):
        return "rate"
    if field_name.endswith("_seconds"):
        return "seconds"
    if field_name.endswith("_ms"):
        return "ms"
    return None


__all__ = [
    "BAR_DIVISIONS",
    "BEAT_UNITS",
    "CHOICES",
    "DIVISIONS",
    "MAX_BEATS_PER_BAR",
    "NOTE_DIVISIONS",
    "FREE",
    "MAX_BPM",
    "MIN_BPM",
    "Transport",
    "TransportFrame",
    "clock_kind",
    "is_rate_field",
    "is_time_field",
]
