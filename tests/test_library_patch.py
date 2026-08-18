import numpy as np

from noodler.module_providers.builtin import (
    ADSREnvelope,
    ADSRParameters,
    ArpeggioBrain,
    ArpeggioBrainParameters,
    ArpeggioPattern,
    ClassicVCO,
    ClassicVCOParameters,
    EchoDelay,
    EchoDelayParameters,
    HarmonyBrain,
    HarmonyBrainParameters,
    StateVariableFilter,
    StateVariableFilterParameters,
    VCA,
    Wogglebug,
    WogglebugParameters,
)
from noodler.patch import PatchGraph


def test_brains_and_subtractive_modules_form_an_executable_voice() -> None:
    patch = PatchGraph()
    patch.add_module(
        "clock",
        Wogglebug(WogglebugParameters(clock_rate_hz=4.0, seed=7)),
    )
    patch.add_module(
        "harmony",
        HarmonyBrain(HarmonyBrainParameters(length=4, seed=7)),
    )
    patch.add_module(
        "arpeggio",
        ArpeggioBrain(
            ArpeggioBrainParameters(
                pattern=ArpeggioPattern.UP,
                octave_range=1,
            )
        ),
    )
    patch.add_module(
        "oscillator",
        ClassicVCO(ClassicVCOParameters(amplitude=0.25)),
    )
    patch.add_module(
        "filter",
        StateVariableFilter(
            StateVariableFilterParameters(cutoff_hz=1_800.0)
        ),
    )
    patch.add_module(
        "envelope",
        ADSREnvelope(
            ADSRParameters(
                attack_seconds=0.005,
                decay_seconds=0.05,
                sustain=0.5,
                release_seconds=0.08,
            )
        ),
    )
    patch.add_module("vca", VCA())
    patch.add_module(
        "delay",
        EchoDelay(
            EchoDelayParameters(time_seconds=0.08, feedback=0.3, mix=0.25)
        ),
    )
    patch.connect("clock", "clock", "harmony", "clock")
    for voice in range(1, 5):
        patch.connect(
            "harmony",
            f"voice_{voice}",
            "arpeggio",
            f"voice_{voice}",
        )
    patch.connect("clock", "clock", "arpeggio", "clock")
    patch.connect("arpeggio", "pitch", "oscillator", "pitch")
    patch.connect("arpeggio", "gate", "envelope", "gate")
    patch.connect("oscillator", "saw", "filter", "audio")
    patch.connect("filter", "low", "vca", "signal")
    patch.connect("envelope", "envelope", "vca", "level_cv")
    patch.connect("vca", "output", "delay", "audio")
    patch.connect_output("delay", "output")

    output = patch.render(8_000, 8_000.0)

    assert patch.processing_order == (
        "clock",
        "harmony",
        "arpeggio",
        "oscillator",
        "envelope",
        "filter",
        "vca",
        "delay",
    )
    assert np.all(np.isfinite(output))
    assert float(np.max(np.abs(output))) > 0.01
    assert float(np.max(np.abs(output))) <= 1.0

