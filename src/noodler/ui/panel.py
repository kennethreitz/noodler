"""What a module's panel contains, worked out before anything is drawn.

A module already describes itself twice over: its manifest names its ports and
what they carry, and its Pydantic parameter model names every control, its
bounds, and its type. A panel is a reading of those two, so it should be derived
rather than hand-built — a module gets a correct panel by existing, and a panel
cannot drift from the module it belongs to.

Deriving it also means the panel can be *measured* before it is drawn, which is
what lets the rack lay itself out. Nothing here imports Dear PyGui.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

from noodler.module_providers import ModuleManifest, PortDirection


COLUMN_CHARS = 12
"""Width of a control column, in characters of the rack's monospace face."""

CHAR_WIDTH = 8.0
"""Approximate advance of that face at the rack's base size."""

CONTROL_COLUMNS = 3
"""Controls per row on a panel."""

CONTROL_ROW_HEIGHT = 82.0
PORT_ROW_HEIGHT = 20.0
PANEL_CHROME_HEIGHT = 78.0
PANEL_PADDING = 20.0

UNIT_SUFFIXES = (
    ("_hz", "Hz"),
    ("_seconds", "s"),
    ("_ms", "ms"),
    ("_cents", "ct"),
    ("_db", "dB"),
)

ABBREVIATIONS = {"frequency": "freq", "modulation": "mod", "attenuverter": "atten"}


def label_and_unit(field_name: str) -> tuple[str, str]:
    """Turn a parameter name into a short label and the unit it implies."""
    name = field_name
    unit = ""
    for suffix, symbol in UNIT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            unit = symbol
            break
    name = name.removesuffix("_amount")
    words = [ABBREVIATIONS.get(word, word) for word in name.split("_") if word]
    return " ".join(words).upper(), unit


def fit(text: str, width: int = COLUMN_CHARS) -> str:
    """Pad or trim one cell so columns line up under one another."""
    if len(text) > width:
        return text[: max(1, width - 1)] + "…"
    return text.ljust(width)


@dataclass(frozen=True, slots=True)
class Control:
    """One editable parameter, and everything needed to show it."""

    path: tuple[str | int, ...]
    label: str
    unit: str
    kind: Literal["knob", "toggle", "choice"]
    value: Any
    minimum: float = 0.0
    maximum: float = 1.0
    logarithmic: bool = False
    integral: bool = False
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Port:
    """One jack, as the manifest declares it."""

    id: str
    name: str
    signal: str
    description: str
    is_input: bool


@dataclass(frozen=True, slots=True)
class PanelSpec:
    """A module's panel: what it shows, and how much room that needs."""

    module_id: str
    title: str
    category: str
    description: str
    controls: tuple[Control, ...]
    inputs: tuple[Port, ...]
    outputs: tuple[Port, ...]

    @property
    def width(self) -> float:
        columns = min(CONTROL_COLUMNS, max(1, len(self.controls)))
        title_width = (len(self.title) + 2) * CHAR_WIDTH
        control_width = columns * COLUMN_CHARS * CHAR_WIDTH
        return max(title_width, control_width) + PANEL_PADDING

    @property
    def height(self) -> float:
        control_rows = -(-len(self.controls) // CONTROL_COLUMNS)
        jacks = max(len(self.inputs), len(self.outputs))
        return (
            PANEL_CHROME_HEIGHT
            + control_rows * CONTROL_ROW_HEIGHT
            + jacks * PORT_ROW_HEIGHT
        )


MAX_LOG_DECADES = 4.0
"""Useful travel for a logarithmic control, in decades.

A frequency declared `gt=0` has no usable lower bound: honouring it literally
gives a knob whose first two thirds live below one hertz. Positive-definite
controls are floored to a span the hand can actually work in.
"""


def _bounds(field_info: Any, value: float) -> tuple[float, float, bool]:
    """Read a field's declared range, and decide how it should be travelled."""
    minimum: float | None = None
    maximum: float | None = None
    for item in getattr(field_info, "metadata", ()):
        for name in ("ge", "gt"):
            declared = getattr(item, name, None)
            if declared is not None:
                minimum = float(declared)
                if name == "gt":
                    minimum += max(1e-9, abs(minimum) * 1e-6)
        for name in ("le", "lt"):
            declared = getattr(item, name, None)
            if declared is not None:
                maximum = float(declared)
                if name == "lt":
                    maximum -= max(1e-9, abs(maximum) * 1e-6)

    if minimum is None and maximum is None:
        extent = max(1.0, abs(value) * 2.0)
        minimum, maximum = (-extent, extent) if value < 0.0 else (0.0, extent)
    elif minimum is None:
        minimum = min(0.0, value - max(1.0, abs(value)))
    elif maximum is None:
        maximum = max(minimum + 1.0, value + max(1.0, abs(value)))
    if maximum <= minimum:
        maximum = minimum + 1.0

    logarithmic = minimum > 0.0 and maximum / minimum >= 100.0
    if logarithmic:
        floor = maximum / (10.0**MAX_LOG_DECADES)
        minimum = max(minimum, floor)
    return minimum, maximum, logarithmic


def _controls_for(
    parameters: BaseModel,
    path: tuple[str | int, ...] = (),
) -> tuple[Control, ...]:
    """Walk a parameter model into a flat list of controls."""
    found: list[Control] = []
    for name, field_info in type(parameters).model_fields.items():
        value = getattr(parameters, name)
        here = (*path, name)
        label, unit = label_and_unit(name)

        if isinstance(value, BaseModel):
            nested = _controls_for(value, here)
            prefix, _ = label_and_unit(name)
            found.extend(
                Control(
                    path=control.path,
                    label=f"{prefix.split()[-1]} {control.label}".strip(),
                    unit=control.unit,
                    kind=control.kind,
                    value=control.value,
                    minimum=control.minimum,
                    maximum=control.maximum,
                    logarithmic=control.logarithmic,
                    integral=control.integral,
                    choices=control.choices,
                )
                for control in nested
            )
            continue

        if isinstance(value, StrEnum):
            found.append(
                Control(
                    path=here,
                    label=label,
                    unit="",
                    kind="choice",
                    value=value.value,
                    choices=tuple(choice.value for choice in type(value)),
                )
            )
            continue

        if isinstance(value, bool):
            found.append(
                Control(path=here, label=label, unit="", kind="toggle", value=value)
            )
            continue

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum, maximum, logarithmic = _bounds(field_info, float(value))
            found.append(
                Control(
                    path=here,
                    label=label,
                    unit=unit,
                    kind="knob",
                    value=float(value),
                    minimum=minimum,
                    maximum=maximum,
                    logarithmic=logarithmic,
                    integral=isinstance(value, int),
                )
            )
            continue

        if isinstance(value, tuple) and value and isinstance(value[0], float):
            for position, item in enumerate(value, start=1):
                found.append(
                    Control(
                        path=(*here, position - 1),
                        label=f"{label} {position}",
                        unit=unit,
                        kind="knob",
                        value=float(item),
                        minimum=-1.0,
                        maximum=1.0,
                    )
                )
    return tuple(found)


def describe(module: object, manifest: ModuleManifest | None = None) -> PanelSpec:
    """Derive a module's whole panel from its manifest and its parameters."""
    manifest = manifest or getattr(module, "manifest")
    parameters = getattr(module, "parameters", None)
    controls = (
        _controls_for(parameters) if isinstance(parameters, BaseModel) else ()
    )
    ports = manifest.ports
    return PanelSpec(
        module_id=manifest.id,
        title=manifest.name.upper(),
        category=manifest.category,
        description=manifest.description,
        controls=controls,
        inputs=tuple(
            Port(p.id, p.name, p.signal_type.value, p.description, True)
            for p in ports
            if p.direction is PortDirection.INPUT
        ),
        outputs=tuple(
            Port(p.id, p.name, p.signal_type.value, p.description, False)
            for p in ports
            if p.direction is PortDirection.OUTPUT
        ),
    )


def panel_value(parameters: BaseModel, path: Sequence[str | int]) -> Any:
    """Read the live value a control points at."""
    target: Any = parameters
    for step in path:
        target = target[step] if isinstance(step, int) else getattr(target, step)
    return target


def set_panel_value(
    parameters: BaseModel,
    path: Sequence[str | int],
    value: Any,
) -> None:
    """Write a control's value back through the validated model."""
    *lead, last = list(path)
    target: Any = parameters
    for step in lead:
        target = target[step] if isinstance(step, int) else getattr(target, step)
    if isinstance(last, int):
        raise TypeError(
            "sequence parameters are set through their owning module, "
            "which validates the whole sequence at once"
        )
    setattr(target, last, value)


__all__ = [
    "COLUMN_CHARS",
    "CONTROL_COLUMNS",
    "Control",
    "PanelSpec",
    "Port",
    "describe",
    "fit",
    "label_and_unit",
    "panel_value",
    "set_panel_value",
]
