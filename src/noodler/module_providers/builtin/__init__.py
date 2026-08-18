"""Noodler's built-in module provider."""

from types import MappingProxyType

from pydantic import BaseModel

from noodler.module_providers import ProviderManifest

from .brains import (
    ARPEGGIO_BRAIN_MANIFEST,
    HARMONY_BRAIN_MANIFEST,
    MELODY_BRAIN_MANIFEST,
    ArpeggioBrain,
    ArpeggioBrainParameters,
    ArpeggioPattern,
    HarmonicStyle,
    HarmonyBrain,
    HarmonyBrainParameters,
    MelodyBrain,
    MelodyBrainParameters,
    MelodyStyle,
)
from .complex_vco import (
    COMPLEX_VCO_MANIFEST,
    ComplexVCO,
    ComplexVCOParameters,
    WaveB,
)
from .function_utility import (
    FUNCTION_UTILITY_MANIFEST,
    MAX_FUNCTION_STAGE_SECONDS,
    MIN_FUNCTION_STAGE_SECONDS,
    FunctionChannelParameters,
    FunctionStage,
    FunctionUtility,
    FunctionUtilityParameters,
)
from .delay import ECHO_DELAY_MANIFEST, EchoDelay, EchoDelayParameters
from .dynamics import (
    ADSR_ENVELOPE_MANIFEST,
    VCA_MANIFEST,
    ADSREnvelope,
    ADSRParameters,
    EnvelopeStage,
    VCA,
    VCAParameters,
    VCAResponse,
)
from .filters import (
    LADDER_FILTER_MANIFEST,
    STATE_VARIABLE_FILTER_MANIFEST,
    LadderFilter,
    LadderFilterParameters,
    StateVariableFilter,
    StateVariableFilterParameters,
)
from .instrument import (
    INSTRUMENT_NAMES,
    INSTRUMENT_VOICE_MANIFEST,
    InstrumentVoice,
    InstrumentVoiceParameters,
    instrument_voice,
)
from .pytheory_voice import (
    PYTHEORY_VOICE_MANIFEST,
    PyTheoryVoice,
    PyTheoryVoiceParameters,
    render_note,
)
from .master import (
    MASTER_CHANNELS,
    MASTER_MIXER_MANIFEST,
    MasterMixer,
    MasterMixerParameters,
)
from .musical import (
    KEY_MANIFEST,
    QUANTIZER_MANIFEST,
    Key,
    KeyParameters,
    Quantizer,
    QuantizerParameters,
)
from .low_pass_gate import (
    LOW_PASS_GATE_MANIFEST,
    LowPassGate,
    LowPassGateParameters,
)
from .polarizing_mixer import (
    POLARIZING_MIXER_MANIFEST,
    PolarizingMixer,
    PolarizingMixerParameters,
    polarizing_mixer_manifest,
)
from .oscillators import (
    CLASSIC_VCO_MANIFEST,
    FM_VOICE_MANIFEST,
    NOISE_SOURCE_MANIFEST,
    SUPERSAW_MANIFEST,
    ClassicVCO,
    ClassicVCOParameters,
    FMVoice,
    FMVoiceParameters,
    NoiseSource,
    NoiseSourceParameters,
    SupersawOscillator,
    SupersawParameters,
)
from .scale_generator import (
    SCALE_GENERATOR_MANIFEST,
    SUPPORTED_SCALE_SYSTEMS,
    TONICS,
    ScaleGenerator,
    ScaleGeneratorParameters,
    SequencePattern,
    scale_names,
)
from .reverb import REVERB_MANIFEST, Reverb, ReverbParameters
from .wogglebug import (
    WOGGLEBUG_MANIFEST,
    Wogglebug,
    WogglebugParameters,
)


BUILTIN_PROVIDER_MANIFEST = ProviderManifest(
    id="noodler.builtin",
    name="Noodler built-in modules",
    version="0.1.0",
    modules=(
        INSTRUMENT_VOICE_MANIFEST,
        PYTHEORY_VOICE_MANIFEST,
        MASTER_MIXER_MANIFEST,
        KEY_MANIFEST,
        QUANTIZER_MANIFEST,
        MELODY_BRAIN_MANIFEST,
        HARMONY_BRAIN_MANIFEST,
        ARPEGGIO_BRAIN_MANIFEST,
        COMPLEX_VCO_MANIFEST,
        CLASSIC_VCO_MANIFEST,
        FM_VOICE_MANIFEST,
        SUPERSAW_MANIFEST,
        NOISE_SOURCE_MANIFEST,
        STATE_VARIABLE_FILTER_MANIFEST,
        LADDER_FILTER_MANIFEST,
        ADSR_ENVELOPE_MANIFEST,
        VCA_MANIFEST,
        POLARIZING_MIXER_MANIFEST,
        FUNCTION_UTILITY_MANIFEST,
        WOGGLEBUG_MANIFEST,
        SCALE_GENERATOR_MANIFEST,
        LOW_PASS_GATE_MANIFEST,
        ECHO_DELAY_MANIFEST,
        REVERB_MANIFEST,
    ),
)

BUILTIN_MODULE_TYPES = MappingProxyType({
    manifest.id: module_type
    for manifest, module_type in (
        (INSTRUMENT_VOICE_MANIFEST, InstrumentVoice),
        (PYTHEORY_VOICE_MANIFEST, PyTheoryVoice),
        (MASTER_MIXER_MANIFEST, MasterMixer),
        (KEY_MANIFEST, Key),
        (QUANTIZER_MANIFEST, Quantizer),
        (MELODY_BRAIN_MANIFEST, MelodyBrain),
        (HARMONY_BRAIN_MANIFEST, HarmonyBrain),
        (ARPEGGIO_BRAIN_MANIFEST, ArpeggioBrain),
        (COMPLEX_VCO_MANIFEST, ComplexVCO),
        (CLASSIC_VCO_MANIFEST, ClassicVCO),
        (FM_VOICE_MANIFEST, FMVoice),
        (SUPERSAW_MANIFEST, SupersawOscillator),
        (NOISE_SOURCE_MANIFEST, NoiseSource),
        (STATE_VARIABLE_FILTER_MANIFEST, StateVariableFilter),
        (LADDER_FILTER_MANIFEST, LadderFilter),
        (ADSR_ENVELOPE_MANIFEST, ADSREnvelope),
        (VCA_MANIFEST, VCA),
        (POLARIZING_MIXER_MANIFEST, PolarizingMixer),
        (FUNCTION_UTILITY_MANIFEST, FunctionUtility),
        (WOGGLEBUG_MANIFEST, Wogglebug),
        (SCALE_GENERATOR_MANIFEST, ScaleGenerator),
        (LOW_PASS_GATE_MANIFEST, LowPassGate),
        (ECHO_DELAY_MANIFEST, EchoDelay),
        (REVERB_MANIFEST, Reverb),
    )
})


class BuiltinProvider:
    """Expose the modules that ship with Noodler."""

    manifest = BUILTIN_PROVIDER_MANIFEST

    def create(self, module_id: str, parameters: object | None = None) -> object:
        """Create a built-in module by the same stable ID used in its manifest."""
        try:
            module_type = BUILTIN_MODULE_TYPES[module_id]
        except KeyError as exc:
            raise KeyError(f"unknown built-in module: {module_id}") from exc
        module = module_type()
        if parameters is None:
            return module
        defaults = getattr(module, "parameters", None)
        if not isinstance(defaults, BaseModel):
            raise TypeError(f"{module_id} has no validated parameter model")
        validated = type(defaults).model_validate(parameters)
        return module_type(validated)


__all__ = [
    "ADSR_ENVELOPE_MANIFEST",
    "PYTHEORY_VOICE_MANIFEST",
    "PyTheoryVoice",
    "PyTheoryVoiceParameters",
    "render_note",
    "INSTRUMENT_NAMES",
    "INSTRUMENT_VOICE_MANIFEST",
    "InstrumentVoice",
    "InstrumentVoiceParameters",
    "instrument_voice",
    "MASTER_CHANNELS",
    "MASTER_MIXER_MANIFEST",
    "MasterMixer",
    "MasterMixerParameters",
    "KEY_MANIFEST",
    "Key",
    "KeyParameters",
    "QUANTIZER_MANIFEST",
    "Quantizer",
    "QuantizerParameters",
    "ARPEGGIO_BRAIN_MANIFEST",
    "BUILTIN_PROVIDER_MANIFEST",
    "BUILTIN_MODULE_TYPES",
    "BuiltinProvider",
    "CLASSIC_VCO_MANIFEST",
    "COMPLEX_VCO_MANIFEST",
    "ComplexVCO",
    "ComplexVCOParameters",
    "ECHO_DELAY_MANIFEST",
    "EchoDelay",
    "EchoDelayParameters",
    "EnvelopeStage",
    "FM_VOICE_MANIFEST",
    "FMVoice",
    "FMVoiceParameters",
    "FUNCTION_UTILITY_MANIFEST",
    "MAX_FUNCTION_STAGE_SECONDS",
    "MIN_FUNCTION_STAGE_SECONDS",
    "FunctionChannelParameters",
    "FunctionStage",
    "FunctionUtility",
    "FunctionUtilityParameters",
    "HARMONY_BRAIN_MANIFEST",
    "HarmonicStyle",
    "HarmonyBrain",
    "HarmonyBrainParameters",
    "LADDER_FILTER_MANIFEST",
    "LOW_PASS_GATE_MANIFEST",
    "LowPassGate",
    "LowPassGateParameters",
    "MELODY_BRAIN_MANIFEST",
    "MelodyBrain",
    "MelodyBrainParameters",
    "MelodyStyle",
    "NOISE_SOURCE_MANIFEST",
    "NoiseSource",
    "NoiseSourceParameters",
    "POLARIZING_MIXER_MANIFEST",
    "PolarizingMixer",
    "PolarizingMixerParameters",
    "REVERB_MANIFEST",
    "Reverb",
    "ReverbParameters",
    "STATE_VARIABLE_FILTER_MANIFEST",
    "SCALE_GENERATOR_MANIFEST",
    "SUPPORTED_SCALE_SYSTEMS",
    "ScaleGenerator",
    "ScaleGeneratorParameters",
    "SequencePattern",
    "StateVariableFilter",
    "StateVariableFilterParameters",
    "SUPERSAW_MANIFEST",
    "SupersawOscillator",
    "SupersawParameters",
    "TONICS",
    "VCA",
    "VCA_MANIFEST",
    "VCAParameters",
    "VCAResponse",
    "WaveB",
    "WOGGLEBUG_MANIFEST",
    "Wogglebug",
    "WogglebugParameters",
    "ADSREnvelope",
    "ADSRParameters",
    "ArpeggioBrain",
    "ArpeggioBrainParameters",
    "ArpeggioPattern",
    "ClassicVCO",
    "ClassicVCOParameters",
    "LadderFilter",
    "LadderFilterParameters",
    "polarizing_mixer_manifest",
    "scale_names",
]
