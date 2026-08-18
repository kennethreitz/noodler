"""Validated runtime patch graphs for block-processing modules."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field

from noodler.module_providers import (
    ModuleManifest,
    PortDirection,
    PortManifest,
    SignalType,
    assess_connection,
)


FloatBlock = NDArray[np.float32]
StereoBlock = NDArray[np.float32]
INSTANCE_ID_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"


class PatchError(ValueError):
    """A patch cannot be constructed or rendered as requested."""


class Endpoint(BaseModel):
    """A serializable reference to one port on one module instance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module_id: str = Field(pattern=INSTANCE_ID_PATTERN)
    port_id: str = Field(pattern=INSTANCE_ID_PATTERN)


class Cable(BaseModel):
    """A directed connection between two module ports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Endpoint
    target: Endpoint


class OutputChannel(StrEnum):
    """Destination channel for one source on the system output bus."""

    BOTH = "both"
    LEFT = "left"
    RIGHT = "right"


class OutputTap(BaseModel):
    """A module output mixed into one or both system output channels."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    source: Endpoint
    gain: float = Field(default=1.0, ge=-4.0, le=4.0)
    channel: OutputChannel = OutputChannel.BOTH


@runtime_checkable
class BlockModule(Protocol):
    """The concrete DSP interface learned from Noodler's first patch."""

    manifest: ModuleManifest

    def process(
        self,
        frame_count: int,
        sample_rate: float,
        inputs: Mapping[str, ArrayLike] | None = None,
    ) -> Mapping[str, ArrayLike]:
        """Render one block of named outputs from named input blocks."""
        ...


class PatchGraph:
    """Own module instances, validate cables, and render a prepared graph.

    Topology changes rebuild a stable processing plan on the control thread.
    Rendering only reads that prepared tuple. A future snapshot handoff will
    make live topology changes safe while the audio callback is running.
    """

    def __init__(self) -> None:
        self._modules: dict[str, BlockModule] = {}
        self._cables: list[Cable] = []
        self._output_taps: list[OutputTap] = []
        self._processing_order: tuple[str, ...] = ()

    @property
    def modules(self) -> Mapping[str, BlockModule]:
        return self._modules

    @property
    def cables(self) -> tuple[Cable, ...]:
        return tuple(self._cables)

    @property
    def output_taps(self) -> tuple[OutputTap, ...]:
        return tuple(self._output_taps)

    @property
    def processing_order(self) -> tuple[str, ...]:
        return self._processing_order

    def add_module(self, instance_id: str, module: BlockModule) -> None:
        """Add a uniquely named runtime module to the graph."""
        Endpoint(module_id=instance_id, port_id="port")
        if instance_id in self._modules:
            raise PatchError(f"module instance already exists: {instance_id}")
        if not isinstance(module, BlockModule):
            raise PatchError(f"{instance_id} does not implement the block module protocol")
        self._modules[instance_id] = module
        self._processing_order = self._compile_processing_order()

    def remove_module(self, instance_id: str) -> int:
        """Remove a module with every cable and tap that touched it.

        Returns the number of connections removed, so the interface can report
        what a deletion actually cost the patch.
        """
        if instance_id not in self._modules:
            raise PatchError(f"unknown module instance: {instance_id}")
        removed = [
            cable
            for cable in self._cables
            if instance_id in (cable.source.module_id, cable.target.module_id)
        ]
        taps = [
            tap for tap in self._output_taps if tap.source.module_id == instance_id
        ]
        for cable in removed:
            self._cables.remove(cable)
        for tap in taps:
            self._output_taps.remove(tap)
        del self._modules[instance_id]
        self._processing_order = self._compile_processing_order()
        return len(removed) + len(taps)

    def connect(
        self,
        source_module: str,
        source_port: str,
        target_module: str,
        target_port: str,
    ) -> Cable:
        """Validate and add a module-to-module cable."""
        source = Endpoint(module_id=source_module, port_id=source_port)
        target = Endpoint(module_id=target_module, port_id=target_port)
        source_manifest = self._port(source)
        target_manifest = self._port(target)
        assessment = assess_connection(source_manifest, target_manifest)
        if not assessment.compatible:
            raise PatchError(assessment.reason)
        if any(cable.target == target for cable in self._cables):
            raise PatchError(
                f"input already has a cable: {target.module_id}.{target.port_id}"
            )

        cable = Cable(source=source, target=target)
        self._cables.append(cable)
        try:
            self._processing_order = self._compile_processing_order()
        except PatchError:
            self._cables.pop()
            raise
        return cable

    def connect_output(
        self,
        source_module: str,
        source_port: str,
        *,
        gain: float = 1.0,
        channel: OutputChannel = OutputChannel.BOTH,
    ) -> OutputTap:
        """Mix an audio or CV output into the system output bus."""
        source = Endpoint(module_id=source_module, port_id=source_port)
        port = self._port(source)
        if port.direction is not PortDirection.OUTPUT:
            raise PatchError(f"{port.name} is not an output port")
        if port.signal_type not in {SignalType.AUDIO, SignalType.CV}:
            raise PatchError("the system output bus accepts audio or continuous CV")
        tap = OutputTap(source=source, gain=gain, channel=channel)
        self._output_taps.append(tap)
        return tap

    def disconnect(self, cable: Cable) -> None:
        """Remove an existing module-to-module cable."""
        try:
            self._cables.remove(cable)
        except ValueError as exc:
            raise PatchError("cable is not part of this patch") from exc
        self._processing_order = self._compile_processing_order()

    def disconnect_output(self, tap: OutputTap) -> None:
        """Remove an existing tap from the system output bus."""
        try:
            self._output_taps.remove(tap)
        except ValueError as exc:
            raise PatchError("output tap is not part of this patch") from exc

    def disconnect_all(self) -> int:
        """Remove every module cable and system-output tap in one graph edit."""
        connection_count = len(self._cables) + len(self._output_taps)
        self._cables.clear()
        self._output_taps.clear()
        self._processing_order = self._compile_processing_order()
        return connection_count

    def prepare(self, sample_rate: float, block_size: int) -> None:
        """Prepare stateful modules before the audio device starts."""
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        for module in self._modules.values():
            prepare = getattr(module, "prepare", None)
            if callable(prepare):
                prepare(sample_rate, block_size)

    def render(self, frame_count: int, sample_rate: float) -> FloatBlock:
        """Render a mono fold-down of the stereo output bus."""
        stereo = self.render_stereo(frame_count, sample_rate)
        return np.asarray(np.mean(stereo, axis=1), dtype=np.float32)

    def render_stereo(self, frame_count: int, sample_rate: float) -> StereoBlock:
        """Render the graph and preserve left/right system-bus routing."""
        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        rendered = self._render_modules(frame_count, sample_rate)
        output = np.zeros((frame_count, 2), dtype=np.float64)
        for tap in self._output_taps:
            try:
                value = rendered[tap.source.module_id][tap.source.port_id]
            except KeyError as exc:
                raise PatchError(
                    "module did not render tapped output "
                    f"{tap.source.module_id}.{tap.source.port_id}"
                ) from exc
            block = tap.gain * self._block(tap.source, value, frame_count)
            if tap.channel in {OutputChannel.BOTH, OutputChannel.LEFT}:
                output[:, 0] += block
            if tap.channel in {OutputChannel.BOTH, OutputChannel.RIGHT}:
                output[:, 1] += block
        return np.asarray(output, dtype=np.float32)

    def _render_modules(
        self,
        frame_count: int,
        sample_rate: float,
    ) -> dict[str, Mapping[str, ArrayLike]]:
        """Render every module once in the compiled processing order."""

        incoming: dict[str, list[Cable]] = {
            module_id: [] for module_id in self._modules
        }
        for cable in self._cables:
            incoming[cable.target.module_id].append(cable)

        rendered: dict[str, Mapping[str, ArrayLike]] = {}
        for module_id in self._processing_order:
            inputs: dict[str, ArrayLike] = {}
            for cable in incoming[module_id]:
                try:
                    inputs[cable.target.port_id] = rendered[cable.source.module_id][
                        cable.source.port_id
                    ]
                except KeyError as exc:
                    raise PatchError(
                        "module did not render connected output "
                        f"{cable.source.module_id}.{cable.source.port_id}"
                    ) from exc
            rendered[module_id] = self._modules[module_id].process(
                frame_count,
                sample_rate,
                inputs,
            )
        return rendered

    def _port(self, endpoint: Endpoint) -> PortManifest:
        try:
            module = self._modules[endpoint.module_id]
        except KeyError as exc:
            raise PatchError(f"unknown module instance: {endpoint.module_id}") from exc
        for port in module.manifest.ports:
            if port.id == endpoint.port_id:
                return port
        raise PatchError(
            f"unknown port: {endpoint.module_id}.{endpoint.port_id}"
        )

    def _compile_processing_order(self) -> tuple[str, ...]:
        incoming_count = {module_id: 0 for module_id in self._modules}
        outgoing: dict[str, list[str]] = {
            module_id: [] for module_id in self._modules
        }
        for cable in self._cables:
            source = cable.source.module_id
            target = cable.target.module_id
            outgoing[source].append(target)
            incoming_count[target] += 1

        ready = [
            module_id
            for module_id in self._modules
            if incoming_count[module_id] == 0
        ]
        order: list[str] = []
        while ready:
            module_id = ready.pop(0)
            order.append(module_id)
            for target in outgoing[module_id]:
                incoming_count[target] -= 1
                if incoming_count[target] == 0:
                    ready.append(target)

        if len(order) != len(self._modules):
            raise PatchError("feedback loops require an explicit delay module")
        return tuple(order)

    @staticmethod
    def _block(
        endpoint: Endpoint,
        value: ArrayLike,
        frame_count: int,
    ) -> NDArray[np.float64]:
        block = np.asarray(value, dtype=np.float64)
        if block.ndim == 0:
            return np.full(frame_count, float(block), dtype=np.float64)
        if block.shape != (frame_count,):
            raise PatchError(
                f"{endpoint.module_id}.{endpoint.port_id} returned {block.shape}; "
                f"expected ({frame_count},)"
            )
        return block


__all__ = [
    "BlockModule",
    "Cable",
    "Endpoint",
    "OutputChannel",
    "OutputTap",
    "PatchError",
    "PatchGraph",
]
