"""Typed state containers for Noodler's Dear PyGui interface."""

from collections.abc import Callable
from dataclasses import dataclass, field

from ..engine import SystemAudioEngine
from ..module_providers import PortDirection
from ..module_providers.builtin import (
    ComplexVCO,
    FunctionUtility,
    LowPassGate,
    PolarizingMixer,
    Reverb,
    ScaleGenerator,
    Wogglebug,
)
from ..motion import (
    Glide,
    KnobDrag,
    Spring,
    ZOOM_HALF_LIFE,
    pixel_spring,
    unit_spring,
)
from ..patch import Endpoint, OutputChannel, PatchGraph
from ..transport import FREE
from .style import KNOB_SIZE


@dataclass(slots=True)
class AppRuntime:
    """Live modules, patch graph, and audio device owned by the app."""

    patch: PatchGraph
    audio: SystemAudioEngine
    vco: ComplexVCO | None = None
    mixer: PolarizingMixer | None = None
    utility: FunctionUtility | None = None
    wogglebug: Wogglebug | None = None
    scale_generator: ScaleGenerator | None = None
    low_pass_gate: LowPassGate | None = None
    reverb: Reverb | None = None


@dataclass(frozen=True, slots=True)
class KnobBinding:
    """Translate a knob position into a parameter and its value readout."""

    setter: Callable[[float], None]
    label: str
    value_label: int | str
    minimum: float
    maximum: float
    formatter: Callable[[float], str]
    logarithmic: bool = False
    size: int = KNOB_SIZE
    default_value: float | None = None
    inset: float = 0.0


@dataclass(slots=True)
class KnobArt:
    """The drawn parts of one knob, kept for inexpensive repainting."""

    size: int
    body: int | str
    track: int | str
    arc: int | str
    pointer: int | str


@dataclass(slots=True)
class KnobInteraction:
    """State shared by the global Ableton-style vertical knob gesture."""

    bindings: dict[int | str, KnobBinding] = field(default_factory=dict)
    positions: dict[int | str, float] = field(default_factory=dict)
    drag_start: float = 0.0
    art: dict[int | str, KnobArt] = field(default_factory=dict)
    active_knob: int | str | None = None
    drag_position: float = 0.0
    drag: KnobDrag = field(default_factory=KnobDrag)
    last_mouse_y: float = 0.0

    def reset(self) -> None:
        self.bindings.clear()
        self.positions.clear()
        self.art.clear()
        self.active_knob = None
        self.drag_position = 0.0
        self.drag = KnobDrag()
        self.last_mouse_y = 0.0


@dataclass(slots=True)
class CanvasInteraction:
    """Pan and zoom state for the rack camera."""

    panning: bool = False
    pan_candidate: bool = False
    pan_moved: bool = False
    press_x: float = 0.0
    press_y: float = 0.0
    last_mouse_x: float = 0.0
    last_mouse_y: float = 0.0
    zoom: float = 1.0
    zoom_target: float = 1.0
    zoom_anchor: tuple[float, float] | None = None
    pending_magnification: float = 0.0
    pending_scroll_x: float = 0.0
    pending_scroll_y: float = 0.0
    native_scroll: bool = False
    rail_y: dict[str, float] = field(default_factory=dict)
    zoom_spring: Spring = field(
        default_factory=lambda: unit_spring(1.0, ZOOM_HALF_LIFE)
    )
    glide_x: Glide = field(default_factory=Glide)
    glide_y: Glide = field(default_factory=Glide)
    pan_velocity_x: float = 0.0
    pan_velocity_y: float = 0.0
    press_consumed: bool = False
    press_classified: bool = False
    drag_classified: bool = False
    drag_pans: bool = False
    pending_reveal: bool = True
    reveal_attempts: int = 0
    marquee_origin: tuple[float, float] | None = None
    recenter_x: Spring = field(default_factory=lambda: pixel_spring(0.0))
    recenter_y: Spring = field(default_factory=lambda: pixel_spring(0.0))
    translate_residue_x: float = 0.0
    translate_residue_y: float = 0.0

    def reset(self) -> None:
        self.forget_gesture()
        self.panning = False
        self.pan_candidate = False
        self.press_x = 0.0
        self.press_y = 0.0
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0
        self.zoom = 1.0
        self.zoom_target = 1.0
        self.zoom_anchor = None
        self.pending_magnification = 0.0
        self.pending_scroll_x = 0.0
        self.pending_scroll_y = 0.0
        self.rail_y.clear()
        self.zoom_spring = unit_spring(1.0, ZOOM_HALF_LIFE)
        self.press_consumed = False
        self.press_classified = False
        self.pending_reveal = True
        self.reveal_attempts = 0
        self.stop_glide()

    def stop_glide(self) -> None:
        """Cancel camera motion, as any fresh press on the rack should."""
        self.glide_x.stop()
        self.glide_y.stop()
        self.pan_velocity_x = 0.0
        self.pan_velocity_y = 0.0
        self.recenter_x.snap(0.0)
        self.recenter_y.snap(0.0)
        self.translate_residue_x = 0.0
        self.translate_residue_y = 0.0

    def arm_pan(self, screen_position: tuple[float, float]) -> None:
        self.pan_candidate = True
        self.press_x = float(screen_position[0])
        self.press_y = float(screen_position[1])

    def forget_gesture(self) -> None:
        self.drag_classified = False
        self.drag_pans = False

    def stop_panning(self) -> None:
        self.forget_gesture()
        self.panning = False
        self.pan_candidate = False
        self.press_x = 0.0
        self.press_y = 0.0
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0


@dataclass(slots=True)
class RateSync:
    """A control the transport may drive, and the division it follows."""

    module: object
    path: tuple[str | int, ...]
    binding: KnobBinding
    division: str = FREE
    kind: str = "rate"


@dataclass(slots=True)
class ModuleCollapseInteraction:
    """Visibility snapshots for modules folded down to their title bars."""

    attributes: dict[int | str, dict[int | str, bool]] = field(default_factory=dict)
    labels: dict[int | str, str] = field(default_factory=dict)

    def reset(self) -> None:
        self.attributes.clear()
        self.labels.clear()

    def is_collapsed(self, node: int | str) -> bool:
        return node in self.attributes


@dataclass(frozen=True, slots=True)
class PatchBayBinding:
    """UI state for one module's compact, graph-aware jack list."""

    patch: PatchGraph
    module_id: str
    node_tag: str
    port_ids: tuple[str, ...]
    toggle_tag: str
    status_tag: str


@dataclass(frozen=True, slots=True)
class ResolvedJack:
    """A node-editor attribute resolved to its runtime patch endpoint."""

    attribute: int | str
    endpoint: Endpoint | None
    direction: PortDirection
    signal: str
    name: str
    output_channel: OutputChannel | None = None


@dataclass(frozen=True, slots=True)
class NodeRegistration:
    """Everything the registries knew about a module, for putting it back."""

    node: int | str
    instance_id: str
    rail: str | None
    rail_index: int
    accent: tuple[int, int, int, int] | None
    patch_bay: PatchBayBinding | None


KNOB_INTERACTION = KnobInteraction()
CANVAS_INTERACTION = CanvasInteraction()
MODULE_COLLAPSE = ModuleCollapseInteraction()
RATE_SYNCS: dict[int | str, RateSync] = {}
PATCH_BAYS: dict[str, PatchBayBinding] = {}
