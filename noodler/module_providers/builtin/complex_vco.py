"""A phase-continuous, triangle-core complex VCO."""

from collections.abc import Mapping
from enum import StrEnum

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
OUTPUT_NAMES = ("sine", "triangle", "saw", "pulse", "morph")


class WaveB(StrEnum):
    """The waveform at the far end of the morph output."""

    SAW = "saw"
    PULSE = "pulse"


class ComplexVCOParameters(BaseModel):
    """Serializable, assignment-validated panel controls."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    frequency: float = Field(default=220.0, gt=0.0, le=20_000.0)
    fine_tune_cents: float = Field(default=0.0, ge=-100.0, le=100.0)
    amplitude: float = Field(default=0.2, ge=0.0, le=1.0)
    frequency_cv_1_amount: float = Field(default=0.0, ge=-1.0, le=1.0)
    frequency_cv_2_amount: float = Field(default=0.0, ge=-1.0, le=1.0)
    linear_fm_amount: float = Field(default=0.0, ge=0.0, le=1.0)
    pulse_width: float = Field(default=0.5, ge=0.01, le=0.99)
    morph: float = Field(default=0.0, ge=0.0, le=1.0)
    wave_b: WaveB = WaveB.SAW


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


COMPLEX_VCO_MANIFEST = ModuleManifest(
    id="complex_vco",
    name="Triangle Core Complex VCO",
    category="Sources",
    description=(
        "A Model 15-inspired triangle-core oscillator with exponential CV, "
        "linear FM, PWM, sync, and voltage-controlled waveform morphing."
    ),
    ports=(
        _port(
            "pitch",
            "1 V/oct",
            PortDirection.INPUT,
            SignalType.CV,
            "Calibrated one volt per octave pitch input.",
        ),
        _port(
            "frequency_cv_1",
            "Frequency CV 1",
            PortDirection.INPUT,
            SignalType.CV,
            "First bipolar, attenuverted exponential frequency input.",
        ),
        _port(
            "frequency_cv_2",
            "Frequency CV 2",
            PortDirection.INPUT,
            SignalType.CV,
            "Second bipolar, attenuverted exponential frequency input.",
        ),
        _port(
            "linear_fm",
            "Linear FM",
            PortDirection.INPUT,
            SignalType.CV,
            "Bipolar audio/CV input for linear frequency modulation.",
        ),
        _port(
            "pwm",
            "PWM",
            PortDirection.INPUT,
            SignalType.CV,
            "Pulse-width modulation input.",
        ),
        _port(
            "morph_cv",
            "Morph",
            PortDirection.INPUT,
            SignalType.CV,
            "Voltage control added to the panel morph position.",
        ),
        _port(
            "sync",
            "Sync",
            PortDirection.INPUT,
            SignalType.TRIGGER,
            "Rising-edge hard sync for the triangle core.",
        ),
        _port(
            "sine",
            "Sine",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Sine shaped from the triangle core.",
        ),
        _port(
            "triangle",
            "Triangle",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Direct triangle core output.",
        ),
        _port(
            "saw",
            "Ramp",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Rising ramp derived from the triangle core phase.",
        ),
        _port(
            "pulse",
            "Pulse",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Voltage-controlled pulse output.",
        ),
        _port(
            "morph",
            "Morph",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Continuous sine-to-ramp or sine-to-pulse output.",
        ),
    ),
)


class ComplexVCO:
    """Generate five related outputs from a single triangle oscillator core.

    The implementation follows the signal architecture of the Plan B Model 15
    without claiming circuit-level emulation. Pitch and the two processed
    frequency inputs are exponential; the dedicated FM path is linear. The
    core may be hard-synced on a rising trigger edge.

    This prototype is not band-limited and allocates output blocks. Those
    constraints remain explicit until the engine has reusable real-time
    buffers and an anti-aliasing strategy.
    """

    manifest = COMPLEX_VCO_MANIFEST

    def __init__(self, parameters: ComplexVCOParameters | None = None) -> None:
        self.parameters = parameters or ComplexVCOParameters()
        self._phase = 0.0
        self._sync_high = False

    @property
    def phase(self) -> float:
        """Return the triangle-core phase for the next block."""
        return self._phase

    def reset(self, phase: float = 0.0) -> None:
        """Reset the triangle core and sync edge detector."""
        self._phase = float(phase) % 1.0
        self._sync_high = False

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
        *,
        pitch_cv: ArrayLike | None = None,
        frequency_cv_1: ArrayLike | None = None,
        frequency_cv_2: ArrayLike | None = None,
        linear_fm: ArrayLike | None = None,
        pwm: ArrayLike | None = None,
        morph_cv: ArrayLike | None = None,
        sync: ArrayLike | None = None,
    ) -> dict[str, FloatBlock]:
        """Render a block for all five outputs and preserve core phase."""
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if frame_count == 0:
            return {
                name: np.empty(0, dtype=np.float32)
                for name in OUTPUT_NAMES
            }

        inputs = inputs or {}
        pitch_cv = inputs.get("pitch", pitch_cv)
        frequency_cv_1 = inputs.get("frequency_cv_1", frequency_cv_1)
        frequency_cv_2 = inputs.get("frequency_cv_2", frequency_cv_2)
        linear_fm = inputs.get("linear_fm", linear_fm)
        pwm = inputs.get("pwm", pwm)
        morph_cv = inputs.get("morph_cv", morph_cv)
        sync = inputs.get("sync", sync)

        pitch = self._control_block("pitch_cv", pitch_cv, frame_count)
        exponential_cv = (
            pitch
            + self.parameters.frequency_cv_1_amount
            * self._control_block("frequency_cv_1", frequency_cv_1, frame_count)
            + self.parameters.frequency_cv_2_amount
            * self._control_block("frequency_cv_2", frequency_cv_2, frame_count)
        )
        base_frequency = self.parameters.frequency * np.exp2(
            self.parameters.fine_tune_cents / 1200.0
        )
        frequency = base_frequency * np.exp2(np.clip(exponential_cv, -32.0, 32.0))
        frequency += (
            self.parameters.linear_fm_amount
            * base_frequency
            * self._control_block("linear_fm", linear_fm, frame_count)
        )
        frequency = np.clip(frequency, 0.0, sample_rate * 0.5)

        sync_block = self._control_block("sync", sync, frame_count)
        phases = self._phase_block(frequency / sample_rate, sync_block)

        triangle = 1.0 - 4.0 * np.abs(phases - 0.5)
        sine = np.sin(2.0 * np.pi * phases)
        saw = 2.0 * phases - 1.0

        pulse_width = np.clip(
            self.parameters.pulse_width
            + 0.49 * self._control_block("pwm", pwm, frame_count),
            0.01,
            0.99,
        )
        pulse = np.where(phases < pulse_width, 1.0, -1.0)

        morph_position = np.clip(
            self.parameters.morph
            + self._control_block("morph_cv", morph_cv, frame_count),
            0.0,
            1.0,
        )
        wave_b = saw if self.parameters.wave_b is WaveB.SAW else pulse
        morph = sine + morph_position * (wave_b - sine)

        amplitude = self.parameters.amplitude
        outputs = {
            "sine": sine,
            "triangle": triangle,
            "saw": saw,
            "pulse": pulse,
            "morph": morph,
        }
        return {
            name: np.asarray(block * amplitude, dtype=np.float32)
            for name, block in outputs.items()
        }

    def _phase_block(
        self,
        increments: NDArray[np.float64],
        sync: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        phases = np.empty(increments.size, dtype=np.float64)
        phase = self._phase
        sync_high = self._sync_high

        for index, (increment, sync_value) in enumerate(
            zip(increments, sync, strict=True)
        ):
            next_sync_high = bool(sync_value > 0.0)
            if next_sync_high and not sync_high:
                phase = 0.0
            phases[index] = phase
            phase = (phase + increment) % 1.0
            sync_high = next_sync_high

        self._phase = float(phase)
        self._sync_high = sync_high
        return phases

    @staticmethod
    def _control_block(
        name: str,
        value: ArrayLike | None,
        frame_count: int,
    ) -> NDArray[np.float64]:
        if value is None:
            return np.zeros(frame_count, dtype=np.float64)

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
    "COMPLEX_VCO_MANIFEST",
    "ComplexVCO",
    "ComplexVCOParameters",
    "WaveB",
]
