"""A clockable complex random source inspired by the Wogglebug."""

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
OUTPUT_NAMES = (
    "stepped",
    "smooth",
    "woggle",
    "clock",
    "burst",
    "smooth_vco",
    "woggle_vco",
    "ring_mod",
)


class WogglebugParameters(BaseModel):
    """Serializable, assignment-validated uncertainty controls."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    clock_rate_hz: float = Field(default=1.5, ge=0.01, le=2_000.0)
    chaos: float = Field(default=0.65, ge=0.0, le=1.0)
    ego_id_balance: float = Field(default=0.7, ge=0.0, le=1.0)
    woggle: float = Field(default=0.5, ge=0.0, le=1.0)
    audio_level: float = Field(default=0.18, ge=0.0, le=1.0)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)


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


WOGGLEBUG_MANIFEST = ModuleManifest(
    id="wogglebug",
    name="Complex Random Voltage Source",
    category="Random & Chaos",
    description=(
        "A Wogglebug-inspired uncertainty source with clocked, slewed, and "
        "chasing random voltages, random gates, and three related audio outputs."
    ),
    ports=(
        _port(
            "external_clock",
            "External Clock",
            PortDirection.INPUT,
            SignalType.TRIGGER,
            "Rising edges replace the internal clock as the source of new values.",
        ),
        _port(
            "clock_cv",
            "Clock CV",
            PortDirection.INPUT,
            SignalType.CV,
            "Exponential clock-rate modulation at one octave per unit.",
        ),
        _port(
            "ego",
            "Ego",
            PortDirection.INPUT,
            SignalType.CV,
            "Audio/CV source blended with internal uncertainty before sampling.",
        ),
        _port(
            "influence",
            "Influence",
            PortDirection.INPUT,
            SignalType.CV,
            "Shifts Woggle CV, bends both audio oscillators, and feeds ring modulation.",
        ),
        _port(
            "stepped",
            "Stepped",
            PortDirection.OUTPUT,
            SignalType.CV,
            "A new held bipolar random value on every clock edge.",
        ),
        _port(
            "smooth",
            "Smooth",
            PortDirection.OUTPUT,
            SignalType.CV,
            "A lagged path that glides between successive random values.",
        ),
        _port(
            "woggle",
            "Woggle",
            PortDirection.OUTPUT,
            SignalType.CV,
            "A perturbed voltage that chases the Smooth output.",
        ),
        _port(
            "clock",
            "Clock",
            PortDirection.OUTPUT,
            SignalType.GATE,
            "Internal clock gate, or a squared copy of the external clock.",
        ),
        _port(
            "burst",
            "Burst",
            PortDirection.OUTPUT,
            SignalType.GATE,
            "Probabilistic gates synchronized to random-value changes.",
        ),
        _port(
            "smooth_vco",
            "Smooth VCO",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Square oscillator whose pitch follows the Smooth voltage.",
        ),
        _port(
            "woggle_vco",
            "Woggle VCO",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Square oscillator whose pitch follows the Woggle voltage.",
        ),
        _port(
            "ring_mod",
            "Ring Mod",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            "Product of the Woggle oscillator and Smooth oscillator or Influence input.",
        ),
    ),
)


class Wogglebug:
    """Generate correlated random control, gate, and audio signals.

    This is a digital interpretation of the Wogglebug's musical signal
    relationships, not a component-level model. All analog voltages are
    represented in Noodler's normalized range, nominally -1 to +1.
    """

    manifest = WOGGLEBUG_MANIFEST

    def __init__(self, parameters: WogglebugParameters | None = None) -> None:
        self.parameters = parameters or WogglebugParameters()
        self._rng = np.random.default_rng(self.parameters.seed)
        self._clock_phase = 0.0
        self._external_clock_high = False
        self._stepped = 0.0
        self._smooth = 0.0
        self._woggle_state = 0.0
        self._wobble_phase = 0.0
        self._wobble_energy = 0.0
        self._smooth_vco_phase = 0.0
        self._woggle_vco_phase = 0.0
        self._burst_remaining = 0
        self._disturb_pending = False

    def reset(self, *, seed: int | None = None) -> None:
        """Return to silence and restart the deterministic random stream."""
        self._rng = np.random.default_rng(
            self.parameters.seed if seed is None else seed
        )
        self._clock_phase = 0.0
        self._external_clock_high = False
        self._stepped = 0.0
        self._smooth = 0.0
        self._woggle_state = 0.0
        self._wobble_phase = 0.0
        self._wobble_energy = 0.0
        self._smooth_vco_phase = 0.0
        self._woggle_vco_phase = 0.0
        self._burst_remaining = 0
        self._disturb_pending = False

    def disturb(self) -> None:
        """Force an uncertainty event at the start of the next block."""
        self._disturb_pending = True

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> dict[str, FloatBlock]:
        """Render all related outputs while preserving continuous state."""
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
        external_clock_patched = "external_clock" in inputs
        influence_patched = "influence" in inputs
        external_clock = self._optional_block(
            "external_clock", inputs, frame_count
        )
        clock_cv = self._optional_block("clock_cv", inputs, frame_count)
        ego = self._optional_block("ego", inputs, frame_count)
        influence = self._optional_block("influence", inputs, frame_count)
        clock_rates = np.clip(
            self.parameters.clock_rate_hz
            * np.exp2(np.clip(clock_cv, -16.0, 16.0)),
            0.001,
            sample_rate * 0.45,
        )

        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in OUTPUT_NAMES
        }
        disturb_pending = self._disturb_pending
        decay_seconds = 0.03 + 0.8 * self.parameters.woggle
        wobble_decay = math.exp(-1.0 / (decay_seconds * sample_rate))

        for index in range(frame_count):
            rate = float(clock_rates[index])
            external_high = bool(external_clock[index] > 0.0)
            if external_clock_patched:
                clock_event = external_high and not self._external_clock_high
                clock_gate = 1.0 if external_high else 0.0
            else:
                clock_gate = 1.0 if self._clock_phase < 0.5 else 0.0
                self._clock_phase += rate / sample_rate
                clock_event = self._clock_phase >= 1.0
                if clock_event:
                    self._clock_phase %= 1.0

            forced = disturb_pending and index == 0
            if clock_event or forced:
                self._new_uncertainty(
                    ego=float(ego[index]),
                    ego_patched="ego" in inputs,
                    rate=rate,
                    sample_rate=sample_rate,
                    forced=forced,
                )

            smooth_cutoff = rate * (
                0.08 + 1.5 * (1.0 - self.parameters.chaos)
            )
            smooth_alpha = self._one_pole_alpha(smooth_cutoff, sample_rate)
            self._smooth += smooth_alpha * (self._stepped - self._smooth)

            catch_rate = rate * (
                0.04 + 5.0 * (1.0 - self.parameters.woggle)
            )
            catch_alpha = self._one_pole_alpha(catch_rate, sample_rate)
            self._woggle_state += catch_alpha * (
                self._smooth - self._woggle_state
            )
            wobble_rate = min(
                sample_rate * 0.45,
                rate * (0.5 + 4.0 * (1.0 - self.parameters.woggle)),
            )
            self._wobble_phase = (
                self._wobble_phase + wobble_rate / sample_rate
            ) % 1.0
            self._wobble_energy *= wobble_decay
            wobble = self._wobble_energy * math.sin(
                math.tau * self._wobble_phase
            )
            woggle = min(
                1.0,
                max(
                    -1.0,
                    self._woggle_state
                    + 0.4 * wobble
                    + 0.25 * float(influence[index]),
                ),
            )

            smooth_sign, self._smooth_vco_phase = self._audio_vco_step(
                self._smooth_vco_phase,
                self._smooth + 0.5 * influence[index],
                base_frequency=110.0,
                sample_rate=sample_rate,
            )
            woggle_sign, self._woggle_vco_phase = self._audio_vco_step(
                self._woggle_vco_phase,
                woggle + 0.5 * influence[index],
                base_frequency=165.0,
                sample_rate=sample_rate,
            )
            ring_source = (
                min(1.0, max(-1.0, float(influence[index])))
                if influence_patched
                else smooth_sign
            )

            outputs["stepped"][index] = self._stepped
            outputs["smooth"][index] = self._smooth
            outputs["woggle"][index] = woggle
            outputs["clock"][index] = clock_gate
            outputs["burst"][index] = 1.0 if self._burst_remaining > 0 else 0.0
            outputs["smooth_vco"][index] = (
                self.parameters.audio_level * smooth_sign
            )
            outputs["woggle_vco"][index] = (
                self.parameters.audio_level * woggle_sign
            )
            outputs["ring_mod"][index] = (
                self.parameters.audio_level * ring_source * woggle_sign
            )

            if self._burst_remaining > 0:
                self._burst_remaining -= 1
            self._external_clock_high = external_high

        self._disturb_pending = False
        return {
            name: np.asarray(block, dtype=np.float32)
            for name, block in outputs.items()
        }

    def _new_uncertainty(
        self,
        *,
        ego: float,
        ego_patched: bool,
        rate: float,
        sample_rate: float,
        forced: bool,
    ) -> None:
        internal = float(self._rng.uniform(-1.0, 1.0))
        balance = self.parameters.ego_id_balance
        if ego_patched:
            target = (
                (1.0 - balance) * min(1.0, max(-1.0, ego))
                + balance * internal
            )
        else:
            spread = 0.08 + 0.92 * balance
            target = spread * internal
        target += self.parameters.chaos * float(self._rng.normal(0.0, 0.12))
        self._stepped = min(1.0, max(-1.0, float(target)))
        self._wobble_energy = (
            self.parameters.chaos * float(self._rng.uniform(-1.0, 1.0))
        )

        burst_probability = 0.15 + 0.7 * self.parameters.chaos
        if forced or self._rng.random() < burst_probability:
            clock_period = sample_rate / max(rate, 0.001)
            width = max(1, int(min(sample_rate * 0.01, clock_period * 0.25)))
            self._burst_remaining = width

    @staticmethod
    def _one_pole_alpha(frequency: float, sample_rate: float) -> float:
        frequency = min(sample_rate * 0.25, max(0.001, frequency))
        return 1.0 - math.exp(-math.tau * frequency / sample_rate)

    @staticmethod
    def _audio_vco_step(
        phase: float,
        modulation: float,
        *,
        base_frequency: float,
        sample_rate: float,
    ) -> tuple[float, float]:
        modulation = min(1.0, max(-1.0, float(modulation)))
        frequency = min(
            sample_rate * 0.45,
            base_frequency * 2.0 ** (4.0 * modulation),
        )
        value = 1.0 if phase < 0.5 else -1.0
        return value, (phase + frequency / sample_rate) % 1.0

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
    "WOGGLEBUG_MANIFEST",
    "Wogglebug",
    "WogglebugParameters",
]
