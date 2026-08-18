"""Small shared helpers for built-in block-processing modules."""

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray

from noodler.module_providers import (
    AudioCvPolicy,
    PortDirection,
    PortManifest,
    SignalType,
)


FloatBlock = NDArray[np.float32]
ControlBlock = NDArray[np.float64]


def port(
    port_id: str,
    name: str,
    direction: PortDirection,
    signal_type: SignalType,
    description: str,
) -> PortManifest:
    """Build a port with Noodler's intentional audio/CV cross-link policy."""
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


def block(
    name: str,
    inputs: Mapping[str, ArrayLike],
    frame_count: int,
    *,
    default: float = 0.0,
) -> ControlBlock:
    """Return one scalar-or-block input as a float64 processing block."""
    if name not in inputs:
        return np.full(frame_count, default, dtype=np.float64)
    value = np.asarray(inputs[name], dtype=np.float64)
    if value.ndim == 0:
        return np.full(frame_count, float(value), dtype=np.float64)
    if value.shape != (frame_count,):
        raise ValueError(
            f"{name} must be scalar or have shape ({frame_count},), "
            f"got {value.shape}"
        )
    return value


def empty_outputs(names: tuple[str, ...]) -> dict[str, FloatBlock]:
    """Return independent empty float32 blocks for a zero-frame request."""
    return {name: np.empty(0, dtype=np.float32) for name in names}


def rising_edge(value: float, previous_high: bool) -> tuple[bool, bool]:
    """Return a rising-edge event and the next boolean edge-detector state."""
    high = bool(value > 0.0)
    return high and not previous_high, high

