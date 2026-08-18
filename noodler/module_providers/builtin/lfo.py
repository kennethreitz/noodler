"""An LFO: the slow oscillator every rack needs and none of the brains is.

One phase, several shapes at once -- sine, triangle, saw, ramp, square,
sample-and-hold, a smooth random walk -- and a chosen one on the main output
with depth and offset applied, unipolar or bipolar. The rate takes the
clock's divisions like every rate in the rack, and a pitch-style rate CV; a
reset trigger starts the cycle over from the phase knob; a trigger goes out
at the top of every cycle. Slow until it is not: the rate runs to fifty
hertz, and the outputs allow audio, so an LFO into a VCA is a tremolo and an
LFO into a filter is a wah, and an LFO into an LFO is a modular.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


SHAPES = ("sine", "triangle", "saw", "ramp", "square", "sample & hold", "smooth random")
DEFAULT_SHAPE = "sine"
TRIGGER_SAMPLES = 240


class LFOParameters(BaseModel):
    """How fast, what shape, how much, and where it sits."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rate_hz: float = Field(default=1.0, ge=0.01, le=50.0)
    shape: str = DEFAULT_SHAPE
    """The shape on the main output; every shape is also on its own jack."""
    depth: float = Field(default=1.0, ge=0.0, le=1.0)
    offset: float = Field(default=0.0, ge=-1.0, le=1.0)
    phase: float = Field(default=0.0, ge=0.0, le=1.0)
    """Where in the cycle a reset lands, in turns."""
    pulse_width: float = Field(default=0.5, ge=0.05, le=0.95)
    unipolar: bool = False
    """Zero to one instead of minus one to one, for a level or a cutoff."""
    seed: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def known(self) -> "LFOParameters":
        if self.shape not in SHAPES:
            object.__setattr__(self, "shape", DEFAULT_SHAPE)
        return self


LFO_OUTPUTS = ("out", "sine", "triangle", "saw", "square", "random", "cycle")

LFO_MANIFEST = ModuleManifest(
    id="lfo",
    name="LFO",
    category="Modulation",
    description=(
        "A low-frequency oscillator with every shape at once -- sine, triangle, "
        "saw, ramp, square, sample-and-hold, smooth random -- one of them on the "
        "main output with depth and offset, the rate on the clock's divisions, "
        "a reset, and a trigger every cycle."
    ),
    ports=(
        port("rate_cv", "Rate CV", PortDirection.INPUT, SignalType.CV, "Added to the rate, in octaves: one volt doubles it."),
        port("depth_cv", "Depth CV", PortDirection.INPUT, SignalType.CV, "Added to the depth, plus or minus one."),
        port("reset", "Reset", PortDirection.INPUT, SignalType.TRIGGER, "Start the cycle over, from the phase knob."),
        port("out", "Out", PortDirection.OUTPUT, SignalType.CV, "The chosen shape, times depth, plus offset."),
        port("sine", "Sine", PortDirection.OUTPUT, SignalType.CV, "The sine, full scale."),
        port("triangle", "Tri", PortDirection.OUTPUT, SignalType.CV, "The triangle."),
        port("saw", "Saw", PortDirection.OUTPUT, SignalType.CV, "The falling saw."),
        port("square", "Square", PortDirection.OUTPUT, SignalType.CV, "The square, at the pulse width."),
        port("random", "Rnd", PortDirection.OUTPUT, SignalType.CV, "The smooth random walk, a new target every cycle."),
        port("cycle", "Cycle", PortDirection.OUTPUT, SignalType.TRIGGER, "A trigger at the top of every cycle."),
    ),
)


class LFO:
    """One phase, many shapes."""

    manifest = LFO_MANIFEST

    def __init__(self, parameters: LFOParameters | None = None) -> None:
        self.parameters = parameters or LFOParameters()
        self._phase = float(self.parameters.phase)
        self._reset_high = False
        self._rng = np.random.default_rng(self.parameters.seed)
        self._held = float(self._rng.uniform(-1.0, 1.0))
        """The sample-and-hold value for this cycle."""
        self._walk_from = 0.0
        self._walk_to = float(self._rng.uniform(-1.0, 1.0))
        """The smooth random walk goes from one to the other over a cycle."""
        self._pending_cycle = 0

    @property
    def label(self) -> str:
        p = self.parameters
        rate = f"{p.rate_hz:.2f} Hz" if p.rate_hz < 10.0 else f"{p.rate_hz:.1f} Hz"
        polarity = "0..1" if p.unipolar else "±1"
        return f"{p.shape.upper()}  ·  {rate}  ·  {polarity}"

    def choices_for(self, field: str) -> tuple[str, ...]:
        return SHAPES if field == "shape" else ()

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

    def _new_cycle(self) -> None:
        self._held = float(self._rng.uniform(-1.0, 1.0))
        self._walk_from = self._walk_to
        self._walk_to = float(self._rng.uniform(-1.0, 1.0))

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
            return empty_outputs(LFO_OUTPUTS)
        inputs = inputs or {}
        p = self.parameters
        rate_cv = np.asarray(block("rate_cv", inputs, frame_count), dtype=np.float64)
        depth_cv = np.asarray(block("depth_cv", inputs, frame_count), dtype=np.float64)
        reset = np.asarray(block("reset", inputs, frame_count), dtype=np.float64) > 0.5
        rate = p.rate_hz * np.exp2(np.clip(rate_cv, -6.0, 6.0))
        step = rate / sample_rate

        # The phase, sample by sample: a cumulative sum, cut at every reset
        # (a rising edge puts the phase at the knob) and wrapped, with the
        # wraps and resets both counting as the top of a cycle.
        edges = reset & ~np.concatenate(([self._reset_high], reset[:-1]))
        self._reset_high = bool(reset[-1])
        phase = np.empty(frame_count, dtype=np.float64)
        cycle = np.zeros(frame_count, dtype=np.float32)
        held = np.empty(frame_count, dtype=np.float64)
        walk = np.empty(frame_count, dtype=np.float64)
        start = 0
        current = self._phase
        edge_indices = np.flatnonzero(edges).tolist() + [frame_count]
        for edge in edge_indices:
            if edge > start:
                segment = current + np.cumsum(step[start:edge])
                wraps = np.floor(segment)
                phase[start:edge] = segment - wraps
                # A wrap is where the floor steps up: a new cycle each time.
                previous_wrap = np.concatenate(([np.floor(current)], wraps[:-1]))
                tops = np.flatnonzero(wraps > previous_wrap)
                # Sample-and-hold and the walk change at each top; fill by run.
                run_start = start
                for top in tops:
                    index = start + int(top)
                    held[run_start:index] = self._held
                    walk[run_start:index] = self._walk_from + (self._walk_to - self._walk_from) * (
                        0.5 - 0.5 * np.cos(np.pi * phase[run_start:index])
                    )
                    self._new_cycle()
                    cycle[index : index + TRIGGER_SAMPLES] = 1.0
                    run_start = index
                held[run_start:edge] = self._held
                walk[run_start:edge] = self._walk_from + (self._walk_to - self._walk_from) * (
                    0.5 - 0.5 * np.cos(np.pi * phase[run_start:edge])
                )
                current = float(phase[edge - 1])
            if edge < frame_count:
                # A reset: back to the knob's phase, a new cycle begins here.
                current = float(p.phase) - float(step[edge])
                self._new_cycle()
                cycle[edge : edge + TRIGGER_SAMPLES] = 1.0
                start = edge
        self._phase = current % 1.0
        if self._pending_cycle:
            cycle[: min(self._pending_cycle, frame_count)] = 1.0
        # A cycle trigger cut off by the block's end continues into the next.
        last_tops = np.flatnonzero(cycle)
        self._pending_cycle = 0
        if last_tops.size and int(last_tops[-1]) == frame_count - 1:
            # Find where the final run began, to know how much is still owed.
            run = int(last_tops[-1])
            while run > 0 and cycle[run - 1] > 0.0:
                run -= 1
            self._pending_cycle = max(0, TRIGGER_SAMPLES - (frame_count - run))

        two_pi = 2.0 * np.pi
        sine = np.sin(two_pi * phase)
        triangle = 1.0 - 4.0 * np.abs(phase - 0.5)
        saw = 1.0 - 2.0 * phase
        ramp = 2.0 * phase - 1.0
        square = np.where(phase < p.pulse_width, 1.0, -1.0)
        random_walk = np.clip(walk, -1.0, 1.0)
        shapes = {
            "sine": sine,
            "triangle": triangle,
            "saw": saw,
            "ramp": ramp,
            "square": square,
            "sample & hold": held,
            "smooth random": random_walk,
        }
        chosen = shapes[p.shape]
        depth = np.clip(p.depth + depth_cv, 0.0, 1.0)

        def polar(values: NDArray[np.float64]) -> NDArray[np.float32]:
            if p.unipolar:
                values = 0.5 * (values + 1.0)
            return np.asarray(values, dtype=np.float32)

        # Depth scales the shape about its own zero -- the middle of a bipolar
        # swing, the bottom of a unipolar one -- and the offset moves it.
        out = polar(chosen).astype(np.float64) * depth + p.offset
        return {
            "out": np.asarray(out, dtype=np.float32),
            "sine": polar(sine),
            "triangle": polar(triangle),
            "saw": polar(saw),
            "square": polar(square),
            "random": polar(random_walk),
            "cycle": cycle,
        }


__all__ = ["LFO", "LFO_MANIFEST", "LFOParameters", "SHAPES"]
