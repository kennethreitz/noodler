"""A voltage-controlled, freezeable mono echo delay."""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


DELAY_OUTPUTS = ("output", "wet")
MAX_DELAY_SECONDS = 4.0


class EchoDelayParameters(BaseModel):
    """Serializable echo time, feedback, tone, and mix controls."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    time_seconds: float = Field(default=0.375, ge=0.001, le=MAX_DELAY_SECONDS)
    feedback: float = Field(default=0.42, ge=-0.98, le=0.98)
    mix: float = Field(default=0.35, ge=0.0, le=1.0)
    damping: float = Field(default=0.45, ge=0.0, le=1.0)
    drive: float = Field(default=1.0, ge=0.25, le=8.0)
    freeze: bool = False


ECHO_DELAY_MANIFEST = ModuleManifest(
    id="echo_delay",
    name="Echo / Delay",
    category="Effects",
    description="A four-second voltage-controlled echo with bipolar feedback, damping, drive, and freeze.",
    ports=(
        port("audio", "Audio In", PortDirection.INPUT, SignalType.AUDIO, "Signal entering the delay line."),
        port("time_cv", "Time CV", PortDirection.INPUT, SignalType.CV, "One-octave-per-unit delay-time modulation."),
        port("feedback_cv", "Feedback CV", PortDirection.INPUT, SignalType.CV, "Bipolar feedback offset."),
        port("mix_cv", "Mix CV", PortDirection.INPUT, SignalType.CV, "Bipolar wet/dry offset."),
        port("freeze", "Freeze", PortDirection.INPUT, SignalType.GATE, "Hold the delay memory without new input."),
        port("output", "Out", PortDirection.OUTPUT, SignalType.AUDIO, "Equal-power wet/dry output."),
        port("wet", "Wet", PortDirection.OUTPUT, SignalType.AUDIO, "Delay-line output without dry signal."),
    ),
)


class EchoDelay:
    """Read a modulated fractional delay line with damped feedback."""

    manifest = ECHO_DELAY_MANIFEST

    def __init__(self, parameters: EchoDelayParameters | None = None) -> None:
        self.parameters = parameters or EchoDelayParameters()
        self._sample_rate: float | None = None
        self._buffer = np.empty(0, dtype=np.float64)
        self._write_index = 0
        self._damping_state = 0.0

    @property
    def sample_rate(self) -> float | None:
        return self._sample_rate

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self._sample_rate == float(sample_rate) and self._buffer.size:
            return
        self._sample_rate = float(sample_rate)
        self._buffer = np.zeros(
            math.ceil(MAX_DELAY_SECONDS * sample_rate) + 2,
            dtype=np.float64,
        )
        self._write_index = 0
        self._damping_state = 0.0

    def reset(self) -> None:
        self._buffer.fill(0.0)
        self._write_index = 0
        self._damping_state = 0.0

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
            return empty_outputs(DELAY_OUTPUTS)
        if self._sample_rate != float(sample_rate) or not self._buffer.size:
            self.prepare(sample_rate)
        inputs = inputs or {}
        audio = block("audio", inputs, frame_count)
        time_cv = block("time_cv", inputs, frame_count)
        feedback_cv = block("feedback_cv", inputs, frame_count)
        mix_cv = block("mix_cv", inputs, frame_count)
        freeze = block("freeze", inputs, frame_count)
        write_index = self._write_index
        damping_state = self._damping_state
        buffer = self._buffer
        size = len(buffer)
        # Everything the loop used to recompute per sample, computed once for
        # the block. Four np.clip calls per sample cost far more than the
        # arithmetic they were guarding.
        seconds = np.clip(
            self.parameters.time_seconds
            * np.exp2(np.clip(time_cv, -8.0, 8.0)),
            0.001,
            MAX_DELAY_SECONDS,
        )
        delay_samples = seconds * sample_rate
        frozen = np.logical_or(bool(self.parameters.freeze), freeze > 0.0)
        feedback = np.where(
            frozen,
            0.999,
            np.clip(self.parameters.feedback + feedback_cv, -0.98, 0.98),
        )
        injection = np.where(frozen, 0.0, np.asarray(audio, dtype=np.float64))
        mix = np.clip(self.parameters.mix + mix_cv, 0.0, 1.0)
        dry_gain = np.cos(mix * np.pi * 0.5)
        wet_gain = np.sin(mix * np.pi * 0.5)
        damping = 0.02 + 0.96 * self.parameters.damping
        coefficient = 1.0 - damping
        drive = self.parameters.drive

        if float(np.min(delay_samples)) >= frame_count:
            # The read is entirely behind this block's writes, so the whole
            # delay line can be gathered at once. Only the one-pole damping
            # stays sequential, and it is a bare float loop.
            offsets = np.arange(frame_count, dtype=np.float64)
            positions = (write_index + offsets - delay_samples) % size
            lower = positions.astype(np.int64)
            fraction = positions - lower
            delayed = (
                buffer[lower] * (1.0 - fraction)
                + buffer[(lower + 1) % size] * fraction
            )
            damped = np.empty(frame_count, dtype=np.float64)
            state = damping_state
            for sample in range(frame_count):
                state += coefficient * (delayed[sample] - state)
                damped[sample] = state
            damping_state = state
            written = np.tanh((injection + damped * feedback) * drive)
            indices = (write_index + np.arange(frame_count)) % size
            buffer[indices] = written
            write_index = int((write_index + frame_count) % size)
            wet = delayed
            output = np.asarray(audio, dtype=np.float64) * dry_gain + delayed * wet_gain
        else:
            wet = np.empty(frame_count, dtype=np.float64)
            output = np.empty(frame_count, dtype=np.float64)
            for sample in range(frame_count):
                read_position = (write_index - delay_samples[sample]) % size
                read_0 = int(math.floor(read_position))
                fraction = read_position - read_0
                delayed = (
                    float(buffer[read_0]) * (1.0 - fraction)
                    + float(buffer[(read_0 + 1) % size]) * fraction
                )
                damping_state += coefficient * (delayed - damping_state)
                buffer[write_index] = math.tanh(
                    (injection[sample] + damping_state * feedback[sample]) * drive
                )
                write_index = (write_index + 1) % size
                wet[sample] = delayed
                output[sample] = (
                    float(audio[sample]) * dry_gain[sample]
                    + delayed * wet_gain[sample]
                )
        self._write_index = write_index
        self._damping_state = damping_state
        return {
            "output": np.asarray(output, dtype=np.float32),
            "wet": np.asarray(wet, dtype=np.float32),
        }


__all__ = [
    "ECHO_DELAY_MANIFEST",
    "EchoDelay",
    "EchoDelayParameters",
    "MAX_DELAY_SECONDS",
]
