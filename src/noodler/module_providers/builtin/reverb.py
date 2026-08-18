"""A modulateable mono late-field reverb."""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field

from noodler.module_providers import (
    AudioCvPolicy,
    ModuleManifest,
    PortDirection,
    PortManifest,
    SignalType,
)


FloatBlock = NDArray[np.float32]
OUTPUT_NAMES = ("wet_left", "wet_right", "left", "right")
MAX_PRE_DELAY_SECONDS = 0.25
COMB_DELAY_SECONDS = (0.0253, 0.0269, 0.0290, 0.0307, 0.0322, 0.0338)
ALLPASS_DELAY_SECONDS = (0.0126, 0.0100, 0.0077)
STEREO_SPREAD_SECONDS = 0.00052


class ReverbParameters(BaseModel):
    """Serializable, assignment-validated room controls."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mix: float = Field(default=0.28, ge=0.0, le=1.0)
    decay_seconds: float = Field(default=3.8, ge=0.1, le=30.0)
    damping: float = Field(default=0.45, ge=0.0, le=1.0)
    diffusion: float = Field(default=0.72, ge=0.0, le=1.0)
    pre_delay_ms: float = Field(default=18.0, ge=0.0, le=250.0)
    freeze: bool = False


def _port(
    port_id: str,
    name: str,
    direction: PortDirection,
    signal_type: SignalType,
    description: str,
) -> PortManifest:
    return PortManifest(
        id=port_id,
        name=name,
        direction=direction,
        signal_type=signal_type,
        description=description,
        audio_cv_policy=(
            AudioCvPolicy.ALLOW
            if signal_type in {SignalType.AUDIO, SignalType.CV}
            else AudioCvPolicy.WARN
        ),
    )


REVERB_MANIFEST = ModuleManifest(
    id="reverb",
    name="Space Reverb",
    category="Effects",
    description=(
        "A pre-delayed, damped feedback reverb with a diffused late field, "
        "voltage-controlled mix and decay, and a freezeable tail."
    ),
    ports=(
        _port(
            "audio",
            "Audio In",
            PortDirection.INPUT,
            SignalType.AUDIO,
            "Mono audio or audio-rate CV entering the reverb tank.",
        ),
        _port(
            "mix_cv",
            "Mix CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Bipolar offset added to the panel wet/dry mix.",
        ),
        _port(
            "decay_cv",
            "Decay CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Exponential tail-time modulation at one octave per unit.",
        ),
        _port(
            "freeze",
            "Freeze",
            PortDirection.INPUT,
            SignalType.GATE,
            "High gate closes the input and holds the current late field.",
        ),
        _port(
            "wet_left",
            "Wet Left",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Left decorrelated late field without the dry input.",
        ),
        _port(
            "wet_right",
            "Wet Right",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Right decorrelated late field without the dry input.",
        ),
        _port(
            "left",
            "Left",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Left equal-power blend of dry input and reverberated field.",
        ),
        _port(
            "right",
            "Right",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Right equal-power blend of dry input and reverberated field.",
        ),
    ),
)


class Reverb:
    """A compact Schroeder/Freeverb-family reverberator.

    Two banks of six mutually detuned, low-pass feedback combs build the
    decay. A small delay spread decorrelates the banks, and three serial
    all-pass stages per side turn those echoes into a dense stereo field.
    Buffers are prepared for the device sample rate before Core Audio starts.
    """

    manifest = REVERB_MANIFEST

    def __init__(self, parameters: ReverbParameters | None = None) -> None:
        self.parameters = parameters or ReverbParameters()
        self._sample_rate: float | None = None
        self._pre_delay = np.empty(0, dtype=np.float64)
        self._pre_delay_index = 0
        self._comb_buffers: list[list[NDArray[np.float64]]] = []
        self._comb_indices: list[list[int]] = []
        self._damping_state: list[NDArray[np.float64]] = []
        self._allpass_buffers: list[list[NDArray[np.float64]]] = []
        self._allpass_indices: list[list[int]] = []

    @property
    def sample_rate(self) -> float | None:
        return self._sample_rate

    def prepare(self, sample_rate: float, _block_size: int | None = None) -> None:
        """Allocate fixed delay lines before real-time rendering begins."""
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        sample_rate = float(sample_rate)
        if self._sample_rate == sample_rate and self._comb_buffers:
            return

        self._sample_rate = sample_rate
        pre_delay_size = max(1, math.ceil(MAX_PRE_DELAY_SECONDS * sample_rate) + 1)
        self._pre_delay = np.zeros(pre_delay_size, dtype=np.float64)
        self._pre_delay_index = 0
        channel_offsets = (0.0, STEREO_SPREAD_SECONDS)
        self._comb_buffers = [
            [
                np.zeros(
                    max(1, round((seconds + offset) * sample_rate)),
                    dtype=np.float64,
                )
                for seconds in COMB_DELAY_SECONDS
            ]
            for offset in channel_offsets
        ]
        self._comb_indices = [
            [0] * len(buffers) for buffers in self._comb_buffers
        ]
        self._damping_state = [
            np.zeros(len(buffers), dtype=np.float64)
            for buffers in self._comb_buffers
        ]
        self._allpass_buffers = [
            [
                np.zeros(
                    max(1, round((seconds + offset) * sample_rate)),
                    dtype=np.float64,
                )
                for seconds in ALLPASS_DELAY_SECONDS
            ]
            for offset in channel_offsets
        ]
        self._allpass_indices = [
            [0] * len(buffers) for buffers in self._allpass_buffers
        ]

    def reset(self) -> None:
        """Clear the room while preserving its prepared allocation."""
        self._pre_delay.fill(0.0)
        self._pre_delay_index = 0
        for channel in self._comb_buffers:
            for buffer in channel:
                buffer.fill(0.0)
        self._comb_indices = [
            [0] * len(buffers) for buffers in self._comb_buffers
        ]
        for state in self._damping_state:
            state.fill(0.0)
        for channel in self._allpass_buffers:
            for buffer in channel:
                buffer.fill(0.0)
        self._allpass_indices = [
            [0] * len(buffers) for buffers in self._allpass_buffers
        ]

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        """Render separate wet and equal-power wet/dry output blocks."""
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self._sample_rate != float(sample_rate) or not self._comb_buffers:
            self.prepare(sample_rate)
        if frame_count == 0:
            return {
                name: np.empty(0, dtype=np.float32)
                for name in OUTPUT_NAMES
            }

        inputs = inputs or {}
        dry = self._optional_block("audio", inputs, frame_count)
        mix_cv = self._optional_block("mix_cv", inputs, frame_count)
        decay_cv = self._optional_block("decay_cv", inputs, frame_count)
        freeze_gate = self._optional_block("freeze", inputs, frame_count)
        decay = np.clip(
            self.parameters.decay_seconds
            * np.exp2(np.clip(decay_cv, -8.0, 8.0)),
            0.1,
            30.0,
        )
        feedback = tuple(
            tuple(
                np.power(
                    10.0,
                    -3.0 * (len(buffer) / float(sample_rate)) / decay,
                )
                for buffer in channel
            )
            for channel in self._comb_buffers
        )
        late = np.empty((frame_count, 2), dtype=np.float64)
        pre_delay_samples = min(
            len(self._pre_delay) - 1,
            round(self.parameters.pre_delay_ms * sample_rate / 1_000.0),
        )
        damping = 0.05 + 0.90 * self.parameters.damping
        diffusion = 0.25 + 0.55 * self.parameters.diffusion

        for sample in range(frame_count):
            input_sample = float(dry[sample])
            if pre_delay_samples:
                read_index = (
                    self._pre_delay_index - pre_delay_samples
                ) % len(self._pre_delay)
                tank_input = float(self._pre_delay[read_index])
            else:
                tank_input = input_sample
            self._pre_delay[self._pre_delay_index] = input_sample
            self._pre_delay_index = (
                self._pre_delay_index + 1
            ) % len(self._pre_delay)

            frozen = self.parameters.freeze or freeze_gate[sample] > 0.0
            injection = 0.0 if frozen else tank_input * 0.24
            for channel in range(2):
                comb_sum = 0.0
                comb_buffers = self._comb_buffers[channel]
                for lane, buffer in enumerate(comb_buffers):
                    index = self._comb_indices[channel][lane]
                    delayed = float(buffer[index])
                    if frozen:
                        filtered = delayed
                        gain = 1.0
                    else:
                        filtered = (
                            delayed * (1.0 - damping)
                            + self._damping_state[channel][lane] * damping
                        )
                        gain = float(feedback[channel][lane][sample])
                    self._damping_state[channel][lane] = filtered
                    buffer[index] = injection + filtered * gain
                    self._comb_indices[channel][lane] = (index + 1) % len(buffer)
                    comb_sum += delayed

                field = comb_sum / len(comb_buffers)
                for stage, buffer in enumerate(self._allpass_buffers[channel]):
                    index = self._allpass_indices[channel][stage]
                    delayed = float(buffer[index])
                    output = delayed - field
                    buffer[index] = field + delayed * diffusion
                    self._allpass_indices[channel][stage] = (
                        index + 1
                    ) % len(buffer)
                    field = output
                late[sample, channel] = field

        wet = np.tanh(late * 2.2)
        mix = np.clip(self.parameters.mix + mix_cv, 0.0, 1.0)
        dry_gain = np.cos(mix * np.pi * 0.5)
        wet_gain = np.sin(mix * np.pi * 0.5)
        left = dry * dry_gain + wet[:, 0] * wet_gain
        right = dry * dry_gain + wet[:, 1] * wet_gain
        return {
            "wet_left": np.asarray(wet[:, 0], dtype=np.float32),
            "wet_right": np.asarray(wet[:, 1], dtype=np.float32),
            "left": np.asarray(left, dtype=np.float32),
            "right": np.asarray(right, dtype=np.float32),
        }

    @staticmethod
    def _optional_block(
        name: str,
        inputs: Mapping[str, ArrayLike],
        frame_count: int,
    ) -> NDArray[np.float64]:
        if name not in inputs:
            return np.zeros(frame_count, dtype=np.float64)
        value = np.asarray(inputs[name], dtype=np.float64)
        if value.ndim == 0:
            return np.full(frame_count, float(value), dtype=np.float64)
        if value.shape != (frame_count,):
            raise ValueError(
                f"{name} must be scalar or have shape ({frame_count},), "
                f"got {value.shape}"
            )
        return value


__all__ = [
    "REVERB_MANIFEST",
    "Reverb",
    "ReverbParameters",
]
