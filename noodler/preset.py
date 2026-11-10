"""Versioned, human-readable Noodler patch documents.

``.noodler`` files are JSON. ``.toml`` files are the same document, written so
a person can edit a tuning or a phrase without a window. Both load through
the same validation.
"""

import json
from pathlib import Path
import tomllib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from noodler.patch import Cable, OutputTap, PatchGraph


PATCH_FORMAT = "noodler.patch"
PATCH_FORMAT_VERSION = 1
PATCH_EXTENSION = ".noodler"
TOML_EXTENSION = ".toml"
READABLE_EXTENSIONS = {PATCH_EXTENSION, TOML_EXTENSION, ".json"}


class Point(BaseModel):
    """A position in rack-local coordinates."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    x: float
    y: float


class ModulePreset(BaseModel):
    """One module instance and its validated panel parameter payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
    module_type: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
    provider: str = Field(default="builtin", min_length=1)
    parameters: dict[str, JsonValue]


class RackNodePreset(BaseModel):
    """Visual state for a module or the system-output panel."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
    position: Point
    collapsed: bool = False


class GroupPreset(BaseModel):
    """A group of modules -- and of groups -- as saved with the document.

    Logical only: a name over some modules that go around together. Members
    are module instance ids; groups are the ids of groups nested inside.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
    name: str = Field(default="GROUP", max_length=60)
    members: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()


class RackViewPreset(BaseModel):
    """Camera and semantic-rail state saved with a patch."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    zoom: float = Field(default=1.0, ge=0.25, le=4.0)
    rails: dict[str, float] = Field(default_factory=dict)
    nodes: tuple[RackNodePreset, ...] = ()
    groups: tuple[GroupPreset, ...] = ()

    @model_validator(mode="after")
    def node_ids_are_unique(self) -> "RackViewPreset":
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("rack view contains duplicate node ids")
        group_ids = [group.group_id for group in self.groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("rack view contains duplicate group ids")
        return self


class SystemOutputPreset(BaseModel):
    """Serializable controls for the final system bus."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    master_gain: float = Field(default=0.8, ge=0.0, le=1.0)


class TransportPreset(BaseModel):
    """The tempo and signature a patch was made at.

    A patch with a beat in it is not the same patch at another tempo, so the
    clock travels with the document. Older documents have none, and open at
    the defaults they were always opened at.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    bpm: float = Field(default=120.0, ge=20.0, le=300.0)
    beats_per_bar: int = Field(default=4, ge=1, le=32)
    beat_unit: int = Field(default=4, ge=1, le=16)


class PatchPreset(BaseModel):
    """The stable version-one `.noodler` patch interchange document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["noodler.patch"] = PATCH_FORMAT
    format_version: Literal[1] = PATCH_FORMAT_VERSION
    application_version: str = "0.1.0"
    name: str = Field(default="Untitled Patch", min_length=1, max_length=120)
    modules: tuple[ModulePreset, ...]
    cables: tuple[Cable, ...] = ()
    output_taps: tuple[OutputTap, ...] = ()
    system_output: SystemOutputPreset = Field(default_factory=SystemOutputPreset)
    transport: TransportPreset = Field(default_factory=TransportPreset)
    view: RackViewPreset = Field(default_factory=RackViewPreset)

    @model_validator(mode="after")
    def graph_references_known_modules(self) -> "PatchPreset":
        module_ids = [module.instance_id for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("patch contains duplicate module instance ids")
        known = set(module_ids)
        for cable in self.cables:
            if cable.source.module_id not in known:
                raise ValueError(
                    f"cable source refers to unknown module: "
                    f"{cable.source.module_id}"
                )
            if cable.target.module_id not in known:
                raise ValueError(
                    f"cable target refers to unknown module: "
                    f"{cable.target.module_id}"
                )
        for tap in self.output_taps:
            if tap.source.module_id not in known:
                raise ValueError(
                    f"output tap refers to unknown module: {tap.source.module_id}"
                )
        return self


def capture_patch_preset(
    *,
    name: str,
    patch: PatchGraph,
    master_gain: float,
    view: RackViewPreset,
    transport: TransportPreset | None = None,
) -> PatchPreset:
    """Snapshot a live graph without serializing transient DSP state."""
    modules = []
    for instance_id, module in patch.modules.items():
        parameters = getattr(module, "parameters", None)
        if not isinstance(parameters, BaseModel):
            raise TypeError(f"{instance_id} has no serializable parameter model")
        modules.append(
            ModulePreset(
                instance_id=instance_id,
                module_type=module.manifest.id,
                parameters=parameters.model_dump(mode="json"),
            )
        )
    return PatchPreset(
        name=name,
        modules=tuple(modules),
        cables=patch.cables,
        output_taps=patch.output_taps,
        system_output=SystemOutputPreset(master_gain=master_gain),
        transport=transport or TransportPreset(),
        view=view,
    )


def preset_path(path: str | Path) -> Path:
    """Give patch documents their recognizable extension.

    A path that already ends in ``.noodler``, ``.json`` or ``.toml`` is kept.
    Anything else is a ``.noodler`` document.
    """
    resolved = Path(path).expanduser()
    if resolved.suffix.lower() in READABLE_EXTENSIONS:
        return resolved
    return resolved.with_name(f"{resolved.name}{PATCH_EXTENSION}")


def write_patch_preset(preset: PatchPreset, path: str | Path) -> Path:
    """Write a formatted patch document and return its normalized path."""
    destination = preset_path(path)
    payload = preset.model_dump(mode="json")
    if destination.suffix.lower() == TOML_EXTENSION:
        text = preset_to_toml(payload)
    else:
        text = json.dumps(payload, indent=2) + "\n"
    destination.write_text(text, encoding="utf-8")
    return destination


def read_patch_preset(path: str | Path) -> PatchPreset:
    """Parse and fully validate a patch document before it reaches the engine."""
    document = Path(path)
    text = document.read_text(encoding="utf-8")
    if document.suffix.lower() == TOML_EXTENSION:
        return PatchPreset.model_validate(tomllib.loads(text))
    return PatchPreset.model_validate_json(text)


def preset_to_toml(payload: dict[str, object]) -> str:
    """Render a patch document as TOML a person can edit."""
    lines: list[str] = []
    _emit_table(payload, prefix="", lines=lines)
    return "\n".join(lines).strip() + "\n"


def _emit_table(data: dict[str, object], *, prefix: str, lines: list[str]) -> None:
    tables: list[tuple[str, dict[str, object]]] = []
    arrays: list[tuple[str, list[object]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            if value:
                tables.append((key, value))
        elif isinstance(value, list) and (not value or isinstance(value[0], dict)):
            arrays.append((key, value))
        else:
            lines.append(f"{key} = {_toml_literal(value)}")
    for key, table in tables:
        path = f"{prefix}.{key}" if prefix else key
        lines.append("")
        lines.append(f"[{path}]")
        _emit_table(table, prefix=path, lines=lines)
    for key, items in arrays:
        path = f"{prefix}.{key}" if prefix else key
        for item in items:
            lines.append("")
            lines.append(f"[[{path}]]")
            if isinstance(item, dict):
                _emit_table(item, prefix=path, lines=lines)


def _toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_literal(item) for item in value) + "]"
    raise TypeError(f"cannot write {type(value).__name__} into a patch")


__all__ = [
    "PATCH_EXTENSION",
    "PATCH_FORMAT",
    "PATCH_FORMAT_VERSION",
    "ModulePreset",
    "PatchPreset",
    "Point",
    "RackNodePreset",
    "GroupPreset",
    "RackViewPreset",
    "SystemOutputPreset",
    "TransportPreset",
    "capture_patch_preset",
    "preset_path",
    "preset_to_toml",
    "read_patch_preset",
    "write_patch_preset",
]
