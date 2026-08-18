"""The mixer everything ends at.

A rack needs somewhere for sound to go, and making that a module like any other
means it is patched like any other: drag a cable to it and the sound is out of
the speakers, with no separate idea of what an output is. Its channels are
plain audio inputs, its level and pan are plain parameters, and the two things
that make it special — that it is always there, and that its bus is always
connected — are the interface's business rather than the graph's.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


MASTER_CHANNELS = 8
"""Inputs the master mixer offers, which is more than most patches reach for."""

MASTER_OUTPUTS = ("left", "right", "sum")


class MasterMixerParameters(BaseModel):
    """Levels and placement for everything arriving at the output."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    levels: tuple[float, ...] = Field(default=(0.8,) * MASTER_CHANNELS)
    pans: tuple[float, ...] = Field(default=(0.0,) * MASTER_CHANNELS)
    master: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def sized(self) -> "MasterMixerParameters":
        if len(self.levels) != MASTER_CHANNELS:
            raise ValueError(f"levels must have {MASTER_CHANNELS} entries")
        if len(self.pans) != MASTER_CHANNELS:
            raise ValueError(f"pans must have {MASTER_CHANNELS} entries")
        for level in self.levels:
            if not -2.0 <= level <= 2.0:
                raise ValueError("a channel level must be between -2 and 2")
        for pan in self.pans:
            if not -1.0 <= pan <= 1.0:
                raise ValueError("a pan must be between -1 and 1")
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

    def set_level(self, channel: int, level: float) -> None:
        """Set one channel's level, validated as the whole set."""
        self._replace("levels", channel, level)

    def set_pan(self, channel: int, pan: float) -> None:
        """Place one channel between the speakers."""
        self._replace("pans", channel, pan)

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
        parameters = self.parameters
        for index in range(MASTER_CHANNELS):
            name = f"channel_{index + 1}"
            if name not in inputs:
                continue
            signal = np.asarray(
                block(name, inputs, frame_count), dtype=np.float64
            ) * parameters.levels[index]
            # Equal power, so moving a channel across does not change how loud
            # it is — only where it is.
            angle = (parameters.pans[index] + 1.0) * 0.25 * np.pi
            left += signal * float(np.cos(angle))
            right += signal * float(np.sin(angle))

        gain = parameters.master * np.sqrt(2.0)
        left *= gain
        right *= gain
        return {
            "left": np.asarray(left, dtype=np.float32),
            "right": np.asarray(right, dtype=np.float32),
            "sum": np.asarray((left + right) * 0.5, dtype=np.float32),
        }


__all__ = [
    "MASTER_CHANNELS",
    "MASTER_MIXER_MANIFEST",
    "MasterMixer",
    "MasterMixerParameters",
]
