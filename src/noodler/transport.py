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

DIVISIONS: dict[str, float] = {
    "4 bars": 64.0,
    "2 bars": 32.0,
    "1 bar": 16.0,
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
"""Named divisions, measured in beats per cycle.

A beat is a quarter note, so "1/4" is one beat and a bar is four. Dotted
divisions are half again as long; triplets are two thirds.
"""

CHOICES: tuple[str, ...] = (FREE, *DIVISIONS)

MIN_BPM = 20.0
MAX_BPM = 300.0


@dataclass(slots=True)
class Transport:
    """The rack's tempo, and where it currently is in the bar."""

    bpm: float = 120.0
    running: bool = True
    phase: float = 0.0
    """Position within a bar, from zero to one."""

    beats_per_bar: int = 4

    def set_bpm(self, bpm: float) -> float:
        """Set the tempo, held inside a range a rack can actually use."""
        self.bpm = min(MAX_BPM, max(MIN_BPM, float(bpm)))
        return self.bpm

    def hz_for(self, division: str) -> float | None:
        """The rate a division asks for, or None if it asks for nothing.

        A division names how *long* one cycle is, so a longer division is a
        slower rate: sixteen beats to the cycle at 120 BPM is one cycle every
        eight seconds.
        """
        beats = DIVISIONS.get(division)
        if beats is None or beats <= 0.0:
            return None
        return (self.bpm / 60.0) / beats

    def advance(self, dt: float) -> float:
        """Move the clock on by one frame and return the position in the bar."""
        if self.running and dt > 0.0:
            bar_seconds = self.beats_per_bar * 60.0 / max(1e-6, self.bpm)
            self.phase = (self.phase + dt / bar_seconds) % 1.0
        return self.phase

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


__all__ = [
    "CHOICES",
    "DIVISIONS",
    "FREE",
    "MAX_BPM",
    "MIN_BPM",
    "Transport",
    "is_rate_field",
]
