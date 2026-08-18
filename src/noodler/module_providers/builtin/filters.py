"""Patchable state-variable and ladder-style filters."""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port


SVF_OUTPUTS = ("low", "band", "high", "notch")
LADDER_OUTPUTS = ("low_6", "low_12", "low_18", "low_24", "band", "high")


class StateVariableFilterParameters(BaseModel):
    """Controls for a topology-preserving state-variable filter."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    cutoff_hz: float = Field(default=1_200.0, ge=10.0, le=20_000.0)
    resonance: float = Field(default=0.25, ge=0.0, le=1.0)
    drive: float = Field(default=1.0, ge=0.25, le=12.0)
    output_level: float = Field(default=1.0, ge=0.0, le=2.0)


STATE_VARIABLE_FILTER_MANIFEST = ModuleManifest(
    id="state_variable_filter",
    name="State Variable Filter",
    category="Filters",
    description="A stable multimode filter with simultaneous low, band, high, and notch outputs.",
    ports=(
        port("audio", "Audio In", PortDirection.INPUT, SignalType.AUDIO, "Signal to filter."),
        port("cutoff_cv", "Cutoff CV", PortDirection.INPUT, SignalType.CV, "One-octave-per-unit cutoff modulation."),
        port("resonance_cv", "Resonance CV", PortDirection.INPUT, SignalType.CV, "Bipolar resonance offset."),
        port("drive_cv", "Drive CV", PortDirection.INPUT, SignalType.CV, "Bipolar input-drive offset."),
        port("low", "Low Pass", PortDirection.OUTPUT, SignalType.AUDIO, "Two-pole low-pass output."),
        port("band", "Band Pass", PortDirection.OUTPUT, SignalType.AUDIO, "Two-pole band-pass output."),
        port("high", "High Pass", PortDirection.OUTPUT, SignalType.AUDIO, "Two-pole high-pass output."),
        port("notch", "Notch", PortDirection.OUTPUT, SignalType.AUDIO, "Low plus high notch output."),
    ),
)


class StateVariableFilter:
    """Topology-preserving state-variable filter with nonlinear input drive."""

    manifest = STATE_VARIABLE_FILTER_MANIFEST

    def __init__(
        self,
        parameters: StateVariableFilterParameters | None = None,
    ) -> None:
        self.parameters = parameters or StateVariableFilterParameters()
        self.reset()

    def reset(self) -> None:
        self._integrator_1 = 0.0
        self._integrator_2 = 0.0

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
            return empty_outputs(SVF_OUTPUTS)
        inputs = inputs or {}
        audio = block("audio", inputs, frame_count)
        cutoff_cv = block("cutoff_cv", inputs, frame_count)
        resonance_cv = block("resonance_cv", inputs, frame_count)
        drive_cv = block("drive_cv", inputs, frame_count)
        cutoff = np.clip(
            self.parameters.cutoff_hz * np.exp2(np.clip(cutoff_cv, -12.0, 12.0)),
            10.0,
            sample_rate * 0.45,
        )
        resonance = np.clip(
            self.parameters.resonance + resonance_cv,
            0.0,
            1.0,
        )
        drive = np.clip(self.parameters.drive * np.exp2(drive_cv), 0.25, 20.0)
        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in SVF_OUTPUTS
        }
        ic1 = self._integrator_1
        ic2 = self._integrator_2
        for sample in range(frame_count):
            g = math.tan(math.pi * float(cutoff[sample]) / sample_rate)
            damping = 2.0 * (1.0 - 0.96 * float(resonance[sample]))
            a1 = 1.0 / (1.0 + g * (g + damping))
            a2 = g * a1
            a3 = g * a2
            driven = math.tanh(float(audio[sample]) * float(drive[sample]))
            v3 = driven - ic2
            band = a1 * ic1 + a2 * v3
            low = ic2 + a2 * ic1 + a3 * v3
            high = driven - damping * band - low
            ic1 = 2.0 * band - ic1
            ic2 = 2.0 * low - ic2
            outputs["low"][sample] = low
            outputs["band"][sample] = band
            outputs["high"][sample] = high
            outputs["notch"][sample] = low + high
        self._integrator_1 = ic1
        self._integrator_2 = ic2
        level = self.parameters.output_level
        return {
            name: np.asarray(np.tanh(value) * level, dtype=np.float32)
            for name, value in outputs.items()
        }


class LadderFilterParameters(BaseModel):
    """Controls for a nonlinear four-stage ladder-style filter."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    cutoff_hz: float = Field(default=900.0, ge=10.0, le=20_000.0)
    resonance: float = Field(default=0.3, ge=0.0, le=1.0)
    drive: float = Field(default=1.4, ge=0.25, le=12.0)
    output_level: float = Field(default=1.0, ge=0.0, le=2.0)


LADDER_FILTER_MANIFEST = ModuleManifest(
    id="ladder_filter",
    name="Four-Pole Ladder Filter",
    category="Filters",
    description="A driven resonant cascade with simultaneous 6, 12, 18, and 24 dB low-pass taps.",
    ports=(
        port("audio", "Audio In", PortDirection.INPUT, SignalType.AUDIO, "Signal to filter."),
        port("cutoff_cv", "Cutoff CV", PortDirection.INPUT, SignalType.CV, "One-octave-per-unit cutoff modulation."),
        port("resonance_cv", "Resonance CV", PortDirection.INPUT, SignalType.CV, "Bipolar resonance offset."),
        port("drive_cv", "Drive CV", PortDirection.INPUT, SignalType.CV, "Exponential drive modulation."),
        port("low_6", "6 dB Low", PortDirection.OUTPUT, SignalType.AUDIO, "First ladder stage."),
        port("low_12", "12 dB Low", PortDirection.OUTPUT, SignalType.AUDIO, "Second ladder stage."),
        port("low_18", "18 dB Low", PortDirection.OUTPUT, SignalType.AUDIO, "Third ladder stage."),
        port("low_24", "24 dB Low", PortDirection.OUTPUT, SignalType.AUDIO, "Fourth ladder stage."),
        port("band", "Band", PortDirection.OUTPUT, SignalType.AUDIO, "Difference between second and fourth stages."),
        port("high", "High", PortDirection.OUTPUT, SignalType.AUDIO, "Input minus the four-pole output."),
    ),
)


class LadderFilter:
    """Saturating four-stage low-pass cascade with resonance feedback."""

    manifest = LADDER_FILTER_MANIFEST

    def __init__(self, parameters: LadderFilterParameters | None = None) -> None:
        self.parameters = parameters or LadderFilterParameters()
        self.reset()

    def reset(self) -> None:
        self._stages = np.zeros(4, dtype=np.float64)

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
            return empty_outputs(LADDER_OUTPUTS)
        inputs = inputs or {}
        audio = block("audio", inputs, frame_count)
        cutoff_cv = block("cutoff_cv", inputs, frame_count)
        resonance_cv = block("resonance_cv", inputs, frame_count)
        drive_cv = block("drive_cv", inputs, frame_count)
        cutoff = np.clip(
            self.parameters.cutoff_hz * np.exp2(np.clip(cutoff_cv, -12.0, 12.0)),
            10.0,
            sample_rate * 0.42,
        )
        resonance = np.clip(
            self.parameters.resonance + resonance_cv,
            0.0,
            1.0,
        )
        drive = np.clip(self.parameters.drive * np.exp2(drive_cv), 0.25, 20.0)
        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in LADDER_OUTPUTS
        }
        stages = self._stages.copy()
        for sample in range(frame_count):
            coefficient = 1.0 - math.exp(
                -math.tau * float(cutoff[sample]) / sample_rate
            )
            feedback = 3.85 * float(resonance[sample]) * stages[3]
            signal = math.tanh(float(audio[sample]) * float(drive[sample]) - feedback)
            previous = signal
            for stage in range(4):
                stages[stage] += coefficient * (
                    math.tanh(previous) - math.tanh(stages[stage])
                )
                previous = stages[stage]
            outputs["low_6"][sample] = stages[0]
            outputs["low_12"][sample] = stages[1]
            outputs["low_18"][sample] = stages[2]
            outputs["low_24"][sample] = stages[3]
            outputs["band"][sample] = stages[1] - stages[3]
            outputs["high"][sample] = signal - stages[3]
        self._stages = stages
        level = self.parameters.output_level
        return {
            name: np.asarray(np.tanh(value) * level, dtype=np.float32)
            for name, value in outputs.items()
        }


__all__ = [
    "LADDER_FILTER_MANIFEST",
    "STATE_VARIABLE_FILTER_MANIFEST",
    "LadderFilter",
    "LadderFilterParameters",
    "StateVariableFilter",
    "StateVariableFilterParameters",
]
