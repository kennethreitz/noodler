"""Noodler, a modular music environment."""

from .module_providers import (
    AudioCvPolicy,
    ConnectionAssessment,
    ConnectionDisposition,
    ModuleManifest,
    ModuleProvider,
    PortDirection,
    PortManifest,
    ProviderManifest,
    SignalType,
    assess_connection,
)

__all__ = [
    "AudioCvPolicy",
    "ConnectionAssessment",
    "ConnectionDisposition",
    "ModuleManifest",
    "ModuleProvider",
    "Patch",
    "PortDirection",
    "PortManifest",
    "ProviderManifest",
    "SignalType",
    "assess_connection",
]


def __getattr__(name: str) -> object:
    # The patch builder imports the application, which imports this package.
    # Loading it on the way in would be a circle, so it waits until asked.
    if name == "Patch":
        from .studio import Patch

        return Patch
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

