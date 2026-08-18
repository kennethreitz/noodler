"""The mixer everything ends at.

A rack needs somewhere for sound to go, and making that a module like any other
means it is patched like any other: drag a cable to it and the sound is out of
the speakers, with no separate idea of what an output is. Its channels are
plain audio inputs, its level and pan are plain parameters, and the two things
that make it special — that it is always there, and that its bus is always
connected — are the interface's business rather than the graph's.

It also has two sends. A reverb has one input, and the third voice that wants
to be in the room has nowhere to go without a mixer in front of it — which is
what a send is. Each channel has an amount for send A and for send B, taken
after its level, and the two buses come out as jacks: patch A to a reverb and
the reverb's outputs back into two channels, and the room is shared by
whatever is turned up into it. The return is a channel like any other, so it
can be levelled and panned like any other.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


MASTER_CHANNELS = 8
"""Inputs the master mixer offers, which is more than most patches reach for."""

MASTER_OUTPUTS = ("left", "right", "sum", "send_a", "send_b")
SENDS = ("a", "b")


class MasterMixerParameters(BaseModel):
    """Levels and placement for everything arriving at the output."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    levels: tuple[float, ...] = Field(default=(0.8,) * MASTER_CHANNELS)
    pans: tuple[float, ...] = Field(default=(0.0,) * MASTER_CHANNELS)
    sends_a: tuple[float, ...] = Field(default=(0.0,) * MASTER_CHANNELS)
    """How much of each channel, after its level, goes to send A."""
    sends_b: tuple[float, ...] = Field(default=(0.0,) * MASTER_CHANNELS)
    master: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def sized(self) -> "MasterMixerParameters":
        for name in ("levels", "pans", "sends_a", "sends_b"):
            if len(getattr(self, name)) != MASTER_CHANNELS:
                raise ValueError(f"{name} must have {MASTER_CHANNELS} entries")
        for level in self.levels:
            if not -2.0 <= level <= 2.0:
                raise ValueError("a channel level must be between -2 and 2")
        for pan in self.pans:
            if not -1.0 <= pan <= 1.0:
                raise ValueError("a pan must be between -1 and 1")
        for amount in (*self.sends_a, *self.sends_b):
            if not 0.0 <= amount <= 1.0:
                raise ValueError("a send must be between 0 and 1")
        return self


MASTER_MIXER_MANIFEST = ModuleManifest(
    id="master_mixer",
    name="Master Mixer",
    category="Utilities",
    description=(
        "Where the rack comes out. Patch anything into a channel and it is "
        "audible; the bus reaches the system output on its own."
    ),
    ports=(
        *(
            port(
                f"channel_{index}",
                f"Ch {index}",
                PortDirection.INPUT,
                SignalType.AUDIO,
                f"Channel {index}, summed into the output bus.",
            )
            for index in range(1, MASTER_CHANNELS + 1)
        ),
        port("send_a", "Send A", PortDirection.OUTPUT, SignalType.AUDIO, "Every channel's send A, summed. Patch it to an effect."),
        port("send_b", "Send B", PortDirection.OUTPUT, SignalType.AUDIO, "Every channel's send B, summed."),
        port("left", "Left", PortDirection.OUTPUT, SignalType.AUDIO, "Left of the stereo bus."),
        port("right", "Right", PortDirection.OUTPUT, SignalType.AUDIO, "Right of the stereo bus."),
        port("sum", "Sum", PortDirection.OUTPUT, SignalType.AUDIO, "Mono fold-down, for metering or feedback."),
    ),
)


class MasterMixer:
    """Sum every patched channel into one stereo bus."""

    manifest = MASTER_MIXER_MANIFEST

    def __init__(self, parameters: MasterMixerParameters | None = None) -> None:
        self.parameters = parameters or MasterMixerParameters()
        self.channel_peaks: tuple[float, ...] = (0.0,) * MASTER_CHANNELS
        """Each channel's post-fader peak from the last block, for its meter."""

    def set_level(self, channel: int, level: float) -> None:
        """Set one channel's level, validated as the whole set."""
        self._replace("levels", channel, level)

    def set_pan(self, channel: int, pan: float) -> None:
        """Place one channel between the speakers."""
        self._replace("pans", channel, pan)

    def set_send(self, bus: str, channel: int, amount: float) -> None:
        """How much of one channel goes to send A or B."""
        if bus not in SENDS:
            raise ValueError(f"bus must be one of {SENDS}")
        self._replace(f"sends_{bus}", channel, amount)

    def _replace(self, field: str, channel: int, value: float) -> None:
        if not 1 <= channel <= MASTER_CHANNELS:
            raise ValueError(f"channel must be between 1 and {MASTER_CHANNELS}")
        current = list(getattr(self.parameters, field))
        current[channel - 1] = float(value)
        setattr(self.parameters, field, tuple(current))

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
            return empty_outputs(MASTER_OUTPUTS)

        inputs = inputs or {}
        left = np.zeros(frame_count, dtype=np.float64)
        right = np.zeros(frame_count, dtype=np.float64)
        send_a = np.zeros(frame_count, dtype=np.float64)
        send_b = np.zeros(frame_count, dtype=np.float64)
        parameters = self.parameters
        peaks = [0.0] * MASTER_CHANNELS
        for index in range(MASTER_CHANNELS):
            name = f"channel_{index + 1}"
            if name not in inputs:
                continue
            signal = np.asarray(
                block(name, inputs, frame_count), dtype=np.float64
            ) * parameters.levels[index]
            peaks[index] = float(np.max(np.abs(signal), initial=0.0))
            # Equal power, so moving a channel across does not change how loud
            # it is — only where it is.
            angle = (parameters.pans[index] + 1.0) * 0.25 * np.pi
            left += signal * float(np.cos(angle))
            right += signal * float(np.sin(angle))
            # Sends are post-fader and pre-pan: turning a channel down takes it
            # out of the room too, and the room decides where it sits.
            if parameters.sends_a[index]:
                send_a += signal * parameters.sends_a[index]
            if parameters.sends_b[index]:
                send_b += signal * parameters.sends_b[index]

        self.channel_peaks = tuple(peaks)
        gain = parameters.master * np.sqrt(2.0)
        left *= gain
        right *= gain
        return {
            "left": np.asarray(left, dtype=np.float32),
            "right": np.asarray(right, dtype=np.float32),
            "sum": np.asarray((left + right) * 0.5, dtype=np.float32),
            "send_a": np.asarray(send_a, dtype=np.float32),
            "send_b": np.asarray(send_b, dtype=np.float32),
        }


__all__ = [
    "MASTER_CHANNELS",
    "SENDS",
    "MASTER_MIXER_MANIFEST",
    "MasterMixer",
    "MasterMixerParameters",
]
