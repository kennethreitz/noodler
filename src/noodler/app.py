"""Noodler's application entry point."""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import math
from pathlib import Path

import dearpygui.dearpygui as dpg
from pydantic import BaseModel

from .module_providers import ModuleManifest, PortDirection
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
from .history import Edit, EditHistory
from .macos_gestures import MacMagnifyMonitor
from .motion import (
    Glide,
    KnobDrag,
    MeterBallistics,
    RAIL_HALF_LIFE,
    Spring,
    ZOOM_HALF_LIFE,
    clamp_timestep,
    pixel_spring,
    unit_spring,
)
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
    read_patch_preset,
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
RACK_WORKSPACE = "noodler.rack_workspace"
UNPLUG_ALL_BUTTON = "noodler.unplug_all"
SAVE_PATCH_BUTTON = "noodler.save_patch"
FRAME_RACK_BUTTON = "noodler.frame_rack"
SAVE_PATCH_DIALOG = "noodler.save_patch_dialog"
ADD_MODULE_BUTTON = "noodler.add_module"
MODULE_SELECTOR = "noodler.module_selector"
MODULE_SELECTOR_SEARCH = "noodler.module_selector.search"
MODULE_SELECTOR_STATUS = "noodler.module_selector.status"
RACK_OUTLINE_BODY = "noodler.rack_outline.body"
RACK_OUTLINE_STATUS = "noodler.rack_outline.status"
MODULE_LIBRARY_SECTIONS = (
    (
        "COMPOSE & MODULATE",
        ("Musical Brains", "Sequencers", "Random & Chaos"),
    ),
    (
        "GENERATE",
        ("Sources", "Oscillators", "Noise & Random"),
    ),
    (
        "SHAPE & CONTROL",
        ("Filters", "Envelopes & Dynamics", "Dynamics"),
    ),
    (
        "MIX & SPACE",
        ("Utilities", "Effects"),
    ),
)
ZOOM_OUT_BUTTON = "noodler.zoom_out"
ZOOM_RESET_BUTTON = "noodler.zoom_reset"
ZOOM_IN_BUTTON = "noodler.zoom_in"
OUTPUT_METER = "noodler.output_meter"
INPUT_HANDLERS = "noodler.input_handlers"
MODULE_CLOSE_LAYER = "noodler.module_close_layer"
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
RACK_THEME = "noodler.theme.rack"
RACK_BOX_SELECTOR = "noodler.theme.rack.box_selector"
BOX_SELECTOR_FILL = f"{RACK_BOX_SELECTOR}.fill"
BOX_SELECTOR_OUTLINE = f"{RACK_BOX_SELECTOR}.outline"
BOX_SELECTOR_HIDDEN = (0, 0, 0, 0)
"""Dragging empty canvas pans, so the marquee stays out of the way."""
BOX_SELECTOR_FILL_COLOR = (211, 145, 57, 38)
BOX_SELECTOR_OUTLINE_COLOR = (211, 145, 57, 170)
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
    "DRAG JACKS TO PATCH  ·  SELECT + DELETE TO UNPATCH OR REMOVE  ·  "
    "⌘Z = UNDO  ·  ⌘K = ADD MODULE  ·  F = FRAME ALL  ·  "
    "SPACE + MOVE = PAN  ·  DRAG BACKGROUND = PAN  ·  SHIFT + DRAG = SELECT  ·  "
    "PINCH = ZOOM  ·  DOUBLE-CLICK TITLE = FOLD  ·  DOUBLE-CLICK KNOB = RESET"
)


KNOB_HINT_DRAG_LIMIT = 3
MIN_RACK_ZOOM = 0.55
MAX_RACK_ZOOM = 1.65
RACK_ZOOM_STEP = 1.12
FRAME_MARGIN = 56.0
"""Breathing room left around the rack when the camera frames it."""
MODULE_KNOB_SCALE = 0.84
RACK_FONT_PREFIX = "noodler.font.rack"
RACK_FONT_SIZES = tuple(range(9, 27))

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
    size: int = 62
    default_value: float | None = None
    """The value the module was built with, restored by double-clicking."""


@dataclass(slots=True)
class KnobInteraction:
    """State shared by the global Ableton-style vertical knob gesture."""

    bindings: dict[int | str, KnobBinding] = field(default_factory=dict)
    active_knob: int | str | None = None
    drag_position: float = 0.0
    drag: KnobDrag = field(default_factory=KnobDrag)
    last_mouse_y: float = 0.0
    tooltip_tags: list[int | str] = field(default_factory=list)
    completed_drags: int = 0

    def reset(self) -> None:
        self.bindings.clear()
        self.active_knob = None
        self.drag_position = 0.0
        self.drag = KnobDrag()
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
    zoom_spring: Spring = field(
        default_factory=lambda: unit_spring(1.0, ZOOM_HALF_LIFE)
    )
    glide_x: Glide = field(default_factory=Glide)
    glide_y: Glide = field(default_factory=Glide)
    pan_velocity_x: float = 0.0
    pan_velocity_y: float = 0.0
    space_panning: bool = False
    press_consumed: bool = False
    """A press already answered by a one-shot control, held until release."""
    recenter_x: Spring = field(default_factory=lambda: pixel_spring(0.0))
    recenter_y: Spring = field(default_factory=lambda: pixel_spring(0.0))
    translate_residue_x: float = 0.0
    translate_residue_y: float = 0.0

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
        self.zoom_spring = unit_spring(1.0, ZOOM_HALF_LIFE)
        self.press_consumed = False
        self.space_panning = False
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

    def stop_panning(self) -> None:
        self.panning = False
        self.pan_candidate = False
        self.press_x = 0.0
        self.press_y = 0.0
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0


CANVAS_INTERACTION = CanvasInteraction()

RAIL_SPRINGS: dict[int | str, tuple[Spring, Spring]] = {}
"""One critically damped spring pair per rack node, in rack coordinates."""

METER_BALLISTICS = MeterBallistics()


def _rail_springs(
    node: int | str,
    x: float,
    y: float,
) -> tuple[Spring, Spring]:
    """Return the spring pair carrying one module toward its rail slot."""
    springs = RAIL_SPRINGS.get(node)
    if springs is None:
        springs = (pixel_spring(x, RAIL_HALF_LIFE), pixel_spring(y, RAIL_HALF_LIFE))
        RAIL_SPRINGS[node] = springs
    return springs


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


def _reset_rack_registry(*, starter_patch: bool) -> None:
    """Return mutable node registries to the requested initial rack."""
    RACK_NODES[:] = BASE_RACK_NODES if starter_patch else (OUTPUT_NODE,)
    INSTANCE_NODE_TAGS.clear()
    if starter_patch:
        INSTANCE_NODE_TAGS.update(BASE_INSTANCE_NODE_TAGS)
    VIEW_NODE_TAGS.clear()
    VIEW_NODE_TAGS.update(INSTANCE_NODE_TAGS)
    VIEW_NODE_TAGS["system_output"] = OUTPUT_NODE
    RACK_RAILS[CONTROL_RAIL][:] = (
        [FUNCTION_NODE, WOGGLE_NODE, SCALE_NODE] if starter_patch else []
    )
    RACK_RAILS[AUDIO_RAIL][:] = (
        [VCO_NODE, MIXER_NODE, LPG_NODE, REVERB_NODE, OUTPUT_NODE]
        if starter_patch
        else [OUTPUT_NODE]
    )
    MODULE_ACCENTS.clear()
    if starter_patch:
        MODULE_ACCENTS.update(BASE_MODULE_ACCENTS)
    else:
        MODULE_ACCENTS[OUTPUT_NODE] = OUTPUT_ACCENT


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
        for size in RACK_FONT_SIZES:
            if size == 16:
                continue
            dpg.add_font(
                str(SYSTEM_MONO_FONT),
                size,
                tag=f"{RACK_FONT_PREFIX}.{size}",
            )
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
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 7, 3)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 4)
        with dpg.theme_component(dpg.mvNode):
            for node_color, color in (
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
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_NodePadding,
                8,
                5,
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


RACK_HISTORY = EditHistory()
"""Reversible rack edits, newest last."""


@dataclass(frozen=True, slots=True)
class NodeRegistration:
    """Everything the registries knew about a module, for putting it back."""

    node: int | str
    instance_id: str
    rail: str | None
    rail_index: int
    accent: tuple[int, int, int, int] | None
    patch_bay: PatchBayBinding | None


def _capture_node_registration(
    node: int | str,
    instance_id: str,
) -> NodeRegistration:
    rail_name = None
    rail_index = 0
    for name, lane in RACK_RAILS.items():
        if node in lane:
            rail_name = name
            rail_index = lane.index(node)
            break
    return NodeRegistration(
        node=node,
        instance_id=instance_id,
        rail=rail_name,
        rail_index=rail_index,
        accent=MODULE_ACCENTS.get(node),
        patch_bay=PATCH_BAYS.get(instance_id),
    )


def _restore_node_registration(registration: NodeRegistration) -> None:
    """Put one module back into every registry that described it."""
    node = registration.node
    if node not in RACK_NODES:
        RACK_NODES.append(node)
    INSTANCE_NODE_TAGS[registration.instance_id] = node
    VIEW_NODE_TAGS[registration.instance_id] = node
    if registration.accent is not None:
        MODULE_ACCENTS[node] = registration.accent
    if registration.patch_bay is not None:
        PATCH_BAYS[registration.instance_id] = registration.patch_bay
    if registration.rail is not None:
        lane = RACK_RAILS[registration.rail]
        if node not in lane:
            lane.insert(min(registration.rail_index, len(lane)), node)


def _output_channel_attribute(channel: OutputChannel) -> str:
    return {
        OutputChannel.BOTH: f"{OUTPUT_NODE}.mono",
        OutputChannel.LEFT: f"{OUTPUT_NODE}.left",
        OutputChannel.RIGHT: f"{OUTPUT_NODE}.right",
    }[channel]


def _endpoint_attribute(endpoint: Endpoint) -> str | None:
    node = INSTANCE_NODE_TAGS.get(endpoint.module_id)
    return None if node is None else f"{node}.{endpoint.port_id}"


def _endpoint_signal(patch: PatchGraph, endpoint: Endpoint) -> str:
    module = patch.modules.get(endpoint.module_id)
    if module is not None:
        for port in module.manifest.ports:
            if port.id == endpoint.port_id:
                return port.signal_type.value
    return "cv"


def _route_description(route: Cable | OutputTap) -> str:
    if isinstance(route, Cable):
        return (
            f"{route.source.module_id}.{route.source.port_id} → "
            f"{route.target.module_id}.{route.target.port_id}"
        )
    return f"{route.source.module_id}.{route.source.port_id} → out"


def _visual_link_for(route: Cable | OutputTap) -> int | str | None:
    """Find the drawn cable that stands for one graph route."""
    if not dpg.does_item_exist(RACK):
        return None
    for link in dpg.get_item_children(RACK).get(0, ()):
        if dpg.get_item_user_data(link) == route:
            return link
    return None


def _erase_route(runtime: AppRuntime, route: Cable | OutputTap) -> None:
    """Remove one cable or tap from the graph and from the rack."""
    if isinstance(route, Cable):
        _edit_patch(runtime, lambda: runtime.patch.disconnect(route))
    else:
        _edit_patch(runtime, lambda: runtime.patch.disconnect_output(route))
    link = _visual_link_for(route)
    if link is not None:
        dpg.delete_item(link)
    _refresh_patch_bays(runtime.patch)
    _refresh_rack_outline(runtime)


def _restore_route(runtime: AppRuntime, route: Cable | OutputTap) -> None:
    """Re-create one cable or tap that an edit removed."""
    if isinstance(route, Cable):
        _edit_patch(
            runtime,
            lambda: runtime.patch.connect(
                route.source.module_id,
                route.source.port_id,
                route.target.module_id,
                route.target.port_id,
            ),
        )
        target_attribute = _endpoint_attribute(route.target)
    else:
        _edit_patch(
            runtime,
            lambda: runtime.patch.connect_output(
                route.source.module_id,
                route.source.port_id,
                gain=route.gain,
                channel=route.channel,
            ),
        )
        target_attribute = _output_channel_attribute(route.channel)
    source_attribute = _endpoint_attribute(route.source)
    if (
        source_attribute is not None
        and target_attribute is not None
        and dpg.does_item_exist(source_attribute)
        and dpg.does_item_exist(target_attribute)
    ):
        _add_visual_link(
            source_attribute,
            target_attribute,
            route,
            _endpoint_signal(runtime.patch, route.source),
        )
    _refresh_patch_bays(runtime.patch)
    _refresh_rack_outline(runtime)


def _restore_routes(
    runtime: AppRuntime,
    routes: tuple[Cable | OutputTap, ...],
) -> None:
    """Re-create several routes, skipping any whose endpoints are gone."""
    for route in routes:
        try:
            _restore_route(runtime, route)
        except (PatchError, ValueError):
            continue


def _erase_routes(
    runtime: AppRuntime,
    routes: tuple[Cable | OutputTap, ...],
) -> None:
    """Remove several routes, skipping any already gone from the graph."""
    for route in routes:
        try:
            _erase_route(runtime, route)
        except (PatchError, ValueError):
            continue


def _routes_touching(patch: PatchGraph, instance_id: str) -> tuple[
    Cable | OutputTap, ...
]:
    """Every cable and tap that would be lost with one module."""
    routes: list[Cable | OutputTap] = [
        cable
        for cable in patch.cables
        if instance_id in (cable.source.module_id, cable.target.module_id)
    ]
    routes.extend(
        tap for tap in patch.output_taps if tap.source.module_id == instance_id
    )
    return tuple(routes)


def _record_edit(
    description: str,
    undo: Callable[[], None],
    redo: Callable[[], None],
    discard: Callable[[], None] | None = None,
) -> None:
    RACK_HISTORY.record(
        Edit(description=description, undo=undo, redo=redo, discard=discard)
    )


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
            _refresh_rack_outline(runtime)
            _record_edit(
                f"PATCH {_route_description(tap)}",
                undo=lambda: _erase_route(runtime, tap),
                redo=lambda: _restore_route(runtime, tap),
            )
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
        _refresh_rack_outline(runtime)
        _record_edit(
            f"PATCH {_route_description(cable)}",
            undo=lambda: _erase_route(runtime, cable),
            redo=lambda: _restore_route(runtime, cable),
        )
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
        _refresh_rack_outline(runtime)
        _record_edit(
            f"UNPATCH {_route_description(route)}",
            undo=lambda: _restore_route(runtime, route),
            redo=lambda: _erase_route(runtime, route),
        )
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

        unplugged: tuple[Cable | OutputTap, ...] = (
            runtime.patch.cables + runtime.patch.output_taps
        )
        removed = _edit_patch(runtime, runtime.patch.disconnect_all)
        rack_children = dpg.get_item_children(RACK)
        for item in tuple(rack_children.get(0, ())):
            route = dpg.get_item_user_data(item)
            if isinstance(route, (Cable, OutputTap)):
                dpg.delete_item(item)

        _refresh_patch_bays(runtime.patch)
        _refresh_rack_outline(runtime)
        _record_edit(
            f"UNPLUG ALL ({removed})",
            undo=lambda: _restore_routes(runtime, unplugged),
            redo=lambda: _erase_routes(runtime, unplugged),
        )
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


def _decibels(level: float) -> str:
    return "-∞" if level <= 0.00001 else f"{20.0 * math.log10(level):.0f}"


def _refresh_ui(runtime: AppRuntime, dt: float = 1.0 / 60.0) -> None:
    """Copy inexpensive audio telemetry onto the UI thread."""
    if not dpg.does_item_exist(OUTPUT_METER):
        return
    # The engine reports a per-block peak, which flickers when drawn raw.
    # Peak-programme ballistics rise instantly and fall on a known slope.
    level = min(1.0, METER_BALLISTICS.advance(runtime.audio.last_peak, dt))
    dpg.set_value(OUTPUT_METER, level)
    dpg.configure_item(
        OUTPUT_METER,
        overlay=f"{_decibels(level)} dB  ·  PK {_decibels(METER_BALLISTICS.peak)}",
    )
    if (
        runtime.scale_generator is not None
        and dpg.does_item_exist(SCALE_NOTE_STATUS)
    ):
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
    # One clamped timestep drives every animation, so the rack feels the same
    # on a 60 Hz monitor as on a 120 Hz panel, and a frame hitch resumes
    # motion rather than teleporting it.
    dt = clamp_timestep(dpg.get_delta_time())
    _release_stale_key_latches()
    _settle_space_pan()
    _consume_macos_magnification()
    _glide_rack(dt)
    _settle_recenter(dt)
    _settle_rack_zoom(dt)
    _settle_rack_rails(dt)
    _refresh_ui(runtime, dt)
    _refresh_module_close_buttons()
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
    """Show every jack unless the user asks to hide open connections."""
    connected = _connected_port_ids(binding.patch, binding.module_id)
    hide_open = (
        bool(dpg.get_value(binding.toggle_tag))
        if dpg.does_item_exist(binding.toggle_tag)
        else False
    )
    for port_id in binding.port_ids:
        tag = f"{binding.node_tag}.{port_id}"
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=not hide_open or port_id in connected)
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
    _hide_open: bool,
    binding: PatchBayBinding,
) -> None:
    _refresh_patch_bay(binding)


def _add_patch_bay_toggle(
    patch: PatchGraph,
    module_id: str,
    node_tag: str,
    port_ids: tuple[str, ...],
) -> None:
    """Add the optional filter for hiding currently open module ports."""
    binding = PatchBayBinding(
        patch=patch,
        module_id=module_id,
        node_tag=node_tag,
        port_ids=port_ids,
        toggle_tag=f"{node_tag}.patch_bay.hide_open",
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
            label="HIDE OPEN",
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


def _rack_font_tag(zoom: float) -> str:
    """Choose a rack-only font without scaling the surrounding workspace."""
    size = min(RACK_FONT_SIZES[-1], max(RACK_FONT_SIZES[0], round(16 * zoom)))
    return APP_FONT if size == 16 else f"{RACK_FONT_PREFIX}.{size}"


def _bind_rack_node_font(node: int | str, zoom: float | None = None) -> None:
    if dpg.does_item_exist(node):
        dpg.bind_item_font(
            node,
            _rack_font_tag(CANVAS_INTERACTION.zoom if zoom is None else zoom),
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
        _bind_rack_node_font(node, new_zoom)
    for spring_x, spring_y in RAIL_SPRINGS.values():
        spring_x.value, spring_y.value = _zoomed_position(
            (spring_x.value, spring_y.value), anchor, ratio
        )
        spring_x.target, spring_y.target = _zoomed_position(
            (spring_x.target, spring_y.target), anchor, ratio
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


def _settle_rack_zoom(dt: float = 1.0 / 60.0) -> None:
    """Spring trackpad and wheel zoom while keeping the pointer anchored."""
    interaction = CANVAS_INTERACTION
    spring = interaction.zoom_spring
    spring.value = interaction.zoom
    spring.retarget(interaction.zoom_target)
    # _set_rack_zoom re-derives the target from the value it is handed, so the
    # real destination and its anchor are restored after every step.
    target = interaction.zoom_target
    anchor = interaction.zoom_anchor
    if spring.settled:
        if not math.isclose(interaction.zoom, target, abs_tol=1e-6):
            _set_rack_zoom(target, screen_anchor=anchor)
            interaction.zoom_target = target
            interaction.zoom_anchor = anchor
        return
    _set_rack_zoom(spring.advance(dt), screen_anchor=anchor)
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


def _rack_content_bounds() -> tuple[float, float, float, float] | None:
    """Return the editor-local box containing every mounted module."""
    boxes = []
    for node in RACK_NODES:
        if not dpg.does_item_exist(node):
            continue
        node_x, node_y = (float(value) for value in dpg.get_item_pos(node))
        width, height = (
            float(value) for value in dpg.get_item_rect_size(node)
        )
        boxes.append(
            (node_x, node_y, node_x + max(width, 1.0), node_y + max(height, 1.0))
        )
    if not boxes:
        return None
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _frame_rack(
    _sender: int | str = 0,
    _app_data: object = None,
    _user_data: object = None,
) -> None:
    """Bring the whole rack back into view, centred and fully visible.

    Momentum makes it easy to send the rack somewhere the window is not, so
    the camera needs a way home. The move is sprung rather than instant, which
    also shows the user which direction their rack came back from.
    """
    if _keyboard_is_captured() or not dpg.does_item_exist(RACK):
        return
    bounds = _rack_content_bounds()
    if bounds is None:
        _set_patch_status("NOTHING TO FRAME  ·  THE RACK IS EMPTY")
        return

    interaction = CANVAS_INTERACTION
    minimum_x, minimum_y, maximum_x, maximum_y = bounds
    view_width, view_height = (
        float(value) for value in dpg.get_item_rect_size(RACK)
    )
    content_width = max(1.0, maximum_x - minimum_x)
    content_height = max(1.0, maximum_y - minimum_y)

    if view_width > 1.0 and view_height > 1.0:
        fit = min(
            (view_width - FRAME_MARGIN * 2.0) / content_width,
            (view_height - FRAME_MARGIN * 2.0) / content_height,
        )
        _queue_rack_zoom(interaction.zoom * max(0.05, fit), screen_anchor=None)
        target_x = view_width * 0.5
        target_y = view_height * 0.5
    else:
        # Without a laid-out viewport, centring is all that can be honoured.
        target_x = (minimum_x + maximum_x) * 0.5
        target_y = (minimum_y + maximum_y) * 0.5

    interaction.recenter_x.snap(0.0)
    interaction.recenter_y.snap(0.0)
    interaction.recenter_x.retarget(target_x - (minimum_x + maximum_x) * 0.5)
    interaction.recenter_y.retarget(target_y - (minimum_y + maximum_y) * 0.5)
    _set_patch_status("FRAMED THE RACK  ·  PRESS F ANY TIME")


def _reveal_node(node: int | str) -> bool:
    """Bring one module into view if it arrived outside the window.

    A module added while the rack is panned away lands somewhere the user is
    not looking, which reads as nothing having happened. The camera moves the
    shortest distance that makes the whole module visible, rather than
    re-framing everything and losing the user's place.
    """
    if not dpg.does_item_exist(RACK) or not dpg.does_item_exist(node):
        return False
    view_width, view_height = (
        float(value) for value in dpg.get_item_rect_size(RACK)
    )
    if view_width <= 1.0 or view_height <= 1.0:
        return False

    node_x, node_y = (float(value) for value in dpg.get_item_pos(node))
    width, height = (float(value) for value in dpg.get_item_rect_size(node))
    width = max(width, 1.0)
    height = max(height, 1.0)

    def _offset(near: float, far: float, extent: float) -> float:
        if near < FRAME_MARGIN:
            return FRAME_MARGIN - near
        if far > extent - FRAME_MARGIN:
            return max(
                FRAME_MARGIN - near,
                (extent - FRAME_MARGIN) - far,
            )
        return 0.0

    delta_x = _offset(node_x, node_x + width, view_width)
    delta_y = _offset(node_y, node_y + height, view_height)
    if not delta_x and not delta_y:
        return False

    interaction = CANVAS_INTERACTION
    interaction.recenter_x.snap(0.0)
    interaction.recenter_y.snap(0.0)
    interaction.recenter_x.retarget(delta_x)
    interaction.recenter_y.retarget(delta_y)
    return True


def _settle_recenter(dt: float = 1.0 / 60.0) -> None:
    """Advance a framing move, translating the rack by the difference."""
    interaction = CANVAS_INTERACTION
    spring_x = interaction.recenter_x
    spring_y = interaction.recenter_y
    if spring_x.settled and spring_y.settled:
        return
    previous_x, previous_y = spring_x.value, spring_y.value
    _translate_rack(
        spring_x.advance(dt) - previous_x,
        spring_y.advance(dt) - previous_y,
    )
    if spring_x.settled and spring_y.settled:
        # The offset has been fully applied; start the next move from zero.
        spring_x.snap(0.0)
        spring_y.snap(0.0)


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


def _settle_rack_rails(dt: float = 1.0 / 60.0) -> None:
    """Spring modules onto semantic lanes and prevent horizontal overlap."""
    if (
        CANVAS_INTERACTION.panning
        or CANVAS_INTERACTION.space_panning
        or not CANVAS_INTERACTION.rail_y
    ):
        return
    active_node = _dragged_rack_node()
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
            spring_x, spring_y = _rail_springs(node, current_x, current_y)
            if node == active_node:
                # The pointer owns a dragged module; the spring only follows.
                spring_x.snap(current_x)
                spring_y.snap(current_y)
                continue
            # Dear PyGui stores node positions as integers, so the spring keeps
            # the sub-pixel truth and the item is only its rendering. Re-syncing
            # from the item every frame would accumulate truncation error and
            # make settling depend on how many frames it took. A difference of
            # more than a pixel means something else moved the module.
            if abs(spring_x.value - current_x) > 1.0:
                spring_x.snap(current_x)
            if abs(spring_y.value - current_y) > 1.0:
                spring_y.snap(current_y)
            spring_x.retarget(target_x)
            spring_y.retarget(target_y)
            next_x = spring_x.advance(dt)
            next_y = spring_y.advance(dt)
            if round(next_x) != round(current_x) or round(next_y) != round(
                current_y
            ):
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


def _module_title_height() -> float:
    return max(24.0, min(44.0, 32.0 * CANVAS_INTERACTION.zoom))


def _module_close_bounds(
    node: int | str,
) -> tuple[float, float, float, float] | None:
    """Return the screen-space close target at a module title's right edge."""
    if (
        node == OUTPUT_NODE
        or MODULE_COLLAPSE.is_collapsed(node)
        or not dpg.does_item_exist(node)
    ):
        return None
    try:
        minimum_x, minimum_y = dpg.get_item_rect_min(node)
        maximum_x, maximum_y = dpg.get_item_rect_max(node)
    except (KeyError, SystemError):
        return None
    title_height = min(maximum_y - minimum_y, _module_title_height())
    size = max(14.0, min(20.0, title_height - 8.0))
    right = maximum_x - 5.0
    left = right - size
    top = minimum_y + max(3.0, (title_height - size) * 0.5)
    bottom = top + size
    try:
        rack_left, rack_top = dpg.get_item_rect_min(RACK)
        rack_right, rack_bottom = dpg.get_item_rect_max(RACK)
    except (KeyError, SystemError):
        return None
    if (
        left < rack_left
        or top < rack_top
        or right > rack_right
        or bottom > rack_bottom
    ):
        return None
    return (left, top, right, bottom)


def _module_close_at(
    screen_position: tuple[float, float],
) -> int | str | None:
    mouse_x, mouse_y = screen_position
    for node in reversed(RACK_NODES):
        bounds = _module_close_bounds(node)
        if bounds is None:
            continue
        left, top, right, bottom = bounds
        if left <= mouse_x <= right and top <= mouse_y <= bottom:
            return node
    return None


def _refresh_module_close_buttons() -> None:
    """Draw title-bar close affordances without changing node contents."""
    if not dpg.does_item_exist(MODULE_CLOSE_LAYER):
        return
    dpg.delete_item(MODULE_CLOSE_LAYER, children_only=True)
    mouse_position = tuple(dpg.get_mouse_pos(local=False))
    hovered_node = _module_close_at(mouse_position)
    for node in RACK_NODES:
        bounds = _module_close_bounds(node)
        if bounds is None:
            continue
        left, top, right, bottom = bounds
        hovered = node == hovered_node
        dpg.draw_rectangle(
            (left, top),
            (right, bottom),
            parent=MODULE_CLOSE_LAYER,
            color=(255, 241, 226, 155 if not hovered else 255),
            fill=(30, 24, 22, 105) if not hovered else OUTPUT_ACCENT,
            rounding=4.0,
            thickness=1.0,
        )
        inset = max(4.0, (right - left) * 0.28)
        line_color = (255, 246, 232, 235)
        dpg.draw_line(
            (left + inset, top + inset),
            (right - inset, bottom - inset),
            parent=MODULE_CLOSE_LAYER,
            color=line_color,
            thickness=1.7,
        )
        dpg.draw_line(
            (right - inset, top + inset),
            (left + inset, bottom - inset),
            parent=MODULE_CLOSE_LAYER,
            color=line_color,
            thickness=1.7,
        )


def _module_title_at(
    screen_position: tuple[float, float],
) -> int | str | None:
    """Find the top title-bar strip under one screen-space point."""
    mouse_x, mouse_y = screen_position
    title_height = _module_title_height()
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


def _reset_knob_to_default(knob: int | str, binding: KnobBinding) -> bool:
    """Restore the value a control was built with, as a panel reset does."""
    if binding.default_value is None:
        return False
    position = _control_position(
        binding.default_value,
        binding.minimum,
        binding.maximum,
        binding.logarithmic,
    )
    dpg.set_value(knob, position)
    _set_knob_value(str(knob), position, binding)
    _set_patch_status(
        f"RESET  {binding.label.upper()}  "
        f"{binding.formatter(binding.default_value)}"
    )
    return True


def _hovered_knob() -> tuple[int | str, KnobBinding] | None:
    """Return the topmost rotary control currently under the pointer."""
    for knob, binding in reversed(tuple(KNOB_INTERACTION.bindings.items())):
        if dpg.does_item_exist(knob) and dpg.is_item_hovered(knob):
            return knob, binding
    return None


def _toggle_module_from_title(
    _sender: int | str,
    _app_data: object,
    runtime: AppRuntime,
) -> None:
    """Resolve a left double-click on the rack.

    A double-click over a control restores its default; over a module title it
    folds the module down to its spine.
    """
    hovered = _hovered_knob()
    if hovered is not None and _reset_knob_to_default(*hovered):
        return
    node = _module_title_at(tuple(dpg.get_mouse_pos(local=False)))
    if node is None:
        return
    _set_module_collapsed(node, not MODULE_COLLAPSE.is_collapsed(node), runtime)


def _add_rack_controls(runtime: AppRuntime) -> None:
    """Add the camera, patch, and library controls shared by every rack view.

    Both rack builders grew their own copy of this cluster, which is how the
    same button ended up labelled two different ways.
    """
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
        label="FRAME ALL",
        tag=FRAME_RACK_BUTTON,
        callback=_frame_rack,
        user_data=runtime,
    )
    with dpg.tooltip(FRAME_RACK_BUTTON):
        dpg.add_text("Bring every module back into view.  ·  F")
    dpg.add_button(
        label="UNPLUG ALL",
        tag=UNPLUG_ALL_BUTTON,
        callback=_unplug_all,
        user_data=runtime,
    )
    with dpg.tooltip(UNPLUG_ALL_BUTTON):
        dpg.add_text("Disconnect every cable from the live patch.  ·  ⌘Z undoes it.")
    dpg.add_button(
        label="+  ADD MODULE",
        tag=ADD_MODULE_BUTTON,
        callback=_show_module_selector,
    )
    with dpg.tooltip(ADD_MODULE_BUTTON):
        dpg.add_text("Browse all built-in instruments and utilities.  ·  ⌘K")
    dpg.add_button(
        label="SAVE PATCH",
        tag=SAVE_PATCH_BUTTON,
        callback=_show_save_patch_dialog,
    )
    with dpg.tooltip(SAVE_PATCH_BUTTON):
        dpg.add_text("Save modules, cables, controls, and rack view.")


KEY_LATCH: set[int] = set()
"""Keys whose current press has already been acted on."""


def _press_once(
    key: int,
    callback: Callable[[int | str, object, AppRuntime], None],
) -> Callable[[int | str, object, AppRuntime], None]:
    """Make a bound key act once per physical press.

    Dear PyGui's key-press callback follows the platform's key repeat, so a held
    Delete would walk through the rack a module at a time and a held ⌘Z would
    unwind the whole history in about a second. Destructive keys should answer
    to presses, not to how long a finger rests on them.
    """

    def handle(sender: int | str, app_data: object, user_data: AppRuntime) -> None:
        if key in KEY_LATCH:
            return
        KEY_LATCH.add(key)
        callback(sender, app_data, user_data)

    return handle


def _release_stale_key_latches() -> None:
    """Let go of any latched key that is no longer down.

    Reconciling against the real key state each frame means a press whose
    release never arrives — a lost focus, a window switch — cannot leave a
    shortcut stuck.
    """
    for key in tuple(KEY_LATCH):
        if not dpg.is_key_down(key):
            KEY_LATCH.discard(key)


def _show_knob_hints(visible: bool) -> None:
    """Show or hide the rotary hint tooltips as one group.

    A hint that covers the value it is explaining, at the moment the value is
    being changed, is worse than no hint at all — so they are put away for the
    duration of every drag, and retired for good once the gesture is learned.
    """
    for tooltip in KNOB_INTERACTION.tooltip_tags:
        if dpg.does_item_exist(tooltip):
            dpg.configure_item(tooltip, show=visible)


def _show_box_selector(visible: bool) -> None:
    """Draw the selection marquee only for the gesture that selects."""
    if not dpg.does_item_exist(BOX_SELECTOR_FILL):
        return
    dpg.set_value(
        BOX_SELECTOR_FILL,
        BOX_SELECTOR_FILL_COLOR if visible else BOX_SELECTOR_HIDDEN,
    )
    dpg.set_value(
        BOX_SELECTOR_OUTLINE,
        BOX_SELECTOR_OUTLINE_COLOR if visible else BOX_SELECTOR_HIDDEN,
    )


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


def _translate_rack(delta_x: float, delta_y: float) -> None:
    """Move every module and every rail by one screen-space offset.

    Node positions are integers, so a sprung or gliding camera would lose the
    fraction of a pixel it asked for on every frame, on every module. The
    remainder is carried instead, and only whole pixels are ever written.
    """
    interaction = CANVAS_INTERACTION
    requested_x = delta_x + interaction.translate_residue_x
    requested_y = delta_y + interaction.translate_residue_y
    delta_x = float(math.trunc(requested_x))
    delta_y = float(math.trunc(requested_y))
    interaction.translate_residue_x = requested_x - delta_x
    interaction.translate_residue_y = requested_y - delta_y
    if not delta_x and not delta_y:
        return
    for node in RACK_NODES:
        if not dpg.does_item_exist(node):
            continue
        node_x, node_y = dpg.get_item_pos(node)
        dpg.set_item_pos(node, [node_x + delta_x, node_y + delta_y])
    for rail in tuple(CANVAS_INTERACTION.rail_y):
        CANVAS_INTERACTION.rail_y[rail] += delta_y
    # Carry the springs with the camera so they keep owning the sub-pixel
    # position rather than re-syncing to a truncated one.
    for spring_x, spring_y in RAIL_SPRINGS.values():
        spring_x.value += delta_x
        spring_x.target += delta_x
        spring_y.value += delta_y
        spring_y.target += delta_y


def _track_pan_velocity(delta_x: float, delta_y: float) -> None:
    """Smooth the pointer velocity that a released pan will carry away.

    A single final frame is too noisy to become momentum on its own, so the
    estimate is blended over the last few frames of the gesture.
    """
    interaction = CANVAS_INTERACTION
    dt = clamp_timestep(dpg.get_delta_time())
    if dt <= 0.0:
        return
    blend = 0.45
    interaction.pan_velocity_x += (
        delta_x / dt - interaction.pan_velocity_x
    ) * blend
    interaction.pan_velocity_y += (
        delta_y / dt - interaction.pan_velocity_y
    ) * blend


def _pan_rack(*, clear_selection: bool = True) -> None:
    interaction = CANVAS_INTERACTION
    if clear_selection:
        _clear_rack_selection()
    mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
    delta_x = mouse_x - interaction.last_mouse_x
    delta_y = mouse_y - interaction.last_mouse_y
    _translate_rack(delta_x, delta_y)
    _track_pan_velocity(delta_x, delta_y)
    interaction.last_mouse_x = float(mouse_x)
    interaction.last_mouse_y = float(mouse_y)


def _settle_space_pan() -> None:
    """Pan by moving the pointer while Space is held, with no button down.

    A held button is what makes the node editor claim a background drag for box
    selection, so the modifier-only form never has to fight it — and it matches
    the hand-tool reach people already have from other canvas tools.
    """
    interaction = CANVAS_INTERACTION
    holding = (
        dpg.is_key_down(dpg.mvKey_Spacebar)
        and not _keyboard_is_captured()
        and _mouse_is_over_rack()
    )
    if not holding:
        if interaction.space_panning:
            interaction.space_panning = False
            _release_pan_momentum()
            _set_patch_status(DEFAULT_CONTROL_STATUS)
        return
    if not interaction.space_panning:
        interaction.space_panning = True
        interaction.stop_glide()
        mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
        interaction.last_mouse_x = float(mouse_x)
        interaction.last_mouse_y = float(mouse_y)
        _set_patch_status("PANNING  ·  MOVE TO PLACE VIEW  ·  RELEASE SPACE")
        return
    # A selection survives a pure space pan; only a stray button press, which
    # the editor would answer with an invisible box select, has to clear it.
    _pan_rack(
        clear_selection=dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
    )


def _release_pan_momentum() -> None:
    """Hand the pointer velocity measured during a pan to the glide."""
    interaction = CANVAS_INTERACTION
    interaction.glide_x.release(interaction.pan_velocity_x)
    interaction.glide_y.release(interaction.pan_velocity_y)
    interaction.pan_velocity_x = 0.0
    interaction.pan_velocity_y = 0.0


def _glide_rack(dt: float = 1.0 / 60.0) -> None:
    """Carry a flicked rack to rest instead of stopping it dead."""
    interaction = CANVAS_INTERACTION
    if interaction.panning or interaction.space_panning:
        return
    _translate_rack(
        interaction.glide_x.advance(dt),
        interaction.glide_y.advance(dt),
    )


def _begin_knob_drag(
    _sender: str,
    _app_data: object,
    interaction_data: KnobInteraction | tuple[KnobInteraction, AppRuntime],
) -> None:
    runtime: AppRuntime | None = None
    if isinstance(interaction_data, tuple):
        interaction, runtime = interaction_data
    else:
        interaction = interaction_data
    if interaction.active_knob is not None:
        return
    if CANVAS_INTERACTION.panning or CANVAS_INTERACTION.press_consumed:
        # Dear PyGui repeats the mouse-down callback for every frame the button
        # is held. Beginning the pan again would move its origin to the current
        # pointer each frame, leaving the drag with nothing to travel, and a
        # press already spent on a one-shot control must not become a drag.
        return
    # Any press on the rack catches a gliding canvas, the way a finger does.
    CANVAS_INTERACTION.stop_glide()
    mouse_position = tuple(dpg.get_mouse_pos(local=False))
    close_node = _module_close_at(mouse_position)
    if runtime is not None and close_node is not None:
        CANVAS_INTERACTION.press_consumed = True
        _remove_module_node(close_node, runtime)
        return
    if dpg.is_key_down(dpg.mvKey_Spacebar) and _mouse_is_over_rack():
        # Space already pans on movement alone; the button has nothing to add
        # and would only hand the gesture to the editor's box selection.
        CANVAS_INTERACTION.press_consumed = True
        return
    for knob, binding in reversed(tuple(interaction.bindings.items())):
        if dpg.does_item_exist(knob) and dpg.is_item_hovered(knob):
            interaction.active_knob = knob
            interaction.drag_position = float(dpg.get_value(knob))
            minimum, maximum = _knob_bounds(binding)
            interaction.drag.minimum = minimum
            interaction.drag.maximum = maximum
            interaction.drag.begin(interaction.drag_position)
            interaction.last_mouse_y = float(dpg.get_mouse_pos(local=False)[1])
            _show_knob_hints(False)
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
        if dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift):
            # Panning owns a plain background drag, so box selection keeps the
            # modified one — and only then is the marquee worth drawing.
            _show_box_selector(True)
            return
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
        if canvas.press_consumed:
            # The drag handler can promote a press into a pan on its own, so it
            # has to respect a press already spent on a one-shot control.
            return
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
    position = interaction.drag.advance(
        mouse_y - interaction.last_mouse_y,
        clamp_timestep(dpg.get_delta_time()),
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
    _show_box_selector(False)
    CANVAS_INTERACTION.press_consumed = False
    if CANVAS_INTERACTION.panning:
        _clear_rack_selection()
        _release_pan_momentum()
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
    _show_knob_hints(interaction.completed_drags < KNOB_HINT_DRAG_LIMIT)
    if dpg.does_item_exist(CONTROL_STATUS):
        dpg.configure_item(CONTROL_STATUS, color=MUTED_TEXT)
        dpg.set_value(CONTROL_STATUS, DEFAULT_CONTROL_STATUS)


def _module_id_for_node(node: int | str) -> str | None:
    """Find the graph instance a rack node stands for."""
    for instance_id, tag in INSTANCE_NODE_TAGS.items():
        if tag == node:
            return instance_id
    return None


def _node_tag_for_item(item: int | str) -> int | str | None:
    """Resolve a node-editor selection back to its registered rack tag."""
    for node in RACK_NODES:
        if not dpg.does_item_exist(node):
            continue
        if node == item or dpg.get_alias_id(node) == item:
            return node
    return None


def _unregister_rack_node(node: int | str, instance_id: str) -> None:
    """Forget every registry entry that referred to a removed module."""
    if node in RACK_NODES:
        RACK_NODES.remove(node)
    INSTANCE_NODE_TAGS.pop(instance_id, None)
    VIEW_NODE_TAGS.pop(instance_id, None)
    MODULE_ACCENTS.pop(node, None)
    RAIL_SPRINGS.pop(node, None)
    PATCH_BAYS.pop(instance_id, None)
    MODULE_COLLAPSE.attributes.pop(node, None)
    MODULE_COLLAPSE.labels.pop(node, None)
    for lane in RACK_RAILS.values():
        if node in lane:
            lane.remove(node)
    # Rotary bindings are pruned by existence, so nested controls need no map.
    for knob in tuple(KNOB_INTERACTION.bindings):
        if not dpg.does_item_exist(knob):
            del KNOB_INTERACTION.bindings[knob]


def _restore_module_node(
    runtime: AppRuntime,
    registration: NodeRegistration,
    module: object,
    routes: tuple[Cable | OutputTap, ...],
) -> None:
    """Put a removed module, its panel, and its cables back on the rack."""
    node = registration.node
    _edit_patch(
        runtime,
        lambda: runtime.patch.add_module(registration.instance_id, module),
    )
    _restore_node_registration(registration)
    if dpg.does_item_exist(node):
        dpg.configure_item(node, show=True)
        if registration.rail is not None:
            # The rack may have been panned or re-flowed while it was gone, so
            # it rejoins its rail rather than returning to a stale position.
            _place_dynamic_node(node, registration.rail)
    _restore_routes(runtime, routes)
    _refresh_patch_bays(runtime.patch)
    _refresh_rack_outline(runtime)
    _reveal_node(node)


def _remove_module_node(
    node: int | str,
    runtime: AppRuntime,
    *,
    record: bool = True,
) -> bool:
    """Remove one module from the executable graph and from the rack.

    The panel is hidden rather than destroyed. Rebuilding it on undo would mean
    re-deriving controls that the module's own builder made, so the cheapest
    correct restore is the panel that was already there.
    """
    if node == OUTPUT_NODE:
        _set_patch_status("SYSTEM OUT CANNOT BE REMOVED", error=True)
        return False
    instance_id = _module_id_for_node(node)
    if instance_id is None:
        return False
    module = runtime.patch.modules.get(instance_id)
    name = module.manifest.name.upper() if module is not None else instance_id
    registration = _capture_node_registration(node, instance_id)
    routes = _routes_touching(runtime.patch, instance_id)
    try:
        removed = _edit_patch(
            runtime,
            lambda: runtime.patch.remove_module(instance_id),
        )
    except (PatchError, ValueError) as exc:
        _set_patch_status(f"CAN'T REMOVE: {exc}", error=True)
        return False

    for link in tuple(dpg.get_item_children(RACK).get(0, ())):
        route = dpg.get_item_user_data(link)
        if isinstance(route, Cable) and instance_id in (
            route.source.module_id,
            route.target.module_id,
        ):
            dpg.delete_item(link)
        elif isinstance(route, OutputTap) and route.source.module_id == instance_id:
            dpg.delete_item(link)

    dpg.configure_item(node, show=False)
    _unregister_rack_node(node, instance_id)
    _refresh_patch_bays(runtime.patch)
    _refresh_rack_outline(runtime)
    if record and module is not None:
        _record_edit(
            f"REMOVE {name}",
            undo=lambda: _restore_module_node(
                runtime, registration, module, routes
            ),
            redo=lambda: _remove_module_node(node, runtime, record=False),
            discard=lambda: _discard_retained_node(runtime, registration),
        )
    noun = "CABLE" if removed == 1 else "CABLES"
    _set_patch_status(f"REMOVED  {name}  ·  {removed} {noun} UNPATCHED")
    return True


def _discard_retained_node(
    runtime: AppRuntime,
    registration: NodeRegistration,
) -> None:
    """Destroy a retained panel once its edit can never be reversed again."""
    if registration.instance_id in runtime.patch.modules:
        return
    if dpg.does_item_exist(registration.node):
        dpg.delete_item(registration.node)
        for knob in tuple(KNOB_INTERACTION.bindings):
            if not dpg.does_item_exist(knob):
                del KNOB_INTERACTION.bindings[knob]


def _keyboard_is_captured() -> bool:
    """Report whether a text field should receive keys instead of the rack.

    Most Mac keyboards send Backspace for the key labelled Delete, so the rack
    must never claim it while a text field is open. A search box or a patch
    name would otherwise lose a character — or the rack would lose a module.
    """
    if dpg.does_item_exist(SAVE_PATCH_DIALOG) and dpg.is_item_shown(
        SAVE_PATCH_DIALOG
    ):
        return True
    if not dpg.does_item_exist(MODULE_SELECTOR):
        return False
    if dpg.get_item_type(MODULE_SELECTOR).endswith("mvWindowAppItem"):
        return dpg.is_item_shown(MODULE_SELECTOR)
    return dpg.does_item_exist(MODULE_SELECTOR_SEARCH) and (
        dpg.is_item_active(MODULE_SELECTOR_SEARCH)
        or dpg.is_item_focused(MODULE_SELECTOR_SEARCH)
    )


def _delete_rack_selection(
    _sender: int | str,
    _app_data: object,
    runtime: AppRuntime,
) -> None:
    """Unpatch selected cables and remove selected modules."""
    if _keyboard_is_captured() or not dpg.does_item_exist(RACK):
        return
    links = tuple(dpg.get_selected_links(RACK))
    nodes = tuple(dpg.get_selected_nodes(RACK))
    if not links and not nodes:
        _set_patch_status("NOTHING SELECTED  ·  CLICK A CABLE OR A MODULE FIRST")
        return
    for link in links:
        _patch_link_deleted(RACK, link, runtime)
    for item in nodes:
        node = _node_tag_for_item(item)
        if node is not None:
            _remove_module_node(node, runtime)
    _clear_rack_selection()


def _dismiss_rack_focus(
    _sender: int | str,
    _app_data: object,
    _runtime: AppRuntime,
) -> None:
    """Close the module browser, or drop the current rack selection."""
    if (
        dpg.does_item_exist(MODULE_SELECTOR)
        and dpg.get_item_type(MODULE_SELECTOR).endswith("mvWindowAppItem")
        and dpg.is_item_shown(MODULE_SELECTOR)
    ):
        dpg.hide_item(MODULE_SELECTOR)
        return
    if _keyboard_is_captured():
        dpg.set_value(MODULE_SELECTOR_SEARCH, "")
        _filter_module_selector("", "", None)
        return
    _clear_rack_selection()
    _set_patch_status(DEFAULT_CONTROL_STATUS)


def _undo_or_redo_rack_edit(
    _sender: int | str,
    _app_data: object,
    _runtime: AppRuntime,
) -> None:
    """Step back or forward through the reversible rack edits."""
    if _keyboard_is_captured():
        return
    if not (
        dpg.is_key_down(dpg.mvKey_ModSuper) or dpg.is_key_down(dpg.mvKey_ModCtrl)
    ):
        return
    forward = dpg.is_key_down(dpg.mvKey_ModShift)
    verb = "REDO" if forward else "UNDO"
    try:
        edit = RACK_HISTORY.redo() if forward else RACK_HISTORY.undo()
    except (PatchError, ValueError) as exc:
        _set_patch_status(f"CAN'T {verb}: {exc}", error=True)
        return
    if edit is None:
        _set_patch_status(f"NOTHING TO {verb}")
        return
    _set_patch_status(f"{'REDID' if forward else 'UNDID'}  {edit.description.upper()}")


def _open_module_selector_shortcut(
    sender: int | str,
    app_data: object,
    runtime: AppRuntime,
) -> None:
    """Open the module browser on the platform's usual command chord."""
    if not (
        dpg.is_key_down(dpg.mvKey_ModSuper) or dpg.is_key_down(dpg.mvKey_ModCtrl)
    ):
        return
    if not dpg.does_item_exist(MODULE_SELECTOR):
        return
    _show_module_selector(sender, app_data, runtime)


def _configure_rack_theme() -> None:
    """Theme the editor itself, not the nodes inside it.

    The grid and the selection marquee are the editor's own colours. Declared
    against mvNode they were simply never applied, which is how a marquee that
    had been transparent for months kept drawing in default blue. Binding the
    theme to the item removes the question of which component type matches.
    """
    if not dpg.does_item_exist(RACK_THEME):
        with dpg.theme(tag=RACK_THEME):
            with dpg.theme_component(dpg.mvNodeEditor):
                for editor_color, color, tag in (
                    (dpg.mvNodeCol_GridBackground, (22, 23, 21, 255), 0),
                    (dpg.mvNodeCol_GridLine, (43, 45, 40, 150), 0),
                    (
                        dpg.mvNodeCol_BoxSelector,
                        BOX_SELECTOR_HIDDEN,
                        BOX_SELECTOR_FILL,
                    ),
                    (
                        dpg.mvNodeCol_BoxSelectorOutline,
                        BOX_SELECTOR_HIDDEN,
                        BOX_SELECTOR_OUTLINE,
                    ),
                ):
                    dpg.add_theme_color(
                        editor_color,
                        color,
                        tag=tag,
                        category=dpg.mvThemeCat_Nodes,
                    )
    if dpg.does_item_exist(RACK):
        dpg.bind_item_theme(RACK, RACK_THEME)


def _configure_knob_handlers(runtime: AppRuntime) -> None:
    if not dpg.does_item_exist(MODULE_CLOSE_LAYER):
        dpg.add_viewport_drawlist(tag=MODULE_CLOSE_LAYER, front=True)
    if dpg.does_item_exist(INPUT_HANDLERS):
        return
    with dpg.handler_registry(tag=INPUT_HANDLERS):
        dpg.add_mouse_down_handler(
            button=dpg.mvMouseButton_Left,
            callback=_begin_knob_drag,
            user_data=(KNOB_INTERACTION, runtime),
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
        # The rack has always advertised these keys; now they are wired.
        for key, action in (
            (dpg.mvKey_Delete, _delete_rack_selection),
            (dpg.mvKey_Back, _delete_rack_selection),
            (dpg.mvKey_Escape, _dismiss_rack_focus),
            (dpg.mvKey_K, _open_module_selector_shortcut),
            (dpg.mvKey_F, _frame_rack),
            (dpg.mvKey_Z, _undo_or_redo_rack_edit),
        ):
            dpg.add_key_press_handler(
                key,
                callback=_press_once(key, action),
                user_data=runtime,
            )


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
    size = max(42, round(size * MODULE_KNOB_SCALE))
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
            default_value=value,
        ),
    )
    KNOB_INTERACTION.bindings[knob] = dpg.get_item_configuration(knob)["user_data"]
    with dpg.tooltip(knob) as tooltip:
        dpg.add_text("DRAG UP / DOWN", color=TEXT)
        dpg.add_text(
            "Slow for fine detail · Shift for finer · Double-click to reset",
            color=MUTED_TEXT,
        )
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


def _add_dynamic_float_control(
    module: object,
    field_info: object,
    value: float,
    field_path: tuple[str | int, ...],
    label: str,
) -> None:
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


def _add_dynamic_parameter_controls(
    module: object,
    parameters: BaseModel,
    path: tuple[str | int, ...] = (),
) -> None:
    pending_floats: list[
        tuple[object, float, tuple[str | int, ...], str]
    ] = []

    def flush_float_row() -> None:
        if not pending_floats:
            return
        with dpg.group(horizontal=True):
            for field_info, value, field_path, label in pending_floats:
                _add_dynamic_float_control(
                    module,
                    field_info,
                    value,
                    field_path,
                    label,
                )
        pending_floats.clear()

    for field_name, field_info in type(parameters).model_fields.items():
        value = getattr(parameters, field_name)
        field_path = (*path, field_name)
        label = field_name.replace("_", " ").title()
        if isinstance(value, float):
            pending_floats.append((field_info, value, field_path, label))
            if len(pending_floats) == 3:
                flush_float_row()
            continue

        flush_float_row()
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

    flush_float_row()


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
            summary = dpg.add_text(
                manifest.category.upper(),
                color=MODULE_ACCENTS[node],
            )
            with dpg.tooltip(summary):
                dpg.add_text(manifest.description, color=MUTED_TEXT, wrap=280)
            parameters = getattr(module, "parameters", None)
            if isinstance(parameters, BaseModel):
                _add_dynamic_parameter_controls(module, parameters)
            _add_patch_bay_toggle(patch, instance_id, node, port_ids)

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
                show=True,
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
                show=True,
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
            _add_patch_bay_toggle(patch, "mixer", MIXER_NODE, port_ids)
        for channel, gain in enumerate(mixer.parameters.gains, start=1):
            with dpg.node_attribute(
                tag=f"{MIXER_NODE}.input_{channel}",
                label=f"Input {channel}",
                attribute_type=dpg.mvNode_Attr_Input,
                show=True,
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
            show=True,
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
                show=True,
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
                show=True,
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
                show=True,
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
                show=True,
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
                show=True,
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


def _module_library_slug(label: str) -> str:
    """Return a stable Dear PyGui tag fragment for a library heading."""
    normalized = "".join(
        character.lower() if character.isalnum() else " "
        for character in label
    )
    return "_".join(normalized.split())


def _module_library_section_tag(section: str) -> str:
    return f"noodler.module_selector.section.{_module_library_slug(section)}"


def _module_library_category_tag(category: str) -> str:
    return f"noodler.module_selector.category.{_module_library_slug(category)}"


def _rack_outline_module_label(
    runtime: AppRuntime,
    instance_id: str,
    connection: str | None = None,
) -> str:
    module = runtime.patch.modules[instance_id]
    label = f"{module.manifest.name.upper()}  [{instance_id}]"
    return f"{label}  ·  {connection}" if connection else label


def _remove_module_from_outline(
    _sender: int | str,
    _app_data: object,
    selection: tuple[AppRuntime, str],
) -> None:
    runtime, instance_id = selection
    node = INSTANCE_NODE_TAGS.get(instance_id)
    if node is not None:
        _remove_module_node(node, runtime)


def _add_rack_outline_remove_button(
    parent: int | str,
    runtime: AppRuntime,
    instance_id: str,
) -> None:
    button = dpg.add_button(
        label="×",
        parent=parent,
        width=22,
        height=20,
        callback=_remove_module_from_outline,
        user_data=(runtime, instance_id),
    )
    with dpg.tooltip(button):
        dpg.add_text(f"Remove {runtime.patch.modules[instance_id].manifest.name}")


def _add_rack_outline_ports(
    parent: int | str,
    runtime: AppRuntime,
    instance_id: str,
) -> None:
    """List every module jack and whether the live graph currently uses it."""
    module = runtime.patch.modules[instance_id]
    connected = _connected_port_ids(runtime.patch, instance_id)
    ports_root = dpg.add_tree_node(
        label=f"PORTS  ·  {len(connected)}/{len(module.manifest.ports)} PATCHED",
        parent=parent,
        default_open=True,
    )
    for direction, heading in (
        (PortDirection.INPUT, "INPUTS"),
        (PortDirection.OUTPUT, "OUTPUTS"),
    ):
        ports = tuple(
            port
            for port in module.manifest.ports
            if port.direction is direction
        )
        if not ports:
            continue
        direction_root = dpg.add_tree_node(
            label=heading,
            parent=ports_root,
            default_open=True,
        )
        for port in ports:
            patched = port.id in connected
            state = "PATCHED" if patched else "OPEN"
            marker = "●" if patched else "○"
            port_text = dpg.add_text(
                f"{marker}  {port.name}  ·  "
                f"{port.signal_type.value.upper()}  ·  {state}",
                parent=direction_root,
                color=(
                    SIGNAL_COLORS[port.signal_type.value]
                    if patched
                    else MUTED_TEXT
                ),
            )
            if port.description:
                with dpg.tooltip(port_text):
                    dpg.add_text(port.description, wrap=280)


def _add_rack_outline_signal_branch(
    parent: int | str,
    runtime: AppRuntime,
    instance_id: str,
    connection: str,
    reachable: set[str],
    trail: frozenset[str] = frozenset(),
) -> None:
    """Draw one module and its upstream dependencies as a signal-flow tree."""
    reachable.add(instance_id)
    row = dpg.add_group(parent=parent, horizontal=True)
    branch = dpg.add_tree_node(
        label=_rack_outline_module_label(runtime, instance_id, connection),
        parent=row,
        default_open=False,
    )
    _add_rack_outline_remove_button(row, runtime, instance_id)
    _add_rack_outline_ports(branch, runtime, instance_id)
    if instance_id in trail:
        dpg.add_text("SHARED SIGNAL", parent=branch, color=MUTED_TEXT)
        return
    incoming = tuple(
        cable
        for cable in runtime.patch.cables
        if cable.target.module_id == instance_id
    )
    if not incoming:
        dpg.add_text("SOURCE / CONTROL ORIGIN", parent=branch, color=MUTED_TEXT)
        return
    next_trail = trail | {instance_id}
    upstream = dpg.add_tree_node(
        label="UPSTREAM",
        parent=branch,
        default_open=True,
    )
    for cable in incoming:
        _add_rack_outline_signal_branch(
            upstream,
            runtime,
            cable.source.module_id,
            f"{cable.source.port_id}  →  {cable.target.port_id}",
            reachable,
            next_trail,
        )


def _rack_outline_unpatched_modules(
    runtime: AppRuntime,
    reachable: set[str],
) -> dict[str, list[str]]:
    grouped = {
        "CONTROL / MODULATION": [],
        "AUDIO PATH": [],
    }
    registered: set[str] = set()
    for rail, heading in (
        (CONTROL_RAIL, "CONTROL / MODULATION"),
        (AUDIO_RAIL, "AUDIO PATH"),
    ):
        for node in RACK_RAILS[rail]:
            instance_id = _module_id_for_node(node)
            if (
                instance_id is not None
                and instance_id in runtime.patch.modules
                and instance_id not in reachable
            ):
                grouped[heading].append(instance_id)
                registered.add(instance_id)
    for instance_id in runtime.patch.modules:
        if instance_id not in reachable and instance_id not in registered:
            grouped["AUDIO PATH"].append(instance_id)
    return grouped


def _refresh_rack_outline(runtime: AppRuntime) -> None:
    """Rebuild the left outline from the real graph after a topology edit."""
    if not dpg.does_item_exist(RACK_OUTLINE_BODY):
        return
    dpg.delete_item(RACK_OUTLINE_BODY, children_only=True)
    reachable: set[str] = set()
    signal_flow = dpg.add_tree_node(
        label="SIGNAL FLOW",
        parent=RACK_OUTLINE_BODY,
        default_open=True,
    )
    system_output = dpg.add_tree_node(
        label="SYSTEM OUTPUT",
        parent=signal_flow,
        default_open=True,
    )
    if runtime.patch.output_taps:
        taps_by_module: dict[str, list[OutputTap]] = {}
        for tap in runtime.patch.output_taps:
            taps_by_module.setdefault(tap.source.module_id, []).append(tap)
        for instance_id, taps in taps_by_module.items():
            destinations = "  ·  ".join(
                f"{tap.source.port_id}  →  {tap.channel.value}"
                for tap in taps
            )
            _add_rack_outline_signal_branch(
                system_output,
                runtime,
                instance_id,
                destinations,
                reachable,
            )
    else:
        dpg.add_text(
            "NO SIGNAL CONNECTED",
            parent=system_output,
            color=MUTED_TEXT,
        )

    unpatched = _rack_outline_unpatched_modules(runtime, reachable)
    if any(unpatched.values()):
        unpatched_root = dpg.add_tree_node(
            label="UNPATCHED",
            parent=RACK_OUTLINE_BODY,
            default_open=True,
        )
        for heading, instance_ids in unpatched.items():
            if not instance_ids:
                continue
            lane = dpg.add_tree_node(
                label=heading,
                parent=unpatched_root,
                default_open=True,
            )
            for instance_id in instance_ids:
                row = dpg.add_group(parent=lane, horizontal=True)
                branch = dpg.add_tree_node(
                    label=_rack_outline_module_label(runtime, instance_id),
                    parent=row,
                    default_open=False,
                )
                _add_rack_outline_remove_button(row, runtime, instance_id)
                _add_rack_outline_ports(branch, runtime, instance_id)

    panels = len(runtime.patch.modules) + 1
    connections = len(runtime.patch.cables) + len(runtime.patch.output_taps)
    panel_noun = "PANEL" if panels == 1 else "PANELS"
    cable_noun = "CABLE" if connections == 1 else "CABLES"
    dpg.set_value(
        RACK_OUTLINE_STATUS,
        f"{panels} {panel_noun}  ·  {connections} {cable_noun}",
    )


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
        _bind_rack_node_font(node)
        _add_spine_texture(node, manifest.name.upper())
        _add_module_spine(node)
        _place_dynamic_node(node, rail)
        _reveal_node(node)
        _refresh_rack_outline(runtime)
        registration = _capture_node_registration(node, instance_id)
        _record_edit(
            f"ADD {manifest.name.upper()}",
            undo=lambda: _remove_module_node(node, runtime, record=False),
            redo=lambda: _restore_module_node(runtime, registration, module, ()),
            discard=lambda: _discard_retained_node(runtime, registration),
        )
        if (
            dpg.does_item_exist(MODULE_SELECTOR)
            and dpg.get_item_type(MODULE_SELECTOR).endswith("mvWindowAppItem")
        ):
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
    category_matches: dict[str, int] = {}
    for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
        haystack = " ".join(
            (manifest.id, manifest.name, manifest.category, manifest.description)
        ).lower()
        show = all(word in haystack for word in words)
        dpg.configure_item(_module_selector_button_tag(manifest.id), show=show)
        visible += int(show)
        category_matches[manifest.category] = (
            category_matches.get(manifest.category, 0) + int(show)
        )
    for section, categories in MODULE_LIBRARY_SECTIONS:
        section_visible = False
        for category in categories:
            category_visible = category_matches.get(category, 0) > 0
            section_visible = section_visible or category_visible
            category_tag = _module_library_category_tag(category)
            if dpg.does_item_exist(category_tag):
                dpg.configure_item(category_tag, show=category_visible)
                if words and category_visible:
                    dpg.set_value(category_tag, True)
        section_tag = _module_library_section_tag(section)
        if dpg.does_item_exist(section_tag):
            dpg.configure_item(section_tag, show=section_visible)
            if words and section_visible:
                dpg.set_value(section_tag, True)
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
    dpg.focus_item(MODULE_SELECTOR_SEARCH)


def _add_module_library_entry(
    runtime: AppRuntime,
    manifest: ModuleManifest,
) -> None:
    """Add one compact, descriptive module button to a browser surface."""
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


def _build_module_library(runtime: AppRuntime) -> None:
    """Build the live rack outline and module catalog beside the canvas."""
    manifests_by_category: dict[str, list[ModuleManifest]] = {}
    for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
        manifests_by_category.setdefault(manifest.category, []).append(manifest)

    with dpg.child_window(
        tag=MODULE_SELECTOR,
        width=330,
        height=-1,
        border=True,
    ):
        dpg.add_text("CURRENT RACK", color=SCALE_ACCENT)
        dpg.add_text(
            "1 PANEL  ·  0 CABLES",
            tag=RACK_OUTLINE_STATUS,
            color=MUTED_TEXT,
        )
        with dpg.child_window(
            tag=RACK_OUTLINE_BODY,
            height=220,
            border=False,
        ):
            pass
        _refresh_rack_outline(runtime)
        dpg.add_separator()
        dpg.add_text("MODULE LIBRARY", color=SCALE_ACCENT)
        dpg.add_text("ADD TO THE FREEFORM RACK", color=MUTED_TEXT)
        dpg.add_input_text(
            tag=MODULE_SELECTOR_SEARCH,
            hint="Search instruments, signals, effects…",
            callback=_filter_module_selector,
            width=-1,
        )
        dpg.add_text(
            f"{len(BUILTIN_PROVIDER_MANIFEST.modules)} MODULES",
            tag=MODULE_SELECTOR_STATUS,
            color=MUTED_TEXT,
        )
        dpg.add_separator()
        for section, categories in MODULE_LIBRARY_SECTIONS:
            with dpg.tree_node(
                tag=_module_library_section_tag(section),
                label=section,
                default_open=True,
            ):
                for category in categories:
                    manifests = manifests_by_category.get(category, ())
                    if not manifests:
                        continue
                    with dpg.tree_node(
                        tag=_module_library_category_tag(category),
                        label=category.upper(),
                        default_open=category
                        in {"Musical Brains", "Sources", "Oscillators"},
                    ):
                        for manifest in manifests:
                            _add_module_library_entry(runtime, manifest)


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
                _add_module_library_entry(runtime, manifest)
        dpg.add_button(
            label="CLOSE",
            callback=lambda _s, _a, _u: dpg.hide_item(MODULE_SELECTOR),
        )


def build_runtime_from_preset(preset: PatchPreset) -> AppRuntime:
    """Instantiate a validated patch document as a fresh executable graph."""
    patch = PatchGraph()
    provider = BuiltinProvider()
    for saved_module in preset.modules:
        if saved_module.provider != "builtin":
            raise ValueError(
                f"unsupported module provider: {saved_module.provider}"
            )
        module = provider.create(
            saved_module.module_type,
            saved_module.parameters,
        )
        patch.add_module(saved_module.instance_id, module)

    for cable in preset.cables:
        patch.connect(
            cable.source.module_id,
            cable.source.port_id,
            cable.target.module_id,
            cable.target.port_id,
        )
    for tap in preset.output_taps:
        patch.connect_output(
            tap.source.module_id,
            tap.source.port_id,
            gain=tap.gain,
            channel=tap.channel,
        )

    return AppRuntime(
        patch=patch,
        audio=SystemAudioEngine(
            patch,
            master_gain=preset.system_output.master_gain,
        ),
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
    starter_patch: bool = False,
) -> AppRuntime:
    """Create an empty rack or the optional generative starter instrument."""
    patch = PatchGraph()
    if not starter_patch:
        return AppRuntime(
            patch=patch,
            audio=SystemAudioEngine(patch, master_gain=0.8),
        )

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


def _build_empty_rack_ui(
    runtime: AppRuntime,
    *,
    patch_name: str = "Untitled Patch",
) -> AppRuntime:
    """Build the library rack around one permanent output module."""
    module_count = len(runtime.patch.modules)
    connection_count = len(runtime.patch.cables) + len(runtime.patch.output_taps)
    rack_summary = (
        "EMPTY RACK  ·  ADD A MODULE TO BEGIN"
        if module_count == 0
        else f"{module_count} MODULES  ·  {connection_count} CABLES"
    )
    with dpg.window(tag=PRIMARY_WINDOW, label="Noodler"):
        with dpg.group(horizontal=True):
            dpg.add_text(patch_name.upper(), color=SCALE_ACCENT)
            dpg.add_text(rack_summary, color=TEXT)
            dpg.add_spacer(width=24)
            dpg.add_text("CV", color=SIGNAL_COLORS["cv"])
            dpg.add_text("AUDIO", color=SIGNAL_COLORS["audio"])
            _add_rack_controls(runtime)
        with dpg.group(horizontal=True):
            dpg.add_text("AUDIO RAIL", color=SIGNAL_COLORS["audio"])
            dpg.add_text("BUILD LEFT TO RIGHT  →  SYSTEM OUT", color=TEXT)
        dpg.add_separator()
        with dpg.child_window(
            tag=RACK_WORKSPACE,
            height=-38,
            border=False,
        ):
            with dpg.group(horizontal=True):
                _build_module_library(runtime)
                with dpg.node_editor(
                    tag=RACK,
                    callback=_patch_link_created,
                    delink_callback=_patch_link_deleted,
                    user_data=runtime,
                    width=-1,
                    height=-1,
                    minimap=True,
                    minimap_location=dpg.mvNodeMiniMap_Location_BottomRight,
                ):
                    _build_output_node(runtime.audio)
                    _add_module_spines(runtime)
        dpg.add_separator()
        dpg.add_text(
            (
                "ADD A MODULE TO BEGIN  ·  DRAG BACKGROUND = PAN  ·  "
                "PINCH / SCROLL = ZOOM"
                if module_count == 0
                else f"LOADED  {patch_name.upper()}  ·  DRAG BACKGROUND = PAN  ·  "
                "PINCH / SCROLL = ZOOM"
            ),
            tag=CONTROL_STATUS,
            color=MUTED_TEXT,
        )
        dpg.bind_item_theme(OUTPUT_NODE, OUTPUT_THEME)
        dpg.set_item_pos(OUTPUT_NODE, [900, 250])
        CANVAS_INTERACTION.rail_y.update(
            {
                CONTROL_RAIL: 40.0,
                AUDIO_RAIL: 250.0,
            }
        )
    with dpg.file_dialog(
        tag=SAVE_PATCH_DIALOG,
        label="Save Noodler Patch",
        show=False,
        modal=True,
        width=720,
        height=460,
        default_filename=f"{Path(patch_name).name}.noodler",
        callback=_save_patch_dialog,
        user_data=runtime,
    ):
        dpg.add_file_extension(".noodler", color=SCALE_ACCENT)
        dpg.add_file_extension(".*")
    _configure_rack_theme()
    _configure_knob_handlers(runtime)
    return runtime


def _mount_preset_ui(runtime: AppRuntime, preset: PatchPreset) -> None:
    """Build panels, cables, and camera state for an instantiated document."""
    saved_nodes = {node.node_id: node for node in preset.view.nodes}
    CANVAS_INTERACTION.rail_y.update(preset.view.rails)

    for saved_module in preset.modules:
        module = runtime.patch.modules[saved_module.instance_id]
        manifest = module.manifest
        node, rail, theme = _register_dynamic_node(
            saved_module.instance_id,
            saved_module.module_type,
            manifest.category,
        )
        _build_generic_module_node(
            saved_module.instance_id,
            module,
            runtime.patch,
        )
        dpg.bind_item_theme(node, theme)
        _add_spine_texture(node, manifest.name.upper())
        _add_module_spine(node)
        saved_node = saved_nodes.get(saved_module.instance_id)
        if saved_node is None:
            _place_dynamic_node(node, rail)
        else:
            dpg.set_item_pos(
                node,
                [saved_node.position.x, saved_node.position.y],
            )

    output_view = saved_nodes.get("system_output")
    if output_view is not None:
        dpg.set_item_pos(
            OUTPUT_NODE,
            [output_view.position.x, output_view.position.y],
        )

    zoom = min(
        MAX_RACK_ZOOM,
        max(MIN_RACK_ZOOM, float(preset.view.zoom)),
    )
    CANVAS_INTERACTION.zoom = zoom
    CANVAS_INTERACTION.zoom_target = zoom
    CANVAS_INTERACTION.zoom_spring.snap(zoom)
    for node in RACK_NODES:
        _bind_rack_node_font(node, zoom)
    for knob, binding in KNOB_INTERACTION.bindings.items():
        if dpg.does_item_exist(knob):
            dpg.configure_item(
                knob,
                width=max(30, round(binding.size * zoom)),
            )
    dpg.configure_item(ZOOM_RESET_BUTTON, label=f"{zoom:.0%}")

    for cable in runtime.patch.cables:
        source = _endpoint_attribute(cable.source)
        target = _endpoint_attribute(cable.target)
        if source is not None and target is not None:
            _add_visual_link(
                source,
                target,
                cable,
                _endpoint_signal(runtime.patch, cable.source),
            )
    for tap in runtime.patch.output_taps:
        source = _endpoint_attribute(tap.source)
        if source is not None:
            _add_visual_link(
                source,
                _output_channel_attribute(tap.channel),
                tap,
                _endpoint_signal(runtime.patch, tap.source),
            )

    for node_id, saved_node in saved_nodes.items():
        node = VIEW_NODE_TAGS.get(node_id)
        if node is not None and saved_node.collapsed:
            _set_module_collapsed(node, True, runtime)

    _refresh_patch_bays(runtime.patch)
    _refresh_rack_outline(runtime)
    _set_patch_status(f"LOADED PATCH  ·  {preset.name.upper()}")


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
    starter_patch: bool = False,
    preset: PatchPreset | None = None,
) -> AppRuntime:
    """Build the initial rack and return its live application runtime."""
    if starter_patch and preset is not None:
        raise ValueError("choose either a starter patch or a patch document")
    _reset_rack_registry(starter_patch=starter_patch and preset is None)
    KNOB_INTERACTION.reset()
    CANVAS_INTERACTION.reset()
    MODULE_COLLAPSE.reset()
    dpg.set_global_font_scale(1.0)
    PATCH_BAYS.clear()
    RAIL_SPRINGS.clear()
    METER_BALLISTICS.reset()
    RACK_HISTORY.clear()
    KEY_LATCH.clear()
    _configure_font()
    _configure_theme()
    runtime = (
        build_runtime_from_preset(preset)
        if preset is not None
        else build_runtime(
            vco,
            mixer,
            utility,
            wogglebug,
            scale_generator,
            low_pass_gate,
            reverb,
            mixer_channels=mixer_channels,
            starter_patch=starter_patch,
        )
    )
    _configure_spine_textures(runtime)
    if preset is not None:
        _build_empty_rack_ui(runtime, patch_name=preset.name)
        _mount_preset_ui(runtime, preset)
        return runtime
    if not starter_patch:
        return _build_empty_rack_ui(runtime)
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
            _add_rack_controls(runtime)
        with dpg.group(horizontal=True):
            dpg.add_text("AUDIO RAIL", color=SIGNAL_COLORS["audio"])
            dpg.add_text(
                "COMPLEX VCO  →  POLARIZING MIX  →  BLOOM  →  SPACE  →  OUT",
                color=TEXT,
            )
        dpg.add_separator()
        with dpg.child_window(
            tag=RACK_WORKSPACE,
            height=-38,
            border=False,
        ), dpg.node_editor(
            tag=RACK,
            callback=_patch_link_created,
            delink_callback=_patch_link_deleted,
            user_data=runtime,
            width=-1,
            height=-1,
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
        dpg.add_separator()
        dpg.add_text(
            DEFAULT_CONTROL_STATUS,
            tag=CONTROL_STATUS,
            color=MUTED_TEXT,
        )
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
    _configure_rack_theme()
    _configure_knob_handlers(runtime)
    return runtime


def _parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="noodler",
        description="Open the Noodler rack or a .noodler patch document.",
    )
    parser.add_argument(
        "patch",
        nargs="?",
        type=Path,
        help="patch document to open",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the Noodler desktop application, optionally opening a patch."""
    args = _parse_cli_args(argv)
    preset: PatchPreset | None = None
    if args.patch is not None:
        try:
            preset = read_patch_preset(args.patch)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"noodler: could not open {args.patch}: {exc}") from exc

    runtime: AppRuntime | None = None
    gesture_monitor = MacMagnifyMonitor(_capture_macos_magnification)
    dpg.create_context()
    try:
        dpg.create_viewport(
            title=(
                f"Noodler — {preset.name}"
                if preset is not None
                else "Noodler"
            ),
            width=1280,
            height=800,
            min_width=900,
            min_height=600,
        )
        runtime = build_ui(preset=preset)
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
