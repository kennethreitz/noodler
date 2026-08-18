"""Envelope and voltage-controlled-amplifier building blocks."""

from collections.abc import Mapping
from enum import StrEnum
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


ENVELOPE_OUTPUTS = ("envelope", "inverse", "end")
VCA_OUTPUTS = ("output", "gain")


class EnvelopeStage(StrEnum):
    """Current segment of an ADSR contour."""

    IDLE = "idle"
    ATTACK = "attack"
    DECAY = "decay"
    SUSTAIN = "sustain"
    RELEASE = "release"


class ADSRParameters(BaseModel):
    """Serializable ADSR timing and response controls."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    attack_seconds: float = Field(default=0.01, ge=0.0005, le=60.0)
    decay_seconds: float = Field(default=0.18, ge=0.0005, le=60.0)
    sustain: float = Field(default=0.62, ge=0.0, le=1.0)
    release_seconds: float = Field(default=0.45, ge=0.0005, le=120.0)
    curve: float = Field(default=0.2, ge=-1.0, le=1.0)


ADSR_ENVELOPE_MANIFEST = ModuleManifest(
    id="adsr_envelope",
    name="ADSR Envelope",
    category="Envelopes & Dynamics",
    description="A retriggerable four-stage contour with voltage-controlled timing and end pulse.",
    ports=(
        port("gate", "Gate", PortDirection.INPUT, SignalType.GATE, "Hold through attack, decay, and sustain."),
        port("retrigger", "Retrigger", PortDirection.INPUT, SignalType.TRIGGER, "Restart attack from the current level."),
        port("time_cv", "Time CV", PortDirection.INPUT, SignalType.CV, "One-octave-per-unit modulation of all times."),
        port("envelope", "Envelope", PortDirection.OUTPUT, SignalType.CV, "Zero-to-one contour."),
        port("inverse", "Inverse", PortDirection.OUTPUT, SignalType.CV, "One minus the envelope."),
        port("end", "End", PortDirection.OUTPUT, SignalType.TRIGGER, "Pulse when release reaches zero."),
    ),
)


class ADSREnvelope:
    """Generate a sample-accurate, retriggerable ADSR contour."""

    manifest = ADSR_ENVELOPE_MANIFEST

    def __init__(self, parameters: ADSRParameters | None = None) -> None:
        self.parameters = parameters or ADSRParameters()
        self.reset()

    @property
    def stage(self) -> EnvelopeStage:
        return self._stage

    def reset(self) -> None:
        self._stage = EnvelopeStage.IDLE
        self._value = 0.0
        self._progress = 0.0
        self._start_value = 0.0
        self._gate_high = False
        self._retrigger_high = False

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
            return empty_outputs(ENVELOPE_OUTPUTS)
        inputs = inputs or {}
        gate = block("gate", inputs, frame_count)
        retrigger = block("retrigger", inputs, frame_count)
        time_cv = block("time_cv", inputs, frame_count)
        envelope = np.empty(frame_count, dtype=np.float64)
        end = np.zeros(frame_count, dtype=np.float64)
        for sample in range(frame_count):
            gate_event, gate_high = rising_edge(gate[sample], self._gate_high)
            retrigger_event, retrigger_high = rising_edge(
                retrigger[sample],
                self._retrigger_high,
            )
            if gate_event or retrigger_event:
                self._begin(EnvelopeStage.ATTACK)
            elif self._gate_high and not gate_high:
                self._begin(EnvelopeStage.RELEASE)

            time_scale = 2.0 ** float(np.clip(time_cv[sample], -12.0, 12.0))
            if self._stage is EnvelopeStage.ATTACK:
                complete = self._advance(
                    self.parameters.attack_seconds * time_scale,
                    sample_rate,
                    target=1.0,
                )
                if complete:
                    self._begin(EnvelopeStage.DECAY)
            elif self._stage is EnvelopeStage.DECAY:
                complete = self._advance(
                    self.parameters.decay_seconds * time_scale,
                    sample_rate,
                    target=self.parameters.sustain,
                )
                if complete:
                    self._stage = EnvelopeStage.SUSTAIN
                    self._value = self.parameters.sustain
            elif self._stage is EnvelopeStage.SUSTAIN:
                self._value = self.parameters.sustain
            elif self._stage is EnvelopeStage.RELEASE:
                complete = self._advance(
                    self.parameters.release_seconds * time_scale,
                    sample_rate,
                    target=0.0,
                )
                if complete:
                    self._stage = EnvelopeStage.IDLE
                    self._value = 0.0
                    end[sample] = 1.0

            envelope[sample] = self._value
            self._gate_high = gate_high
            self._retrigger_high = retrigger_high
        return {
            "envelope": np.asarray(envelope, dtype=np.float32),
            "inverse": np.asarray(1.0 - envelope, dtype=np.float32),
            "end": np.asarray(end, dtype=np.float32),
        }

    def _begin(self, stage: EnvelopeStage) -> None:
        self._stage = stage
        self._progress = 0.0
        self._start_value = self._value

    def _advance(
        self,
        seconds: float,
        sample_rate: float,
        *,
        target: float,
    ) -> bool:
        self._progress = min(1.0, self._progress + 1.0 / (seconds * sample_rate))
        if self._progress >= 1.0 - 1e-12:
            self._progress = 1.0
        shaped = self._shape(self._progress, self.parameters.curve)
        self._value = self._start_value + (target - self._start_value) * shaped
        return self._progress >= 1.0

    @staticmethod
    def _shape(position: float, curve: float) -> float:
        if abs(curve) < 1e-9:
            return position
        exponent = 2.0 ** (3.0 * abs(curve))
        if curve > 0.0:
            return 1.0 - (1.0 - position) ** exponent
        return position**exponent


class VCAResponse(StrEnum):
    """Gain laws for a VCA control input."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class VCAParameters(BaseModel):
    """Controls for a DC-coupled voltage-controlled amplifier."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    level: float = Field(default=1.0, ge=0.0, le=2.0)
    bias: float = Field(default=0.0, ge=0.0, le=1.0)
    response: VCAResponse = VCAResponse.EXPONENTIAL
    drive: float = Field(default=1.0, ge=0.25, le=12.0)


VCA_MANIFEST = ModuleManifest(
    id="vca",
    name="VCA / Attenuator",
    category="Envelopes & Dynamics",
    description="A DC-coupled linear or exponential VCA with manual bias and soft drive.",
    ports=(
        port("signal", "Signal", PortDirection.INPUT, SignalType.AUDIO, "Audio or CV to scale."),
        port("level_cv", "Level CV", PortDirection.INPUT, SignalType.CV, "Zero-to-one gain control."),
        port("output", "Out", PortDirection.OUTPUT, SignalType.AUDIO, "Scaled audio or CV."),
        port("gain", "Gain", PortDirection.OUTPUT, SignalType.CV, "The applied gain coefficient."),
    ),
)


class VCA:
    """Apply a patchable gain law to audio or CV."""

    manifest = VCA_MANIFEST

    def __init__(self, parameters: VCAParameters | None = None) -> None:
        self.parameters = parameters or VCAParameters()

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
            return empty_outputs(VCA_OUTPUTS)
        inputs = inputs or {}
        signal = block("signal", inputs, frame_count)
        level_cv = block("level_cv", inputs, frame_count)
        gain = np.clip(self.parameters.bias + level_cv, 0.0, 1.0)
        if self.parameters.response is VCAResponse.EXPONENTIAL:
            gain = gain * gain
        gain *= self.parameters.level
        drive = self.parameters.drive
        driven = np.tanh(signal * drive) / drive
        return {
            "output": np.asarray(driven * gain, dtype=np.float32),
            "gain": np.asarray(gain, dtype=np.float32),
        }


__all__ = [
    "ADSR_ENVELOPE_MANIFEST",
    "VCA_MANIFEST",
    "ADSREnvelope",
    "ADSRParameters",
    "EnvelopeStage",
    "VCA",
    "VCAParameters",
    "VCAResponse",
]
