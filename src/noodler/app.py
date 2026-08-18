"""Noodler's application entry point."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
import math
from pathlib import Path

import dearpygui.dearpygui as dpg
from pydantic import BaseModel

from .module_providers import PortDirection
from .module_providers.builtin import (
    BUILTIN_PROVIDER_MANIFEST,
    FUNCTION_UTILITY_MANIFEST,
    MAX_FUNCTION_STAGE_SECONDS,
    MIN_FUNCTION_STAGE_SECONDS,
    ComplexVCO,
    ComplexVCOParameters,
    FunctionChannelParameters,
    FunctionUtility,
    FunctionUtilityParameters,
    LowPassGate,
    LowPassGateParameters,
    PolarizingMixer,
    PolarizingMixerParameters,
    Reverb,
    ReverbParameters,
    SUPPORTED_SCALE_SYSTEMS,
    TONICS,
    ScaleGenerator,
    ScaleGeneratorParameters,
    SequencePattern,
    WaveB,
    Wogglebug,
    WogglebugParameters,
    BuiltinProvider,
    scale_names,
)
from .engine import SystemAudioEngine
from .macos_gestures import MacMagnifyMonitor
from .patch import (
    Cable,
    Endpoint,
    OutputChannel,
    OutputTap,
    PatchError,
    PatchGraph,
)
from .preset import (
    PatchPreset,
    Point,
    RackNodePreset,
    RackViewPreset,
    capture_patch_preset,
    write_patch_preset,
)
from .spine import render_spine_texture


PRIMARY_WINDOW = "noodler.primary_window"
RACK = "noodler.rack"
VCO_NODE = "noodler.complex_vco"
MIXER_NODE = "noodler.polarizing_mixer"
FUNCTION_NODE = "noodler.function_utility"
OUTPUT_NODE = "noodler.system_output"
WOGGLE_NODE = "noodler.wogglebug"
SCALE_NODE = "noodler.scale_generator"
LPG_NODE = "noodler.low_pass_gate"
REVERB_NODE = "noodler.reverb"
BASE_RACK_NODES = (
    FUNCTION_NODE,
    WOGGLE_NODE,
    SCALE_NODE,
    VCO_NODE,
    MIXER_NODE,
    LPG_NODE,
    REVERB_NODE,
    OUTPUT_NODE,
)
BASE_INSTANCE_NODE_TAGS = {
    "utility": FUNCTION_NODE,
    "wogglebug": WOGGLE_NODE,
    "scale_generator": SCALE_NODE,
    "vco": VCO_NODE,
    "mixer": MIXER_NODE,
    "low_pass_gate": LPG_NODE,
    "reverb": REVERB_NODE,
}
RACK_NODES = list(BASE_RACK_NODES)
INSTANCE_NODE_TAGS = dict(BASE_INSTANCE_NODE_TAGS)
VIEW_NODE_TAGS = {**INSTANCE_NODE_TAGS, "system_output": OUTPUT_NODE}
CONTROL_RAIL = "control"
AUDIO_RAIL = "audio"
RACK_RAILS = {
    CONTROL_RAIL: [FUNCTION_NODE, WOGGLE_NODE, SCALE_NODE],
    AUDIO_RAIL: [VCO_NODE, MIXER_NODE, LPG_NODE, REVERB_NODE, OUTPUT_NODE],
}
RACK_RAIL_GAP = 48.0
AUDIO_STATUS = "noodler.audio_status"
CONTROL_STATUS = "noodler.control_status"
UNPLUG_ALL_BUTTON = "noodler.unplug_all"
SAVE_PATCH_BUTTON = "noodler.save_patch"
SAVE_PATCH_DIALOG = "noodler.save_patch_dialog"
ADD_MODULE_BUTTON = "noodler.add_module"
MODULE_SELECTOR = "noodler.module_selector"
MODULE_SELECTOR_SEARCH = "noodler.module_selector.search"
MODULE_SELECTOR_STATUS = "noodler.module_selector.status"
ZOOM_OUT_BUTTON = "noodler.zoom_out"
ZOOM_RESET_BUTTON = "noodler.zoom_reset"
ZOOM_IN_BUTTON = "noodler.zoom_in"
OUTPUT_METER = "noodler.output_meter"
INPUT_HANDLERS = "noodler.input_handlers"
VCO_MIXER_LINK = "noodler.link.vco_mixer"
UTILITY_VCO_LINK = "noodler.link.utility_vco"
WOGGLE_VCO_LINK = "noodler.link.woggle_vco"
WOGGLE_SCALE_LINK = "noodler.link.woggle_scale"
SCALE_VCO_LINK = "noodler.link.scale_vco"
VCO_TRIANGLE_MIXER_LINK = "noodler.link.vco_triangle_mixer"
WOGGLE_MIXER_LINK = "noodler.link.woggle_mixer"
MIXER_LPG_LINK = "noodler.link.mixer_lpg"
SCALE_LPG_LINK = "noodler.link.scale_lpg"
UTILITY_REVERB_LINK = "noodler.link.utility_reverb"
LPG_REVERB_LINK = "noodler.link.lpg_reverb"
WOGGLE_REVERB_LINK = "noodler.link.woggle_reverb"
REVERB_LEFT_OUTPUT_LINK = "noodler.link.reverb_left_output"
REVERB_RIGHT_OUTPUT_LINK = "noodler.link.reverb_right_output"
APP_FONT = "noodler.font"
FONT_REGISTRY = "noodler.font_registry"
SPINE_TEXTURE_REGISTRY = "noodler.spine_textures"
SYSTEM_MONO_FONT = Path("/System/Library/Fonts/SFNSMono.ttf")
APP_THEME = "noodler.theme.app"
UTILITY_THEME = "noodler.theme.utility"
VCO_THEME = "noodler.theme.vco"
MIXER_THEME = "noodler.theme.mixer"
OUTPUT_THEME = "noodler.theme.output"
WOGGLE_THEME = "noodler.theme.wogglebug"
SCALE_THEME = "noodler.theme.scale_generator"
LPG_THEME = "noodler.theme.low_pass_gate"
REVERB_THEME = "noodler.theme.reverb"
CV_LINK_THEME = "noodler.theme.link.cv"
AUDIO_LINK_THEME = "noodler.theme.link.audio"
GATE_LINK_THEME = "noodler.theme.link.gate"
MUSICAL_LINK_THEME = "noodler.theme.link.musical"
METER_THEME = "noodler.theme.meter"
SCALE_SYSTEM_CONTROL = "noodler.scale_generator.control.system"
SCALE_NAME_CONTROL = "noodler.scale_generator.control.scale"
SCALE_NOTE_STATUS = "noodler.scale_generator.note_status"

TEXT = (235, 230, 216, 255)
MUTED_TEXT = (157, 153, 142, 255)
UTILITY_ACCENT = (211, 145, 57, 255)
VCO_ACCENT = (63, 153, 161, 255)
MIXER_ACCENT = (103, 151, 108, 255)
OUTPUT_ACCENT = (191, 91, 73, 255)
WOGGLE_ACCENT = (191, 102, 159, 255)
SCALE_ACCENT = (135, 119, 211, 255)
LPG_ACCENT = (194, 154, 79, 255)
REVERB_ACCENT = (92, 129, 184, 255)
MODULE_ACCENTS = {
    FUNCTION_NODE: UTILITY_ACCENT,
    WOGGLE_NODE: WOGGLE_ACCENT,
    SCALE_NODE: SCALE_ACCENT,
    VCO_NODE: VCO_ACCENT,
    MIXER_NODE: MIXER_ACCENT,
    LPG_NODE: LPG_ACCENT,
    REVERB_NODE: REVERB_ACCENT,
    OUTPUT_NODE: OUTPUT_ACCENT,
}
BASE_MODULE_ACCENTS = dict(MODULE_ACCENTS)
SIGNAL_COLORS = {
    "audio": (91, 196, 191, 255),
    "cv": (226, 174, 78, 255),
    "gate": (221, 111, 82, 255),
    "trigger": (221, 111, 82, 255),
    "musical": (163, 126, 205, 255),
}
DEFAULT_CONTROL_STATUS = (
    "DRAG JACKS TO PATCH  ·  SELECT CABLE + DELETE TO UNPATCH  ·  "
    "DRAG BACKGROUND = PAN  ·  PINCH / SCROLL = ZOOM  ·  "
    "DOUBLE-CLICK TITLE = FOLD  ·  DRAG KNOBS ↑ ↓  ·  SHIFT = FINE"
)
KNOB_HINT_DRAG_LIMIT = 3
MIN_RACK_ZOOM = 0.55
MAX_RACK_ZOOM = 1.65
RACK_ZOOM_STEP = 1.12

UTILITY_PORT_ORDER = (
    "channel_1",
    "channel_1_signal",
    "channel_1_trigger",
    "channel_1_cycle",
    "channel_1_rise_cv",
    "channel_1_both_cv",
    "channel_1_fall_cv",
    "channel_1_unity",
    "channel_1_eor",
    "channel_2_signal",
    "channel_2",
    "channel_3_signal",
    "channel_3",
    "channel_4",
    "channel_4_signal",
    "channel_4_trigger",
    "channel_4_cycle",
    "channel_4_rise_cv",
    "channel_4_both_cv",
    "channel_4_fall_cv",
    "channel_4_unity",
    "channel_4_eoc",
    "sum",
    "inverse",
    "or",
)
@dataclass(slots=True)
class AppRuntime:
    """Live modules, patch graph, and audio device owned by the app."""

    vco: ComplexVCO
    mixer: PolarizingMixer
    utility: FunctionUtility
    wogglebug: Wogglebug
    scale_generator: ScaleGenerator
    low_pass_gate: LowPassGate
    reverb: Reverb
    patch: PatchGraph
    audio: SystemAudioEngine


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
    size: int = 62


@dataclass(slots=True)
class KnobInteraction:
    """State shared by the global Ableton-style vertical knob gesture."""

    bindings: dict[int | str, KnobBinding] = field(default_factory=dict)
    active_knob: int | str | None = None
    drag_position: float = 0.0
    last_mouse_y: float = 0.0
    tooltip_tags: list[int | str] = field(default_factory=list)
    completed_drags: int = 0

    def reset(self) -> None:
        self.bindings.clear()
        self.active_knob = None
        self.drag_position = 0.0
        self.last_mouse_y = 0.0
        self.tooltip_tags.clear()
        self.completed_drags = 0


KNOB_INTERACTION = KnobInteraction()


@dataclass(slots=True)
class CanvasInteraction:
    """Pan and zoom state for the rack camera."""

    panning: bool = False
    pan_candidate: bool = False
    press_x: float = 0.0
    press_y: float = 0.0
    last_mouse_x: float = 0.0
    last_mouse_y: float = 0.0
    zoom: float = 1.0
    zoom_target: float = 1.0
    zoom_anchor: tuple[float, float] | None = None
    pending_magnification: float = 0.0
    rail_y: dict[str, float] = field(default_factory=dict)

    def reset(self) -> None:
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
        self.rail_y.clear()

    def arm_pan(self, screen_position: tuple[float, float]) -> None:
        self.pan_candidate = True
        self.press_x = float(screen_position[0])
        self.press_y = float(screen_position[1])

    def stop_panning(self) -> None:
        self.panning = False
        self.pan_candidate = False
        self.press_x = 0.0
        self.press_y = 0.0
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0


CANVAS_INTERACTION = CanvasInteraction()


@dataclass(slots=True)
class ModuleCollapseInteraction:
    """Visibility snapshots for modules folded down to their title bars."""

    attributes: dict[int | str, dict[int | str, bool]] = field(
        default_factory=dict
    )
    labels: dict[int | str, str] = field(default_factory=dict)

    def reset(self) -> None:
        self.attributes.clear()
        self.labels.clear()

    def is_collapsed(self, node: int | str) -> bool:
        return node in self.attributes


MODULE_COLLAPSE = ModuleCollapseInteraction()


def _reset_rack_registry() -> None:
    """Return mutable node registries to the built-in init rack."""
    RACK_NODES[:] = BASE_RACK_NODES
    INSTANCE_NODE_TAGS.clear()
    INSTANCE_NODE_TAGS.update(BASE_INSTANCE_NODE_TAGS)
    VIEW_NODE_TAGS.clear()
    VIEW_NODE_TAGS.update(INSTANCE_NODE_TAGS)
    VIEW_NODE_TAGS["system_output"] = OUTPUT_NODE
    RACK_RAILS[CONTROL_RAIL][:] = [FUNCTION_NODE, WOGGLE_NODE, SCALE_NODE]
    RACK_RAILS[AUDIO_RAIL][:] = [
        VCO_NODE,
        MIXER_NODE,
        LPG_NODE,
        REVERB_NODE,
        OUTPUT_NODE,
    ]
    MODULE_ACCENTS.clear()
    MODULE_ACCENTS.update(BASE_MODULE_ACCENTS)


@dataclass(frozen=True, slots=True)
class PatchBayBinding:
    """UI state for one module's compact, graph-aware jack list."""

    patch: PatchGraph
    module_id: str
    node_tag: str
    port_ids: tuple[str, ...]
    toggle_tag: str
    status_tag: str


PATCH_BAYS: dict[str, PatchBayBinding] = {}


@dataclass(frozen=True, slots=True)
class ResolvedJack:
    """A node-editor attribute resolved to its runtime patch endpoint."""

    attribute: int | str
    endpoint: Endpoint | None
    direction: PortDirection
    signal: str
    name: str
    output_channel: OutputChannel | None = None


def _configure_font() -> None:
    """Use a readable macOS font that includes the patch-direction glyphs."""
    if dpg.does_item_exist(APP_FONT) or not SYSTEM_MONO_FONT.is_file():
        return
    with dpg.font_registry(tag=FONT_REGISTRY):
        dpg.add_font(str(SYSTEM_MONO_FONT), 16, tag=APP_FONT)
    dpg.bind_font(APP_FONT)


def _node_theme(tag: str, accent: tuple[int, int, int, int]) -> None:
    with dpg.theme(tag=tag):
        with dpg.theme_component(dpg.mvNode):
            dpg.add_theme_color(
                dpg.mvNodeCol_TitleBar,
                accent,
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_TitleBarHovered,
                tuple(min(channel + 18, 255) for channel in accent[:3]) + (255,),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_TitleBarSelected,
                accent,
                category=dpg.mvThemeCat_Nodes,
            )


def _link_theme(tag: str, color: tuple[int, int, int, int]) -> None:
    with dpg.theme(tag=tag):
        with dpg.theme_component(dpg.mvNodeLink):
            dpg.add_theme_color(
                dpg.mvNodeCol_Link,
                color,
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_LinkHovered,
                TEXT,
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_LinkSelected,
                TEXT,
                category=dpg.mvThemeCat_Nodes,
            )


def _configure_theme() -> None:
    """Build Noodler's warm, instrument-like visual language."""
    if dpg.does_item_exist(APP_THEME):
        return
    with dpg.theme(tag=APP_THEME):
        with dpg.theme_component(dpg.mvAll):
            for theme_color, color in (
                (dpg.mvThemeCol_WindowBg, (20, 19, 17, 255)),
                (dpg.mvThemeCol_ChildBg, (24, 23, 21, 255)),
                (dpg.mvThemeCol_TitleBg, (35, 33, 29, 255)),
                (dpg.mvThemeCol_TitleBgActive, (73, 66, 55, 255)),
                (dpg.mvThemeCol_TitleBgCollapsed, (35, 33, 29, 255)),
                (dpg.mvThemeCol_Text, TEXT),
                (dpg.mvThemeCol_TextDisabled, MUTED_TEXT),
                (dpg.mvThemeCol_FrameBg, (48, 45, 40, 255)),
                (dpg.mvThemeCol_FrameBgHovered, (61, 57, 50, 255)),
                (dpg.mvThemeCol_FrameBgActive, (68, 63, 55, 255)),
                (dpg.mvThemeCol_Button, (57, 53, 47, 255)),
                (dpg.mvThemeCol_ButtonHovered, (76, 70, 60, 255)),
                (dpg.mvThemeCol_ButtonActive, (91, 83, 70, 255)),
                (dpg.mvThemeCol_CheckMark, UTILITY_ACCENT),
                (dpg.mvThemeCol_SliderGrab, VCO_ACCENT),
                (dpg.mvThemeCol_SliderGrabActive, TEXT),
                (dpg.mvThemeCol_Border, (87, 80, 68, 255)),
                (dpg.mvThemeCol_Separator, (75, 70, 62, 180)),
                (dpg.mvThemeCol_ScrollbarBg, (24, 23, 21, 255)),
                (dpg.mvThemeCol_ScrollbarGrab, (76, 70, 60, 255)),
                (dpg.mvThemeCol_ScrollbarGrabHovered, (97, 88, 74, 255)),
                (dpg.mvThemeCol_ScrollbarGrabActive, UTILITY_ACCENT),
            ):
                dpg.add_theme_color(theme_color, color)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 7)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 8)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 5)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 9, 7)
        with dpg.theme_component(dpg.mvNode):
            for node_color, color in (
                (dpg.mvNodeCol_GridBackground, (22, 23, 21, 255)),
                (dpg.mvNodeCol_GridLine, (43, 45, 40, 150)),
                (dpg.mvNodeCol_BoxSelector, (22, 23, 21, 0)),
                (dpg.mvNodeCol_BoxSelectorOutline, (22, 23, 21, 0)),
                (dpg.mvNodeCol_NodeBackground, (38, 36, 32, 248)),
                (dpg.mvNodeCol_NodeBackgroundHovered, (43, 41, 36, 252)),
                (dpg.mvNodeCol_NodeBackgroundSelected, (45, 42, 37, 255)),
                (dpg.mvNodeCol_NodeOutline, (92, 84, 70, 255)),
                (dpg.mvNodeCol_Pin, (224, 208, 169, 255)),
                (dpg.mvNodeCol_PinHovered, (255, 245, 210, 255)),
            ):
                dpg.add_theme_color(
                    node_color,
                    color,
                    category=dpg.mvThemeCat_Nodes,
                )
            for node_style, value in (
                (dpg.mvNodeStyleVar_NodeCornerRounding, 10),
                (dpg.mvNodeStyleVar_NodeBorderThickness, 1.5),
                (dpg.mvNodeStyleVar_PinCircleRadius, 5),
                (dpg.mvNodeStyleVar_PinHoverRadius, 9),
                (dpg.mvNodeStyleVar_LinkThickness, 3),
                (dpg.mvNodeStyleVar_GridSpacing, 32),
            ):
                dpg.add_theme_style(
                    node_style,
                    value,
                    category=dpg.mvThemeCat_Nodes,
                )
    _node_theme(UTILITY_THEME, UTILITY_ACCENT)
    _node_theme(VCO_THEME, VCO_ACCENT)
    _node_theme(MIXER_THEME, MIXER_ACCENT)
    _node_theme(OUTPUT_THEME, OUTPUT_ACCENT)
    _node_theme(WOGGLE_THEME, WOGGLE_ACCENT)
    _node_theme(SCALE_THEME, SCALE_ACCENT)
    _node_theme(LPG_THEME, LPG_ACCENT)
    _node_theme(REVERB_THEME, REVERB_ACCENT)
    _link_theme(CV_LINK_THEME, SIGNAL_COLORS["cv"])
    _link_theme(AUDIO_LINK_THEME, SIGNAL_COLORS["audio"])
    _link_theme(GATE_LINK_THEME, SIGNAL_COLORS["gate"])
    _link_theme(MUSICAL_LINK_THEME, SIGNAL_COLORS["musical"])
    with dpg.theme(tag=METER_THEME):
        with dpg.theme_component(dpg.mvProgressBar):
            dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, OUTPUT_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 40, 36, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
    dpg.bind_theme(APP_THEME)


def _set_wave_b(_sender: str, value: str, vco: ComplexVCO) -> None:
    vco.parameters.wave_b = WaveB(value)


def _start_audio(
    _sender: str,
    _value: object,
    engine: SystemAudioEngine,
) -> None:
    try:
        engine.start()
        rate = engine.sample_rate
        dpg.set_value(
            AUDIO_STATUS,
            f"Playing on {engine.output_device_name} at {rate:.0f} Hz",
        )
    except Exception as exc:
        dpg.set_value(AUDIO_STATUS, f"Audio error: {exc}")


def _stop_audio(
    _sender: str,
    _value: object,
    engine: SystemAudioEngine,
) -> None:
    engine.stop()
    dpg.set_value(AUDIO_STATUS, "Stopped")


def _set_patch_status(message: str, *, error: bool = False) -> None:
    """Put patch-edit feedback where it remains visible above the rack."""
    if not dpg.does_item_exist(CONTROL_STATUS):
        return
    dpg.set_value(CONTROL_STATUS, message)
    dpg.configure_item(
        CONTROL_STATUS,
        color=OUTPUT_ACCENT if error else MUTED_TEXT,
    )


def _resolve_jack(attribute: int | str, runtime: AppRuntime) -> ResolvedJack:
    """Resolve a Dear PyGui attribute item to a graph endpoint."""
    alias = dpg.get_item_alias(attribute)
    tag = alias or (attribute if isinstance(attribute, str) else "")
    system_outputs = {
        f"{OUTPUT_NODE}.mono": (OutputChannel.BOTH, "System Mono"),
        f"{OUTPUT_NODE}.left": (OutputChannel.LEFT, "System Left"),
        f"{OUTPUT_NODE}.right": (OutputChannel.RIGHT, "System Right"),
    }
    if tag in system_outputs:
        channel, name = system_outputs[tag]
        return ResolvedJack(
            attribute=attribute,
            endpoint=None,
            direction=PortDirection.INPUT,
            signal="audio",
            name=name,
            output_channel=channel,
        )

    for module_id, node_tag in INSTANCE_NODE_TAGS.items():
        prefix = f"{node_tag}."
        if not str(tag).startswith(prefix):
            continue
        port_id = str(tag).removeprefix(prefix)
        module = runtime.patch.modules[module_id]
        port = next(
            (candidate for candidate in module.manifest.ports if candidate.id == port_id),
            None,
        )
        if port is None:
            break
        return ResolvedJack(
            attribute=attribute,
            endpoint=Endpoint(module_id=module_id, port_id=port_id),
            direction=port.direction,
            signal=port.signal_type.value,
            name=port.name,
        )
    raise PatchError("that control is not a patch jack")


def _edit_patch(runtime: AppRuntime, operation: Callable[[], object]) -> object:
    """Make a topology change while no audio callback can read the graph."""
    was_running = runtime.audio.is_running
    if was_running:
        runtime.audio.stop()
    try:
        result = operation()
    except Exception:
        if was_running:
            try:
                runtime.audio.start()
            except Exception as restart_error:
                if dpg.does_item_exist(AUDIO_STATUS):
                    dpg.set_value(AUDIO_STATUS, f"Audio error: {restart_error}")
        raise
    if was_running:
        try:
            runtime.audio.start()
        except Exception as restart_error:
            if dpg.does_item_exist(AUDIO_STATUS):
                dpg.set_value(AUDIO_STATUS, f"Audio error: {restart_error}")
    return result


def _add_visual_link(
    source_attribute: int | str,
    target_attribute: int | str,
    route: Cable | OutputTap,
    signal: str,
    *,
    tag: int | str = 0,
) -> int | str:
    """Draw one graph-backed cable and give it the matching signal color."""
    link = dpg.add_node_link(
        source_attribute,
        target_attribute,
        parent=RACK,
        tag=tag,
        user_data=route,
    )
    theme = {
        "audio": AUDIO_LINK_THEME,
        "cv": CV_LINK_THEME,
        "gate": GATE_LINK_THEME,
        "trigger": GATE_LINK_THEME,
        "musical": MUSICAL_LINK_THEME,
    }.get(signal, CV_LINK_THEME)
    dpg.bind_item_theme(link, theme)
    return link


def _default_cable(
    patch: PatchGraph,
    source_module: str,
    source_port: str,
    target_module: str,
    target_port: str,
) -> Cable:
    """Find one known init-patch route without depending on list position."""
    route = next(
        (
            cable
            for cable in patch.cables
            if cable.source
            == Endpoint(module_id=source_module, port_id=source_port)
            and cable.target
            == Endpoint(module_id=target_module, port_id=target_port)
        ),
        None,
    )
    if route is None:
        raise PatchError(
            f"missing init route: {source_module}.{source_port} -> "
            f"{target_module}.{target_port}"
        )
    return route


def _patch_link_created(
    _sender: int | str,
    app_data: tuple[int | str, int | str],
    runtime: AppRuntime,
) -> None:
    """Turn a cable gesture into a validated graph route."""
    try:
        if not isinstance(app_data, (tuple, list)) or len(app_data) != 2:
            raise PatchError("could not identify both cable ends")
        first = _resolve_jack(app_data[0], runtime)
        second = _resolve_jack(app_data[1], runtime)
        system_jacks = [jack for jack in (first, second) if jack.endpoint is None]

        if system_jacks:
            if len(system_jacks) != 1:
                raise PatchError("the system output cannot be connected to itself")
            source = second if first.endpoint is None else first
            target = first if first.endpoint is None else second
            if source.direction is not PortDirection.OUTPUT or source.endpoint is None:
                raise PatchError("the system output needs a module output")
            if target.direction is not PortDirection.INPUT:
                raise PatchError("the system output is not a signal source")
            if target.output_channel is None:
                raise PatchError("could not identify the system output channel")
            if any(
                tap.channel is target.output_channel
                for tap in runtime.patch.output_taps
            ):
                raise PatchError(f"{target.name.lower()} already has a cable")
            tap = _edit_patch(
                runtime,
                lambda: runtime.patch.connect_output(
                    source.endpoint.module_id,
                    source.endpoint.port_id,
                    channel=target.output_channel,
                ),
            )
            assert isinstance(tap, OutputTap)
            _add_visual_link(
                source.attribute,
                target.attribute,
                tap,
                source.signal,
            )
            _refresh_patch_bays(runtime.patch)
            _set_patch_status(
                f"PATCHED  {source.name.upper()}  →  {target.name.upper()}"
            )
            return

        if first.direction is second.direction:
            kind = "outputs" if first.direction is PortDirection.OUTPUT else "inputs"
            raise PatchError(f"cannot connect two {kind}")
        source = first if first.direction is PortDirection.OUTPUT else second
        target = second if source is first else first
        assert source.endpoint is not None and target.endpoint is not None
        cable = _edit_patch(
            runtime,
            lambda: runtime.patch.connect(
                source.endpoint.module_id,
                source.endpoint.port_id,
                target.endpoint.module_id,
                target.endpoint.port_id,
            ),
        )
        assert isinstance(cable, Cable)
        _add_visual_link(
            source.attribute,
            target.attribute,
            cable,
            source.signal,
        )
        _refresh_patch_bays(runtime.patch)
        _set_patch_status(
            f"PATCHED  {source.name.upper()}  →  {target.name.upper()}"
        )
    except (PatchError, ValueError) as exc:
        _set_patch_status(f"CAN'T PATCH: {exc}", error=True)
    except Exception as exc:
        _set_patch_status(f"PATCH ERROR: {exc}", error=True)


def _patch_link_deleted(
    _sender: int | str,
    link: int | str,
    runtime: AppRuntime,
) -> None:
    """Remove the graph route represented by a deleted node-editor link."""
    try:
        route = dpg.get_item_user_data(link)
        if isinstance(route, Cable):
            _edit_patch(runtime, lambda: runtime.patch.disconnect(route))
            description = (
                f"{route.source.module_id}.{route.source.port_id}  →  "
                f"{route.target.module_id}.{route.target.port_id}"
            )
        elif isinstance(route, OutputTap):
            _edit_patch(runtime, lambda: runtime.patch.disconnect_output(route))
            description = f"{route.source.module_id}.{route.source.port_id}  →  out"
        else:
            raise PatchError("cable has no patch route")
        dpg.delete_item(link)
        _refresh_patch_bays(runtime.patch)
        _set_patch_status(f"UNPATCHED  {description.upper()}")
    except (PatchError, ValueError) as exc:
        _set_patch_status(f"CAN'T UNPATCH: {exc}", error=True)
    except Exception as exc:
        _set_patch_status(f"UNPATCH ERROR: {exc}", error=True)


def _unplug_all(
    _sender: int | str,
    _value: object,
    runtime: AppRuntime,
) -> None:
    """Remove every visual cable and its corresponding executable route."""
    try:
        connection_count = len(runtime.patch.cables) + len(
            runtime.patch.output_taps
        )
        if connection_count == 0:
            _set_patch_status("NO CABLES TO UNPLUG")
            return

        removed = _edit_patch(runtime, runtime.patch.disconnect_all)
        rack_children = dpg.get_item_children(RACK)
        for item in tuple(rack_children.get(0, ())):
            route = dpg.get_item_user_data(item)
            if isinstance(route, (Cable, OutputTap)):
                dpg.delete_item(item)

        _refresh_patch_bays(runtime.patch)
        noun = "CABLE" if removed == 1 else "CABLES"
        _set_patch_status(f"UNPLUGGED ALL  ·  {removed} {noun} REMOVED")
    except Exception as exc:
        _set_patch_status(f"UNPLUG ERROR: {exc}", error=True)


def _capture_current_preset(runtime: AppRuntime, name: str) -> PatchPreset:
    nodes = tuple(
        RackNodePreset(
            node_id=node_id,
            position=Point(
                x=float(dpg.get_item_pos(node)[0]),
                y=float(dpg.get_item_pos(node)[1]),
            ),
            collapsed=MODULE_COLLAPSE.is_collapsed(node),
        )
        for node_id, node in VIEW_NODE_TAGS.items()
        if dpg.does_item_exist(node)
    )
    view = RackViewPreset(
        zoom=CANVAS_INTERACTION.zoom,
        rails=dict(CANVAS_INTERACTION.rail_y),
        nodes=nodes,
    )
    return capture_patch_preset(
        name=name,
        patch=runtime.patch,
        master_gain=runtime.audio.master_gain,
        view=view,
    )


def _show_save_patch_dialog(
    _sender: int | str,
    _app_data: object,
    _user_data: object,
) -> None:
    if dpg.does_item_exist(SAVE_PATCH_DIALOG):
        dpg.show_item(SAVE_PATCH_DIALOG)


def _save_patch_dialog(
    _sender: int | str,
    app_data: object,
    runtime: AppRuntime,
) -> None:
    """Validate and save the current instrument from a file-dialog result."""
    try:
        if not isinstance(app_data, dict):
            raise ValueError("the file dialog did not return a destination")
        selected = app_data.get("file_path_name")
        if not isinstance(selected, str) or not selected:
            raise ValueError("choose a patch filename")
        requested_path = Path(selected)
        name = requested_path.stem or "Untitled Patch"
        preset = _capture_current_preset(runtime, name)
        destination = write_patch_preset(preset, requested_path)
        _set_patch_status(f"SAVED PATCH  ·  {destination.name}")
    except (OSError, TypeError, ValueError) as exc:
        _set_patch_status(f"SAVE ERROR: {exc}", error=True)


def _refresh_ui(runtime: AppRuntime) -> None:
    """Copy inexpensive audio telemetry onto the UI thread."""
    if not dpg.does_item_exist(OUTPUT_METER):
        return
    peak = min(max(runtime.audio.last_peak, 0.0), 1.0)
    dpg.set_value(OUTPUT_METER, peak)
    decibels = "-∞ dB" if peak <= 0.00001 else f"{20.0 * math.log10(peak):.0f} dB"
    dpg.configure_item(OUTPUT_METER, overlay=decibels)
    if dpg.does_item_exist(SCALE_NOTE_STATUS):
        generator = runtime.scale_generator
        dpg.set_value(
            SCALE_NOTE_STATUS,
            f"{generator.current_note}  ·  "
            f"DEGREE {generator.current_degree}/{generator.degree_count}  ·  "
            f"{generator.current_frequency:.2f} Hz",
        )


def _refresh_frame(
    _sender: str,
    _app_data: object,
    runtime: AppRuntime,
) -> None:
    _consume_macos_magnification()
    _settle_rack_zoom()
    _settle_rack_rails()
    _refresh_ui(runtime)
    dpg.set_frame_callback(
        dpg.get_frame_count() + 1,
        _refresh_frame,
        user_data=runtime,
    )


def _connected_port_ids(patch: PatchGraph, module_id: str) -> set[str]:
    """Return the jacks currently participating in the executable graph."""
    connected: set[str] = set()
    for cable in patch.cables:
        if cable.source.module_id == module_id:
            connected.add(cable.source.port_id)
        if cable.target.module_id == module_id:
            connected.add(cable.target.port_id)
    connected.update(
        tap.source.port_id
        for tap in patch.output_taps
        if tap.source.module_id == module_id
    )
    return connected


def _patch_bay_flow_label(binding: PatchBayBinding, connected: set[str]) -> str:
    ports = {
        port.id: port
        for port in binding.patch.modules[binding.module_id].manifest.ports
    }
    inputs = sum(
        ports[port_id].direction is PortDirection.INPUT
        for port_id in connected.intersection(binding.port_ids)
    )
    outputs = sum(
        ports[port_id].direction is PortDirection.OUTPUT
        for port_id in connected.intersection(binding.port_ids)
    )
    if inputs and outputs:
        flow = f"{inputs} IN  →  {outputs} OUT"
    elif inputs:
        flow = f"{inputs} IN"
    else:
        flow = f"{outputs} OUT"
    return f"SIGNAL PATH  ·  {flow}"


def _refresh_patch_bay(binding: PatchBayBinding) -> None:
    """Show all jacks while expanded, otherwise only live connections."""
    connected = _connected_port_ids(binding.patch, binding.module_id)
    expanded = (
        bool(dpg.get_value(binding.toggle_tag))
        if dpg.does_item_exist(binding.toggle_tag)
        else False
    )
    for port_id in binding.port_ids:
        tag = f"{binding.node_tag}.{port_id}"
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=expanded or port_id in connected)
    if dpg.does_item_exist(binding.status_tag):
        dpg.set_value(binding.status_tag, _patch_bay_flow_label(binding, connected))
    if MODULE_COLLAPSE.is_collapsed(binding.node_tag):
        visibility = MODULE_COLLAPSE.attributes[binding.node_tag]
        for port_id in binding.port_ids:
            attribute = f"{binding.node_tag}.{port_id}"
            if dpg.does_item_exist(attribute):
                visibility[attribute] = bool(
                    dpg.get_item_configuration(attribute)["show"]
                )
        for attribute in _node_attributes(binding.node_tag):
            dpg.configure_item(attribute, show=False)


def _refresh_patch_bays(patch: PatchGraph) -> None:
    for binding in PATCH_BAYS.values():
        if binding.patch is patch:
            _refresh_patch_bay(binding)


def _toggle_patch_bay(
    _sender: str,
    _expanded: bool,
    binding: PatchBayBinding,
) -> None:
    _refresh_patch_bay(binding)


def _add_patch_bay_toggle(
    patch: PatchGraph,
    module_id: str,
    node_tag: str,
    port_ids: tuple[str, ...],
) -> None:
    """Add a compact-by-default disclosure for one module's ports."""
    binding = PatchBayBinding(
        patch=patch,
        module_id=module_id,
        node_tag=node_tag,
        port_ids=port_ids,
        toggle_tag=f"{node_tag}.patch_bay.expanded",
        status_tag=f"{node_tag}.patch_bay.status",
    )
    PATCH_BAYS[module_id] = binding
    connected = _connected_port_ids(patch, module_id)
    dpg.add_separator()
    with dpg.group(horizontal=True):
        dpg.add_text(
            _patch_bay_flow_label(binding, connected),
            tag=binding.status_tag,
            color=MUTED_TEXT,
        )
        dpg.add_checkbox(
            label="SHOW ALL",
            tag=binding.toggle_tag,
            default_value=False,
            callback=_toggle_patch_bay,
            user_data=binding,
        )


def _format_duration(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f} us"
    if seconds < 1.0:
        return f"{seconds * 1_000:.1f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    return f"{seconds / 60.0:.2f} min"


def _format_frequency(frequency: float) -> str:
    if frequency < 1.0:
        return f"{frequency:.2f} Hz"
    if frequency < 1_000.0:
        return f"{frequency:.1f} Hz"
    return f"{frequency / 1_000.0:.2f} kHz"


def _control_position(
    value: float,
    minimum: float,
    maximum: float,
    logarithmic: bool,
) -> float:
    if not logarithmic:
        return value
    log_minimum = math.log(minimum)
    return (math.log(value) - log_minimum) / (math.log(maximum) - log_minimum)


def _control_value(position: float, binding: KnobBinding) -> float:
    if not binding.logarithmic:
        return position
    log_minimum = math.log(binding.minimum)
    span = math.log(binding.maximum) - log_minimum
    return math.exp(log_minimum + position * span)


def _knob_bounds(binding: KnobBinding) -> tuple[float, float]:
    return (0.0, 1.0) if binding.logarithmic else (
        binding.minimum,
        binding.maximum,
    )


def _vertical_drag_position(
    start_position: float,
    delta_y: float,
    binding: KnobBinding,
    *,
    fine: bool = False,
) -> float:
    """Map upward mouse movement to a higher knob position."""
    minimum, maximum = _knob_bounds(binding)
    travel = 180.0 * (10.0 if fine else 1.0)
    position = start_position - delta_y * (maximum - minimum) / travel
    return min(maximum, max(minimum, position))


def _set_knob_value(
    _sender: str,
    position: float,
    binding: KnobBinding,
) -> None:
    value = min(
        binding.maximum,
        max(binding.minimum, _control_value(position, binding)),
    )
    binding.setter(value)
    dpg.set_value(binding.value_label, binding.formatter(value))


def _point_is_over_rack(screen_position: tuple[float, float]) -> bool:
    if not dpg.does_item_exist(RACK):
        return False
    mouse_x, mouse_y = screen_position
    minimum_x, minimum_y = dpg.get_item_rect_min(RACK)
    maximum_x, maximum_y = dpg.get_item_rect_max(RACK)
    return (
        minimum_x <= mouse_x <= maximum_x
        and minimum_y <= mouse_y <= maximum_y
    )


def _mouse_is_over_rack() -> bool:
    if not dpg.does_item_exist(RACK):
        return False
    if bool(dpg.get_item_state(RACK).get("hovered", False)):
        return True
    return _point_is_over_rack(tuple(dpg.get_mouse_pos(local=False)))


def _point_is_over_rack_background(
    screen_position: tuple[float, float],
) -> bool:
    """Treat every part of the editor outside a module as pannable canvas."""
    if not _point_is_over_rack(screen_position):
        return False
    mouse_x, mouse_y = screen_position
    for node in RACK_NODES:
        if not dpg.does_item_exist(node):
            continue
        minimum_x, minimum_y = dpg.get_item_rect_min(node)
        maximum_x, maximum_y = dpg.get_item_rect_max(node)
        if minimum_x <= mouse_x <= maximum_x and minimum_y <= mouse_y <= maximum_y:
            return False
    return True


def _mouse_is_over_rack_background() -> bool:
    return _point_is_over_rack_background(
        tuple(dpg.get_mouse_pos(local=False))
    )


def _zoomed_position(
    position: tuple[float, float] | list[float],
    anchor: tuple[float, float],
    ratio: float,
) -> tuple[float, float]:
    """Scale one rack-space position while keeping the anchor stationary."""
    return (
        anchor[0] + (float(position[0]) - anchor[0]) * ratio,
        anchor[1] + (float(position[1]) - anchor[1]) * ratio,
    )


def _rack_zoom_anchor(
    screen_position: tuple[float, float] | None = None,
) -> tuple[float, float]:
    """Convert a screen position to the node editor's local coordinates."""
    rack_minimum_x, rack_minimum_y = dpg.get_item_rect_min(RACK)
    if screen_position is None:
        rack_width, rack_height = dpg.get_item_rect_size(RACK)
        return (rack_width * 0.5, rack_height * 0.5)
    return (
        float(screen_position[0]) - rack_minimum_x,
        float(screen_position[1]) - rack_minimum_y,
    )


def _set_rack_zoom(
    requested_zoom: float,
    *,
    screen_anchor: tuple[float, float] | None = None,
) -> None:
    """Zoom the complete rack around the cursor or editor center."""
    old_zoom = CANVAS_INTERACTION.zoom
    new_zoom = min(MAX_RACK_ZOOM, max(MIN_RACK_ZOOM, float(requested_zoom)))
    CANVAS_INTERACTION.zoom_target = new_zoom
    CANVAS_INTERACTION.zoom_anchor = screen_anchor
    if math.isclose(old_zoom, new_zoom, abs_tol=1e-6):
        return

    anchor = _rack_zoom_anchor(screen_anchor)
    ratio = new_zoom / old_zoom
    for node in RACK_NODES:
        if not dpg.does_item_exist(node):
            continue
        dpg.set_item_pos(
            node,
            list(_zoomed_position(dpg.get_item_pos(node), anchor, ratio)),
        )
    for rail, rail_y in tuple(CANVAS_INTERACTION.rail_y.items()):
        CANVAS_INTERACTION.rail_y[rail] = _zoomed_position(
            (0.0, rail_y),
            anchor,
            ratio,
        )[1]
    for knob, binding in KNOB_INTERACTION.bindings.items():
        if dpg.does_item_exist(knob):
            dpg.configure_item(
                knob,
                width=max(30, round(binding.size * new_zoom)),
            )

    CANVAS_INTERACTION.zoom = new_zoom
    dpg.set_global_font_scale(new_zoom)
    if dpg.does_item_exist(ZOOM_RESET_BUTTON):
        dpg.configure_item(ZOOM_RESET_BUTTON, label=f"{new_zoom:.0%}")
    _set_patch_status(
        f"RACK ZOOM  {new_zoom:.0%}  ·  SCROLL OR USE − / +"
    )


def _queue_rack_zoom(
    requested_zoom: float,
    *,
    screen_anchor: tuple[float, float],
) -> None:
    """Set a camera destination that subsequent frames ease toward."""
    CANVAS_INTERACTION.zoom_target = min(
        MAX_RACK_ZOOM,
        max(MIN_RACK_ZOOM, float(requested_zoom)),
    )
    CANVAS_INTERACTION.zoom_anchor = screen_anchor


def _capture_macos_magnification(delta: float) -> None:
    """Collect native gesture deltas for the next Dear PyGui frame."""
    if math.isfinite(delta):
        CANVAS_INTERACTION.pending_magnification += float(delta)


def _consume_macos_magnification() -> None:
    """Apply one frame of native pinch input to the rack camera target."""
    interaction = CANVAS_INTERACTION
    delta = interaction.pending_magnification
    interaction.pending_magnification = 0.0
    if delta == 0.0 or not _mouse_is_over_rack():
        return
    _queue_rack_zoom(
        interaction.zoom_target * max(0.1, 1.0 + delta),
        screen_anchor=tuple(dpg.get_mouse_pos(local=False)),
    )


def _settle_rack_zoom() -> None:
    """Ease trackpad and wheel zoom while keeping the pointer anchored."""
    interaction = CANVAS_INTERACTION
    remaining = interaction.zoom_target - interaction.zoom
    if math.isclose(remaining, 0.0, abs_tol=0.001):
        if not math.isclose(interaction.zoom, interaction.zoom_target):
            target = interaction.zoom_target
            anchor = interaction.zoom_anchor
            _set_rack_zoom(target, screen_anchor=anchor)
        return
    target = interaction.zoom_target
    anchor = interaction.zoom_anchor
    next_zoom = interaction.zoom + remaining * 0.3
    _set_rack_zoom(next_zoom, screen_anchor=anchor)
    interaction.zoom_target = target
    interaction.zoom_anchor = anchor


def _zoom_rack(
    _sender: int | str,
    wheel_delta: float,
    _user_data: object,
) -> None:
    """Turn wheel and trackpad scroll events over the rack into zoom."""
    if not _mouse_is_over_rack():
        return
    delta = min(4.0, max(-4.0, float(wheel_delta)))
    if delta == 0.0:
        return
    _queue_rack_zoom(
        CANVAS_INTERACTION.zoom_target * (RACK_ZOOM_STEP ** delta),
        screen_anchor=tuple(dpg.get_mouse_pos(local=False)),
    )


def _zoom_rack_button(
    _sender: int | str,
    _value: object,
    direction: int,
) -> None:
    """Move the rack camera one visible zoom step."""
    _set_rack_zoom(
        CANVAS_INTERACTION.zoom * (RACK_ZOOM_STEP ** direction)
    )


def _reset_rack_zoom(
    _sender: int | str,
    _value: object,
    _user_data: object,
) -> None:
    _set_rack_zoom(1.0)


def _rail_x_targets(
    positions: tuple[float, ...],
    widths: tuple[float, ...],
    *,
    active_index: int | None,
    gap: float,
) -> tuple[float, ...]:
    """Make room around an active module while preserving semantic order."""
    if len(positions) != len(widths):
        raise ValueError("rail positions and widths must have the same length")
    if not positions:
        return ()
    targets = list(positions)
    if active_index is None:
        for index in range(1, len(targets)):
            minimum = targets[index - 1] + widths[index - 1] + gap
            targets[index] = max(targets[index], minimum)
        return tuple(targets)
    if not 0 <= active_index < len(targets):
        raise ValueError("active rail index is out of range")

    for index in range(active_index - 1, -1, -1):
        maximum = targets[index + 1] - widths[index] - gap
        targets[index] = min(targets[index], maximum)
    for index in range(active_index + 1, len(targets)):
        minimum = targets[index - 1] + widths[index - 1] + gap
        targets[index] = max(targets[index], minimum)
    return tuple(targets)


def _dragged_rack_node() -> int | str | None:
    """Return the node currently under a native node-drag gesture."""
    if CANVAS_INTERACTION.panning or not dpg.is_mouse_button_dragging(
        dpg.mvMouseButton_Left,
        threshold=1.0,
    ):
        return None
    mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
    for node in RACK_NODES:
        if not dpg.does_item_exist(node):
            continue
        minimum_x, minimum_y = dpg.get_item_rect_min(node)
        maximum_x, maximum_y = dpg.get_item_rect_max(node)
        if minimum_x <= mouse_x <= maximum_x and minimum_y <= mouse_y <= maximum_y:
            return node
    return None


def _settle_rack_rails() -> None:
    """Spring modules onto semantic lanes and prevent horizontal overlap."""
    if CANVAS_INTERACTION.panning or not CANVAS_INTERACTION.rail_y:
        return
    active_node = _dragged_rack_node()
    easing = 0.24
    gap = RACK_RAIL_GAP * CANVAS_INTERACTION.zoom
    for rail, nodes in RACK_RAILS.items():
        available = tuple(node for node in nodes if dpg.does_item_exist(node))
        if not available:
            continue
        positions = tuple(float(dpg.get_item_pos(node)[0]) for node in available)
        widths = tuple(
            max(1.0, float(dpg.get_item_rect_size(node)[0]))
            for node in available
        )
        active_index = (
            available.index(active_node) if active_node in available else None
        )
        targets = _rail_x_targets(
            positions,
            widths,
            active_index=active_index,
            gap=gap,
        )
        target_y = CANVAS_INTERACTION.rail_y[rail]
        for node, current_x, target_x in zip(available, positions, targets):
            current_y = float(dpg.get_item_pos(node)[1])
            next_x = (
                current_x
                if node == active_node
                else current_x + (target_x - current_x) * easing
            )
            next_y = current_y + (target_y - current_y) * easing
            if abs(next_x - target_x) < 0.75:
                next_x = target_x
            if abs(next_y - target_y) < 0.75:
                next_y = target_y
            if next_x != current_x or next_y != current_y:
                dpg.set_item_pos(node, [next_x, next_y])


def _clear_rack_selection() -> None:
    if dpg.does_item_exist(RACK):
        dpg.clear_selected_nodes(RACK)
        dpg.clear_selected_links(RACK)


def _spine_texture_tag(node: int | str) -> str:
    return f"{node}.spine.texture"


def _spine_attribute_tag(node: int | str) -> str:
    return f"{node}.spine.attribute"


def _module_spine_labels(runtime: AppRuntime) -> dict[int | str, str]:
    labels = {
        node: runtime.patch.modules[instance_id].manifest.name.upper()
        for instance_id, node in INSTANCE_NODE_TAGS.items()
    }
    labels[OUTPUT_NODE] = "SYSTEM OUT"
    return labels


def _add_spine_texture(node: int | str, label: str) -> None:
    if dpg.does_item_exist(_spine_texture_tag(node)):
        return
    texture = render_spine_texture(
        label,
        MODULE_ACCENTS[node],
        SYSTEM_MONO_FONT,
    )
    dpg.add_static_texture(
        texture.width,
        texture.height,
        texture.pixels,
        tag=_spine_texture_tag(node),
        parent=SPINE_TEXTURE_REGISTRY,
    )


def _configure_spine_textures(runtime: AppRuntime) -> None:
    """Create rotated labels for collapsed book-spine modules."""
    if not dpg.does_item_exist(SPINE_TEXTURE_REGISTRY):
        dpg.add_texture_registry(tag=SPINE_TEXTURE_REGISTRY)
    for node, label in _module_spine_labels(runtime).items():
        _add_spine_texture(node, label)


def _add_module_spine(node: int | str) -> None:
    with dpg.node_attribute(
        parent=node,
        tag=_spine_attribute_tag(node),
        attribute_type=dpg.mvNode_Attr_Static,
        show=False,
    ):
        dpg.add_image(_spine_texture_tag(node))


def _add_module_spines(runtime: AppRuntime) -> None:
    """Attach one normally hidden vertical book spine to every module."""
    for node in _module_spine_labels(runtime):
        _add_module_spine(node)


def _node_attributes(node: int | str) -> tuple[int | str, ...]:
    """Return the immediate node attributes that make up a module panel."""
    return tuple(
        child
        for child in dpg.get_item_children(node).get(1, ())
        if dpg.get_item_type(child) == "mvAppItemType::mvNodeAttribute"
        and child != dpg.get_alias_id(_spine_attribute_tag(node))
    )


def _route_node_tags(route: Cable | OutputTap) -> set[int | str]:
    if isinstance(route, Cable):
        return {
            INSTANCE_NODE_TAGS[route.source.module_id],
            INSTANCE_NODE_TAGS[route.target.module_id],
        }
    return {INSTANCE_NODE_TAGS[route.source.module_id], OUTPUT_NODE}


def _sync_collapsed_link_visibility() -> None:
    """Hide visual cables whose live endpoint is inside a folded spine."""
    if not dpg.does_item_exist(RACK):
        return
    for link in dpg.get_item_children(RACK).get(0, ()):
        route = dpg.get_item_user_data(link)
        if not isinstance(route, (Cable, OutputTap)):
            continue
        hidden = any(
            MODULE_COLLAPSE.is_collapsed(node)
            for node in _route_node_tags(route)
        )
        dpg.configure_item(link, show=not hidden)


def _module_title_at(
    screen_position: tuple[float, float],
) -> int | str | None:
    """Find the top title-bar strip under one screen-space point."""
    mouse_x, mouse_y = screen_position
    title_height = max(24.0, min(44.0, 32.0 * CANVAS_INTERACTION.zoom))
    for node in reversed(RACK_NODES):
        if not dpg.does_item_exist(node):
            continue
        minimum_x, minimum_y = dpg.get_item_rect_min(node)
        maximum_x, maximum_y = dpg.get_item_rect_max(node)
        if MODULE_COLLAPSE.is_collapsed(node):
            if minimum_x <= mouse_x <= maximum_x and minimum_y <= mouse_y <= maximum_y:
                return node
            continue
        title_bottom = min(maximum_y, minimum_y + title_height)
        if minimum_x <= mouse_x <= maximum_x and minimum_y <= mouse_y <= title_bottom:
            return node
    return None


def _set_module_collapsed(
    node: int | str,
    collapsed: bool,
    runtime: AppRuntime,
) -> None:
    """Fold or unfold one visual module without touching its live graph."""
    if not dpg.does_item_exist(node):
        return
    state = MODULE_COLLAPSE
    if collapsed:
        if state.is_collapsed(node):
            return
        state.attributes[node] = {
            attribute: bool(dpg.get_item_configuration(attribute)["show"])
            for attribute in _node_attributes(node)
        }
        label = str(dpg.get_item_configuration(node)["label"])
        state.labels[node] = label
        for attribute in state.attributes[node]:
            dpg.configure_item(attribute, show=False)
        dpg.configure_item(_spine_attribute_tag(node), show=True)
        dpg.configure_item(node, label="▸")
        _sync_collapsed_link_visibility()
        _set_patch_status(f"FOLDED  {label}")
        return

    visibility = state.attributes.pop(node, None)
    label = state.labels.pop(node, None)
    if visibility is None or label is None:
        return
    for attribute, show in visibility.items():
        if dpg.does_item_exist(attribute):
            dpg.configure_item(attribute, show=show)
    dpg.configure_item(_spine_attribute_tag(node), show=False)
    dpg.configure_item(node, label=label)
    _refresh_patch_bays(runtime.patch)
    _sync_collapsed_link_visibility()
    _set_patch_status(f"OPENED  {label}")


def _toggle_module_from_title(
    _sender: int | str,
    _app_data: object,
    runtime: AppRuntime,
) -> None:
    """Fold the module whose title bar received a left double-click."""
    node = _module_title_at(tuple(dpg.get_mouse_pos(local=False)))
    if node is None:
        return
    _set_module_collapsed(node, not MODULE_COLLAPSE.is_collapsed(node), runtime)


def _begin_canvas_pan(
    origin: tuple[float, float] | None = None,
) -> None:
    mouse_x, mouse_y = origin or tuple(dpg.get_mouse_pos(local=False))
    CANVAS_INTERACTION.panning = True
    CANVAS_INTERACTION.pan_candidate = True
    CANVAS_INTERACTION.last_mouse_x = float(mouse_x)
    CANVAS_INTERACTION.last_mouse_y = float(mouse_y)
    _clear_rack_selection()
    if dpg.does_item_exist(CONTROL_STATUS):
        dpg.configure_item(CONTROL_STATUS, color=MUTED_TEXT)
        dpg.set_value(CONTROL_STATUS, "PANNING  ·  RELEASE TO PLACE VIEW")


def _pan_rack() -> None:
    interaction = CANVAS_INTERACTION
    _clear_rack_selection()
    mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
    delta_x = mouse_x - interaction.last_mouse_x
    delta_y = mouse_y - interaction.last_mouse_y
    if delta_x or delta_y:
        for node in RACK_NODES:
            if not dpg.does_item_exist(node):
                continue
            node_x, node_y = dpg.get_item_pos(node)
            dpg.set_item_pos(node, [node_x + delta_x, node_y + delta_y])
        for rail in tuple(interaction.rail_y):
            interaction.rail_y[rail] += delta_y
    interaction.last_mouse_x = float(mouse_x)
    interaction.last_mouse_y = float(mouse_y)


def _begin_knob_drag(
    _sender: str,
    _app_data: object,
    interaction: KnobInteraction,
) -> None:
    if interaction.active_knob is not None:
        return
    mouse_position = tuple(dpg.get_mouse_pos(local=False))
    if dpg.is_key_down(dpg.mvKey_Spacebar) and _mouse_is_over_rack():
        CANVAS_INTERACTION.arm_pan(mouse_position)
        _begin_canvas_pan(mouse_position)
        return
    for knob, binding in reversed(tuple(interaction.bindings.items())):
        if dpg.does_item_exist(knob) and dpg.is_item_hovered(knob):
            interaction.active_knob = knob
            interaction.drag_position = float(dpg.get_value(knob))
            interaction.last_mouse_y = float(dpg.get_mouse_pos(local=False)[1])
            if dpg.does_item_exist(CONTROL_STATUS):
                value = _control_value(interaction.drag_position, binding)
                dpg.configure_item(CONTROL_STATUS, color=MUTED_TEXT)
                dpg.set_value(
                    CONTROL_STATUS,
                    f"{binding.label.upper()}  {binding.formatter(value)}  "
                    "·  DRAG ↑ ↓  ·  SHIFT = FINE",
                )
            return
    if _mouse_is_over_rack_background():
        CANVAS_INTERACTION.arm_pan(mouse_position)
        _begin_canvas_pan(mouse_position)


def _drag_knob(
    _sender: str,
    _app_data: object,
    interaction: KnobInteraction,
) -> None:
    if CANVAS_INTERACTION.panning:
        _pan_rack()
        return
    knob = interaction.active_knob
    if knob is None:
        canvas = CANVAS_INTERACTION
        mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
        if canvas.pan_candidate:
            origin = (canvas.press_x, canvas.press_y)
        else:
            drag_x, drag_y = dpg.get_mouse_drag_delta(
                button=dpg.mvMouseButton_Left
            )
            origin = (float(mouse_x - drag_x), float(mouse_y - drag_y))
            if not _point_is_over_rack_background(origin):
                return
            canvas.arm_pan(origin)
        _begin_canvas_pan(origin)
        _pan_rack()
        return
    if not dpg.does_item_exist(knob):
        return
    binding = interaction.bindings[knob]
    mouse_y = float(dpg.get_mouse_pos(local=False)[1])
    fine = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
    position = _vertical_drag_position(
        interaction.drag_position,
        mouse_y - interaction.last_mouse_y,
        binding,
        fine=fine,
    )
    interaction.drag_position = position
    interaction.last_mouse_y = mouse_y
    dpg.set_value(knob, position)
    _set_knob_value(str(knob), position, binding)
    if dpg.does_item_exist(CONTROL_STATUS):
        value = _control_value(position, binding)
        precision = "FINE" if fine else "COARSE"
        dpg.set_value(
            CONTROL_STATUS,
            f"{binding.label.upper()}  {binding.formatter(value)}  ·  {precision}",
        )


def _end_knob_drag(
    _sender: str,
    _app_data: object,
    interaction: KnobInteraction,
) -> None:
    if CANVAS_INTERACTION.panning:
        _clear_rack_selection()
        CANVAS_INTERACTION.stop_panning()
        if dpg.does_item_exist(CONTROL_STATUS):
            dpg.configure_item(CONTROL_STATUS, color=MUTED_TEXT)
            dpg.set_value(CONTROL_STATUS, DEFAULT_CONTROL_STATUS)
        return
    CANVAS_INTERACTION.stop_panning()
    if interaction.active_knob is None:
        return
    interaction.active_knob = None
    interaction.completed_drags += 1
    if interaction.completed_drags == KNOB_HINT_DRAG_LIMIT:
        for tooltip in interaction.tooltip_tags:
            if dpg.does_item_exist(tooltip):
                dpg.configure_item(tooltip, show=False)
    if dpg.does_item_exist(CONTROL_STATUS):
        dpg.configure_item(CONTROL_STATUS, color=MUTED_TEXT)
        dpg.set_value(CONTROL_STATUS, DEFAULT_CONTROL_STATUS)


def _configure_knob_handlers(runtime: AppRuntime) -> None:
    if dpg.does_item_exist(INPUT_HANDLERS):
        return
    with dpg.handler_registry(tag=INPUT_HANDLERS):
        dpg.add_mouse_down_handler(
            button=dpg.mvMouseButton_Left,
            callback=_begin_knob_drag,
            user_data=KNOB_INTERACTION,
        )
        dpg.add_mouse_drag_handler(
            button=dpg.mvMouseButton_Left,
            threshold=0.0,
            callback=_drag_knob,
            user_data=KNOB_INTERACTION,
        )
        dpg.add_mouse_release_handler(
            button=dpg.mvMouseButton_Left,
            callback=_end_knob_drag,
            user_data=KNOB_INTERACTION,
        )
        dpg.add_mouse_double_click_handler(
            button=dpg.mvMouseButton_Left,
            callback=_toggle_module_from_title,
            user_data=runtime,
        )
        dpg.add_mouse_wheel_handler(callback=_zoom_rack)


def _add_knob(
    value: float,
    label: str,
    minimum: float,
    maximum: float,
    formatter: Callable[[float], str],
    setter: Callable[[float], None],
    *,
    logarithmic: bool = False,
    size: int = 62,
    tag: int | str = 0,
) -> int | str:
    """Add a compact rotary control with a separate live value readout."""
    position = _control_position(value, minimum, maximum, logarithmic)
    knob_minimum, knob_maximum = ((0.0, 1.0) if logarithmic else (minimum, maximum))
    with dpg.group():
        dpg.add_text(label.upper(), color=MUTED_TEXT)
        knob = dpg.add_knob_float(
            label="",
            tag=tag,
            default_value=position,
            min_value=knob_minimum,
            max_value=knob_maximum,
            width=size,
        )
        value_label = dpg.add_text(formatter(value), color=TEXT)
    dpg.configure_item(
        knob,
        callback=_set_knob_value,
        user_data=KnobBinding(
            setter=setter,
            label=label,
            value_label=value_label,
            minimum=minimum,
            maximum=maximum,
            formatter=formatter,
            logarithmic=logarithmic,
            size=size,
        ),
    )
    KNOB_INTERACTION.bindings[knob] = dpg.get_item_configuration(knob)["user_data"]
    with dpg.tooltip(knob) as tooltip:
        dpg.add_text("DRAG UP / DOWN", color=TEXT)
        dpg.add_text("Hold Shift for fine control", color=MUTED_TEXT)
    KNOB_INTERACTION.tooltip_tags.append(tooltip)
    return knob


def _set_attribute(target: object, attribute: str) -> Callable[[float], None]:
    return lambda value: setattr(target, attribute, value)


def _dynamic_parameter_bounds(
    field_info: object,
    value: float,
) -> tuple[float, float]:
    lower: float | None = None
    upper: float | None = None
    for constraint in getattr(field_info, "metadata", ()):
        for name in ("ge", "gt"):
            candidate = getattr(constraint, name, None)
            if candidate is not None:
                lower = float(candidate)
                if name == "gt":
                    lower += max(1e-6, abs(lower) * 1e-6)
        for name in ("le", "lt"):
            candidate = getattr(constraint, name, None)
            if candidate is not None:
                upper = float(candidate)
                if name == "lt":
                    upper -= max(1e-6, abs(upper) * 1e-6)
    if lower is None and upper is None:
        extent = max(1.0, abs(value) * 2.0)
        lower, upper = (-extent, extent) if value < 0.0 else (0.0, extent)
    elif lower is None:
        assert upper is not None
        lower = min(0.0, value - max(1.0, abs(value)))
    elif upper is None:
        upper = max(lower + 1.0, value + max(1.0, abs(value)))
    if upper <= lower:
        upper = lower + 1.0
    return lower, upper


def _set_dynamic_parameter(
    module: object,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    parameters = getattr(module, "parameters")
    values = parameters.model_dump(mode="python")
    target: object = values
    for component in path[:-1]:
        if isinstance(component, int):
            target = target[component]  # type: ignore[index]
        else:
            target = target[component]  # type: ignore[index]
    final = path[-1]
    if isinstance(final, int):
        sequence = list(target)  # type: ignore[arg-type]
        sequence[final] = value
        if len(path) != 2 or not isinstance(path[0], str):
            raise ValueError("nested sequence parameters are not supported")
        values[path[0]] = sequence
    else:
        target[final] = value  # type: ignore[index]

    configure = getattr(module, "configure", None)
    if len(path) == 1 and callable(configure):
        configure(**{str(path[0]): value})
    else:
        module.parameters = type(parameters).model_validate(values)


def _format_dynamic_value(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000.0:
        return f"{value:,.0f}"
    if magnitude >= 10.0:
        return f"{value:.1f}"
    return f"{value:.3f}"


def _add_dynamic_parameter_controls(
    module: object,
    parameters: BaseModel,
    path: tuple[str | int, ...] = (),
) -> None:
    for field_name, field_info in type(parameters).model_fields.items():
        value = getattr(parameters, field_name)
        field_path = (*path, field_name)
        label = field_name.replace("_", " ").title()
        if isinstance(value, BaseModel):
            dpg.add_text(label.upper(), color=MUTED_TEXT)
            _add_dynamic_parameter_controls(module, value, field_path)
            continue
        if isinstance(value, bool):
            dpg.add_checkbox(
                label=label,
                default_value=value,
                callback=lambda _s, changed, data: _set_dynamic_parameter(
                    data[0], data[1], changed
                ),
                user_data=(module, field_path),
            )
            continue
        if isinstance(value, StrEnum):
            choices = [choice.value for choice in type(value)]
            dpg.add_combo(
                choices,
                label=label,
                default_value=value.value,
                callback=lambda _s, changed, data: _set_dynamic_parameter(
                    data[0], data[1], changed
                ),
                user_data=(module, field_path),
                width=180,
            )
            continue
        if isinstance(value, float):
            minimum, maximum = _dynamic_parameter_bounds(field_info, value)
            logarithmic = minimum > 0.0 and maximum / minimum >= 100.0
            _add_knob(
                value,
                label,
                minimum,
                maximum,
                _format_dynamic_value,
                lambda changed, target=module, target_path=field_path: (
                    _set_dynamic_parameter(target, target_path, changed)
                ),
                logarithmic=logarithmic,
                size=58,
            )
            continue
        if isinstance(value, int):
            dpg.add_input_int(
                label=label,
                default_value=value,
                callback=lambda _s, changed, data: _set_dynamic_parameter(
                    data[0], data[1], changed
                ),
                user_data=(module, field_path),
                width=140,
            )
            continue
        if isinstance(value, str):
            dpg.add_input_text(
                label=label,
                default_value=value,
                callback=lambda _s, changed, data: _set_dynamic_parameter(
                    data[0], data[1], changed
                ),
                user_data=(module, field_path),
                width=180,
            )
            continue
        if isinstance(value, tuple) and all(
            isinstance(item, (int, float)) for item in value
        ):
            dpg.add_text(label.upper(), color=MUTED_TEXT)
            with dpg.group(horizontal=True):
                for index, item in enumerate(value):
                    numeric = float(item)
                    minimum, maximum = _dynamic_parameter_bounds(
                        field_info,
                        numeric,
                    )
                    _add_knob(
                        numeric,
                        str(index + 1),
                        minimum,
                        maximum,
                        _format_dynamic_value,
                        lambda changed, target=module, target_path=(
                            *field_path,
                            index,
                        ): _set_dynamic_parameter(target, target_path, changed),
                        size=48,
                    )
            continue
        dpg.add_text(f"{label}: {value}", color=MUTED_TEXT, wrap=260)


def _build_generic_module_node(
    instance_id: str,
    module: object,
    patch: PatchGraph,
) -> int | str:
    node = INSTANCE_NODE_TAGS[instance_id]
    manifest = module.manifest
    port_ids = tuple(port.id for port in manifest.ports)
    with dpg.node(parent=RACK, tag=node, label=manifest.name.upper()):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text(manifest.category.upper(), color=MODULE_ACCENTS[node])
            dpg.add_text(manifest.description, color=MUTED_TEXT, wrap=280)
            parameters = getattr(module, "parameters", None)
            if isinstance(parameters, BaseModel):
                _add_dynamic_parameter_controls(module, parameters)
            _add_patch_bay_toggle(patch, instance_id, node, port_ids)

        connected = _connected_port_ids(patch, instance_id)
        for port in manifest.ports:
            attribute_type = (
                dpg.mvNode_Attr_Input
                if port.direction is PortDirection.INPUT
                else dpg.mvNode_Attr_Output
            )
            with dpg.node_attribute(
                tag=f"{node}.{port.id}",
                label=port.name,
                attribute_type=attribute_type,
                show=port.id in connected,
            ):
                _add_port_text(
                    port.name,
                    port.signal_type.value,
                    port.description,
                )
    return node


def _add_port_text(name: str, signal: str, description: str) -> None:
    """Show the musical label and keep engineering detail in a tooltip."""
    text_item = dpg.add_text(name, color=SIGNAL_COLORS[signal])
    with dpg.tooltip(text_item):
        dpg.add_text(signal.upper(), color=SIGNAL_COLORS[signal])
        if description:
            dpg.add_text(description, color=MUTED_TEXT, wrap=280)


def _build_vco_node(vco: ComplexVCO, patch: PatchGraph) -> None:
    port_ids = (
        "morph_cv",
        "pitch",
        "frequency_cv_1",
        "frequency_cv_2",
        "linear_fm",
        "pwm",
        "sync",
        "morph",
        "sine",
        "triangle",
        "saw",
        "pulse",
    )
    with dpg.node(tag=VCO_NODE, label="TRIANGLE CORE VCO"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            parameters = vco.parameters
            dpg.add_text("TRIANGLE CORE / COMPLEX VOICE", color=VCO_ACCENT)
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.frequency,
                    "Frequency",
                    1.0,
                    20_000.0,
                    lambda value: f"{value:.0f} Hz",
                    _set_attribute(parameters, "frequency"),
                    logarithmic=True,
                    size=72,
                    tag=f"{VCO_NODE}.control.frequency",
                )
                _add_knob(
                    parameters.fine_tune_cents,
                    "Fine",
                    -100.0,
                    100.0,
                    lambda value: f"{value:+.0f} ct",
                    _set_attribute(parameters, "fine_tune_cents"),
                    size=62,
                )
                _add_knob(
                    parameters.amplitude,
                    "Level",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "amplitude"),
                    size=62,
                )
            dpg.add_separator()
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.frequency_cv_1_amount,
                    "FM 1",
                    -1.0,
                    1.0,
                    lambda value: f"{value:+.2f}",
                    _set_attribute(parameters, "frequency_cv_1_amount"),
                    size=58,
                )
                _add_knob(
                    parameters.frequency_cv_2_amount,
                    "FM 2",
                    -1.0,
                    1.0,
                    lambda value: f"{value:+.2f}",
                    _set_attribute(parameters, "frequency_cv_2_amount"),
                    size=58,
                )
                _add_knob(
                    parameters.linear_fm_amount,
                    "Lin FM",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "linear_fm_amount"),
                    size=58,
                )
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.pulse_width,
                    "Pulse",
                    0.01,
                    0.99,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "pulse_width"),
                    size=58,
                )
                _add_knob(
                    parameters.morph,
                    "Morph",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "morph"),
                    size=58,
                )
                with dpg.group():
                    dpg.add_text("WAVE B", color=MUTED_TEXT)
                    dpg.add_combo(
                        [wave.value for wave in WaveB],
                        default_value=parameters.wave_b.value,
                        label="",
                        width=80,
                        callback=_set_wave_b,
                        user_data=vco,
                    )
            _add_patch_bay_toggle(patch, "vco", VCO_NODE, port_ids)

        ports = {port.id: port for port in vco.manifest.ports}
        connected = _connected_port_ids(patch, "vco")
        for port_id in port_ids:
            port = ports[port_id]
            attribute_type = (
                dpg.mvNode_Attr_Input
                if port.direction is PortDirection.INPUT
                else dpg.mvNode_Attr_Output
            )
            with dpg.node_attribute(
                tag=f"{VCO_NODE}.{port.id}",
                label=port.name,
                attribute_type=attribute_type,
                show=port.id in connected,
            ):
                _add_port_text(
                    port.name,
                    port.signal_type.value,
                    port.description,
                )


def _build_mixer_node(mixer: PolarizingMixer, patch: PatchGraph) -> None:
    port_ids = tuple(
        f"input_{channel}"
        for channel in range(1, mixer.parameters.channels + 1)
    ) + ("output",)
    with dpg.node(
        tag=MIXER_NODE,
        label=f"POLARIZING MIXER / {mixer.parameters.channels}",
    ):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text("POLARIZE / SUM", color=MIXER_ACCENT)
            _add_patch_bay_toggle(patch, "mixer", MIXER_NODE, port_ids)
        connected = _connected_port_ids(patch, "mixer")
        for channel, gain in enumerate(mixer.parameters.gains, start=1):
            with dpg.node_attribute(
                tag=f"{MIXER_NODE}.input_{channel}",
                label=f"Input {channel}",
                attribute_type=dpg.mvNode_Attr_Input,
                show=f"input_{channel}" in connected,
            ):
                _add_knob(
                    gain,
                    f"Input {channel}",
                    -1.0,
                    1.0,
                    lambda value: f"{value:+.2f}",
                    lambda value, channel=channel: mixer.set_gain(channel, value),
                    size=54,
                    tag=f"{MIXER_NODE}.control.gain_{channel}",
                )
        with dpg.node_attribute(
            tag=f"{MIXER_NODE}.output",
            label="Sum",
            attribute_type=dpg.mvNode_Attr_Output,
            show="output" in connected,
        ):
            _add_port_text(
                "SUM",
                "audio",
                "Unclipped sum of the polarizing inputs.",
            )


def _disturb_wogglebug(
    _sender: str,
    _value: object,
    wogglebug: Wogglebug,
) -> None:
    wogglebug.disturb()
    _set_patch_status("DISTURB  ·  UNCERTAINTY EVENT ARMED")


def _build_wogglebug_node(wogglebug: Wogglebug, patch: PatchGraph) -> None:
    port_ids = (
        "external_clock",
        "clock_cv",
        "ego",
        "influence",
        "stepped",
        "smooth",
        "woggle",
        "clock",
        "burst",
        "smooth_vco",
        "woggle_vco",
        "ring_mod",
    )
    with dpg.node(tag=WOGGLE_NODE, label="WOGGLEBUG / UNCERTAINTY"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            parameters = wogglebug.parameters
            dpg.add_text("A MUSICAL SOURCE OF UNCERTAINTY", color=WOGGLE_ACCENT)
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.clock_rate_hz,
                    "Rate",
                    0.01,
                    2_000.0,
                    _format_frequency,
                    _set_attribute(parameters, "clock_rate_hz"),
                    logarithmic=True,
                    size=64,
                    tag=f"{WOGGLE_NODE}.control.rate",
                )
                _add_knob(
                    parameters.chaos,
                    "Chaos",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "chaos"),
                    size=58,
                )
                _add_knob(
                    parameters.ego_id_balance,
                    "Ego / Id",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "ego_id_balance"),
                    size=58,
                )
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.woggle,
                    "Woggle",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "woggle"),
                    size=58,
                )
                _add_knob(
                    parameters.audio_level,
                    "Audio",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "audio_level"),
                    size=58,
                )
                with dpg.group():
                    dpg.add_text("UNCERTAINTY", color=MUTED_TEXT)
                    dpg.add_button(
                        label="DISTURB",
                        width=92,
                        height=36,
                        callback=_disturb_wogglebug,
                        user_data=wogglebug,
                    )
            _add_patch_bay_toggle(
                patch,
                "wogglebug",
                WOGGLE_NODE,
                port_ids,
            )

        ports = {port.id: port for port in wogglebug.manifest.ports}
        connected = _connected_port_ids(patch, "wogglebug")
        for port_id in port_ids:
            port = ports[port_id]
            attribute_type = (
                dpg.mvNode_Attr_Input
                if port.direction is PortDirection.INPUT
                else dpg.mvNode_Attr_Output
            )
            with dpg.node_attribute(
                tag=f"{WOGGLE_NODE}.{port.id}",
                label=port.name,
                attribute_type=attribute_type,
                show=port.id in connected,
            ):
                _add_port_text(
                    port.name,
                    port.signal_type.value,
                    port.description,
                )


def _set_scale_system(
    _sender: str,
    system: str,
    generator: ScaleGenerator,
) -> None:
    names = scale_names(system)
    current = generator.parameters.scale_name
    selected = current if current in names else (
        "major" if "major" in names else names[0]
    )
    generator.configure(system=system, scale_name=selected)
    dpg.configure_item(SCALE_NAME_CONTROL, items=list(names))
    dpg.set_value(SCALE_NAME_CONTROL, selected)
    _set_patch_status(f"SCALE  ·  {generator.scale_label.upper()}")


def _set_scale_name(
    _sender: str,
    scale_name: str,
    generator: ScaleGenerator,
) -> None:
    generator.configure(scale_name=scale_name)
    _set_patch_status(f"SCALE  ·  {generator.scale_label.upper()}")


def _set_scale_tonic(
    _sender: str,
    tonic: str,
    generator: ScaleGenerator,
) -> None:
    generator.configure(tonic=tonic)
    _set_patch_status(f"SCALE  ·  {generator.scale_label.upper()}")


def _set_scale_octave(
    _sender: str,
    octave: str,
    generator: ScaleGenerator,
) -> None:
    generator.configure(octave=int(octave))
    _set_patch_status(f"SCALE  ·  {generator.scale_label.upper()}")


def _set_scale_pattern(
    _sender: str,
    pattern: str,
    generator: ScaleGenerator,
) -> None:
    generator.parameters.pattern = SequencePattern(pattern)
    _set_patch_status(f"PATTERN  ·  {pattern.upper()}")


def _build_scale_generator_node(
    generator: ScaleGenerator,
    patch: PatchGraph,
) -> None:
    port_ids = (
        "clock",
        "reset",
        "transpose",
        "note",
        "pitch",
        "frequency",
        "degree",
        "gate",
        "trigger",
    )
    with dpg.node(tag=SCALE_NODE, label="PYTHEORY / SCALE GENERATOR"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            parameters = generator.parameters
            dpg.add_text("CLOCKED MUSICAL VOLTAGE", color=SCALE_ACCENT)
            with dpg.group(horizontal=True):
                with dpg.group():
                    dpg.add_text("SYSTEM", color=MUTED_TEXT)
                    dpg.add_combo(
                        list(SUPPORTED_SCALE_SYSTEMS),
                        tag=SCALE_SYSTEM_CONTROL,
                        default_value=parameters.system,
                        width=130,
                        callback=_set_scale_system,
                        user_data=generator,
                    )
                with dpg.group():
                    dpg.add_text("SCALE", color=MUTED_TEXT)
                    dpg.add_combo(
                        list(scale_names(parameters.system)),
                        tag=SCALE_NAME_CONTROL,
                        default_value=parameters.scale_name,
                        width=150,
                        callback=_set_scale_name,
                        user_data=generator,
                    )
            with dpg.group(horizontal=True):
                with dpg.group():
                    dpg.add_text("TONIC", color=MUTED_TEXT)
                    dpg.add_combo(
                        list(TONICS),
                        default_value=parameters.tonic,
                        width=76,
                        callback=_set_scale_tonic,
                        user_data=generator,
                    )
                with dpg.group():
                    dpg.add_text("OCTAVE", color=MUTED_TEXT)
                    dpg.add_combo(
                        [str(value) for value in range(9)],
                        default_value=str(parameters.octave),
                        width=76,
                        callback=_set_scale_octave,
                        user_data=generator,
                    )
                with dpg.group():
                    dpg.add_text("PATTERN", color=MUTED_TEXT)
                    dpg.add_combo(
                        [pattern.value for pattern in SequencePattern],
                        default_value=parameters.pattern.value,
                        width=116,
                        callback=_set_scale_pattern,
                        user_data=generator,
                    )
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.rate_hz,
                    "Rate",
                    0.01,
                    100.0,
                    _format_frequency,
                    lambda value: setattr(generator.parameters, "rate_hz", value),
                    logarithmic=True,
                    size=60,
                )
                _add_knob(
                    parameters.gate_length,
                    "Gate",
                    0.01,
                    0.99,
                    lambda value: f"{value * 100:.0f}%",
                    lambda value: setattr(
                        generator.parameters,
                        "gate_length",
                        value,
                    ),
                    size=60,
                )
                with dpg.group():
                    dpg.add_text("NOW PLAYING", color=MUTED_TEXT)
                    dpg.add_text(
                        f"{generator.current_note}  ·  DEGREE 1/{generator.degree_count}",
                        tag=SCALE_NOTE_STATUS,
                        color=SCALE_ACCENT,
                    )
            _add_patch_bay_toggle(
                patch,
                "scale_generator",
                SCALE_NODE,
                port_ids,
            )

        ports = {port.id: port for port in generator.manifest.ports}
        connected = _connected_port_ids(patch, "scale_generator")
        for port_id in port_ids:
            port = ports[port_id]
            attribute_type = (
                dpg.mvNode_Attr_Input
                if port.direction is PortDirection.INPUT
                else dpg.mvNode_Attr_Output
            )
            with dpg.node_attribute(
                tag=f"{SCALE_NODE}.{port.id}",
                label=port.name,
                attribute_type=attribute_type,
                show=port.id in connected,
            ):
                _add_port_text(
                    port.name,
                    port.signal_type.value,
                    port.description,
                )


def _function_channel_controls(
    label: str,
    parameters: FunctionChannelParameters,
) -> None:
    dpg.add_text(label.upper(), color=UTILITY_ACCENT)
    with dpg.group(horizontal=True):
        _add_knob(
            parameters.rise_seconds,
            "Rise",
            MIN_FUNCTION_STAGE_SECONDS,
            MAX_FUNCTION_STAGE_SECONDS,
            _format_duration,
            _set_attribute(parameters, "rise_seconds"),
            logarithmic=True,
            size=58,
        )
        _add_knob(
            parameters.fall_seconds,
            "Fall",
            MIN_FUNCTION_STAGE_SECONDS,
            MAX_FUNCTION_STAGE_SECONDS,
            _format_duration,
            _set_attribute(parameters, "fall_seconds"),
            logarithmic=True,
            size=58,
        )
        _add_knob(
            parameters.curve,
            "Shape",
            -1.0,
            1.0,
            lambda value: f"{value:+.2f}",
            _set_attribute(parameters, "curve"),
            size=58,
        )
        _add_knob(
            parameters.attenuverter,
            "Level",
            -1.0,
            1.0,
            lambda value: f"{value:+.2f}",
            _set_attribute(parameters, "attenuverter"),
            size=58,
        )
    dpg.add_checkbox(
        label="CYCLE",
        default_value=parameters.cycle,
        callback=lambda _sender, value, _data=None: setattr(
            parameters,
            "cycle",
            value,
        ),
    )


def _build_function_node(utility: FunctionUtility, patch: PatchGraph) -> None:
    ports = {port.id: port for port in FUNCTION_UTILITY_MANIFEST.ports}
    port_ids = tuple(
        port_id
        for direction in (PortDirection.INPUT, PortDirection.OUTPUT)
        for port_id in UTILITY_PORT_ORDER
        if ports[port_id].direction is direction
    )
    with dpg.node(tag=FUNCTION_NODE, label="DUAL FUNCTION / MATH"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            _function_channel_controls("Channel 1", utility.parameters.channel_1)
            dpg.add_separator()
            dpg.add_text("POLARIZERS", color=UTILITY_ACCENT)
            with dpg.group(horizontal=True):
                _add_knob(
                    utility.parameters.channel_2_attenuverter,
                    "Channel 2",
                    -1.0,
                    1.0,
                    lambda value: f"{value:+.2f}",
                    _set_attribute(utility.parameters, "channel_2_attenuverter"),
                    size=58,
                )
                _add_knob(
                    utility.parameters.channel_3_attenuverter,
                    "Channel 3",
                    -1.0,
                    1.0,
                    lambda value: f"{value:+.2f}",
                    _set_attribute(utility.parameters, "channel_3_attenuverter"),
                    size=58,
                )
            dpg.add_separator()
            _function_channel_controls("Channel 4", utility.parameters.channel_4)
            _add_patch_bay_toggle(
                patch,
                "utility",
                FUNCTION_NODE,
                port_ids,
            )

        connected = _connected_port_ids(patch, "utility")
        for port_id in port_ids:
            port = ports[port_id]
            attribute_type = (
                dpg.mvNode_Attr_Input
                if port.direction is PortDirection.INPUT
                else dpg.mvNode_Attr_Output
            )
            with dpg.node_attribute(
                tag=f"{FUNCTION_NODE}.{port.id}",
                label=port.name,
                attribute_type=attribute_type,
                show=port.id in connected,
            ):
                _add_port_text(
                    port.name,
                    port.signal_type.value,
                    port.description,
                )


def _build_low_pass_gate_node(
    low_pass_gate: LowPassGate,
    patch: PatchGraph,
) -> None:
    port_ids = (
        "audio",
        "strike",
        "level_cv",
        "decay_cv",
        "output",
        "envelope",
    )
    with dpg.node(tag=LPG_NODE, label="BLOOM / LOW-PASS GATE"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            parameters = low_pass_gate.parameters
            dpg.add_text("STRUCK DYNAMICS / SPECTRAL DECAY", color=LPG_ACCENT)
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.decay_seconds,
                    "Decay",
                    0.02,
                    30.0,
                    _format_duration,
                    _set_attribute(parameters, "decay_seconds"),
                    logarithmic=True,
                    size=62,
                )
                _add_knob(
                    parameters.brightness,
                    "Light",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "brightness"),
                    size=60,
                )
                _add_knob(
                    parameters.character,
                    "Wood",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "character"),
                    size=60,
                )
                _add_knob(
                    parameters.level,
                    "Level",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "level"),
                    size=58,
                )
            _add_patch_bay_toggle(
                patch,
                "low_pass_gate",
                LPG_NODE,
                port_ids,
            )

        ports = {port.id: port for port in low_pass_gate.manifest.ports}
        connected = _connected_port_ids(patch, "low_pass_gate")
        for port_id in port_ids:
            port = ports[port_id]
            attribute_type = (
                dpg.mvNode_Attr_Input
                if port.direction is PortDirection.INPUT
                else dpg.mvNode_Attr_Output
            )
            with dpg.node_attribute(
                tag=f"{LPG_NODE}.{port.id}",
                label=port.name,
                attribute_type=attribute_type,
                show=port.id in connected,
            ):
                _add_port_text(
                    port.name,
                    port.signal_type.value,
                    port.description,
                )


def _build_reverb_node(reverb: Reverb, patch: PatchGraph) -> None:
    port_ids = (
        "audio",
        "mix_cv",
        "decay_cv",
        "freeze",
        "wet_left",
        "wet_right",
        "left",
        "right",
    )
    with dpg.node(tag=REVERB_NODE, label="SPACE / STEREO REVERB"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            parameters = reverb.parameters
            dpg.add_text("MONO IN / WIDE DECORRELATED FIELD", color=REVERB_ACCENT)
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.mix,
                    "Mix",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "mix"),
                    size=62,
                    tag=f"{REVERB_NODE}.control.mix",
                )
                _add_knob(
                    parameters.decay_seconds,
                    "Time",
                    0.1,
                    30.0,
                    _format_duration,
                    _set_attribute(parameters, "decay_seconds"),
                    logarithmic=True,
                    size=66,
                    tag=f"{REVERB_NODE}.control.decay",
                )
                _add_knob(
                    parameters.damping,
                    "Damp",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "damping"),
                    size=58,
                )
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.diffusion,
                    "Diffuse",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "diffusion"),
                    size=58,
                )
                _add_knob(
                    parameters.pre_delay_ms,
                    "Pre-delay",
                    0.0,
                    250.0,
                    lambda value: f"{value:.0f} ms",
                    _set_attribute(parameters, "pre_delay_ms"),
                    size=62,
                )
                with dpg.group():
                    dpg.add_text("INFINITE", color=MUTED_TEXT)
                    dpg.add_checkbox(
                        label="FREEZE",
                        default_value=parameters.freeze,
                        callback=lambda _sender, value, _data=None: setattr(
                            parameters,
                            "freeze",
                            value,
                        ),
                    )
            _add_patch_bay_toggle(patch, "reverb", REVERB_NODE, port_ids)

        ports = {port.id: port for port in reverb.manifest.ports}
        connected = _connected_port_ids(patch, "reverb")
        for port_id in port_ids:
            port = ports[port_id]
            attribute_type = (
                dpg.mvNode_Attr_Input
                if port.direction is PortDirection.INPUT
                else dpg.mvNode_Attr_Output
            )
            with dpg.node_attribute(
                tag=f"{REVERB_NODE}.{port.id}",
                label=port.name,
                attribute_type=attribute_type,
                show=port.id in connected,
            ):
                _add_port_text(
                    port.name,
                    port.signal_type.value,
                    port.description,
                )


def _build_output_node(engine: SystemAudioEngine) -> None:
    with dpg.node(tag=OUTPUT_NODE, label="SYSTEM OUT"):
        for port_id, name, description in (
            ("mono", "MONO / BOTH", "Route one source equally to left and right."),
            ("left", "LEFT", "Route this source to the left system channel."),
            ("right", "RIGHT", "Route this source to the right system channel."),
        ):
            with dpg.node_attribute(
                tag=f"{OUTPUT_NODE}.{port_id}",
                label=name.title(),
                attribute_type=dpg.mvNode_Attr_Input,
            ):
                _add_port_text(name, "audio", description)
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            _add_knob(
                engine.master_gain,
                "Master",
                0.0,
                1.0,
                lambda value: f"{value:.2f}",
                lambda value: setattr(engine, "master_gain", value),
                size=68,
                tag=f"{OUTPUT_NODE}.control.master",
            )
            dpg.add_text("OUTPUT LEVEL", color=MUTED_TEXT)
            dpg.add_progress_bar(
                tag=OUTPUT_METER,
                default_value=0.0,
                overlay="-∞ dB",
                width=150,
            )
            dpg.bind_item_theme(OUTPUT_METER, METER_THEME)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Start",
                    callback=_start_audio,
                    user_data=engine,
                )
                dpg.add_button(
                    label="Stop",
                    callback=_stop_audio,
                    user_data=engine,
                )
            dpg.add_text("Stopped", tag=AUDIO_STATUS, wrap=180)


def _module_selector_button_tag(module_id: str) -> str:
    return f"noodler.module_selector.item.{module_id}"


def _module_appearance(module_id: str, category: str) -> tuple[str, str, tuple]:
    if module_id in {"melody_brain", "harmony_brain", "arpeggio_brain"}:
        return CONTROL_RAIL, SCALE_THEME, SCALE_ACCENT
    if module_id in {"scale_generator"} or category == "Sequencers":
        return CONTROL_RAIL, SCALE_THEME, SCALE_ACCENT
    if module_id in {"wogglebug", "adsr_envelope", "function_utility"}:
        return CONTROL_RAIL, WOGGLE_THEME, WOGGLE_ACCENT
    if category in {"Oscillators", "Sources", "Noise & Random"}:
        return AUDIO_RAIL, VCO_THEME, VCO_ACCENT
    if category == "Filters":
        return AUDIO_RAIL, LPG_THEME, LPG_ACCENT
    if category in {"Effects", "Dynamics"}:
        return AUDIO_RAIL, REVERB_THEME, REVERB_ACCENT
    if category == "Envelopes & Dynamics" and module_id != "vca":
        return CONTROL_RAIL, UTILITY_THEME, UTILITY_ACCENT
    return AUDIO_RAIL, MIXER_THEME, MIXER_ACCENT


def _next_module_instance_id(module_id: str, patch: PatchGraph) -> str:
    if module_id not in patch.modules:
        return module_id
    suffix = 2
    while f"{module_id}_{suffix}" in patch.modules:
        suffix += 1
    return f"{module_id}_{suffix}"


def _register_dynamic_node(
    instance_id: str,
    module_id: str,
    category: str,
) -> tuple[int | str, str, str]:
    node = f"noodler.module.{instance_id}"
    rail, theme, accent = _module_appearance(module_id, category)
    INSTANCE_NODE_TAGS[instance_id] = node
    VIEW_NODE_TAGS[instance_id] = node
    RACK_NODES.append(node)
    MODULE_ACCENTS[node] = accent
    if rail == AUDIO_RAIL and OUTPUT_NODE in RACK_RAILS[rail]:
        RACK_RAILS[rail].insert(RACK_RAILS[rail].index(OUTPUT_NODE), node)
    else:
        RACK_RAILS[rail].append(node)
    return node, rail, theme


def _place_dynamic_node(node: int | str, rail: str) -> None:
    lane = RACK_RAILS[rail]
    index = lane.index(node)
    if index + 1 < len(lane):
        next_node = lane[index + 1]
        x = float(dpg.get_item_pos(next_node)[0])
    elif index > 0:
        previous = lane[index - 1]
        previous_x = float(dpg.get_item_pos(previous)[0])
        previous_width = max(280.0, float(dpg.get_item_rect_size(previous)[0]))
        x = previous_x + previous_width + RACK_RAIL_GAP
    else:
        x = 20.0
    dpg.set_item_pos(node, [x, CANVAS_INTERACTION.rail_y[rail]])


def _add_selected_module(
    _sender: int | str,
    _app_data: object,
    selection: tuple[AppRuntime, str],
) -> None:
    runtime, module_id = selection
    try:
        provider = BuiltinProvider()
        module = provider.create(module_id)
        manifest = module.manifest
        instance_id = _next_module_instance_id(module_id, runtime.patch)
        _edit_patch(
            runtime,
            lambda: runtime.patch.add_module(instance_id, module),
        )
        node, rail, theme = _register_dynamic_node(
            instance_id,
            module_id,
            manifest.category,
        )
        _build_generic_module_node(instance_id, module, runtime.patch)
        dpg.bind_item_theme(node, theme)
        _add_spine_texture(node, manifest.name.upper())
        _add_module_spine(node)
        _place_dynamic_node(node, rail)
        dpg.hide_item(MODULE_SELECTOR)
        _set_patch_status(
            f"ADDED  {manifest.name.upper()}  ·  INSTANCE {instance_id}"
        )
    except Exception as exc:
        if dpg.does_item_exist(MODULE_SELECTOR_STATUS):
            dpg.configure_item(MODULE_SELECTOR_STATUS, color=OUTPUT_ACCENT)
            dpg.set_value(MODULE_SELECTOR_STATUS, f"COULD NOT ADD: {exc}")


def _filter_module_selector(
    _sender: int | str,
    query: str,
    _user_data: object,
) -> None:
    words = tuple(query.lower().split())
    visible = 0
    for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
        haystack = " ".join(
            (manifest.id, manifest.name, manifest.category, manifest.description)
        ).lower()
        show = all(word in haystack for word in words)
        dpg.configure_item(_module_selector_button_tag(manifest.id), show=show)
        visible += int(show)
    dpg.configure_item(MODULE_SELECTOR_STATUS, color=MUTED_TEXT)
    dpg.set_value(MODULE_SELECTOR_STATUS, f"{visible} MODULES")


def _show_module_selector(
    _sender: int | str,
    _app_data: object,
    _user_data: object,
) -> None:
    dpg.set_value(MODULE_SELECTOR_SEARCH, "")
    _filter_module_selector("", "", None)
    dpg.show_item(MODULE_SELECTOR)


def _build_module_selector(runtime: AppRuntime) -> None:
    with dpg.window(
        tag=MODULE_SELECTOR,
        label="Add a Module",
        show=False,
        modal=True,
        width=620,
        height=700,
        no_collapse=True,
    ):
        dpg.add_input_text(
            tag=MODULE_SELECTOR_SEARCH,
            hint="Search oscillators, filters, PyTheory…",
            callback=_filter_module_selector,
            width=-1,
        )
        dpg.add_text(
            f"{len(BUILTIN_PROVIDER_MANIFEST.modules)} MODULES",
            tag=MODULE_SELECTOR_STATUS,
            color=MUTED_TEXT,
        )
        with dpg.child_window(height=-42, border=False):
            current_category = None
            for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
                if manifest.category != current_category:
                    if current_category is not None:
                        dpg.add_separator()
                    current_category = manifest.category
                    dpg.add_text(current_category.upper(), color=SCALE_ACCENT)
                button = dpg.add_button(
                    label=manifest.name,
                    tag=_module_selector_button_tag(manifest.id),
                    callback=_add_selected_module,
                    user_data=(runtime, manifest.id),
                    width=-1,
                )
                with dpg.tooltip(button):
                    dpg.add_text(manifest.description, wrap=360)
                    dpg.add_text(
                        f"{len(manifest.ports)} PATCH POINTS  ·  {manifest.id}",
                        color=MUTED_TEXT,
                    )
        dpg.add_button(
            label="CLOSE",
            callback=lambda _s, _a, _u: dpg.hide_item(MODULE_SELECTOR),
        )


def build_runtime(
    vco: ComplexVCO | None = None,
    mixer: PolarizingMixer | None = None,
    utility: FunctionUtility | None = None,
    wogglebug: Wogglebug | None = None,
    scale_generator: ScaleGenerator | None = None,
    low_pass_gate: LowPassGate | None = None,
    reverb: Reverb | None = None,
    *,
    mixer_channels: int = 4,
) -> AppRuntime:
    """Create Noodler's seeded, generative ambient instrument."""
    if vco is None:
        vco = ComplexVCO(
            ComplexVCOParameters(
                frequency=220.0,
                amplitude=0.22,
                frequency_cv_2_amount=0.018,
                morph=0.08,
                wave_b=WaveB.SAW,
            )
        )
    if mixer is None:
        gains_list = [0.0] * mixer_channels
        gains_list[0] = 0.48
        if mixer_channels >= 2:
            gains_list[1] = 0.14
        if mixer_channels >= 3:
            gains_list[2] = 0.12
        mixer = PolarizingMixer(
            PolarizingMixerParameters(
                channels=mixer_channels,
                gains=tuple(gains_list),
            )
        )
    if utility is None:
        utility = FunctionUtility(
            FunctionUtilityParameters(
                channel_1=FunctionChannelParameters(
                    rise_seconds=11.0,
                    fall_seconds=17.0,
                    curve=0.22,
                    cycle=True,
                    attenuverter=0.38,
                ),
                channel_4=FunctionChannelParameters(
                    rise_seconds=31.0,
                    fall_seconds=47.0,
                    curve=-0.18,
                    cycle=True,
                    attenuverter=0.16,
                ),
            )
        )
    wogglebug = wogglebug or Wogglebug(
        WogglebugParameters(
            clock_rate_hz=0.47,
            chaos=0.58,
            ego_id_balance=0.78,
            woggle=0.72,
            audio_level=0.12,
            seed=777,
        )
    )
    scale_generator = scale_generator or ScaleGenerator(
        ScaleGeneratorParameters(
            system="japanese",
            tonic="A",
            octave=3,
            scale_name="hirajoshi",
            pattern=SequencePattern.WANDER,
            rate_hz=0.47,
            gate_length=0.32,
            reference_frequency_hz=220.0,
            seed=777,
        )
    )
    low_pass_gate = low_pass_gate or LowPassGate(
        LowPassGateParameters(
            decay_seconds=2.4,
            brightness=0.72,
            character=0.58,
            level=0.9,
        )
    )
    reverb = reverb or Reverb(
        ReverbParameters(
            mix=0.52,
            decay_seconds=8.5,
            damping=0.62,
            diffusion=0.88,
            pre_delay_ms=42.0,
        )
    )

    patch = PatchGraph()
    patch.add_module("utility", utility)
    patch.add_module("vco", vco)
    patch.add_module("mixer", mixer)
    patch.add_module("wogglebug", wogglebug)
    patch.add_module("scale_generator", scale_generator)
    patch.add_module("low_pass_gate", low_pass_gate)
    patch.add_module("reverb", reverb)
    patch.connect("utility", "channel_1", "vco", "morph_cv")
    patch.connect("wogglebug", "woggle", "vco", "frequency_cv_2")
    patch.connect("wogglebug", "clock", "scale_generator", "clock")
    patch.connect("scale_generator", "pitch", "vco", "pitch")
    patch.connect("vco", "morph", "mixer", "input_1")
    if mixer.parameters.channels >= 2:
        patch.connect("vco", "triangle", "mixer", "input_2")
    if mixer.parameters.channels >= 3:
        patch.connect("wogglebug", "ring_mod", "mixer", "input_3")
    patch.connect("mixer", "output", "low_pass_gate", "audio")
    patch.connect("scale_generator", "trigger", "low_pass_gate", "strike")
    patch.connect("utility", "channel_4", "reverb", "decay_cv")
    patch.connect("low_pass_gate", "output", "reverb", "audio")
    patch.connect("wogglebug", "burst", "reverb", "freeze")
    patch.connect_output("reverb", "left", channel=OutputChannel.LEFT)
    patch.connect_output("reverb", "right", channel=OutputChannel.RIGHT)
    return AppRuntime(
        vco=vco,
        mixer=mixer,
        utility=utility,
        wogglebug=wogglebug,
        scale_generator=scale_generator,
        low_pass_gate=low_pass_gate,
        reverb=reverb,
        patch=patch,
        audio=SystemAudioEngine(patch, master_gain=0.72),
    )


def build_ui(
    vco: ComplexVCO | None = None,
    mixer: PolarizingMixer | None = None,
    utility: FunctionUtility | None = None,
    wogglebug: Wogglebug | None = None,
    scale_generator: ScaleGenerator | None = None,
    low_pass_gate: LowPassGate | None = None,
    reverb: Reverb | None = None,
    *,
    mixer_channels: int = 4,
) -> AppRuntime:
    """Build the initial rack and return its live application runtime."""
    _reset_rack_registry()
    KNOB_INTERACTION.reset()
    CANVAS_INTERACTION.reset()
    MODULE_COLLAPSE.reset()
    dpg.set_global_font_scale(1.0)
    PATCH_BAYS.clear()
    _configure_font()
    _configure_theme()
    runtime = build_runtime(
        vco,
        mixer,
        utility,
        wogglebug,
        scale_generator,
        low_pass_gate,
        reverb,
        mixer_channels=mixer_channels,
    )
    _configure_spine_textures(runtime)
    with dpg.window(tag=PRIMARY_WINDOW, label="Noodler"):
        with dpg.group(horizontal=True):
            dpg.add_text("HIRAJOSHI GARDEN", color=SCALE_ACCENT)
            dpg.add_text(
                "CONTROL RAIL  ·  FUNCTION  →  WOGGLE  →  PYTHEORY",
                color=TEXT,
            )
            dpg.add_spacer(width=24)
            dpg.add_text("WOGGLEBUG READY", color=WOGGLE_ACCENT)
            dpg.add_text("CV", color=SIGNAL_COLORS["cv"])
            dpg.add_text("AUDIO", color=SIGNAL_COLORS["audio"])
            dpg.add_spacer(width=16)
            dpg.add_button(
                label="−",
                tag=ZOOM_OUT_BUTTON,
                callback=_zoom_rack_button,
                user_data=-1,
            )
            dpg.add_button(
                label="100%",
                tag=ZOOM_RESET_BUTTON,
                callback=_reset_rack_zoom,
            )
            dpg.add_button(
                label="+",
                tag=ZOOM_IN_BUTTON,
                callback=_zoom_rack_button,
                user_data=1,
            )
            dpg.add_button(
                label="UNPLUG ALL",
                tag=UNPLUG_ALL_BUTTON,
                callback=_unplug_all,
                user_data=runtime,
            )
            with dpg.tooltip(UNPLUG_ALL_BUTTON):
                dpg.add_text("Disconnect every cable from the live patch.")
            dpg.add_button(
                label="ADD MODULE",
                tag=ADD_MODULE_BUTTON,
                callback=_show_module_selector,
            )
            with dpg.tooltip(ADD_MODULE_BUTTON):
                dpg.add_text("Browse all built-in instruments and utilities.")
            dpg.add_button(
                label="SAVE PATCH",
                tag=SAVE_PATCH_BUTTON,
                callback=_show_save_patch_dialog,
            )
            with dpg.tooltip(SAVE_PATCH_BUTTON):
                dpg.add_text("Save modules, cables, controls, and rack view.")
        with dpg.group(horizontal=True):
            dpg.add_text("AUDIO RAIL", color=SIGNAL_COLORS["audio"])
            dpg.add_text(
                "COMPLEX VCO  →  POLARIZING MIX  →  BLOOM  →  SPACE  →  OUT",
                color=TEXT,
            )
        dpg.add_text(
            DEFAULT_CONTROL_STATUS,
            tag=CONTROL_STATUS,
            color=MUTED_TEXT,
        )
        dpg.add_separator()
        with dpg.node_editor(
            tag=RACK,
            callback=_patch_link_created,
            delink_callback=_patch_link_deleted,
            user_data=runtime,
            minimap=True,
            minimap_location=dpg.mvNodeMiniMap_Location_BottomRight,
        ):
            _build_vco_node(runtime.vco, runtime.patch)
            _build_mixer_node(runtime.mixer, runtime.patch)
            _build_function_node(runtime.utility, runtime.patch)
            _build_wogglebug_node(runtime.wogglebug, runtime.patch)
            _build_scale_generator_node(
                runtime.scale_generator,
                runtime.patch,
            )
            _build_low_pass_gate_node(runtime.low_pass_gate, runtime.patch)
            _build_reverb_node(runtime.reverb, runtime.patch)
            _build_output_node(runtime.audio)
            _add_module_spines(runtime)
            _add_visual_link(
                f"{FUNCTION_NODE}.channel_1",
                f"{VCO_NODE}.morph_cv",
                _default_cable(
                    runtime.patch,
                    "utility",
                    "channel_1",
                    "vco",
                    "morph_cv",
                ),
                "cv",
                tag=UTILITY_VCO_LINK,
            )
            _add_visual_link(
                f"{WOGGLE_NODE}.woggle",
                f"{VCO_NODE}.frequency_cv_2",
                _default_cable(
                    runtime.patch,
                    "wogglebug",
                    "woggle",
                    "vco",
                    "frequency_cv_2",
                ),
                "cv",
                tag=WOGGLE_VCO_LINK,
            )
            _add_visual_link(
                f"{WOGGLE_NODE}.clock",
                f"{SCALE_NODE}.clock",
                _default_cable(
                    runtime.patch,
                    "wogglebug",
                    "clock",
                    "scale_generator",
                    "clock",
                ),
                "gate",
                tag=WOGGLE_SCALE_LINK,
            )
            _add_visual_link(
                f"{SCALE_NODE}.pitch",
                f"{VCO_NODE}.pitch",
                _default_cable(
                    runtime.patch,
                    "scale_generator",
                    "pitch",
                    "vco",
                    "pitch",
                ),
                "cv",
                tag=SCALE_VCO_LINK,
            )
            _add_visual_link(
                f"{VCO_NODE}.morph",
                f"{MIXER_NODE}.input_1",
                _default_cable(
                    runtime.patch,
                    "vco",
                    "morph",
                    "mixer",
                    "input_1",
                ),
                "audio",
                tag=VCO_MIXER_LINK,
            )
            if runtime.mixer.parameters.channels >= 2:
                _add_visual_link(
                    f"{VCO_NODE}.triangle",
                    f"{MIXER_NODE}.input_2",
                    _default_cable(
                        runtime.patch,
                        "vco",
                        "triangle",
                        "mixer",
                        "input_2",
                    ),
                    "audio",
                    tag=VCO_TRIANGLE_MIXER_LINK,
                )
            if runtime.mixer.parameters.channels >= 3:
                _add_visual_link(
                    f"{WOGGLE_NODE}.ring_mod",
                    f"{MIXER_NODE}.input_3",
                    _default_cable(
                        runtime.patch,
                        "wogglebug",
                        "ring_mod",
                        "mixer",
                        "input_3",
                    ),
                    "audio",
                    tag=WOGGLE_MIXER_LINK,
                )
            _add_visual_link(
                f"{MIXER_NODE}.output",
                f"{LPG_NODE}.audio",
                _default_cable(
                    runtime.patch,
                    "mixer",
                    "output",
                    "low_pass_gate",
                    "audio",
                ),
                "audio",
                tag=MIXER_LPG_LINK,
            )
            _add_visual_link(
                f"{SCALE_NODE}.trigger",
                f"{LPG_NODE}.strike",
                _default_cable(
                    runtime.patch,
                    "scale_generator",
                    "trigger",
                    "low_pass_gate",
                    "strike",
                ),
                "gate",
                tag=SCALE_LPG_LINK,
            )
            _add_visual_link(
                f"{FUNCTION_NODE}.channel_4",
                f"{REVERB_NODE}.decay_cv",
                _default_cable(
                    runtime.patch,
                    "utility",
                    "channel_4",
                    "reverb",
                    "decay_cv",
                ),
                "cv",
                tag=UTILITY_REVERB_LINK,
            )
            _add_visual_link(
                f"{LPG_NODE}.output",
                f"{REVERB_NODE}.audio",
                _default_cable(
                    runtime.patch,
                    "low_pass_gate",
                    "output",
                    "reverb",
                    "audio",
                ),
                "audio",
                tag=LPG_REVERB_LINK,
            )
            _add_visual_link(
                f"{WOGGLE_NODE}.burst",
                f"{REVERB_NODE}.freeze",
                _default_cable(
                    runtime.patch,
                    "wogglebug",
                    "burst",
                    "reverb",
                    "freeze",
                ),
                "gate",
                tag=WOGGLE_REVERB_LINK,
            )
            _add_visual_link(
                f"{REVERB_NODE}.left",
                f"{OUTPUT_NODE}.left",
                runtime.patch.output_taps[0],
                "audio",
                tag=REVERB_LEFT_OUTPUT_LINK,
            )
            _add_visual_link(
                f"{REVERB_NODE}.right",
                f"{OUTPUT_NODE}.right",
                runtime.patch.output_taps[1],
                "audio",
                tag=REVERB_RIGHT_OUTPUT_LINK,
            )
            _refresh_patch_bays(runtime.patch)
        dpg.bind_item_theme(FUNCTION_NODE, UTILITY_THEME)
        dpg.bind_item_theme(VCO_NODE, VCO_THEME)
        dpg.bind_item_theme(MIXER_NODE, MIXER_THEME)
        dpg.bind_item_theme(WOGGLE_NODE, WOGGLE_THEME)
        dpg.bind_item_theme(SCALE_NODE, SCALE_THEME)
        dpg.bind_item_theme(LPG_NODE, LPG_THEME)
        dpg.bind_item_theme(REVERB_NODE, REVERB_THEME)
        dpg.bind_item_theme(OUTPUT_NODE, OUTPUT_THEME)
        dpg.set_item_pos(FUNCTION_NODE, [20, 20])
        dpg.set_item_pos(WOGGLE_NODE, [430, 20])
        dpg.set_item_pos(SCALE_NODE, [860, 20])
        dpg.set_item_pos(VCO_NODE, [330, 570])
        dpg.set_item_pos(MIXER_NODE, [690, 570])
        dpg.set_item_pos(LPG_NODE, [960, 570])
        dpg.set_item_pos(REVERB_NODE, [1_280, 570])
        dpg.set_item_pos(OUTPUT_NODE, [1_670, 570])
        CANVAS_INTERACTION.rail_y.update(
            {
                CONTROL_RAIL: 20.0,
                AUDIO_RAIL: 570.0,
            }
        )
    with dpg.file_dialog(
        tag=SAVE_PATCH_DIALOG,
        label="Save Noodler Patch",
        show=False,
        modal=True,
        width=720,
        height=460,
        default_filename="Hirajoshi Garden.noodler",
        callback=_save_patch_dialog,
        user_data=runtime,
    ):
        dpg.add_file_extension(".noodler", color=SCALE_ACCENT)
        dpg.add_file_extension(".*")
    _build_module_selector(runtime)
    _configure_knob_handlers(runtime)
    return runtime


def main() -> None:
    """Run the Noodler desktop application."""
    runtime: AppRuntime | None = None
    gesture_monitor = MacMagnifyMonitor(_capture_macos_magnification)
    dpg.create_context()
    try:
        dpg.create_viewport(
            title="Noodler",
            width=1280,
            height=800,
            min_width=900,
            min_height=600,
        )
        runtime = build_ui()
        dpg.setup_dearpygui()
        dpg.set_primary_window(PRIMARY_WINDOW, True)
        dpg.show_viewport()
        gesture_monitor.start()
        dpg.set_frame_callback(1, _refresh_frame, user_data=runtime)
        dpg.start_dearpygui()
    finally:
        gesture_monitor.stop()
        if runtime is not None:
            runtime.audio.close()
        dpg.destroy_context()


if __name__ == "__main__":
    main()
