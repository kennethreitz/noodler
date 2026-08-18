"""General-purpose oscillator and noise sources for the built-in library."""

from collections.abc import Mapping
import math

import numpy as np
from numpy.typing import ArrayLike
from pydantic import BaseModel, ConfigDict, Field

from noodler.module_providers import ModuleManifest, PortDirection, SignalType

from ._dsp import FloatBlock, block, empty_outputs, port, rising_edge


CLASSIC_VCO_OUTPUTS = ("sine", "triangle", "saw", "pulse", "sub")
FM_VOICE_OUTPUTS = ("output", "carrier", "modulator")
SUPERSAW_OUTPUTS = ("cluster", "center", "sub")
NOISE_OUTPUTS = ("white", "pink", "brown", "crackle", "sample_hold")


class ClassicVCOParameters(BaseModel):
    """Panel controls for a conventional multi-wave oscillator."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    frequency: float = Field(default=110.0, gt=0.0, le=20_000.0)
    fine_tune_cents: float = Field(default=0.0, ge=-100.0, le=100.0)
    fm_amount: float = Field(default=0.0, ge=-1.0, le=1.0)
    pulse_width: float = Field(default=0.5, ge=0.01, le=0.99)
    amplitude: float = Field(default=0.2, ge=0.0, le=1.0)


CLASSIC_VCO_MANIFEST = ModuleManifest(
    id="classic_vco",
    name="Classic VCO",
    category="Oscillators",
    description="A familiar multi-wave VCO with exponential FM, PWM, sync, and a sub octave.",
    ports=(
        port("pitch", "1 V/oct", PortDirection.INPUT, SignalType.CV, "Calibrated pitch input."),
        port("fm", "FM", PortDirection.INPUT, SignalType.CV, "Bipolar exponential frequency modulation."),
        port("pwm", "PWM", PortDirection.INPUT, SignalType.CV, "Bipolar pulse-width modulation."),
        port("sync", "Sync", PortDirection.INPUT, SignalType.TRIGGER, "Rising-edge hard sync."),
        port("sine", "Sine", PortDirection.OUTPUT, SignalType.AUDIO, "Sine output."),
        port("triangle", "Triangle", PortDirection.OUTPUT, SignalType.AUDIO, "Triangle output."),
        port("saw", "Saw", PortDirection.OUTPUT, SignalType.AUDIO, "Rising saw output."),
        port("pulse", "Pulse", PortDirection.OUTPUT, SignalType.AUDIO, "Variable-width pulse output."),
        port("sub", "Sub", PortDirection.OUTPUT, SignalType.AUDIO, "Square wave one octave below."),
    ),
)


class ClassicVCO:
    """Generate the usual oscillator family from one phase accumulator."""

    manifest = CLASSIC_VCO_MANIFEST

    def __init__(self, parameters: ClassicVCOParameters | None = None) -> None:
        self.parameters = parameters or ClassicVCOParameters()
        self.reset()

    def reset(self, phase: float = 0.0) -> None:
        self._phase = float(phase) % 1.0
        self._sub_phase = (float(phase) * 0.5) % 1.0
        self._sync_high = False

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
            return empty_outputs(CLASSIC_VCO_OUTPUTS)
        inputs = inputs or {}
        pitch = block("pitch", inputs, frame_count)
        fm = block("fm", inputs, frame_count)
        pwm = block("pwm", inputs, frame_count)
        sync = block("sync", inputs, frame_count)
        base = self.parameters.frequency * 2.0 ** (
            self.parameters.fine_tune_cents / 1200.0
        )
        frequency = base * np.exp2(
            np.clip(pitch + self.parameters.fm_amount * fm, -16.0, 16.0)
        )
        frequency = np.clip(frequency, 0.0, sample_rate * 0.45)
        phases = np.empty(frame_count, dtype=np.float64)
        sub_phases = np.empty(frame_count, dtype=np.float64)
        phase = self._phase
        sub_phase = self._sub_phase
        sync_high = self._sync_high
        for sample in range(frame_count):
            event, next_sync_high = rising_edge(sync[sample], sync_high)
            if event:
                phase = 0.0
                sub_phase = 0.0
            phases[sample] = phase
            sub_phases[sample] = sub_phase
            increment = float(frequency[sample]) / sample_rate
            phase = (phase + increment) % 1.0
            sub_phase = (sub_phase + increment * 0.5) % 1.0
            sync_high = next_sync_high
        self._phase = phase
        self._sub_phase = sub_phase
        self._sync_high = sync_high

        width = np.clip(self.parameters.pulse_width + 0.49 * pwm, 0.01, 0.99)
        amplitude = self.parameters.amplitude
        values = {
            "sine": np.sin(math.tau * phases),
            "triangle": 1.0 - 4.0 * np.abs(phases - 0.5),
            "saw": 2.0 * phases - 1.0,
            "pulse": np.where(phases < width, 1.0, -1.0),
            "sub": np.where(sub_phases < 0.5, 1.0, -1.0),
        }
        return {
            name: np.asarray(value * amplitude, dtype=np.float32)
            for name, value in values.items()
        }


class FMVoiceParameters(BaseModel):
    """Controls for a two-operator phase-modulation voice."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    frequency: float = Field(default=110.0, gt=0.0, le=20_000.0)
    ratio: float = Field(default=2.0, ge=0.125, le=16.0)
    index: float = Field(default=1.5, ge=0.0, le=12.0)
    feedback: float = Field(default=0.08, ge=0.0, le=0.95)
    amplitude: float = Field(default=0.18, ge=0.0, le=1.0)


FM_VOICE_MANIFEST = ModuleManifest(
    id="fm_voice",
    name="Two-Operator FM Voice",
    category="Oscillators",
    description="A sine carrier and modulator with ratio, index, feedback, and external phase modulation.",
    ports=(
        port("pitch", "1 V/oct", PortDirection.INPUT, SignalType.CV, "Carrier pitch."),
        port("ratio_cv", "Ratio CV", PortDirection.INPUT, SignalType.CV, "Exponential modulator-ratio control."),
        port("index_cv", "Index CV", PortDirection.INPUT, SignalType.CV, "Bipolar index offset."),
        port("mod", "External Mod", PortDirection.INPUT, SignalType.CV, "Additional audio/CV phase modulation."),
        port("output", "FM Out", PortDirection.OUTPUT, SignalType.AUDIO, "Modulated carrier output."),
        port("carrier", "Carrier", PortDirection.OUTPUT, SignalType.AUDIO, "Unmodulated carrier sine."),
        port("modulator", "Modulator", PortDirection.OUTPUT, SignalType.AUDIO, "Internal modulator sine."),
    ),
)


class FMVoice:
    """Render a compact two-operator FM/phase-modulation voice."""

    manifest = FM_VOICE_MANIFEST

    def __init__(self, parameters: FMVoiceParameters | None = None) -> None:
        self.parameters = parameters or FMVoiceParameters()
        self.reset()

    def reset(self) -> None:
        self._carrier_phase = 0.0
        self._modulator_phase = 0.0
        self._feedback_sample = 0.0

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
            return empty_outputs(FM_VOICE_OUTPUTS)
        inputs = inputs or {}
        pitch = block("pitch", inputs, frame_count)
        ratio_cv = block("ratio_cv", inputs, frame_count)
        index_cv = block("index_cv", inputs, frame_count)
        external_mod = block("mod", inputs, frame_count)
        carrier_frequency = np.clip(
            self.parameters.frequency * np.exp2(np.clip(pitch, -16.0, 16.0)),
            0.0,
            sample_rate * 0.45,
        )
        ratio = np.clip(
            self.parameters.ratio * np.exp2(np.clip(ratio_cv, -4.0, 4.0)),
            0.03125,
            32.0,
        )
        index = np.clip(self.parameters.index + 6.0 * index_cv, 0.0, 18.0)
        output = np.empty(frame_count, dtype=np.float64)
        carrier = np.empty(frame_count, dtype=np.float64)
        modulator = np.empty(frame_count, dtype=np.float64)
        carrier_phase = self._carrier_phase
        modulator_phase = self._modulator_phase
        feedback_sample = self._feedback_sample
        for sample in range(frame_count):
            plain = math.sin(math.tau * carrier_phase)
            mod = math.sin(
                math.tau * modulator_phase
                + self.parameters.feedback * feedback_sample
            )
            value = math.sin(
                math.tau * carrier_phase
                + float(index[sample]) * mod
                + math.pi * float(external_mod[sample])
            )
            carrier[sample] = plain
            modulator[sample] = mod
            output[sample] = value
            feedback_sample = value
            carrier_phase = (
                carrier_phase + float(carrier_frequency[sample]) / sample_rate
            ) % 1.0
            modulator_phase = (
                modulator_phase
                + float(carrier_frequency[sample] * ratio[sample]) / sample_rate
            ) % 1.0
        self._carrier_phase = carrier_phase
        self._modulator_phase = modulator_phase
        self._feedback_sample = feedback_sample
        amplitude = self.parameters.amplitude
        return {
            "output": np.asarray(output * amplitude, dtype=np.float32),
            "carrier": np.asarray(carrier * amplitude, dtype=np.float32),
            "modulator": np.asarray(modulator * amplitude, dtype=np.float32),
        }


class SupersawParameters(BaseModel):
    """Controls for a detuned unison saw cluster."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    frequency: float = Field(default=110.0, gt=0.0, le=20_000.0)
    voices: int = Field(default=7, ge=3, le=11)
    detune_cents: float = Field(default=11.0, ge=0.0, le=50.0)
    curve: float = Field(default=0.6, ge=0.0, le=1.0)
    amplitude: float = Field(default=0.18, ge=0.0, le=1.0)


SUPERSAW_MANIFEST = ModuleManifest(
    id="supersaw",
    name="Supersaw Cluster",
    category="Oscillators",
    description="An odd-numbered unison saw bank with curved detuning and a centered sub output.",
    ports=(
        port("pitch", "1 V/oct", PortDirection.INPUT, SignalType.CV, "Cluster pitch."),
        port("fm", "FM", PortDirection.INPUT, SignalType.CV, "Exponential frequency modulation."),
        port("detune_cv", "Detune CV", PortDirection.INPUT, SignalType.CV, "Bipolar detune-width offset."),
        port("cluster", "Cluster", PortDirection.OUTPUT, SignalType.AUDIO, "Averaged detuned saw bank."),
        port("center", "Center", PortDirection.OUTPUT, SignalType.AUDIO, "Undetuned center saw."),
        port("sub", "Sub", PortDirection.OUTPUT, SignalType.AUDIO, "Center square one octave below."),
    ),
)


class SupersawOscillator:
    """Render a mono detuned saw ensemble with stable per-voice phases."""

    manifest = SUPERSAW_MANIFEST

    def __init__(self, parameters: SupersawParameters | None = None) -> None:
        self.parameters = parameters or SupersawParameters()
        self.reset()

    def reset(self) -> None:
        self._phases = np.linspace(
            0.0,
            1.0,
            self.parameters.voices,
            endpoint=False,
            dtype=np.float64,
        )
        self._sub_phase = 0.0

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
            return empty_outputs(SUPERSAW_OUTPUTS)
        if self._phases.size != self.parameters.voices:
            self.reset()
        inputs = inputs or {}
        pitch = block("pitch", inputs, frame_count)
        fm = block("fm", inputs, frame_count)
        detune_cv = block("detune_cv", inputs, frame_count)
        base_frequency = np.clip(
            self.parameters.frequency * np.exp2(np.clip(pitch + fm, -16.0, 16.0)),
            0.0,
            sample_rate * 0.4,
        )
        raw_offsets = np.linspace(-1.0, 1.0, self.parameters.voices)
        exponent = 1.0 + 2.0 * self.parameters.curve
        offsets = np.sign(raw_offsets) * np.abs(raw_offsets) ** exponent
        cluster = np.empty(frame_count, dtype=np.float64)
        center = np.empty(frame_count, dtype=np.float64)
        sub = np.empty(frame_count, dtype=np.float64)
        phases = self._phases.copy()
        sub_phase = self._sub_phase
        center_index = self.parameters.voices // 2
        for sample in range(frame_count):
            width = max(
                0.0,
                self.parameters.detune_cents * (1.0 + float(detune_cv[sample])),
            )
            ratios = np.exp2(offsets * width / 1200.0)
            saws = 2.0 * phases - 1.0
            cluster[sample] = float(np.mean(saws))
            center[sample] = float(saws[center_index])
            sub[sample] = 1.0 if sub_phase < 0.5 else -1.0
            increments = float(base_frequency[sample]) * ratios / sample_rate
            phases = np.mod(phases + increments, 1.0)
            sub_phase = (
                sub_phase + float(base_frequency[sample]) / (2.0 * sample_rate)
            ) % 1.0
        self._phases = phases
        self._sub_phase = sub_phase
        amplitude = self.parameters.amplitude
        return {
            "cluster": np.asarray(cluster * amplitude, dtype=np.float32),
            "center": np.asarray(center * amplitude, dtype=np.float32),
            "sub": np.asarray(sub * amplitude, dtype=np.float32),
        }


class NoiseSourceParameters(BaseModel):
    """Controls for a deterministic family of noise and random voltages."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    level: float = Field(default=0.2, ge=0.0, le=1.0)
    clock_rate_hz: float = Field(default=2.0, ge=0.01, le=2_000.0)
    crackle_density: float = Field(default=0.12, ge=0.0, le=1.0)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)


NOISE_SOURCE_MANIFEST = ModuleManifest(
    id="noise_source",
    name="Noise / Random Source",
    category="Noise & Random",
    description="Deterministic white, pink, brown, crackle, and clocked sample-and-hold outputs.",
    ports=(
        port("clock", "Clock", PortDirection.INPUT, SignalType.GATE, "External sample-and-hold clock."),
        port("rate_cv", "Rate CV", PortDirection.INPUT, SignalType.CV, "Exponential internal-clock modulation."),
        port("white", "White", PortDirection.OUTPUT, SignalType.AUDIO, "Flat-spectrum noise."),
        port("pink", "Pink", PortDirection.OUTPUT, SignalType.AUDIO, "Approximately 1/f noise."),
        port("brown", "Brown", PortDirection.OUTPUT, SignalType.AUDIO, "Integrated low-frequency noise."),
        port("crackle", "Crackle", PortDirection.OUTPUT, SignalType.AUDIO, "Sparse decaying impulses."),
        port("sample_hold", "S&H", PortDirection.OUTPUT, SignalType.CV, "Clocked held random voltage."),
    ),
)


class NoiseSource:
    """Generate related deterministic noise colors and sampled randomness."""

    manifest = NOISE_SOURCE_MANIFEST

    def __init__(self, parameters: NoiseSourceParameters | None = None) -> None:
        self.parameters = parameters or NoiseSourceParameters()
        self.reset()

    def reset(self, *, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(
            self.parameters.seed if seed is None else seed
        )
        self._pink = np.zeros(3, dtype=np.float64)
        self._brown = 0.0
        self._crackle = 0.0
        self._held = 0.0
        self._clock_phase = 0.0
        self._clock_high = False

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
            return empty_outputs(NOISE_OUTPUTS)
        inputs = inputs or {}
        external_clock = "clock" in inputs
        clock = block("clock", inputs, frame_count)
        rate_cv = block("rate_cv", inputs, frame_count)
        outputs = {
            name: np.empty(frame_count, dtype=np.float64)
            for name in NOISE_OUTPUTS
        }
        pink = self._pink.copy()
        brown = self._brown
        crackle = self._crackle
        held = self._held
        clock_phase = self._clock_phase
        clock_high_state = self._clock_high
        for sample in range(frame_count):
            # Draw in sample order so changing audio block boundaries cannot
            # change the deterministic relationship between noise colors.
            value = float(self._rng.uniform(-1.0, 1.0))
            pink[0] = 0.99765 * pink[0] + value * 0.0990460
            pink[1] = 0.96300 * pink[1] + value * 0.2965164
            pink[2] = 0.57000 * pink[2] + value * 1.0526913
            pink_value = (pink.sum() + value * 0.1848) * 0.23
            brown = float(np.clip(0.995 * brown + 0.055 * value, -1.0, 1.0))
            if self._rng.random() < self.parameters.crackle_density / sample_rate * 35.0:
                crackle = float(self._rng.uniform(-1.0, 1.0))
            crackle *= 0.992

            clock_event, clock_high = rising_edge(clock[sample], clock_high_state)
            if not external_clock:
                rate = self.parameters.clock_rate_hz * 2.0 ** float(
                    np.clip(rate_cv[sample], -12.0, 12.0)
                )
                clock_phase += min(sample_rate * 0.45, rate) / sample_rate
                clock_event = clock_phase >= 1.0
                if clock_event:
                    clock_phase %= 1.0
            if clock_event:
                held = value

            outputs["white"][sample] = value
            outputs["pink"][sample] = pink_value
            outputs["brown"][sample] = brown
            outputs["crackle"][sample] = crackle
            outputs["sample_hold"][sample] = held
            clock_high_state = clock_high
        self._pink = pink
        self._brown = brown
        self._crackle = crackle
        self._held = held
        self._clock_phase = clock_phase
        self._clock_high = clock_high_state
        level = self.parameters.level
        return {
            name: np.asarray(np.clip(value, -1.0, 1.0) * level, dtype=np.float32)
            for name, value in outputs.items()
        }


__all__ = [
    "CLASSIC_VCO_MANIFEST",
    "FM_VOICE_MANIFEST",
    "NOISE_SOURCE_MANIFEST",
    "SUPERSAW_MANIFEST",
    "ClassicVCO",
    "ClassicVCOParameters",
    "FMVoice",
    "FMVoiceParameters",
    "NoiseSource",
    "NoiseSourceParameters",
    "SupersawOscillator",
    "SupersawParameters",
]
