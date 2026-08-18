"""A four-channel function and analog-logic utility inspired by MATHS."""

from collections.abc import Mapping
from dataclasses import dataclass
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
MIN_FUNCTION_STAGE_SECONDS = 0.0005
MAX_FUNCTION_STAGE_SECONDS = 750.0


class FunctionStage(StrEnum):
    """The internal stage of a triggered or cycling function."""

    IDLE = "idle"
    RISING = "rising"
    FALLING = "falling"


class FunctionChannelParameters(BaseModel):
    """Controls for one rise/fall function generator."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rise_seconds: float = Field(
        default=0.1,
        ge=MIN_FUNCTION_STAGE_SECONDS,
        le=MAX_FUNCTION_STAGE_SECONDS,
    )
    fall_seconds: float = Field(
        default=0.1,
        ge=MIN_FUNCTION_STAGE_SECONDS,
        le=MAX_FUNCTION_STAGE_SECONDS,
    )
    curve: float = Field(default=0.0, ge=-1.0, le=1.0)
    cycle: bool = False
    attenuverter: float = Field(default=1.0, ge=-1.0, le=1.0)


CONTROL_STRIDE = 32
"""Samples per decision when a channel is running free.

A function generator is a control source: its contours are measured in seconds,
not samples, so stepping its stage machine once per sample spends most of a
patch's CPU deciding nothing has changed. Running free it advances in strides
and interpolates between decisions, which is inaudible on a contour and leaves
the audio callback the headroom it actually needs.

Striding is only ever used when nothing sub-stride can change the outcome: a
signal to slew, a trigger, or a cycle gate all put the channel back on a
per-sample loop. The stride also shrinks with the contour, because these
channels reach audio rate, where a stage lasts a handful of samples and every
one of them is the shape.
"""

MIN_STEPS_PER_STAGE = 256
"""Decisions guaranteed per rise or fall, however fast it has been set."""


class FunctionUtilityParameters(BaseModel):
    """Serializable controls for all four utility channels."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    channel_1: FunctionChannelParameters = Field(
        default_factory=FunctionChannelParameters
    )
    channel_2_attenuverter: float = Field(default=0.0, ge=-1.0, le=1.0)
    channel_3_attenuverter: float = Field(default=0.0, ge=-1.0, le=1.0)
    channel_4: FunctionChannelParameters = Field(
        default_factory=FunctionChannelParameters
    )


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


def _function_ports(channel: int) -> tuple[PortManifest, ...]:
    prefix = f"channel_{channel}"
    return (
        _port(
            f"{prefix}_signal",
            f"Channel {channel} Signal",
            PortDirection.INPUT,
            SignalType.CV,
            "Direct-coupled input for slew, lag, and envelope following.",
        ),
        _port(
            f"{prefix}_trigger",
            f"Channel {channel} Trigger",
            PortDirection.INPUT,
            SignalType.TRIGGER,
            "Rising edge starts a rise/fall transient.",
        ),
        _port(
            f"{prefix}_cycle",
            f"Channel {channel} Cycle",
            PortDirection.INPUT,
            SignalType.GATE,
            "High gate enables continuous cycling.",
        ),
        _port(
            f"{prefix}_rise_cv",
            f"Channel {channel} Rise CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Positive CV lengthens rise time.",
        ),
        _port(
            f"{prefix}_both_cv",
            f"Channel {channel} Both CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Positive exponential CV shortens rise and fall together.",
        ),
        _port(
            f"{prefix}_fall_cv",
            f"Channel {channel} Fall CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Positive CV lengthens fall time.",
        ),
    )


FUNCTION_UTILITY_MANIFEST = ModuleManifest(
    id="function_utility",
    name="Function & Logic Utility",
    category="Utilities",
    description=(
        "A MATHS-style four-channel function generator, polarizer, summer, "
        "inverter, and analog maximum selector."
    ),
    ports=(
        *_function_ports(1),
        _port(
            "channel_2_signal",
            "Channel 2 Signal",
            PortDirection.INPUT,
            SignalType.CV,
            "Polarizing input normalized to +1.0 when unpatched.",
        ),
        _port(
            "channel_3_signal",
            "Channel 3 Signal",
            PortDirection.INPUT,
            SignalType.CV,
            "Polarizing input normalized to +0.5 when unpatched.",
        ),
        *_function_ports(4),
        _port(
            "channel_1_unity",
            "Channel 1 Unity",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Unattenuverted Channel 1 function output.",
        ),
        _port(
            "channel_1",
            "Channel 1",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Attenuverted Channel 1 output.",
        ),
        _port(
            "channel_1_eor",
            "Channel 1 EOR",
            PortDirection.OUTPUT,
            SignalType.GATE,
            "End-of-rise gate, high during the falling stage.",
        ),
        _port(
            "channel_2",
            "Channel 2",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Attenuverted Channel 2 signal or normalized offset.",
        ),
        _port(
            "channel_3",
            "Channel 3",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Attenuverted Channel 3 signal or normalized offset.",
        ),
        _port(
            "channel_4_unity",
            "Channel 4 Unity",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Unattenuverted Channel 4 function output.",
        ),
        _port(
            "channel_4",
            "Channel 4",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Attenuverted Channel 4 output.",
        ),
        _port(
            "channel_4_eoc",
            "Channel 4 EOC",
            PortDirection.OUTPUT,
            SignalType.GATE,
            "End-of-cycle gate, high outside the falling stage.",
        ),
        _port(
            "sum",
            "SUM",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Unclipped sum of the four variable channel outputs.",
        ),
        _port(
            "inverse",
            "INV",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Exact inverse of the SUM output.",
        ),
        _port(
            "or",
            "OR",
            PortDirection.OUTPUT,
            SignalType.CV,
            "Non-negative maximum of the four variable channels.",
        ),
    ),
)


@dataclass(slots=True)
class _FunctionState:
    value: float = 0.0
    start_value: float = 0.0
    progress: float = 0.0
    stage: FunctionStage = FunctionStage.IDLE
    trigger_high: bool = False


class FunctionUtility:
    """Process dual functions, two polarizers, and three combined outputs."""

    manifest = FUNCTION_UTILITY_MANIFEST

    def __init__(self, parameters: FunctionUtilityParameters | None = None) -> None:
        self.parameters = parameters or FunctionUtilityParameters()
        self._channel_1_state = _FunctionState()
        self._channel_4_state = _FunctionState()

    def reset(self) -> None:
        """Reset both function generators to their idle states."""
        self._channel_1_state = _FunctionState()
        self._channel_4_state = _FunctionState()

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        """Render all individual and combined utility outputs."""
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        inputs = inputs or {}

        channel_1_unity, channel_1_eor, _ = self._process_function_channel(
            channel=1,
            parameters=self.parameters.channel_1,
            state=self._channel_1_state,
            frame_count=frame_count,
            sample_rate=sample_rate,
            inputs=inputs,
        )
        channel_4_unity, _, channel_4_eoc = self._process_function_channel(
            channel=4,
            parameters=self.parameters.channel_4,
            state=self._channel_4_state,
            frame_count=frame_count,
            sample_rate=sample_rate,
            inputs=inputs,
        )

        channel_1 = channel_1_unity * self.parameters.channel_1.attenuverter
        channel_2_source = self._optional_block(
            "channel_2_signal",
            inputs,
            frame_count,
            normalized=1.0,
        )
        channel_2 = channel_2_source * self.parameters.channel_2_attenuverter
        channel_3_source = self._optional_block(
            "channel_3_signal",
            inputs,
            frame_count,
            normalized=0.5,
        )
        channel_3 = channel_3_source * self.parameters.channel_3_attenuverter
        channel_4 = channel_4_unity * self.parameters.channel_4.attenuverter

        summed = channel_1 + channel_2 + channel_3 + channel_4
        analog_or = np.maximum.reduce(
            [
                np.zeros(frame_count, dtype=np.float64),
                channel_1,
                channel_2,
                channel_3,
                channel_4,
            ]
        )

        outputs = {
            "channel_1_unity": channel_1_unity,
            "channel_1": channel_1,
            "channel_1_eor": channel_1_eor,
            "channel_2": channel_2,
            "channel_3": channel_3,
            "channel_4_unity": channel_4_unity,
            "channel_4": channel_4,
            "channel_4_eoc": channel_4_eoc,
            "sum": summed,
            "inverse": -summed,
            "or": analog_or,
        }
        return {
            name: np.asarray(block, dtype=np.float32)
            for name, block in outputs.items()
        }

    def _process_function_channel(
        self,
        *,
        channel: int,
        parameters: FunctionChannelParameters,
        state: _FunctionState,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike],
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        prefix = f"channel_{channel}"
        signal = (
            self._block(f"{prefix}_signal", inputs[f"{prefix}_signal"], frame_count)
            if f"{prefix}_signal" in inputs
            else None
        )
        trigger = self._optional_block(
            f"{prefix}_trigger", inputs, frame_count, normalized=0.0
        )
        cycle = self._optional_block(
            f"{prefix}_cycle", inputs, frame_count, normalized=0.0
        )
        rise_cv = self._optional_block(
            f"{prefix}_rise_cv", inputs, frame_count, normalized=0.0
        )
        both_cv = self._optional_block(
            f"{prefix}_both_cv", inputs, frame_count, normalized=0.0
        )
        fall_cv = self._optional_block(
            f"{prefix}_fall_cv", inputs, frame_count, normalized=0.0
        )
        minimum_stage_seconds = max(MIN_FUNCTION_STAGE_SECONDS, 1.0 / sample_rate)
        rise_times = np.clip(
            parameters.rise_seconds
            * np.exp2(np.clip(rise_cv - both_cv, -32.0, 32.0)),
            minimum_stage_seconds,
            MAX_FUNCTION_STAGE_SECONDS,
        )
        fall_times = np.clip(
            parameters.fall_seconds
            * np.exp2(np.clip(fall_cv - both_cv, -32.0, 32.0)),
            minimum_stage_seconds,
            MAX_FUNCTION_STAGE_SECONDS,
        )

        output = np.empty(frame_count, dtype=np.float64)
        eor = np.empty(frame_count, dtype=np.float64)
        eoc = np.empty(frame_count, dtype=np.float64)

        free_running = (
            signal is None
            and f"{prefix}_trigger" not in inputs
            and f"{prefix}_cycle" not in inputs
        )
        stride = 1
        if free_running and frame_count:
            stage_samples = (
                min(float(rise_times.min()), float(fall_times.min())) * sample_rate
            )
            stride = int(
                min(CONTROL_STRIDE, max(1.0, stage_samples // MIN_STEPS_PER_STAGE))
            )
        if stride > 1:
            cycle_enabled = parameters.cycle
            index = 0
            while index < frame_count:
                span = min(stride, frame_count - index)
                previous = state.value
                if state.stage is FunctionStage.IDLE and cycle_enabled:
                    self._begin_stage(state, FunctionStage.RISING)
                self._function_step(
                    state,
                    float(rise_times[index]),
                    float(fall_times[index]),
                    parameters.curve,
                    cycle_enabled,
                    sample_rate / span,
                )
                output[index : index + span] = np.linspace(
                    previous,
                    state.value,
                    span,
                    endpoint=False,
                )
                falling = state.stage is FunctionStage.FALLING
                eor[index : index + span] = 1.0 if falling else 0.0
                eoc[index : index + span] = 0.0 if falling else 1.0
                index += span
            return output, eor, eoc

        for index in range(frame_count):
            trigger_high = bool(trigger[index] > 0.0)
            trigger_edge = trigger_high and not state.trigger_high
            cycle_enabled = parameters.cycle or cycle[index] > 0.0

            if signal is not None:
                self._slew_step(
                    state,
                    float(signal[index]),
                    float(rise_times[index]),
                    float(fall_times[index]),
                    parameters.curve,
                    sample_rate,
                )
            else:
                if (
                    trigger_edge and state.stage is not FunctionStage.RISING
                ) or (state.stage is FunctionStage.IDLE and cycle_enabled):
                    self._begin_stage(state, FunctionStage.RISING)
                self._function_step(
                    state,
                    float(rise_times[index]),
                    float(fall_times[index]),
                    parameters.curve,
                    cycle_enabled,
                    sample_rate,
                )

            state.trigger_high = trigger_high
            output[index] = state.value
            eor[index] = 1.0 if state.stage is FunctionStage.FALLING else 0.0
            eoc[index] = 0.0 if state.stage is FunctionStage.FALLING else 1.0

        return output, eor, eoc

    @staticmethod
    def _begin_stage(state: _FunctionState, stage: FunctionStage) -> None:
        state.stage = stage
        state.start_value = state.value
        state.progress = 0.0

    def _function_step(
        self,
        state: _FunctionState,
        rise_seconds: float,
        fall_seconds: float,
        curve: float,
        cycle: bool,
        sample_rate: float,
    ) -> None:
        if state.stage is FunctionStage.RISING:
            state.progress = min(1.0, state.progress + 1.0 / (rise_seconds * sample_rate))
            if np.isclose(state.progress, 1.0, rtol=0.0, atol=1e-12):
                state.progress = 1.0
            shaped = self._shape(state.progress, curve)
            state.value = state.start_value + (1.0 - state.start_value) * shaped
            if state.progress >= 1.0:
                state.value = 1.0
                self._begin_stage(state, FunctionStage.FALLING)
        elif state.stage is FunctionStage.FALLING:
            state.progress = min(1.0, state.progress + 1.0 / (fall_seconds * sample_rate))
            if np.isclose(state.progress, 1.0, rtol=0.0, atol=1e-12):
                state.progress = 1.0
            shaped = self._shape(state.progress, curve)
            state.value = state.start_value * (1.0 - shaped)
            if state.progress >= 1.0:
                state.value = 0.0
                self._begin_stage(
                    state,
                    FunctionStage.RISING if cycle else FunctionStage.IDLE,
                )

    @staticmethod
    def _slew_step(
        state: _FunctionState,
        target: float,
        rise_seconds: float,
        fall_seconds: float,
        curve: float,
        sample_rate: float,
    ) -> None:
        difference = target - state.value
        if difference == 0.0:
            state.stage = FunctionStage.IDLE
            return
        state.stage = (
            FunctionStage.RISING if difference > 0.0 else FunctionStage.FALLING
        )
        seconds = rise_seconds if difference > 0.0 else fall_seconds
        linear_step = 1.0 / (seconds * sample_rate)
        if curve > 0.0:
            step = linear_step * max(abs(difference), 1e-6)
        elif curve < 0.0:
            step = linear_step * (1.0 + 3.0 * -curve)
        else:
            step = linear_step
        state.value += np.sign(difference) * min(abs(difference), step)

    @staticmethod
    def _shape(progress: float, curve: float) -> float:
        if curve >= 0.0:
            exponent = 1.0 + 4.0 * curve
        else:
            exponent = 1.0 / (1.0 + 4.0 * -curve)
        return progress**exponent

    def _optional_block(
        self,
        name: str,
        inputs: Mapping[str, ArrayLike],
        frame_count: int,
        *,
        normalized: float,
    ) -> NDArray[np.float64]:
        if name not in inputs:
            return np.full(frame_count, normalized, dtype=np.float64)
        return self._block(name, inputs[name], frame_count)

    @staticmethod
    def _block(
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
    "FUNCTION_UTILITY_MANIFEST",
    "MAX_FUNCTION_STAGE_SECONDS",
    "MIN_FUNCTION_STAGE_SECONDS",
    "FunctionChannelParameters",
    "FunctionStage",
    "FunctionUtility",
    "FunctionUtilityParameters",
]
