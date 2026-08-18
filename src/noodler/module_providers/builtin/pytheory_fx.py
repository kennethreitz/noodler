"""PyTheory's effects, streamed.

PyTheory colours a rendered part with a chorus, a phaser, a tremolo, an
overdriven amp, tape saturation and a guitar cabinet -- each written for a
whole buffer at once. This module runs the same algorithms a block at a time:
the LFOs keep their phase between blocks, the delay line and the filters keep
their state, and the waveshapers, which have no state, are the same functions.
One module, one word to say which effect it is, and the two or three knobs
that effect has.
"""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


EFFECTS: tuple[str, ...] = ("chorus", "phaser", "tremolo", "distortion", "saturation", "cabinet")
DEFAULT_EFFECT = "chorus"
FX_OUTPUTS = ("audio",)

CHORUS_BASE_DELAY = 0.007
"""Seven milliseconds, as PyTheory's chorus is: the Juno's, the CE-1's."""
PHASER_STAGES = 4
PHASER_LOW_HZ = 200.0
PHASER_SPAN = 20.0
"""The phaser sweeps its notches from 200 Hz up by a factor of twenty, on a log
scale, as PyTheory's does."""


class PyTheoryFXParameters(BaseModel):
    """Which effect, how much, and the knobs the effect has.

    ``rate_hz`` is the LFO of the chorus, phaser and tremolo -- and takes the
    clock, since it is a rate. ``depth`` is chorus depth in milliseconds of
    wobble, tremolo depth, or the amount of saturation; ``drive`` is the
    amp's; ``brightness`` is the cabinet's.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    effect: str = DEFAULT_EFFECT
    mix: float = Field(default=0.5, ge=0.0, le=1.0)
    rate_hz: float = Field(default=1.5, ge=0.05, le=20.0)
    depth: float = Field(default=0.5, ge=0.0, le=1.0)
    drive: float = Field(default=2.0, ge=0.1, le=20.0)
    brightness: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def known(self) -> "PyTheoryFXParameters":
        if self.effect not in EFFECTS:
            object.__setattr__(self, "effect", DEFAULT_EFFECT)
        return self


PYTHEORY_FX_MANIFEST = ModuleManifest(
    id="pytheory_fx",
    name="PyTheory FX",
    category="Effects",
    description=(
        "PyTheory's effects, one at a time: chorus, phaser, tremolo, an "
        "overdriven amp, tape saturation, or a guitar cabinet -- the same "
        "algorithms the library colours its parts with, streamed."
    ),
    ports=(
        port("audio", "Audio In", PortDirection.INPUT, SignalType.AUDIO, "The signal to colour."),
        port("rate_cv", "Rate CV", PortDirection.INPUT, SignalType.CV, "Added to the LFO rate, in octaves."),
        port("depth_cv", "Depth CV", PortDirection.INPUT, SignalType.CV, "Added to depth or drive, plus or minus one."),
        port("audio_out", "Out", PortDirection.OUTPUT, SignalType.AUDIO, "The coloured signal."),
    ),
)


def _biquad_allpass(hz: float, sample_rate: float) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """PyTheory's phaser allpass: a biquad with Q of a half, for a wide sweep."""
    w0 = 2.0 * math.pi * hz / sample_rate
    alpha = math.sin(w0) / 2.0
    cos_w0 = math.cos(w0)
    a0 = 1.0 + alpha
    b = np.array([(1.0 - alpha) / a0, (-2.0 * cos_w0) / a0, (1.0 + alpha) / a0])
    a = np.array([1.0, (-2.0 * cos_w0) / a0, (1.0 - alpha) / a0])
    return b, a


def _butter(order: int, cutoff, kind: str, sample_rate: float):
    from scipy.signal import butter

    return butter(order, cutoff, btype=kind, fs=sample_rate)


class PyTheoryFX:
    """Colour a signal with one of PyTheory's effects."""

    manifest = PYTHEORY_FX_MANIFEST

    def __init__(self, parameters: PyTheoryFXParameters | None = None) -> None:
        self.parameters = parameters or PyTheoryFXParameters()
        self._sample_rate = 48_000.0
        self._phase = 0.0
        self._delay = np.zeros(1, dtype=np.float64)
        self._delay_index = 0
        self._phaser_state: list[NDArray[np.float64]] = []
        self._cabinet: dict[str, object] = {}
        self._cabinet_for: tuple[float, float] | None = None

    def choices_for(self, field: str) -> tuple[str, ...]:
        return EFFECTS if field == "effect" else ()

    @property
    def label(self) -> str:
        return self.parameters.effect.upper()

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._sample_rate = float(sample_rate)
        self._delay = np.zeros(int(0.05 * self._sample_rate) + 4, dtype=np.float64)
        self._delay_index = 0
        self._phase = 0.0
        self._phaser_state = [np.zeros(2, dtype=np.float64) for _ in range(PHASER_STAGES)]
        self._cabinet_for = None

    # ---- the effects, one block each -------------------------------------

    def _lfo(self, frame_count: int, sample_rate: float, rate_cv: NDArray[np.float64]) -> NDArray[np.float64]:
        """The LFO's phase for every sample of the block, in turns, carried on."""
        rate = self.parameters.rate_hz * np.exp2(np.clip(rate_cv, -4.0, 4.0))
        phase = self._phase + np.cumsum(rate / sample_rate)
        self._phase = float(phase[-1]) % 1.0
        return phase

    def _chorus(self, dry, phase, depth, sample_rate):
        # A modulated delay of seven milliseconds plus up to `depth` of wobble,
        # read from a ring buffer with linear interpolation.
        wobble = CHORUS_BASE_DELAY + 0.006 * depth * np.sin(2.0 * math.pi * phase)
        delay_samples = wobble * sample_rate
        size = self._delay.size
        indices = (self._delay_index + np.arange(dry.size)) % size
        self._delay[indices] = dry
        read = indices - delay_samples
        lower = np.floor(read).astype(np.int64)
        fraction = read - lower
        wet = self._delay[lower % size] * (1.0 - fraction) + self._delay[(lower + 1) % size] * fraction
        self._delay_index = int((self._delay_index + dry.size) % size)
        return wet

    def _phaser(self, dry, phase, sample_rate):
        from scipy.signal import lfilter

        # Four allpass stages whose centre sweeps 200 Hz to 4 kHz on a log
        # scale, coefficients set from the middle of each 128-sample slice --
        # PyTheory uses 64; the sweep is slow enough that half the updates
        # sound the same and cost half as much.
        wet = dry.astype(np.float64).copy()
        centre = PHASER_LOW_HZ * PHASER_SPAN ** (0.5 + 0.5 * np.sin(2.0 * math.pi * phase))
        for stage in range(PHASER_STAGES):
            out = np.empty_like(wet)
            position = 0
            while position < wet.size:
                end = min(position + 128, wet.size)
                b, a = _biquad_allpass(float(centre[(position + end) // 2]), sample_rate)
                out[position:end], self._phaser_state[stage] = lfilter(
                    b, a, wet[position:end], zi=self._phaser_state[stage]
                )
                position = end
            wet = out
        return wet

    def _cabinet_filters(self, brightness: float, sample_rate: float):
        key = (round(brightness, 3), sample_rate)
        if self._cabinet_for != key:
            cutoff = 3_500.0 + brightness * 2_000.0
            self._cabinet = {
                "high": _butter(2, 80.0, "high", sample_rate),
                "low": _butter(3, min(cutoff, sample_rate * 0.45), "low", sample_rate),
                "band": _butter(2, [1_700.0, 3_300.0], "band", sample_rate),
                "zi": {},
            }
            self._cabinet_for = key
        return self._cabinet

    def _cabinet_run(self, dry, brightness, sample_rate):
        from scipy.signal import lfilter, lfilter_zi

        filters = self._cabinet_filters(brightness, sample_rate)
        signal = dry.astype(np.float64)
        for name in ("high", "low"):
            b, a = filters[name]
            zi = filters["zi"].get(name)
            if zi is None:
                zi = lfilter_zi(b, a) * 0.0
            signal, filters["zi"][name] = lfilter(b, a, signal, zi=zi)
        b, a = filters["band"]
        zi = filters["zi"].get("band")
        if zi is None:
            zi = lfilter_zi(b, a) * 0.0
        presence, filters["zi"]["band"] = lfilter(b, a, signal, zi=zi)
        return signal + presence * 0.3

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
            return empty_outputs(FX_OUTPUTS)
        if self._sample_rate != float(sample_rate) or self._delay.size < 8:
            self.prepare(sample_rate)
        inputs = inputs or {}
        dry = np.asarray(block("audio", inputs, frame_count), dtype=np.float64)
        rate_cv = np.asarray(block("rate_cv", inputs, frame_count), dtype=np.float64)
        depth_cv = np.asarray(block("depth_cv", inputs, frame_count), dtype=np.float64)
        parameters = self.parameters
        depth = float(np.clip(parameters.depth + float(np.mean(depth_cv)), 0.0, 1.0))
        mix = parameters.mix
        effect = parameters.effect

        if effect == "chorus":
            phase = self._lfo(frame_count, sample_rate, rate_cv)
            wet = self._chorus(dry, phase, depth, sample_rate)
            out = dry * (1.0 - mix * 0.5) + wet * mix * 0.5
        elif effect == "phaser":
            phase = self._lfo(frame_count, sample_rate, rate_cv)
            wet = self._phaser(dry, phase, sample_rate)
            out = dry * (1.0 - mix) + wet * mix
        elif effect == "tremolo":
            phase = self._lfo(frame_count, sample_rate, rate_cv)
            lfo = 1.0 - depth * 0.5 * (1.0 + np.sin(2.0 * math.pi * phase))
            out = dry * (1.0 - mix) + dry * lfo * mix
        elif effect == "distortion":
            drive = float(np.clip(parameters.drive * (1.0 + float(np.mean(depth_cv))), 0.1, 40.0))
            stage1 = np.tanh(dry * drive)
            stage2 = np.tanh(stage1 * drive * 0.5)
            if drive > 3.0:
                driven = np.where(stage2 > 0.0, np.tanh(stage2 * 1.5), np.tanh(stage2 * 1.2))
            else:
                driven = stage2
            out = dry * (1.0 - mix) + driven * mix
        elif effect == "saturation":
            amount = depth
            driven = (dry + amount * dry * dry) / (1.0 + amount)
            out = dry * (1.0 - mix) + np.clip(driven, -1.0, 1.0) * mix
        else:  # cabinet
            wet = self._cabinet_run(dry, parameters.brightness, sample_rate)
            out = dry * (1.0 - mix) + wet * mix
        return {"audio_out": np.asarray(out, dtype=np.float32)}


__all__ = ["EFFECTS", "PYTHEORY_FX_MANIFEST", "PyTheoryFX", "PyTheoryFXParameters"]
