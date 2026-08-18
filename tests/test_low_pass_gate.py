import numpy as np
import pytest
from pydantic import ValidationError

from noodler.module_providers import PortDirection, SignalType
from noodler.module_providers.builtin import (
    LOW_PASS_GATE_MANIFEST,
    LowPassGate,
    LowPassGateParameters,
)


def test_manifest_exposes_strike_audio_and_envelope_paths() -> None:
    ports = {port.id: port for port in LOW_PASS_GATE_MANIFEST.ports}

    assert set(ports) == {
        "audio",
        "strike",
        "level_cv",
        "decay_cv",
        "output",
        "envelope",
    }
    assert ports["audio"].direction is PortDirection.INPUT
    assert ports["strike"].signal_type is SignalType.TRIGGER
    assert ports["output"].signal_type is SignalType.AUDIO
    assert ports["envelope"].signal_type is SignalType.CV


def test_strike_reopens_a_decayed_gate() -> None:
    gate = LowPassGate(
        LowPassGateParameters(
            decay_seconds=0.02,
            brightness=0.7,
            character=0.0,
            level=1.0,
        )
    )
    gate.process(500, 1_000.0, {"audio": 1.0})

    quiet = gate.process(8, 1_000.0, {"audio": 1.0})
    struck = gate.process(
        8,
        1_000.0,
        {"audio": 1.0, "strike": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
    )

    assert struck["envelope"][1] > 0.9
    assert struck["output"].max() > quiet["output"].max() * 20.0


def test_processing_is_stable_across_audio_block_boundaries() -> None:
    parameters = LowPassGateParameters(
        decay_seconds=0.3,
        brightness=0.55,
        character=0.4,
        level=0.8,
    )
    continuous = LowPassGate(parameters.model_copy())
    split = LowPassGate(parameters.model_copy())
    audio = np.sin(np.linspace(0.0, 8.0 * np.pi, 200, endpoint=False))
    strike = np.zeros(200)
    strike[[25, 120]] = 1.0

    expected = continuous.process(
        200,
        2_000.0,
        {"audio": audio, "strike": strike},
    )
    first = split.process(
        73,
        2_000.0,
        {"audio": audio[:73], "strike": strike[:73]},
    )
    second = split.process(
        127,
        2_000.0,
        {"audio": audio[73:], "strike": strike[73:]},
    )

    for name in expected:
        np.testing.assert_allclose(
            np.concatenate((first[name], second[name])),
            expected[name],
        )


def test_parameters_remain_bounded() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        LowPassGateParameters(brightness=1.1)

