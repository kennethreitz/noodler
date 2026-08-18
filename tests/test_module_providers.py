import pytest
from pydantic import ValidationError

from noodler.module_providers import (
    AudioCvPolicy,
    ConnectionDisposition,
    ModuleManifest,
    PortDirection,
    PortManifest,
    ProviderManifest,
    SignalType,
    assess_connection,
)
from noodler.module_providers.builtin import (
    BUILTIN_MODULE_TYPES,
    BUILTIN_PROVIDER_MANIFEST,
    BuiltinProvider,
)


def port(
    port_id: str,
    direction: PortDirection,
    signal_type: SignalType,
    *,
    policy: AudioCvPolicy = AudioCvPolicy.WARN,
) -> PortManifest:
    return PortManifest(
        id=port_id,
        name=port_id.replace("_", " ").title(),
        direction=direction,
        signal_type=signal_type,
        audio_cv_policy=policy,
    )


def test_matching_signal_types_connect_directly() -> None:
    assessment = assess_connection(
        port("oscillator", PortDirection.OUTPUT, SignalType.AUDIO),
        port("input", PortDirection.INPUT, SignalType.AUDIO),
    )

    assert assessment.compatible is True
    assert assessment.disposition is ConnectionDisposition.DIRECT


@pytest.mark.parametrize(
    ("source_type", "target_type"),
    [
        (SignalType.AUDIO, SignalType.CV),
        (SignalType.CV, SignalType.AUDIO),
    ],
)
def test_audio_and_cv_cross_link_with_an_advisory(
    source_type: SignalType,
    target_type: SignalType,
) -> None:
    assessment = assess_connection(
        port("source", PortDirection.OUTPUT, source_type),
        port("target", PortDirection.INPUT, target_type),
    )

    assert assessment.compatible is True
    assert assessment.disposition is ConnectionDisposition.ADVISORY


def test_audio_and_cv_can_explicitly_opt_in() -> None:
    assessment = assess_connection(
        port(
            "source",
            PortDirection.OUTPUT,
            SignalType.AUDIO,
            policy=AudioCvPolicy.ALLOW,
        ),
        port(
            "target",
            PortDirection.INPUT,
            SignalType.CV,
            policy=AudioCvPolicy.ALLOW,
        ),
    )

    assert assessment.compatible is True
    assert assessment.disposition is ConnectionDisposition.CROSS_SIGNAL


def test_either_endpoint_can_reject_audio_cv_cross_linking() -> None:
    assessment = assess_connection(
        port("source", PortDirection.OUTPUT, SignalType.CV),
        port(
            "target",
            PortDirection.INPUT,
            SignalType.AUDIO,
            policy=AudioCvPolicy.REJECT,
        ),
    )

    assert assessment.compatible is False
    assert assessment.disposition is ConnectionDisposition.REJECTED


def test_unrelated_signal_types_remain_incompatible() -> None:
    assessment = assess_connection(
        port("source", PortDirection.OUTPUT, SignalType.GATE),
        port("target", PortDirection.INPUT, SignalType.AUDIO),
    )

    assert assessment.compatible is False
    assert assessment.disposition is ConnectionDisposition.REJECTED


def test_provider_manifests_round_trip_through_json() -> None:
    manifest = ProviderManifest(
        id="noodler.builtin",
        name="Built-in modules",
        version="0.1.0",
        modules=(
            ModuleManifest(
                id="oscillator",
                name="Oscillator",
                ports=(
                    port("pitch", PortDirection.INPUT, SignalType.CV),
                    port("audio", PortDirection.OUTPUT, SignalType.AUDIO),
                ),
            ),
        ),
    )

    restored = ProviderManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest


def test_module_port_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="module port IDs must be unique"):
        ModuleManifest(
            id="invalid",
            name="Invalid",
            ports=(
                port("signal", PortDirection.INPUT, SignalType.CV),
                port("signal", PortDirection.OUTPUT, SignalType.CV),
            ),
        )


def test_builtin_provider_can_create_every_catalog_module_by_stable_id() -> None:
    provider = BuiltinProvider()

    assert len(BUILTIN_PROVIDER_MANIFEST.modules) == len(BUILTIN_MODULE_TYPES) >= 23
    assert set(BUILTIN_MODULE_TYPES) == {
        manifest.id for manifest in BUILTIN_PROVIDER_MANIFEST.modules
    }
    for manifest in provider.manifest.modules:
        module = provider.create(manifest.id)
        assert module.manifest.id == manifest.id

    with pytest.raises(KeyError, match="unknown built-in module"):
        provider.create("imaginary_module")
