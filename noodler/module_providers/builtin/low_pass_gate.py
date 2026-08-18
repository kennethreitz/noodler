"""A struck, vactrol-inspired low-pass gate for organic dynamics."""

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


class LowPassGateParameters(BaseModel):
    """Serializable controls for the gate's amplitude and spectral decay."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    decay_seconds: float = Field(default=1.8, ge=0.02, le=30.0)
    brightness: float = Field(default=0.62, ge=0.0, le=1.0)
    character: float = Field(default=0.35, ge=0.0, le=1.0)
    level: float = Field(default=0.8, ge=0.0, le=1.0)


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


LOW_PASS_GATE_MANIFEST = ModuleManifest(
    id="low_pass_gate",
    name="Organic Low-Pass Gate",
    category="Dynamics",
    description=(
        "A struck, vactrol-inspired gate whose amplitude and brightness decay "
        "together for rounded acoustic gestures."
    ),
    ports=(
        _port(
            "audio",
            "Audio In",
            PortDirection.INPUT,
            SignalType.AUDIO,
            "Audio or audio-rate CV shaped by the gate.",
        ),
        _port(
            "strike",
            "Strike",
            PortDirection.INPUT,
            SignalType.TRIGGER,
            "A rising trigger fully excites the gate.",
        ),
        _port(
            "level_cv",
            "Level CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Bipolar offset added to the struck envelope.",
        ),
        _port(
            "decay_cv",
            "Decay CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Exponential decay-time modulation at one octave per unit.",
        ),
        _port(
            "output",
            "Out",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "The dynamically darkened and attenuated signal.",
        ),
        _port(
            "envelope",
            "Envelope",
            PortDirection.OUTPUT,
            SignalType.CV,
            "The gate's unscaled vactrol-style response.",
        ),
    ),
)


class LowPassGate:
    """Shape a signal with a coupled exponential amplitude/filter response.

    The implementation is intentionally an instrument rather than a component
    model. A strike opens the gate immediately; two related decays give it the
    quick onset and lingering spectral tail associated with an optical LPG.
    """

    manifest = LOW_PASS_GATE_MANIFEST

    def __init__(self, parameters: LowPassGateParameters | None = None) -> None:
        self.parameters = parameters or LowPassGateParameters()
        # Starting open makes the initial patch audible as soon as audio starts.
        self._envelope = 1.0
        self._filter_state = 0.0
        self._strike_high = False

    def reset(self) -> None:
        """Restore the initial open gesture and clear the filter memory."""
        self._envelope = 1.0
        self._filter_state = 0.0
        self._strike_high = False

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        """Render the struck response and its companion envelope."""
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if frame_count == 0:
            empty = np.empty(0, dtype=np.float32)
            return {"output": empty, "envelope": empty.copy()}

        inputs = inputs or {}
        audio = self._optional_block("audio", inputs, frame_count)
        strike = self._optional_block("strike", inputs, frame_count)
        level_cv = self._optional_block("level_cv", inputs, frame_count)
        decay_cv = self._optional_block("decay_cv", inputs, frame_count)
        output = np.empty(frame_count, dtype=np.float64)
        envelope_output = np.empty(frame_count, dtype=np.float64)

        envelope = self._envelope
        filter_state = self._filter_state
        strike_high = self._strike_high
        parameters = self.parameters
        minimum_cutoff = 55.0 + 170.0 * parameters.character
        maximum_cutoff = 900.0 * 2.0 ** (4.0 * parameters.brightness)

        for index in range(frame_count):
            next_strike_high = bool(strike[index] > 0.0)
            if next_strike_high and not strike_high:
                envelope = 1.0

            decay_seconds = parameters.decay_seconds * 2.0 ** float(
                np.clip(decay_cv[index], -6.0, 6.0)
            )
            # Character lengthens the quiet tail without blurring the attack.
            tail = decay_seconds * (0.72 + 1.1 * parameters.character)
            envelope *= math.exp(-1.0 / (tail * sample_rate))
            response = envelope ** (1.15 + 1.6 * parameters.character)
            level = float(np.clip(response + level_cv[index], 0.0, 1.0))

            cutoff = minimum_cutoff + (maximum_cutoff - minimum_cutoff) * (
                response ** (1.25 - 0.5 * parameters.character)
            )
            cutoff = min(cutoff, sample_rate * 0.45)
            alpha = 1.0 - math.exp(-math.tau * cutoff / sample_rate)
            filter_state += alpha * (float(audio[index]) - filter_state)

            # A touch of level-dependent saturation keeps bright strikes soft.
            warmth = 1.0 + 1.8 * parameters.character * response
            shaped = math.tanh(filter_state * warmth) / math.tanh(warmth)
            output[index] = shaped * level * parameters.level
            envelope_output[index] = envelope
            strike_high = next_strike_high

        self._envelope = envelope
        self._filter_state = filter_state
        self._strike_high = strike_high
        return {
            "output": np.asarray(output, dtype=np.float32),
            "envelope": np.asarray(envelope_output, dtype=np.float32),
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
    "LOW_PASS_GATE_MANIFEST",
    "LowPassGate",
    "LowPassGateParameters",
]
