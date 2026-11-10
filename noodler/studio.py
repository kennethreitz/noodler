"""A patch, written the way a person would describe one.

The rack is a graph of modules and cables. This is that graph without the
window: name a module, name a cable, and save. The document that comes out is
the same one the rack opens.

::

    from noodler.studio import Patch

    patch = Patch("DADGAD Chapel").at(bpm=72)
    patch.module("board", "fretboard", tuning="dadgad")
    patch.module("voice", "pytheory_voice", instrument="acoustic_guitar")
    patch.cable("board.pitch", "voice.pitch")
    patch.cable("board.gate", "voice.gate")
    patch.hear("voice.audio")
    patch.save("chapel.noodler")
"""

from pathlib import Path

from noodler.module_providers.builtin import BuiltinProvider
from noodler.patch import PatchGraph
from noodler.preset import (
    PatchPreset,
    Point,
    RackNodePreset,
    RackViewPreset,
    TransportPreset,
    capture_patch_preset,
    write_patch_preset,
)


MASTER_ID = "master"


class Patch:
    """One patch, built by naming modules and the cables between them."""

    def __init__(self, name: str = "Untitled Patch") -> None:
        self.name = name
        self.graph = PatchGraph()
        self._provider = BuiltinProvider()
        self._places: dict[str, tuple[float, float]] = {}
        self.bpm = 96.0
        self.beats_per_bar = 4
        self.beat_unit = 4
        self.master_gain = 0.85
        # The master is part of the rack, not something a patch has to remember
        # to add. Imported here so describing a patch does not import the
        # window until a module is actually constructed.
        from noodler.app import ensure_master

        self.master = ensure_master(self.graph)

    def at(
        self,
        *,
        bpm: float | None = None,
        beats: int | None = None,
        unit: int | None = None,
        gain: float | None = None,
    ) -> "Patch":
        """Set the tempo, the signature, or the level the file is saved at."""
        if bpm is not None:
            self.bpm = bpm
        if beats is not None:
            self.beats_per_bar = beats
        if unit is not None:
            self.beat_unit = unit
        if gain is not None:
            self.master_gain = gain
        return self

    def module(
        self,
        instance_id: str,
        module_type: str,
        *,
        at: tuple[float, float] | None = None,
        **parameters: object,
    ) -> "Patch":
        """Add a module. Parameters are the same names as the knobs."""
        module = self._provider.create(module_type, parameters or None)
        self.graph.add_module(instance_id, module)
        if at is None:
            placed = len(self._places)
            at = (40.0 + (placed % 4) * 320.0, 40.0 + (placed // 4) * 300.0)
        self._places[instance_id] = (float(at[0]), float(at[1]))
        return self

    def cable(self, source: str, target: str) -> "Patch":
        """Patch ``"module.port"`` into ``"module.port"``."""
        source_module, source_port = _endpoint(source)
        target_module, target_port = _endpoint(target)
        self.graph.connect(source_module, source_port, target_module, target_port)
        return self

    def hear(
        self,
        source: str,
        *,
        channel: int | None = None,
        level: float = 0.7,
        pan: float = 0.0,
        send_a: float = 0.0,
        send_b: float = 0.0,
    ) -> "Patch":
        """Send a module's audio to a channel of the master, and out."""
        if channel is None:
            channel = self._next_channel()
        source_module, source_port = _endpoint(source)
        self.graph.connect(source_module, source_port, MASTER_ID, f"channel_{channel}")
        self.master.set_level(channel, level)
        self.master.set_pan(channel, pan)
        if send_a:
            self.master.set_send("a", channel, send_a)
        if send_b:
            self.master.set_send("b", channel, send_b)
        return self

    def _next_channel(self) -> int:
        used = {
            int(cable.target.port_id.removeprefix("channel_"))
            for cable in self.graph.cables
            if cable.target.module_id == MASTER_ID
            and cable.target.port_id.startswith("channel_")
        }
        for channel in range(1, 9):
            if channel not in used:
                return channel
        raise RuntimeError("the master has no free channel")

    def preset(self) -> PatchPreset:
        """The document this patch would save, master included."""
        view = RackViewPreset(
            nodes=tuple(
                RackNodePreset(node_id=instance_id, position=Point(x=x, y=y))
                for instance_id, (x, y) in self._places.items()
            )
        )
        return capture_patch_preset(
            name=self.name,
            patch=self.graph,
            master_gain=self.master_gain,
            view=view,
            transport=TransportPreset(
                bpm=self.bpm,
                beats_per_bar=self.beats_per_bar,
                beat_unit=self.beat_unit,
            ),
        )

    def save(self, path: str | Path) -> Path:
        """Write a ``.noodler`` JSON document, or TOML when the path says so."""
        return write_patch_preset(self.preset(), path)

    def render(self, *, bars: int = 8, tail_seconds: float = 2.0):
        """Play the patch offline and return stereo audio."""
        from noodler.bounce import bounce

        return bounce(self.preset(), bars=bars, tail_seconds=tail_seconds)


def _endpoint(spec: str) -> tuple[str, str]:
    module_id, separator, port_id = spec.partition(".")
    if not separator or not module_id or not port_id:
        raise ValueError(f"a cable end is module.port, not {spec!r}")
    return module_id, port_id


__all__ = ["MASTER_ID", "Patch"]
