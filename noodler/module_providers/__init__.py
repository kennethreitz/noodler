"""Serializable contracts for Noodler module providers.

Provider packages exchange Pydantic manifests with Noodler. Runtime DSP APIs
remain exploratory while the first working modules teach us what they need.
"""

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator


IDENTIFIER_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"


class SignalType(StrEnum):
    """The semantic type carried by a module port."""

    AUDIO = "audio"
    CV = "cv"
    GATE = "gate"
    TRIGGER = "trigger"
    MUSICAL = "musical"


class PortDirection(StrEnum):
    """The direction in which a port carries its signal."""

    INPUT = "input"
    OUTPUT = "output"


class AudioCvPolicy(StrEnum):
    """How a port treats connections across the audio/CV boundary."""

    ALLOW = "allow"
    WARN = "warn"
    REJECT = "reject"


class ConnectionDisposition(StrEnum):
    """The result of assessing two ports before creating a cable."""

    DIRECT = "direct"
    CROSS_SIGNAL = "cross_signal"
    ADVISORY = "advisory"
    REJECTED = "rejected"


class PortManifest(BaseModel):
    """A serializable input or output exposed by a module type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    direction: PortDirection
    signal_type: SignalType
    description: str = ""
    audio_cv_policy: AudioCvPolicy = AudioCvPolicy.WARN


class ModuleManifest(BaseModel):
    """A provider-neutral description of one kind of module."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    category: str = Field(default="Utility", min_length=1)
    description: str = ""
    ports: tuple[PortManifest, ...] = ()

    @model_validator(mode="after")
    def port_ids_are_unique(self) -> "ModuleManifest":
        port_ids = [port.id for port in self.ports]
        if len(port_ids) != len(set(port_ids)):
            raise ValueError("module port IDs must be unique")
        return self


class ProviderManifest(BaseModel):
    """The JSON-compatible catalog published by a module provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    modules: tuple[ModuleManifest, ...] = ()

    @model_validator(mode="after")
    def module_ids_are_unique(self) -> "ProviderManifest":
        module_ids = [module.id for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("provider module IDs must be unique")
        return self


class ConnectionAssessment(BaseModel):
    """A serializable compatibility decision for a proposed cable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compatible: bool
    disposition: ConnectionDisposition
    reason: str


@runtime_checkable
class ModuleProvider(Protocol):
    """The discovery boundary implemented by module provider packages."""

    @property
    def manifest(self) -> ProviderManifest:
        """Describe the modules supplied by this provider."""
        ...


def assess_connection(
    source: PortManifest,
    target: PortManifest,
) -> ConnectionAssessment:
    """Assess whether an output may be patched into an input.

    Audio and CV use compatible block-shaped data in Noodler. Crossing that
    semantic boundary is therefore supported by default, but produces an
    advisory unless both ports explicitly opt in. Either endpoint may reject
    the crossing when it would be misleading or unsafe for that module.
    """
    if source.direction is not PortDirection.OUTPUT:
        return ConnectionAssessment(
            compatible=False,
            disposition=ConnectionDisposition.REJECTED,
            reason=f"{source.name} is not an output port",
        )

    if target.direction is not PortDirection.INPUT:
        return ConnectionAssessment(
            compatible=False,
            disposition=ConnectionDisposition.REJECTED,
            reason=f"{target.name} is not an input port",
        )

    if source.signal_type is target.signal_type:
        return ConnectionAssessment(
            compatible=True,
            disposition=ConnectionDisposition.DIRECT,
            reason=f"direct {source.signal_type.value} connection",
        )

    signal_pair = {source.signal_type, target.signal_type}
    if signal_pair == {SignalType.GATE, SignalType.TRIGGER}:
        # A trigger is a short gate. Every module reads both at the rising
        # edge, and in a rack they are the same voltage on the same cable.
        return ConnectionAssessment(
            compatible=True,
            disposition=ConnectionDisposition.CROSS_SIGNAL,
            reason="a trigger is a short gate; both are read at the rising edge",
        )
    if signal_pair != {SignalType.AUDIO, SignalType.CV}:
        return ConnectionAssessment(
            compatible=False,
            disposition=ConnectionDisposition.REJECTED,
            reason=(
                f"{source.signal_type.value} cannot be connected to "
                f"{target.signal_type.value}"
            ),
        )

    policies = {source.audio_cv_policy, target.audio_cv_policy}
    if AudioCvPolicy.REJECT in policies:
        return ConnectionAssessment(
            compatible=False,
            disposition=ConnectionDisposition.REJECTED,
            reason="an endpoint rejects audio/CV cross-linking",
        )

    if AudioCvPolicy.WARN in policies:
        return ConnectionAssessment(
            compatible=True,
            disposition=ConnectionDisposition.ADVISORY,
            reason=(
                "audio/CV cross-link is valid; check the expected range, "
                "rate, and DC behavior"
            ),
        )

    return ConnectionAssessment(
        compatible=True,
        disposition=ConnectionDisposition.CROSS_SIGNAL,
        reason="both endpoints explicitly support audio/CV cross-linking",
    )


__all__ = [
    "AudioCvPolicy",
    "ConnectionAssessment",
    "ConnectionDisposition",
    "ModuleManifest",
    "ModuleProvider",
    "PortDirection",
    "PortManifest",
    "ProviderManifest",
    "SignalType",
    "assess_connection",
]
