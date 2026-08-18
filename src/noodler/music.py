"""Musical intent, as something a cable can carry.

A patch graph moves numbers: a voltage, a gate, a block of samples. Musical
meaning has until now been reduced to a number at the point it leaves a module —
a scale becomes one pitch, a chord becomes its root — and everything downstream
receives a value with no idea what it meant. Whatever knew the music kept the
knowledge to itself.

A scale is a small, immutable description that survives the journey: which
system, which tonic, which mode, and the tones that follow from those. Modules
downstream can then ask musical questions of it — what is the nearest degree,
what is in this mode — instead of being handed an answer already computed by
somebody else.

PyTheory is asked once, on the control path, and the result is cached: the audio
callback only ever reads a sorted array of numbers.
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray
from pytheory import SYSTEMS, TonedScale


SYSTEM_NAMES: tuple[str, ...] = tuple(SYSTEMS)
"""Every tone system PyTheory knows, not merely the familiar ones."""

DEFAULT_SYSTEM = "western"
DEFAULT_SCALE = "major"
DEFAULT_TONIC = "C"
DEFAULT_OCTAVE = 4
PITCH_SPAN = 5
"""Periods generated either side of the tonic, which is more than a rack uses."""


@lru_cache(maxsize=64)
def tonics_for(system: str) -> tuple[str, ...]:
    """The tone names a system actually recognises.

    Systems do not share a vocabulary: an Arabic tonic is named Do or Sib, a
    Carnatic one Sa, a gamelan one barang. Offering C to all of them is how a
    tonic ends up rejected by the system it was chosen for.
    """
    try:
        names = SYSTEMS[system].tone_names
    except KeyError:
        return ()
    return tuple(group[0] for group in names)


@lru_cache(maxsize=256)
def scale_names_for(system: str, tonic: str, octave: int) -> tuple[str, ...]:
    """The modes available for one tonic in one system.

    Asked of the built scale rather than the system, because that is where the
    musically interesting names live: maqamat for Arabic, melakarta for
    Carnatic, thaats for shruti, pelog and slendro for gamelan.
    """
    try:
        return tuple(TonedScale(tonic=f"{tonic}{octave}", system=system).scales)
    except Exception:
        return ()


@dataclass(frozen=True, slots=True)
class ScaleField:
    """A scale, travelling as itself rather than as one of its notes."""

    system: str
    tonic: str
    octave: int
    name: str
    tones: tuple[tuple[str, float], ...]
    """Each tone of one period: its spelling, and its frequency in hertz."""

    period: float
    """The frequency ratio at which the scale repeats — not always an octave."""

    @property
    def label(self) -> str:
        return f"{self.tonic}{self.octave} {self.name} · {self.system}"

    @property
    def root_hz(self) -> float:
        return self.tones[0][1] if self.tones else 0.0

    def frequencies(self, span: int = PITCH_SPAN) -> tuple[float, ...]:
        """Every frequency the scale allows, across the spanned periods."""
        if not self.tones:
            return ()
        found: list[float] = []
        for step in range(-span, span + 1):
            factor = self.period**step
            found.extend(frequency * factor for _name, frequency in self.tones)
        return tuple(sorted(set(found)))

    def pitch_table(
        self,
        reference_hz: float,
        span: int = PITCH_SPAN,
    ) -> NDArray[np.float64]:
        """The allowed pitches in one-volt-per-octave terms, ascending."""
        if reference_hz <= 0.0:
            return np.zeros(0, dtype=np.float64)
        frequencies = self.frequencies(span)
        if not frequencies:
            return np.zeros(0, dtype=np.float64)
        return np.log2(np.asarray(frequencies, dtype=np.float64) / reference_hz)


@lru_cache(maxsize=256)
def build_scale(
    system: str = DEFAULT_SYSTEM,
    tonic: str = DEFAULT_TONIC,
    octave: int = DEFAULT_OCTAVE,
    name: str = DEFAULT_SCALE,
) -> ScaleField | None:
    """Ask PyTheory for a scale, once, and keep the answer.

    Returns None rather than raising when a system, tonic and mode do not go
    together: a rack should say so on its panel, not stop.
    """
    try:
        built = TonedScale(tonic=f"{tonic}{octave}", system=system)[name]
        tones = tuple(
            (str(tone), float(tone.frequency))
            for tone in built.tones
            if getattr(tone, "frequency", None)
        )
    except Exception:
        return None
    if not tones:
        return None
    period = float(getattr(SYSTEMS.get(system), "period", 2.0) or 2.0)
    return ScaleField(
        system=system,
        tonic=tonic,
        octave=int(octave),
        name=name,
        tones=tones,
        period=period,
    )


def quantize(
    pitches: NDArray[np.float64],
    table: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Snap pitches to the nearest allowed one.

    Vectorised on purpose: the scale is worked out on the control path, and all
    the audio callback does is a binary search over a sorted array.
    """
    if table.size == 0:
        return pitches
    upper = np.searchsorted(table, pitches)
    upper = np.clip(upper, 1, table.size - 1)
    lower = upper - 1
    below = table[lower]
    above = table[upper]
    nearer_above = np.abs(above - pitches) < np.abs(pitches - below)
    return np.where(nearer_above, above, below)


__all__ = [
    "DEFAULT_OCTAVE",
    "DEFAULT_SCALE",
    "DEFAULT_SYSTEM",
    "DEFAULT_TONIC",
    "PITCH_SPAN",
    "SYSTEM_NAMES",
    "ScaleField",
    "build_scale",
    "quantize",
    "scale_names_for",
    "tonics_for",
]
