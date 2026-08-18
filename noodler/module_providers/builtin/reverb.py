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
DC_BLOCK_HZ = 6.0
"""Corner of the high-pass on the way into the tank. Below anything musical."""

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
        self._dc_last_in = 0.0
        self._dc_last_out = 0.0

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
        self._dc_last_in = 0.0
        self._dc_last_out = 0.0

    def _block_dc(self, dry: NDArray[np.float64], sample_rate: float) -> NDArray[np.float64]:
        """Take the offset out of what enters the tank.

        The combs feed back at very nearly unity when the decay is long, and at
        DC there is no damping to lose it, so an input with any offset at all
        -- a slightly asymmetric waveform, one of PyTheory's renders, a source
        sitting a hundredth above zero -- integrates until the soft clip pins
        the whole tank at a rail. Eleven seconds of decay turned an offset of
        0.009 into a constant 0.71 on both sides. A one-pole high-pass at a few
        hertz costs nothing audible and removes the failure entirely.
        """
        radius = 1.0 - 2.0 * np.pi * DC_BLOCK_HZ / sample_rate
        samples = dry.tolist()
        last_in = self._dc_last_in
        last_out = self._dc_last_out
        blocked = [0.0] * len(samples)
        for index, sample in enumerate(samples):
            last_out = sample - last_in + radius * last_out
            last_in = sample
            blocked[index] = last_out
        self._dc_last_in = last_in
        self._dc_last_out = last_out
        return np.asarray(blocked, dtype=np.float64)

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
        # The dry path keeps whatever offset it had; only the tank is protected.
        tank_input = self._block_dc(np.asarray(dry, dtype=np.float64), sample_rate)
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
        # Reading a numpy scalar costs far more than the float arithmetic
        # around it, and this loop reads several per sample per comb lane.
        # Handing the loop plain Python lists is the whole optimisation.
        feedback_lanes = tuple(
            tuple(lane.tolist() for lane in channel) for channel in feedback
        )
        dry_samples = tank_input.tolist()
        freeze_samples = np.asarray(freeze_gate, dtype=np.float64).tolist()
        late = np.empty((frame_count, 2), dtype=np.float64)
        pre_delay_samples = min(
            len(self._pre_delay) - 1,
            round(self.parameters.pre_delay_ms * sample_rate / 1_000.0),
        )
        damping = 0.05 + 0.90 * self.parameters.damping
        diffusion = 0.25 + 0.55 * self.parameters.diffusion

        shortest = min(
            min(len(buffer) for buffer in channel)
            for channel in (*self._comb_buffers, *self._allpass_buffers)
        )
        steady_freeze = bool(np.all(freeze_gate > 0.0)) or not bool(
            np.any(freeze_gate > 0.0)
        )
        pre_delay_ready = pre_delay_samples == 0 or pre_delay_samples >= frame_count
        if frame_count <= shortest and steady_freeze and pre_delay_ready:
            late = self._render_tank(
                frame_count,
                tank_input,
                feedback,
                pre_delay_samples,
                damping,
                diffusion,
                bool(self.parameters.freeze or np.any(freeze_gate > 0.0)),
            )
            return self._blend(dry, late, mix_cv)

        for sample in range(frame_count):
            input_sample = dry_samples[sample]
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

            frozen = self.parameters.freeze or freeze_samples[sample] > 0.0
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
                        gain = feedback_lanes[channel][lane][sample]
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

        return self._blend(dry, late, mix_cv)

    def _blend(self, dry, late, mix_cv) -> dict[str, FloatBlock]:
        """Fold the tank back in against the dry signal."""
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

    def _render_tank(
        self,
        frame_count: int,
        dry: NDArray[np.float64],
        feedback,
        pre_delay_samples: int,
        damping: float,
        diffusion: float,
        frozen: bool,
    ) -> NDArray[np.float64]:
        """Run the whole tank a block at a time.

        Every delay in the network is longer than a block, so each read is
        entirely behind this block's writes: nothing a comb or an allpass reads
        was written by the same block. That makes all of it a gather, an
        arithmetic pass and a scatter, and leaves only the damping one-pole
        genuinely sequential — as a bare float loop, with no numpy in it.
        """
        offsets = np.arange(frame_count)
        if pre_delay_samples:
            size = len(self._pre_delay)
            read = (self._pre_delay_index - pre_delay_samples + offsets) % size
            tank = self._pre_delay[read].copy()
            write = (self._pre_delay_index + offsets) % size
            self._pre_delay[write] = dry
            self._pre_delay_index = int((self._pre_delay_index + frame_count) % size)
        else:
            tank = dry.copy()

        injection = np.zeros(frame_count) if frozen else tank * 0.24
        late = np.empty((frame_count, 2), dtype=np.float64)
        for channel in range(2):
            comb_sum = np.zeros(frame_count, dtype=np.float64)
            for lane, buffer in enumerate(self._comb_buffers[channel]):
                size = len(buffer)
                index = self._comb_indices[channel][lane]
                positions = (index + offsets) % size
                delayed = buffer[positions].copy()

                if frozen:
                    filtered = delayed
                    self._damping_state[channel][lane] = float(delayed[-1])
                    buffer[positions] = injection + filtered
                else:
                    state = float(self._damping_state[channel][lane])
                    heard = delayed.tolist()
                    filtered_values = [0.0] * frame_count
                    for sample in range(frame_count):
                        state = heard[sample] * (1.0 - damping) + state * damping
                        filtered_values[sample] = state
                    self._damping_state[channel][lane] = state
                    filtered = np.asarray(filtered_values, dtype=np.float64)
                    buffer[positions] = injection + filtered * feedback[channel][lane]

                self._comb_indices[channel][lane] = int((index + frame_count) % size)
                comb_sum += delayed

            field = comb_sum / len(self._comb_buffers[channel])
            for stage, buffer in enumerate(self._allpass_buffers[channel]):
                size = len(buffer)
                index = self._allpass_indices[channel][stage]
                positions = (index + offsets) % size
                delayed = buffer[positions].copy()
                buffer[positions] = field + delayed * diffusion
                self._allpass_indices[channel][stage] = int(
                    (index + frame_count) % size
                )
                field = delayed - field
            late[:, channel] = field
        return late

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
