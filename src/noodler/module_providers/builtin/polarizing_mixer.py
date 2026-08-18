"""A configurable n-channel polarizing mixer."""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noodler.module_providers import (
    AudioCvPolicy,
    ModuleManifest,
    PortDirection,
    PortManifest,
    SignalType,
)


FloatBlock = NDArray[np.float32]
MAX_CHANNELS = 64


class PolarizingMixerParameters(BaseModel):
    """Serializable channel count and attenuverter positions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    channels: int = Field(default=4, ge=1, le=MAX_CHANNELS)
    gains: tuple[float, ...] = ()

    @model_validator(mode="after")
    def gains_match_channel_count(self) -> "PolarizingMixerParameters":
        if not self.gains:
            object.__setattr__(self, "gains", (0.0,) * self.channels)
        elif len(self.gains) != self.channels:
            raise ValueError("gains must contain exactly one value per channel")
        if any(gain < -1.0 or gain > 1.0 for gain in self.gains):
            raise ValueError("mixer gains must be between -1 and 1")
        return self

    def with_gain(self, channel: int, gain: float) -> "PolarizingMixerParameters":
        """Return a validated copy with one one-based channel gain changed."""
        if not 1 <= channel <= self.channels:
            raise IndexError(f"channel must be between 1 and {self.channels}")
        gains = list(self.gains)
        gains[channel - 1] = gain
        return type(self)(channels=self.channels, gains=tuple(gains))


def polarizing_mixer_manifest(channels: int) -> ModuleManifest:
    """Build an instance-shaped manifest for a mixer channel count."""
    validated_channels = PolarizingMixerParameters(channels=channels).channels
    inputs = tuple(
        PortManifest(
            id=f"input_{channel}",
            name=f"Input {channel}",
            direction=PortDirection.INPUT,
            signal_type=SignalType.CV,
            description=f"Bipolar audio/CV input for channel {channel}.",
            audio_cv_policy=AudioCvPolicy.ALLOW,
        )
        for channel in range(1, validated_channels + 1)
    )
    output = PortManifest(
        id="output",
        name="Sum",
        direction=PortDirection.OUTPUT,
        signal_type=SignalType.CV,
        description="Unclipped sum of all attenuverted channel inputs.",
        audio_cv_policy=AudioCvPolicy.ALLOW,
    )
    return ModuleManifest(
        id="polarizing_mixer",
        name=f"{validated_channels}-Channel Polarizing Mixer",
        category="Utilities",
        description="A configurable audio/CV mixer with a bipolar gain per channel.",
        ports=(*inputs, output),
    )


POLARIZING_MIXER_MANIFEST = polarizing_mixer_manifest(4)


class PolarizingMixer:
    """Scale, invert, and sum an arbitrary number of audio/CV blocks."""

    def __init__(self, parameters: PolarizingMixerParameters | None = None) -> None:
        self.parameters = parameters or PolarizingMixerParameters()
        self.manifest = polarizing_mixer_manifest(self.parameters.channels)

    def set_gain(self, channel: int, gain: float) -> None:
        """Replace the immutable parameter snapshot with one changed gain."""
        self.parameters = self.parameters.with_gain(channel, gain)

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        """Return the unclipped polarizing sum for the current block."""
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        inputs = inputs or {}
        output = np.zeros(frame_count, dtype=np.float64)
        for channel, gain in enumerate(self.parameters.gains, start=1):
            value = inputs.get(f"input_{channel}")
            if value is not None:
                output += gain * self._input_block(
                    f"input_{channel}",
                    value,
                    frame_count,
                )
        return {"output": np.asarray(output, dtype=np.float32)}

    @staticmethod
    def _input_block(
        name: str,
        value: ArrayLike,
        frame_count: int,
    ) -> NDArray[np.float64]:
        block = np.asarray(value, dtype=np.float64)
        if block.ndim == 0:
            return np.full(frame_count, float(block), dtype=np.float64)
        if block.shape != (frame_count,):
            raise ValueError(
                f"{name} must be scalar or have shape ({frame_count},), "
                f"got {block.shape}"
            )
        return block


__all__ = [
    "MAX_CHANNELS",
    "POLARIZING_MIXER_MANIFEST",
    "PolarizingMixer",
    "PolarizingMixerParameters",
    "polarizing_mixer_manifest",
]

