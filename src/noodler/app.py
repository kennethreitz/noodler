"""Noodler's application entry point."""

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import math
import sys
import threading
import time
import typing
from pathlib import Path

import dearpygui.dearpygui as dpg
import numpy as np
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
    MASTER_CHANNELS,
    MasterMixer,
    RETURN_PORTS,
    SENDS,
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
from .desktop import default_window, name_the_process, visible_screen
from .macos_gestures import MacCursor, MacMagnifyMonitor, MacScrollMonitor
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
    TransportPreset,
    capture_patch_preset,
    read_patch_preset,
    write_patch_preset,
)
from .transport import (
    BEAT_UNITS,
    CHOICES as CLOCK_CHOICES,
    FREE,
    MAX_BEATS_PER_BAR,
    MAX_BPM,
    MIN_BPM,
    Transport,
    clock_kind,
    is_rate_field,
)


PRIMARY_WINDOW = "noodler.primary_window"
RACK = "noodler.rack"
VCO_NODE = "noodler.complex_vco"
MIXER_NODE = "noodler.polarizing_mixer"
FUNCTION_NODE = "noodler.function_utility"
OUTPUT_NODE = "noodler.system_output"
MASTER_ID = "master"
"""The instance every rack has. It is a module like any other -- real channels,
real levels, real DSP -- and the only things special about it are that it is
always present and that its bus reaches the speakers without being asked."""

CONSOLE_PREFIX = "noodler.console."
"""Every strip, fader, meter and knob of the console carries this prefix, which
is how the zoom knows to leave them alone."""

CONSOLE_STRIP = CONSOLE_PREFIX + "strip_{channel}"
CONSOLE_MARGIN = 14.0
"""The gap between the console and the bottom-left corner of the canvas."""
CONSOLE_GAP = 4.0
"""Between one strip and the next."""

LEVEL_DIAL_SIZE = 32
LEVEL_DIAL_INSET = 4.0
STRIP_KNOB_SIZE = 20
"""Pan and the sends on a strip: a little smaller than a module's knobs."""
"""A strip's level is a dial, and its meter is a ring drawn around that dial in
the margin the inset leaves -- so the meter costs no space at all."""

CONSOLE_LEVEL = CONSOLE_PREFIX + "level_{channel}"
CONSOLE_METER = CONSOLE_PREFIX + "meter_{channel}"
CONSOLE_READOUT = CONSOLE_PREFIX + "readout_{channel}"
CONSOLE_MASTER_LEVEL = CONSOLE_PREFIX + "master_level"
CONSOLE_MASTER_METER = CONSOLE_PREFIX + "master_meter"
CONSOLE_MASTER_READOUT = CONSOLE_PREFIX + "master_readout"
CONSOLE_THEME = "noodler.theme.console"
CONSOLE_STRIP_THEME = "noodler.theme.console_strip"
STRIP_JACK_INSET = 0.0
RETURN_JACK_INSET = 0.0
CONSOLE_RETURN_THEME = "noodler.theme.console_return"
CONSOLE_POST = CONSOLE_PREFIX + "post_{name}"
JACK_POST_THEME = "noodler.theme.jack_post"
JACK_POST_LIFT = 30.0
"""How far above a strip's top its jack posts stand.

The pin lands about fourteen pixels below a post's top, so this puts it just
above the strip's edge -- touching it, not on it. That matters: clicking a
node brings it to the front, and a pin drawn over the strip would go under
the strip the moment the strip was clicked. Nothing can cover what stands
above the top edge."""
POST_ANCHORS: dict[str, tuple[str, float]] = {}
POST_TEXTS: dict[str, int | str] = {}
"""Each post's one text item, whose centre is where its pin is drawn."""
CONSOLE_CABLES = "noodler.console_cables"
CONSOLE_CABLE_ITEMS: dict[int | str, int | str] = {}
"""Drawn console cables, by the link they stand in for."""
CONSOLE_LINK_HIDDEN_THEME = "noodler.theme.link.console_hidden"
CONSOLE_CABLE_HOVER_PX = 7.0
"""Each jack post and where it stands: which strip, and how far across it.

A jack post is a node that is nothing but a pin. Dear PyGui draws a pin on a
node's left edge and nowhere else, and offsets set on a node's theme are read
after the node's styles are gone, so the only way to put a jack at the top
centre of a strip is to stand a separate, invisible node there whose left edge
is the strip's middle. The cable lands on the post; the strip has no jack of
its own."""
"""How far a strip's jack is pulled in from its edge, to sit at the top centre.

Dear PyGui draws a pin on a node's left or right edge, and nowhere else. But
imnodes lets a pin be offset from that edge, and pulled in by half a strip's
width the input jack sits at the top of the strip, in the middle, where a
cable expects to land -- as on a desk, where the input is at the top of the
channel and not on its side."""
CONSOLE_MUTE = CONSOLE_PREFIX + "mute_{channel}"
CONSOLE_SOLO = CONSOLE_PREFIX + "solo_{channel}"
CONSOLE_RETURN = CONSOLE_PREFIX + "return_{bus}"
CONSOLE_RETURN_LEVEL = CONSOLE_PREFIX + "return_level_{bus}"
CONSOLE_RETURN_READOUT = CONSOLE_PREFIX + "return_readout_{bus}"
CONSOLE_RETURN_MUTE = CONSOLE_PREFIX + "return_mute_{bus}"
TOGGLE_OFF_THEME = "noodler.theme.toggle_off"
MUTE_ON_THEME = "noodler.theme.mute_on"
SOLO_ON_THEME = "noodler.theme.solo_on"

PINNED_NODES: list[int | str] = []
"""Nodes the camera does not carry: the console strips, left to right.

The rack pans and zooms underneath them; they stay along the bottom edge of
the canvas, in this order, so there is always somewhere to drag a cable to.
"""
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
VIEW_NODE_TAGS = {**INSTANCE_NODE_TAGS}
CONTROL_RAIL = "control"
AUDIO_RAIL = "audio"
RACK_RAILS = {
    CONTROL_RAIL: [FUNCTION_NODE, WOGGLE_NODE, SCALE_NODE],
    AUDIO_RAIL: [VCO_NODE, MIXER_NODE, LPG_NODE, REVERB_NODE],
}
RACK_RAIL_GAP = 48.0
AUDIO_STATUS = "noodler.audio_status"
CONTROL_STATUS = "noodler.control_status"
RACK_WORKSPACE = "noodler.rack_workspace"
UNPLUG_ALL_BUTTON = "noodler.unplug_all"
SAVE_PATCH_BUTTON = "noodler.save_patch"
FRAME_RACK_MENU_ITEM = "noodler.frame_rack.menu"
RACK_MENU_BAR = "noodler.menu_bar"
RACK_OUTLINE_HEIGHT = 220
LIBRARY_HEADER_ROOM = 36
TIDY_RACK_BUTTON = "noodler.tidy_rack"
SAVE_PATCH_DIALOG = "noodler.save_patch_dialog"
OPEN_PATCH_DIALOG = "noodler.open_patch_dialog"
NEW_PATCH_MENU_ITEM = "noodler.menu.new_patch"
EXPORT_MENU = "noodler.menu.export"
EXPORT_DIALOG = "noodler.export_dialog"
EXPORT_BAR_CHOICES = (4, 8, 16, 32)
EXPORT_TAIL_SECONDS = 3.0
EXPORT_BARS: list[int] = [8]
EXPORT_MESSAGES: list[tuple[str, bool]] = []
"""Progress from the bounce thread, shown by the frame loop, in order."""
EXAMPLES_MENU = "noodler.menu.examples"
OPEN_PATCH_MENU_ITEM = "noodler.menu.open"
SAVE_PATCH_MENU_ITEM = "noodler.menu.save"
SAVE_AS_MENU_ITEM = "noodler.menu.save_as"
EXIT_MENU_ITEM = "noodler.menu.exit"
ADD_MODULE_BUTTON = "noodler.add_module"
MODULE_SELECTOR = "noodler.module_selector"
MODULE_SELECTOR_SEARCH = "noodler.module_selector.search"
MODULE_SELECTOR_STATUS = "noodler.module_selector.status"
RACK_OUTLINE_BODY = "noodler.rack_outline.body"
RACK_OUTLINE_STATUS = "noodler.rack_outline.status"
RACK_SUMMARY = "noodler.rack_summary"
CLOCK_READOUT = "noodler.clock.readout"
CLOCK_REWIND_ITEM = "noodler.clock.rewind"
CLOCK_BPM_INPUT = "noodler.clock.bpm"
CLOCK_RUN_ITEM = "noodler.clock.run"
CLOCK_BEATS_INPUT = "noodler.clock.beats"
CLOCK_UNIT_INPUT = "noodler.clock.unit"
CLOCK_SPACER = "noodler.clock.spacer"
CLOCK_MARGIN = 18.0
MODULE_LIBRARY_HEADER = "noodler.module_library.header"
LIBRARY_PANE_BUTTON = "noodler.library_pane"
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
OUTPUT_SCOPE = "noodler.output_scope"
BAR_SCOPE = "noodler.bar_scope"
BAR_SCOPE_TRACE = "noodler.bar_scope.trace"
BAR_SCOPE_WIDTH = 220
BAR_SCOPE_HEIGHT = 22
OUTPUT_SCOPE_TRACE = "noodler.output_scope.trace"
SCOPE_WIDTH = 172
SCOPE_HEIGHT = 54
SCOPE_POINTS_DRAWN = 172
"""One point per pixel: any more is detail the trace cannot show."""
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
METER_QUIET = (98, 168, 112, 255)
METER_HOT = (214, 164, 72, 255)
METER_CLIP = OUTPUT_ACCENT
"""Green, amber, red: the three things a meter has ever needed to say."""
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
    "DRAG JACKS TO PATCH  ·  DOUBLE-CLICK A CABLE TO UNPATCH  ·  "
    "⌘K ADD MODULE  ·  ⌘Z UNDO"
)
"""What the status line says when it has nothing to report.

It listed eleven gestures because eleven gestures existed, which made it a
reference card that ran off the edge of the window. Actions and the keys
that reach them belong in the menu; this line is for what just happened,
and for the two gestures that have nowhere else to be discovered.
"""





KNOB_COLUMN_CHARS = 8
"""Width of one control column, in characters of the rack's monospace font.

Panels are laid out in a monospace face, so a fixed character count is a fixed
pixel width: padding a label and its readout to the same count is what makes
columns line up under one another instead of running together. Kept narrow
because a rack is read by scanning across it, and a panel that will not fit
beside its neighbour is a panel nobody can see in context.
"""

KNOB_SIZE_MINIMUM = 12
"""Smallest a rotary control is allowed to be drawn."""

KNOB_SIZE = 24
"""Diameter of a rotary control. Small enough to read a panel at a glance,
big enough to be a target.

Drawn by hand, because Dear PyGui's knob is forty pixels whatever it is asked:
its width, its height and its font all change nothing about the picture. Every
"knobs are too big" fix before this one changed a number that was never read.
"""

KNOB_SIZE_LARGE = 30
"""For the one control on a panel that deserves the eye first."""

KNOB_SWEEP_START = 0.75 * math.pi
KNOB_SWEEP_END = 2.25 * math.pi
"""A knob turns through 270 degrees, from seven o'clock round to five."""

KNOB_TRACK = (58, 56, 50, 255)
KNOB_BODY = (34, 35, 32, 255)
KNOB_ARC = SCALE_ACCENT

UNIT_SUFFIXES = (
    ("_hz", " Hz"),
    ("_seconds", " s"),
    ("_ms", " ms"),
    ("_cents", " ct"),
    ("_db", " dB"),
)
"""Field-name endings that name a unit, which belongs on the value."""

LABEL_ABBREVIATIONS = {"frequency": "freq", "modulation": "mod"}

MIN_RACK_ZOOM = 0.55
MAX_RACK_ZOOM = 1.65
RACK_ZOOM_STEP = 1.12
FRAME_MARGIN = 56.0
"""Breathing room left around the rack when the camera frames it."""
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
    size: int = KNOB_SIZE
    default_value: float | None = None
    """The value the module was built with, restored by double-clicking."""
    inset: float = 0.0
    """Margin left around the dial, for something else to be drawn in."""


@dataclass(slots=True)
class KnobArt:
    """The drawn parts of one knob, kept so a change can repaint just them."""

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
    """Where the knob was when the drag began, so the whole turn is one edit."""
    """Where each knob is, in its own units. The picture has no value of its own."""
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


KNOB_INTERACTION = KnobInteraction()


@dataclass(slots=True)
class CanvasInteraction:
    """Pan and zoom state for the rack camera."""

    panning: bool = False
    pan_candidate: bool = False
    pan_moved: bool = False
    """Whether the current pan has actually moved the rack yet."""
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
    """The current press has been looked at once; the held-button repeats of
    the mouse-down callback are not fresh presses."""
    drag_classified: bool = False
    drag_pans: bool = False
    pending_reveal: bool = True
    reveal_attempts: int = 0
    """The rack has not been put in front of the user yet."""
    marquee_origin: tuple[float, float] | None = None
    """Where a shift-drag began, while it lasts: the marquee is drawn from here."""
    """A press already answered by a one-shot control, held until release."""
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
        """Forget how the current press was classified, once it has ended."""
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


CANVAS_INTERACTION = CanvasInteraction()

TIDY_TARGETS: dict[int | str, tuple[float, float]] = {}
"""Where TIDY asked each module to go, until it gets there or is dragged."""

RAIL_SPRINGS: dict[int | str, tuple[Spring, Spring]] = {}
"""One critically damped spring pair per rack node, in rack coordinates."""

METER_BALLISTICS = MeterBallistics()

CURRENT_PATCH_PATH: list[Path] = []
"""Where this patch was last saved or opened from, if anywhere."""

PENDING_OPEN: list[PatchPreset] = []
"""A document waiting to replace the rack at the start of the next frame."""


PATCH_NAME: list[str] = ["Untitled Patch"]
SAVED_REVISION: list[int] = [0]
"""The history revision at the last save; anything else is unsaved work."""


RECENT_FILE = Path.home() / ".noodler" / "recent.json"
RECENT_LIMIT = 8
RECENT_MENU = "noodler.menu.recent"


def _recent_documents() -> list[Path]:
    """The last few patches opened or saved, most recent first, that still exist."""
    try:
        import json

        listed = json.loads(RECENT_FILE.read_text())
    except (OSError, ValueError):
        return []
    found: list[Path] = []
    for entry in listed if isinstance(listed, list) else []:
        try:
            path = Path(str(entry))
        except (TypeError, ValueError):
            continue
        if path.is_file() and path not in found:
            found.append(path)
    return found[:RECENT_LIMIT]


def _remember_recent(path: Path) -> None:
    """Put a document at the top of the recent list, on disk."""
    try:
        import json

        recent = [path.resolve()] + [p for p in _recent_documents() if p != path.resolve()]
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECENT_FILE.write_text(json.dumps([str(p) for p in recent[:RECENT_LIMIT]], indent=2))
    except OSError:
        return
    _refresh_recent_menu()


def _refresh_recent_menu() -> None:
    """Rebuild the Open Recent submenu from the list on disk."""
    if not dpg.does_item_exist(RECENT_MENU):
        return
    dpg.delete_item(RECENT_MENU, children_only=True)
    recent = _recent_documents()
    if not recent:
        dpg.add_menu_item(label="(nothing yet)", parent=RECENT_MENU, enabled=False)
        return
    for document in recent:
        dpg.add_menu_item(
            label=document.stem,
            parent=RECENT_MENU,
            callback=_open_recent,
            user_data=document,
        )


def _open_recent(_sender: int | str, _app_data: object, document: Path) -> None:
    def open_it() -> None:
        try:
            preset = read_patch_preset(document)
        except (OSError, TypeError, ValueError) as error:
            _set_patch_status(f"COULD NOT OPEN: {error}", error=True)
            return
        _remember_patch_path(document)
        PENDING_OPEN[:] = [preset]
        _set_patch_status(f"OPENING  ·  {preset.name}")

    _guard_unsaved(open_it, "Open another patch")


def _remember_patch_path(path: Path) -> None:
    CURRENT_PATCH_PATH[:] = [path]
    _remember_recent(path)


def _mark_saved(name: str | None = None) -> None:
    if name:
        PATCH_NAME[:] = [name]
    SAVED_REVISION[:] = [RACK_HISTORY.revision]
    _refresh_window_title()


def _has_unsaved_changes() -> bool:
    return RACK_HISTORY.revision != SAVED_REVISION[0]


LAST_TITLE: list[str] = [""]


def _refresh_window_title_if_changed() -> None:
    marker = "  •" if _has_unsaved_changes() else ""
    title = f"Noodler — {PATCH_NAME[0]}{marker}"
    if LAST_TITLE[0] != title:
        LAST_TITLE[0] = title
        _refresh_window_title()


def _refresh_window_title() -> None:
    """The title bar names the patch and, with a dot, whether it is saved."""
    marker = "  •" if _has_unsaved_changes() else ""
    title = f"Noodler — {PATCH_NAME[0]}{marker}"
    try:
        dpg.set_viewport_title(title)
    except Exception:
        # No viewport yet, or none at all in a test: nothing to title.
        return


def _save_patch_to(runtime: AppRuntime, destination: Path) -> None:
    """Write the instrument to a path, and remember where that was."""
    name = destination.stem or "Untitled Patch"
    written = write_patch_preset(_capture_current_preset(runtime, name), destination)
    _remember_patch_path(written)
    _mark_saved(name)
    _set_patch_status(f"SAVED  ·  {written.name}")


def _save_patch(
    _sender: int | str = 0,
    _app_data: object = None,
    runtime: AppRuntime | None = None,
) -> None:
    """Save over the file this patch came from, or ask where to put it."""
    if runtime is None:
        return
    if not CURRENT_PATCH_PATH:
        _show_save_patch_dialog(0, None, runtime)
        return
    try:
        _save_patch_to(runtime, CURRENT_PATCH_PATH[0])
    except (OSError, TypeError, ValueError) as error:
        _set_patch_status(f"SAVE ERROR: {error}", error=True)


UNSAVED_DIALOG = "noodler.dialog.unsaved"
UNSAVED_DIALOG_TEXT = "noodler.dialog.unsaved.text"
PENDING_ACTION: list[Callable[[], None]] = []
"""What was about to happen when the unsaved-changes question interrupted it."""


def _guard_unsaved(action: Callable[[], None], verb: str) -> None:
    """Do something that would lose unsaved work -- after asking, if it would.

    Quit, New and Open all throw the rack away. With nothing unsaved they just
    happen; otherwise a small question stands in the way: save, don't save, or
    cancel. Save with a known path writes and carries on; without one it opens
    the save dialog and leaves the action for afterwards.
    """
    if not _has_unsaved_changes():
        action()
        return
    PENDING_ACTION[:] = [action]
    if not dpg.does_item_exist(UNSAVED_DIALOG):
        with dpg.window(
            tag=UNSAVED_DIALOG,
            label="Unsaved changes",
            modal=True,
            no_resize=True,
            no_collapse=True,
            no_move=False,
            width=420,
            height=130,
            show=False,
        ):
            dpg.add_text("", tag=UNSAVED_DIALOG_TEXT, wrap=390)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", width=110, callback=_unsaved_save)
                dpg.add_button(label="Don't Save", width=110, callback=_unsaved_discard)
                dpg.add_button(label="Cancel", width=110, callback=_unsaved_cancel)
    dpg.set_value(
        UNSAVED_DIALOG_TEXT,
        f"{PATCH_NAME[0]} has changes that are not saved. {verb} anyway?",
    )
    try:
        width = dpg.get_viewport_client_width()
        height = dpg.get_viewport_client_height()
        dpg.configure_item(
            UNSAVED_DIALOG, pos=[max(0, width // 2 - 210), max(0, height // 2 - 80)]
        )
    except Exception:
        pass  # no viewport in a test: the window opens where it opens
    dpg.show_item(UNSAVED_DIALOG)


def _unsaved_cancel(*_args: object) -> None:
    PENDING_ACTION.clear()
    if dpg.does_item_exist(UNSAVED_DIALOG):
        dpg.hide_item(UNSAVED_DIALOG)
    _set_patch_status("KEPT WORKING")


def _unsaved_discard(*_args: object) -> None:
    if dpg.does_item_exist(UNSAVED_DIALOG):
        dpg.hide_item(UNSAVED_DIALOG)
    action = PENDING_ACTION.pop() if PENDING_ACTION else None
    PENDING_ACTION.clear()
    # The work is being let go of on purpose: it is not unsaved any more.
    _mark_saved()
    if action is not None:
        action()


def _unsaved_save(*_args: object) -> None:
    if dpg.does_item_exist(UNSAVED_DIALOG):
        dpg.hide_item(UNSAVED_DIALOG)
    runtime = ACTIVE_RUNTIME[0] if ACTIVE_RUNTIME else None
    if runtime is None:
        return
    if not CURRENT_PATCH_PATH:
        PENDING_ACTION.clear()
        _set_patch_status("SAVE IT FIRST  ·  THEN TRY AGAIN")
        _show_save_patch_dialog(0, None, runtime)
        return
    try:
        _save_patch_to(runtime, CURRENT_PATCH_PATH[0])
    except (OSError, TypeError, ValueError) as error:
        PENDING_ACTION.clear()
        _set_patch_status(f"SAVE ERROR: {error}", error=True)
        return
    action = PENDING_ACTION.pop() if PENDING_ACTION else None
    PENDING_ACTION.clear()
    if action is not None:
        action()


def _exit_noodler(
    _sender: int | str = 0,
    _app_data: object = None,
    _user_data: object = None,
) -> None:
    """Leave. The audio device is closed on the way out by main's finally."""
    if _keyboard_is_captured():
        return
    _guard_unsaved(_leave, "Quit")


def _leave() -> None:
    _set_patch_status("CLOSING")
    dpg.stop_dearpygui()


def _show_open_patch_dialog(
    _sender: int | str = 0,
    _app_data: object = None,
    _user_data: object = None,
) -> None:
    def show() -> None:
        if dpg.does_item_exist(OPEN_PATCH_DIALOG):
            dpg.show_item(OPEN_PATCH_DIALOG)

    _guard_unsaved(show, "Open another patch")


def _open_patch_dialog(
    _sender: int | str,
    app_data: object,
    _runtime: object = None,
) -> None:
    """Read a document, and queue it to replace the rack next frame.

    The rack is rebuilt from the frame callback rather than from here: taking
    the window apart while Dear PyGui is in the middle of dispatching to it is
    how a file dialog turns into a crash.
    """
    try:
        if not isinstance(app_data, dict):
            raise ValueError("the file dialog did not return a document")
        selected = app_data.get("file_path_name")
        if not isinstance(selected, str) or not selected:
            raise ValueError("choose a patch to open")
        preset = read_patch_preset(selected)
        _remember_patch_path(Path(selected))
        PENDING_OPEN[:] = [preset]
        _set_patch_status(f"OPENING  ·  {preset.name}")
    except (OSError, TypeError, ValueError) as error:
        _set_patch_status(f"COULD NOT OPEN: {error}", error=True)


def _new_patch(_sender: int | str = 0, _app_data: object = None, _u: object = None) -> None:
    """Queue an empty rack -- just the master -- to replace this one next frame.

    Rebuilt from the frame callback like an opened document, and for the same
    reason: taking the window apart mid-dispatch is how a menu turns into a
    crash. Save no longer knows a path, so it will ask.
    """
    _guard_unsaved(_new_patch_now, "Start a new rack")


def _new_patch_now() -> None:
    CURRENT_PATCH_PATH.clear()
    PENDING_OPEN[:] = [default_rack_preset()]
    PARK_EFFECTS[:] = [True]
    _set_patch_status("NEW RACK")


PARK_EFFECTS: list[bool] = []
"""Set when the default rack is built: park its two effects above the effect
strips once the console has settled, wherever the window put the console."""
PARK_LIFT = 130.0
"""Room left between the parked effects and the console for the cables."""


def _park_default_effects() -> None:
    """Stand the default rack's delay and room above FX A and FX B.

    The console is pinned to the bottom of whatever window this is, so the two
    effects that hang off it cannot have positions in the document; they are
    placed here, once, after the strips have settled: the room's right edge a
    little past FX B's, the delay a gap to its left, both a cable's height
    above the strips, both collapsed to their names and jacks.
    """
    if not PARK_EFFECTS:
        return
    delay = INSTANCE_NODE_TAGS.get("delay")
    room = INSTANCE_NODE_TAGS.get("reverb")
    fx_a = CONSOLE_RETURN.format(bus="a")
    fx_b = CONSOLE_RETURN.format(bus="b")
    if not all(dpg.does_item_exist(item) for item in (delay, room, fx_a, fx_b) if item is not None):
        return
    if delay is None or room is None:
        PARK_EFFECTS.clear()
        return
    # Not before the console has settled. On the first frame the rack measures
    # a few pixels, _settle_console leaves the strips where they were built --
    # at the origin -- and parking against those put the effects a screen
    # above and to the left of where the strips went next.
    if not dpg.does_item_exist(RACK):
        return
    view_width, view_height = (float(v) for v in dpg.get_item_rect_size(RACK))
    if view_width < MIN_REVEAL_VIEWPORT or view_height < MIN_REVEAL_VIEWPORT:
        return
    try:
        strip_x, strip_y = (float(v) for v in dpg.get_item_pos(fx_b))
        strip_w = float(dpg.get_item_rect_size(fx_b)[0])
        room_w, room_h = (float(v) for v in dpg.get_item_rect_size(room))
        delay_w, delay_h = (float(v) for v in dpg.get_item_rect_size(delay))
    except (KeyError, SystemError):
        return
    if strip_w <= 1.0 or room_w <= 1.0 or delay_w <= 1.0:
        return
    if strip_y <= CONSOLE_MARGIN:
        return  # still where it was built; the row has not been laid yet
    room_x = strip_x + strip_w + 40.0 - room_w
    room_y = strip_y - PARK_LIFT - room_h
    delay_x = room_x - delay_w - 44.0
    delay_y = strip_y - PARK_LIFT + 16.0 - delay_h
    dpg.set_item_pos(room, [room_x, room_y])
    dpg.set_item_pos(delay, [delay_x, delay_y])
    CANVAS_INTERACTION.pending_reveal = False
    PARK_EFFECTS.clear()


def default_rack_preset() -> PatchPreset:
    """The rack a new document opens as: the console, a delay on send A and a
    room on send B, both already returning.

    A desk comes with its effects patched, so that turning a strip's A up is
    all it takes to hear an echo, and B a room. Both effects run fully wet, as
    an effect on a send should. Everything else is left to the patch.
    """
    provider = BuiltinProvider()
    patch = PatchGraph()
    master = ensure_master(patch)
    echo = provider.create("echo_delay", {"time_seconds": 0.375, "feedback": 0.35, "mix": 1.0, "damping": 0.5})
    room = provider.create("pytheory_reverb", {"space": "hall", "mix": 1.0, "decay_seconds": 2.5, "width": 0.9})
    patch.add_module("delay", echo)
    patch.add_module("reverb", room)
    patch.connect(MASTER_ID, "send_a", "delay", "audio")
    patch.connect("delay", "output", MASTER_ID, "return_a_left")
    patch.connect(MASTER_ID, "send_b", "reverb", "audio")
    patch.connect("reverb", "wet_left", MASTER_ID, "return_b_left")
    patch.connect("reverb", "wet_right", MASTER_ID, "return_b_right")
    master.set_return_level("a", 0.5)
    master.set_return_level("b", 0.55)
    view = RackViewPreset(
        zoom=1.0,
        rails={},
        nodes=(
            # Collapsed: they are furniture until they are wanted, and a
            # collapsed module is its name and the jacks that are patched.
            RackNodePreset(node_id="delay", position=Point(x=40.0, y=40.0), collapsed=True),
            RackNodePreset(node_id="reverb", position=Point(x=300.0, y=40.0), collapsed=True),
        ),
    )
    return capture_patch_preset(
        name="Untitled Patch", patch=patch, master_gain=0.8, view=view
    )


def _example_documents() -> tuple[Path, ...]:
    """The example patches shipped beside the package, if this is a checkout."""
    folder = Path(__file__).resolve().parents[2] / "examples"
    if not folder.is_dir():
        return ()
    return tuple(sorted(folder.glob("*.noodler")))


def _open_example(_sender: int | str, _app_data: object, document: Path) -> None:
    """Open one of the shipped examples, without a dialog."""
    _guard_unsaved(lambda: _open_example_now(document), "Open the example")


def _open_example_now(document: Path) -> None:
    try:
        preset = read_patch_preset(document)
    except (OSError, TypeError, ValueError) as error:
        _set_patch_status(f"COULD NOT OPEN: {error}", error=True)
        return
    # An example is a starting point, not a file to write back over: Save asks.
    CURRENT_PATCH_PATH.clear()
    PENDING_OPEN[:] = [preset]
    _set_patch_status(f"OPENING  ·  {preset.name}")


def _consume_pending_open() -> AppRuntime | None:
    """Replace the rack with a document that was chosen last frame."""
    if not PENDING_OPEN:
        return None
    preset = PENDING_OPEN.pop()
    previous = ACTIVE_RUNTIME[0] if ACTIVE_RUNTIME else None
    if previous is not None:
        previous.audio.close()
    for item in (
        PRIMARY_WINDOW,
        INPUT_HANDLERS,
        MODULE_CLOSE_LAYER,
        CONSOLE_CABLES,
        OUTLINE_LAYER,
        SELECTION_LAYER,
        SAVE_PATCH_DIALOG,
        OPEN_PATCH_DIALOG,
        EXPORT_DIALOG,
        UNSAVED_DIALOG,
    ):
        if dpg.does_item_exist(item):
            dpg.delete_item(item)
    runtime = build_ui(preset=preset)
    dpg.set_primary_window(PRIMARY_WINDOW, True)
    if len(runtime.patch.modules) <= 1:
        _set_patch_status(EMPTY_RACK_STATUS)
    else:
        _set_patch_status(f"OPENED  ·  {preset.name}")
    return runtime


ACTIVE_RUNTIME: list[AppRuntime] = []
"""The rack the frame callback is currently driving."""

TRANSPORT = Transport(running=False)
"""The rack's clock. It starts stopped: play is what starts it, along with the
audio, from the button in the menu bar."""

TRANSPORT_BUTTON = "noodler.transport.button"
"""The rack's tempo, shared by every module that repeats."""


@dataclass(slots=True)
class RateSync:
    """A control the transport may drive, and the division it follows.

    ``kind`` says what the clock writes: hertz for a rate, seconds or
    milliseconds for a length. Either way it is written through the same
    validated model a hand on the knob would write through.
    """

    module: object
    path: tuple[str | int, ...]
    binding: KnobBinding
    division: str = FREE
    kind: str = "rate"


RATE_SYNCS: dict[int | str, RateSync] = {}
"""Keyed by the knob that shows the rate."""

WORD_CONTROLS: dict[int | str, tuple[object, tuple[str | int, ...], str]] = {}
"""Combos over words a module recognises, keyed by the combo."""


def _refresh_word_controls(module: object) -> None:
    """Re-offer a module's word lists after one of them changes what is valid.

    A tone system decides its own tonics, and a tonic its own modes, so
    choosing one narrows the next two. The lists are asked for again rather
    than left showing names the module would refuse.
    """
    for combo, (owner, _path, field_name) in WORD_CONTROLS.items():
        if owner is not module or not dpg.does_item_exist(combo):
            continue
        choices = list(getattr(owner, "choices_for", lambda _f: ())(field_name))
        if not choices:
            continue
        parameters = getattr(owner, "parameters", None)
        current = str(getattr(parameters, field_name, choices[0]))
        dpg.configure_item(combo, items=choices)
        dpg.set_value(combo, current if current in choices else choices[0])


def _set_word_parameter(combo: int | str, chosen: str, _u: object = None) -> None:
    entry = WORD_CONTROLS.get(combo)
    if entry is None:
        return
    module, path, _field_name = entry
    try:
        _set_dynamic_parameter(module, path, chosen)
    except Exception as error:
        _set_patch_status(f"CAN'T SET: {error}".split("\n")[0][:90], error=True)
        return
    # Some modules do real work when a word changes -- rendering an
    # instrument, for one -- and that belongs here, on the control thread,
    # rather than in the callback that will play it.
    refresh = getattr(module, "refresh", None)
    if callable(refresh):
        refresh()
    _refresh_word_controls(module)
    label = getattr(module, "label", None)
    _set_patch_status(str(label) if label else f"SET {chosen.upper()}")


def _set_rate_division(_sender: int | str, division: str, knob: int | str) -> None:
    sync = RATE_SYNCS.get(knob)
    if sync is None:
        return
    sync.division = division
    _set_patch_status(
        f"{sync.binding.label.upper()}  ·  "
        + ("FREE RUNNING" if division == FREE else f"SYNCED {division}")
    )


def _apply_transport_sync() -> None:
    """Drive every synced rate from the clock, at control rate.

    The DSP never learns about tempo: a division is turned into the hertz the
    module already understands, and written through the same validated model a
    hand on the knob would write through.
    """
    for knob, sync in RATE_SYNCS.items():
        if sync.kind == "rate":
            wanted = TRANSPORT.hz_for(sync.division)
        else:
            wanted = TRANSPORT.seconds_for(sync.division)
            if wanted is not None and sync.kind == "ms":
                wanted *= 1_000.0
        if wanted is None:
            continue
        binding = sync.binding
        value = min(binding.maximum, max(binding.minimum, wanted))
        try:
            _set_dynamic_parameter(sync.module, sync.path, value)
        except Exception:
            continue
        if dpg.does_item_exist(knob):
            _set_knob_position(
                knob,
                _control_position(
                    value, binding.minimum, binding.maximum, binding.logarithmic
                ),
            )
        if dpg.does_item_exist(binding.value_label):
            dpg.set_value(binding.value_label, binding.formatter(value))


def _refresh_clock(dt: float) -> None:
    """Run the clock and show where it is.

    While audio is playing the engine advances the clock on the sample clock,
    per block, and this only reads it. Otherwise the frame rate is the best
    clock there is, and it is good enough for a readout.
    """
    if not (ACTIVE_RUNTIME and ACTIVE_RUNTIME[0].audio.is_running):
        TRANSPORT.advance(dt)
    _apply_transport_sync()
    if not dpg.does_item_exist(CLOCK_READOUT):
        return
    marker = "●" if TRANSPORT.running and TRANSPORT.on_beat() else "○"
    dpg.set_value(
        CLOCK_READOUT,
        f"{marker}  {TRANSPORT.bpm:.0f} BPM  ·  {TRANSPORT.signature}"
        f"  ·  BEAT {TRANSPORT.beat}",
    )
    _settle_clock_readout()
    dpg.configure_item(
        CLOCK_READOUT,
        color=SCALE_ACCENT if TRANSPORT.running and TRANSPORT.on_beat() else MUTED_TEXT,
    )


def _set_clock_bpm(_sender: int | str, value: float, _user_data: object) -> None:
    TRANSPORT.set_bpm(value)
    _set_patch_status(f"TEMPO  {TRANSPORT.bpm:.0f} BPM")


def _set_clock_signature(_sender: int | str, _value: object, _u: object) -> None:
    """Read both halves of the signature from their controls."""
    beats = TRANSPORT.beats_per_bar
    unit = TRANSPORT.beat_unit
    if dpg.does_item_exist(CLOCK_BEATS_INPUT):
        beats = int(dpg.get_value(CLOCK_BEATS_INPUT))
    if dpg.does_item_exist(CLOCK_UNIT_INPUT):
        unit = int(dpg.get_value(CLOCK_UNIT_INPUT))
    _set_patch_status(f"TIME SIGNATURE  {TRANSPORT.set_signature(beats, unit)}")


def _settle_clock_readout() -> None:
    """Keep the transport readout against the right edge of the menu bar.

    Dear PyGui lays a menu bar out left to right with no notion of alignment,
    so the gap before the readout is measured and corrected each frame. It
    converges immediately and follows the window when it is resized.
    """
    if not (
        dpg.does_item_exist(CLOCK_SPACER) and dpg.does_item_exist(CLOCK_READOUT)
    ):
        return
    width = float(dpg.get_item_rect_size(CLOCK_READOUT)[0])
    if width <= 1.0:
        return
    left = float(dpg.get_item_rect_min(CLOCK_READOUT)[0])
    wanted = float(dpg.get_viewport_client_width()) - width - CLOCK_MARGIN
    gap = float(dpg.get_item_configuration(CLOCK_SPACER)["width"])
    adjusted = max(1.0, gap + (wanted - left))
    if abs(adjusted - gap) >= 1.0:
        dpg.configure_item(CLOCK_SPACER, width=round(adjusted))


def _toggle_clock(_sender: int | str = 0, _app_data: object = None, _u: object = None) -> None:
    TRANSPORT.running = not TRANSPORT.running
    _set_patch_status("CLOCK RUNNING" if TRANSPORT.running else "CLOCK STOPPED")


def _rewind_clock(_sender: int | str = 0, _app_data: object = None, _u: object = None) -> None:
    """Back to the top of bar one, so every clocked pattern starts over together."""
    TRANSPORT.rewind()
    _set_patch_status("CLOCK  ·  BAR ONE")

RACK_CURSOR = MacCursor()
"""The pointer shape, while a pan gesture holds it."""


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


def ensure_master(patch: PatchGraph) -> MasterMixer:
    """Give a patch its master mixer, and wire that mixer to the speakers.

    Every rack has one, so nothing has to be dragged to an output before it can
    be heard -- patch into a channel and it is audible. It is an ordinary module
    in an ordinary graph; the interface is what makes it permanent.
    """
    existing = patch.modules.get(MASTER_ID)
    if not isinstance(existing, MasterMixer):
        existing = MasterMixer()
        patch.add_module(MASTER_ID, existing)
    taps = {
        (tap.source.module_id, tap.source.port_id, tap.channel)
        for tap in patch.output_taps
    }
    for port_id, channel in (("left", OutputChannel.LEFT), ("right", OutputChannel.RIGHT)):
        if (MASTER_ID, port_id, channel) not in taps:
            patch.connect_output(MASTER_ID, port_id, channel=channel)
    return existing


def adopt_output_taps(patch: PatchGraph) -> None:
    """Move anything wired straight to the speakers into the master mixer.

    Patches saved before the master existed tapped the system output directly.
    Those taps still describe what the patch sounds like, so they become
    channels rather than being dropped: it plays the same and is now mixable.
    Where a tap was placed -- left, right, both -- becomes where the channel is
    panned, which is the same statement in the vocabulary that replaced it.
    """
    strays = [
        tap for tap in patch.output_taps if tap.source.module_id != MASTER_ID
    ]
    if not strays:
        return
    master = ensure_master(patch)
    placement = {
        OutputChannel.LEFT: -1.0,
        OutputChannel.RIGHT: 1.0,
        OutputChannel.BOTH: 0.0,
    }
    for channel, tap in enumerate(strays[:MASTER_CHANNELS], start=1):
        patch.disconnect_output(tap)
        patch.connect(
            tap.source.module_id,
            tap.source.port_id,
            MASTER_ID,
            f"channel_{channel}",
        )
        master.set_level(channel, tap.gain)
        master.set_pan(channel, placement[tap.channel])
    for tap in strays[MASTER_CHANNELS:]:
        patch.disconnect_output(tap)


def _reset_rack_registry(*, starter_patch: bool) -> None:
    """Return mutable node registries to the requested initial rack."""
    RACK_NODES[:] = BASE_RACK_NODES if starter_patch else ()
    INSTANCE_NODE_TAGS.clear()
    if starter_patch:
        INSTANCE_NODE_TAGS.update(BASE_INSTANCE_NODE_TAGS)
    INSTANCE_NODE_TAGS[MASTER_ID] = OUTPUT_NODE
    strips = [CONSOLE_STRIP.format(channel=c) for c in range(1, MASTER_CHANNELS + 1)]
    returns = [CONSOLE_RETURN.format(bus=bus) for bus in SENDS]
    # Master first, returns last. A node editor draws every cable leaving an
    # output to the right and arriving at an input from the left, so the
    # master's sends leave the left end of the console heading toward the
    # effects, and what the effects give back arrives at the right end from
    # the left. Channels sit between, taking cables straight down from above.
    posts = [CONSOLE_POST.format(name=f"channel_{c}") for c in range(1, MASTER_CHANNELS + 1)]
    for bus in SENDS:
        posts.append(CONSOLE_POST.format(name=f"send_{bus}"))
        posts += [CONSOLE_POST.format(name=port) for port in RETURN_PORTS[bus]]
    # Channels, then the two effect strips -- each of which carries its own
    # send out and its return in, so a send and its return are one thing on
    # the desk. There is no master strip: the master's level lives in the
    # status bar, and OUTPUT_NODE is only the prefix its jacks are tagged by.
    PINNED_NODES[:] = [*strips, *returns, *posts]
    strips = strips + returns + posts
    for strip in strips:
        if strip not in RACK_NODES:
            RACK_NODES.append(strip)
    VIEW_NODE_TAGS.clear()
    VIEW_NODE_TAGS.update(INSTANCE_NODE_TAGS)
    RACK_RAILS[CONTROL_RAIL][:] = (
        [FUNCTION_NODE, WOGGLE_NODE, SCALE_NODE] if starter_patch else []
    )
    RACK_RAILS[AUDIO_RAIL][:] = (
        [VCO_NODE, MIXER_NODE, LPG_NODE, REVERB_NODE] if starter_patch else []
    )
    MODULE_ACCENTS.clear()
    if starter_patch:
        MODULE_ACCENTS.update(BASE_MODULE_ACCENTS)
    else:
        pass


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


def _console_theme(tag: str, jack_inset: float) -> None:
    with dpg.theme(tag=tag):
        with dpg.theme_component(dpg.mvNode):
            for node_color, color in (
                (dpg.mvNodeCol_NodeBackground, (27, 27, 25, 252)),
                (dpg.mvNodeCol_NodeBackgroundHovered, (31, 31, 29, 255)),
                (dpg.mvNodeCol_NodeBackgroundSelected, (31, 31, 29, 255)),
                (dpg.mvNodeCol_NodeOutline, (64, 60, 52, 255)),
                (dpg.mvNodeCol_TitleBar, (46, 43, 38, 255)),
                (dpg.mvNodeCol_TitleBarHovered, (54, 50, 44, 255)),
                (dpg.mvNodeCol_TitleBarSelected, (46, 43, 38, 255)),
            ):
                dpg.add_theme_color(node_color, color, category=dpg.mvThemeCat_Nodes)
            styles = [
                (dpg.mvNodeStyleVar_NodeCornerRounding, 4),
                (dpg.mvNodeStyleVar_NodeBorderThickness, 1.0),
                (dpg.mvNodeStyleVar_PinCircleRadius, 6),
                (dpg.mvNodeStyleVar_PinHoverRadius, 12),
            ]
            if jack_inset:
                # Negative pulls a pin in from the node's edge -- the jack at
                # the top centre of the strip, where a cable expects to land.
                styles.append((dpg.mvNodeStyleVar_PinOffset, -jack_inset))
            for node_style, value in styles:
                dpg.add_theme_style(node_style, value, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_NodePadding, 5, 4, category=dpg.mvThemeCat_Nodes
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
            # The marquee refused to take a colour from either a node-editor
            # component or a theme bound to the editor itself, so it is set
            # here, where Dear PyGui applies a theme to everything.
            for selector_color, tag in (
                (dpg.mvNodeCol_BoxSelector, BOX_SELECTOR_FILL),
                (dpg.mvNodeCol_BoxSelectorOutline, BOX_SELECTOR_OUTLINE),
            ):
                dpg.add_theme_color(
                    selector_color,
                    BOX_SELECTOR_HIDDEN,
                    tag=tag,
                    category=dpg.mvThemeCat_Nodes,
                )
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
    with dpg.theme(tag=CONSOLE_LINK_HIDDEN_THEME):
        # imnodes draws every link arriving from the left, which hooks a cable
        # that drops onto a strip; those links are drawn by hand instead, and
        # the editor's own copy is made invisible.
        with dpg.theme_component(dpg.mvNodeLink):
            for link_color in (dpg.mvNodeCol_Link, dpg.mvNodeCol_LinkHovered, dpg.mvNodeCol_LinkSelected):
                dpg.add_theme_color(link_color, (0, 0, 0, 0), category=dpg.mvThemeCat_Nodes)
    # A cable glows with what is on it, in the same steps as its jack.
    for signal, colour in SIGNAL_COLORS.items():
        for step in range(ACTIVITY_STEPS + 1):
            _link_theme(_link_glow_theme(signal, step), _glow(colour, step))
    # The console is furniture, not a module: darker, squarer, quieter, with
    # the one warm line of its title to say which strip is which. Strips and
    # returns also pull their jack in from the edge to the top centre.
    for tag, inset in (
        (CONSOLE_THEME, 0.0),
        (CONSOLE_STRIP_THEME, STRIP_JACK_INSET),
        (CONSOLE_RETURN_THEME, RETURN_JACK_INSET),
    ):
        _console_theme(tag, inset)
    with dpg.theme(tag=OUTLINE_LINK_THEME):
        with dpg.theme_component(dpg.mvSelectable):
            dpg.add_theme_color(dpg.mvThemeCol_Text, SCALE_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Header, (0, 0, 0, 0))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (135, 119, 211, 40))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (135, 119, 211, 70))
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0)
    with dpg.theme(tag=OUTLINE_ARROW_THEME):
        # The disclosure arrow on a module's row: the tree's own arrow, as a
        # button with no body, so the row reads as one line of the tree.
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 0, 0, 0))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (135, 119, 211, 40))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (135, 119, 211, 70))
            dpg.add_theme_color(dpg.mvThemeCol_Text, TEXT)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 2, 1)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)
    with dpg.theme(tag=JACK_POST_THEME):
        # A jack post is not seen, only its pin: no body, no title, no border.
        with dpg.theme_component(dpg.mvNode):
            for node_color in (
                dpg.mvNodeCol_NodeBackground,
                dpg.mvNodeCol_NodeBackgroundHovered,
                dpg.mvNodeCol_NodeBackgroundSelected,
                dpg.mvNodeCol_NodeOutline,
                dpg.mvNodeCol_TitleBar,
                dpg.mvNodeCol_TitleBarHovered,
                dpg.mvNodeCol_TitleBarSelected,
            ):
                dpg.add_theme_color(node_color, (0, 0, 0, 0), category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_style(dpg.mvNodeStyleVar_NodePadding, 2, 1, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_style(dpg.mvNodeStyleVar_NodeBorderThickness, 0.0, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_style(dpg.mvNodeStyleVar_PinCircleRadius, 6, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_style(dpg.mvNodeStyleVar_PinHoverRadius, 12, category=dpg.mvThemeCat_Nodes)
    for tag, background, foreground in (
        (TOGGLE_OFF_THEME, (36, 36, 34, 255), MUTED_TEXT),
        (MUTE_ON_THEME, METER_HOT, (28, 26, 22, 255)),
        (SOLO_ON_THEME, METER_QUIET, (24, 30, 24, 255)),
    ):
        with dpg.theme(tag=tag):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, background)
                dpg.add_theme_color(
                    dpg.mvThemeCol_ButtonHovered,
                    tuple(min(255, c + 16) for c in background[:3]) + (255,),
                )
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, background)
                dpg.add_theme_color(dpg.mvThemeCol_Text, foreground)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 5, 1)
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
        if dpg.does_item_exist(AUDIO_STATUS):
            dpg.set_value(
                AUDIO_STATUS,
                f"{engine.output_device_name}  ·  {rate / 1000:.1f} kHz",
            )
    except Exception as exc:
        if dpg.does_item_exist(AUDIO_STATUS):
            dpg.set_value(AUDIO_STATUS, f"AUDIO ERROR: {exc}")
        raise


def _stop_audio(
    _sender: str,
    _value: object,
    engine: SystemAudioEngine,
) -> None:
    engine.stop()
    if dpg.does_item_exist(AUDIO_STATUS):
        dpg.set_value(AUDIO_STATUS, "")


def _toggle_playback(
    _sender: int | str = 0, _app_data: object = None, runtime: AppRuntime | None = None
) -> None:
    """Play or stop: the audio and the clock together, from one button.

    Audio never starts on its own -- pressing play is what opens the device --
    and the clock runs while it is open, so a beat that follows the transport
    starts when the sound does. Stopping closes the device: the button says
    stop, and it should stop.
    """
    if runtime is None and ACTIVE_RUNTIME:
        runtime = ACTIVE_RUNTIME[0]
    if runtime is None:
        return
    engine = runtime.audio
    if engine.is_running:
        TRANSPORT.running = False
        _stop_audio(0, None, engine)
        _set_patch_status("STOPPED")
    else:
        try:
            _start_audio(0, None, engine)
        except Exception as exc:
            _set_patch_status(f"COULD NOT START AUDIO: {exc}", error=True)
            return
        TRANSPORT.running = True
        _set_patch_status("PLAYING")
    _refresh_transport_button(runtime)


def _refresh_transport_button(runtime: AppRuntime | None = None) -> None:
    """Make the button say what it will do next."""
    if not dpg.does_item_exist(TRANSPORT_BUTTON):
        return
    if runtime is None and ACTIVE_RUNTIME:
        runtime = ACTIVE_RUNTIME[0]
    playing = runtime is not None and runtime.audio.is_running
    label = "■  STOP" if playing else "▶  PLAY"
    if dpg.get_item_configuration(TRANSPORT_BUTTON)["label"] != label:
        dpg.configure_item(TRANSPORT_BUTTON, label=label)


def _play_shortcut(sender: int | str, app_data: object, runtime: AppRuntime) -> None:
    if _commanded() and not _keyboard_is_captured():
        _toggle_playback(sender, app_data, runtime)


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
    if _is_console_route(route):
        dpg.bind_item_theme(link, CONSOLE_LINK_HIDDEN_THEME)
    CABLE_INDEX_KEY.clear()
    return link


def _is_console_route(route: object) -> bool:
    """Whether a cable touches the console -- and so is drawn by hand."""
    target = getattr(route, "target", None)
    source = getattr(route, "source", None)
    return (target is not None and target.module_id == MASTER_ID) or (
        source is not None and source.module_id == MASTER_ID
    )


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
        # A tap has no jack to draw to: the master's bus is not a cable.
        target_attribute = None
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


def _wet_an_effect_on_a_send(runtime: AppRuntime, cable: Cable) -> bool:
    """An effect fed from a send should be all wet, so it is made so.

    A reverb straight in a signal path mixes its room with the dry sound. On a
    send the dry sound is already on the channel, and a return that carried it
    again would double it -- so when a cable from a master send lands on a
    module with a mix, the mix goes to full and the status bar says so. It is
    still a knob: turn it back if that is not what was meant.
    """
    if cable.source.module_id != MASTER_ID or not cable.source.port_id.startswith("send_"):
        return False
    module = runtime.patch.modules.get(cable.target.module_id)
    parameters = getattr(module, "parameters", None)
    if parameters is None or not hasattr(parameters, "mix"):
        return False
    try:
        if float(parameters.mix) >= 0.999:
            return False
        _set_dynamic_parameter(module, ("mix",), 1.0)
    except Exception:
        return False
    knob = f"{INSTANCE_NODE_TAGS.get(cable.target.module_id)}.control.mix"
    if knob in KNOB_INTERACTION.bindings:
        binding = KNOB_INTERACTION.bindings[knob]
        _set_knob_position(
            knob, _control_position(1.0, binding.minimum, binding.maximum, binding.logarithmic)
        )
        if dpg.does_item_exist(binding.value_label):
            dpg.set_value(binding.value_label, binding.formatter(1.0))
    _set_patch_status(
        f"{module.manifest.name.upper()} SET FULLY WET  ·  IT IS ON A SEND"
    )
    return True


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
        if not _wet_an_effect_on_a_send(runtime, cable):
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
        # Every cable, and every tap that is not the master's own: the bus to
        # the speakers is not something anyone patched, so it is not unplugged.
        unplugged: tuple[Cable | OutputTap, ...] = runtime.patch.cables + tuple(
            tap for tap in runtime.patch.output_taps if tap.source.module_id != MASTER_ID
        )
        if not unplugged:
            _set_patch_status("NO CABLES TO UNPLUG")
            return

        def unplug() -> int:
            for route in unplugged:
                if isinstance(route, Cable):
                    runtime.patch.disconnect(route)
                else:
                    runtime.patch.disconnect_output(route)
            return len(unplugged)

        removed = _edit_patch(runtime, unplug)
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
        transport=TransportPreset(
            bpm=TRANSPORT.bpm,
            beats_per_bar=TRANSPORT.beats_per_bar,
            beat_unit=TRANSPORT.beat_unit,
        ),
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
        _save_patch_to(runtime, requested_path)
        _set_patch_status(f"SAVED PATCH  ·  {requested_path.name}")
    except (OSError, TypeError, ValueError) as exc:
        _set_patch_status(f"SAVE ERROR: {exc}", error=True)


def _choose_export(_sender: int | str, _app_data: object, data: tuple[AppRuntime, int]) -> None:
    """Remember how many bars, and ask where the file goes."""
    _runtime, bars = data
    EXPORT_BARS[:] = [int(bars)]
    if dpg.does_item_exist(EXPORT_DIALOG):
        dpg.configure_item(EXPORT_DIALOG, default_filename=f"{PATCH_NAME[0]}.wav")
        dpg.show_item(EXPORT_DIALOG)


def _export_dialog(_sender: int | str, app_data: object, runtime: AppRuntime) -> None:
    """Bounce the current patch to the chosen file, on a thread, from bar one."""
    try:
        if not isinstance(app_data, dict):
            raise ValueError("the file dialog did not return a destination")
        selected = app_data.get("file_path_name")
        if not isinstance(selected, str) or not selected:
            raise ValueError("choose a file to export to")
    except (TypeError, ValueError) as exc:
        _set_patch_status(f"EXPORT ERROR: {exc}", error=True)
        return
    destination = Path(selected)
    preset = _capture_current_preset(runtime, PATCH_NAME[0])
    bars = EXPORT_BARS[0]
    sample_rate = runtime.audio.sample_rate if runtime.audio.is_running else 48_000.0

    def work() -> None:
        from .bounce import bounce, write_wav

        try:
            EXPORT_MESSAGES.append((f"BOUNCING  ·  {bars} BARS AT {preset.transport.bpm:.0f} BPM", False))
            audio = bounce(
                preset,
                bars=bars,
                tail_seconds=EXPORT_TAIL_SECONDS,
                sample_rate=float(sample_rate),
                progress=lambda done, total: EXPORT_MESSAGES.append(
                    (f"BOUNCING  ·  BAR {done}/{total}", False)
                ),
            )
            written = write_wav(destination, audio, float(sample_rate))
            seconds = audio.shape[0] / float(sample_rate)
            EXPORT_MESSAGES.append(
                (f"EXPORTED  ·  {written.name}  ·  {seconds:.1f} s", False)
            )
        except Exception as exc:  # noqa: BLE001 - reported to the user, not raised on a thread
            EXPORT_MESSAGES.append((f"EXPORT ERROR: {exc}", True))

    threading.Thread(target=work, name="noodler-bounce", daemon=True).start()


def _show_export_messages() -> None:
    """Say what the bounce thread said, from the frame loop."""
    while EXPORT_MESSAGES:
        message, error = EXPORT_MESSAGES.pop(0)
        _set_patch_status(message, error=error)


def _decibels(level: float) -> str:
    return "-∞" if level <= 0.00001 else f"{20.0 * math.log10(level):.0f}"


def _add_bar_scope() -> None:
    """A trace of the output along the bottom bar, where it is always in view."""
    if dpg.does_item_exist(BAR_SCOPE):
        return
    with dpg.drawlist(width=BAR_SCOPE_WIDTH, height=BAR_SCOPE_HEIGHT, tag=BAR_SCOPE):
        dpg.draw_line(
            (0, BAR_SCOPE_HEIGHT * 0.5),
            (BAR_SCOPE_WIDTH, BAR_SCOPE_HEIGHT * 0.5),
            color=(58, 56, 50, 255),
        )
        dpg.draw_polyline(
            [(index, BAR_SCOPE_HEIGHT * 0.5) for index in range(BAR_SCOPE_WIDTH)],
            color=SIGNAL_COLORS["audio"],
            thickness=1.0,
            tag=BAR_SCOPE_TRACE,
        )


def _draw_trace(
    trace,
    item: int | str,
    width: int,
    height: float,
) -> None:
    """Fit a captured trace to one drawlist."""
    if not dpg.does_item_exist(item) or trace.size < width:
        return
    step = trace.size // width
    middle = height * 0.5
    reach = height * 0.46
    dpg.configure_item(
        item,
        points=[
            (float(index), middle - float(trace[index * step]) * reach)
            for index in range(width)
        ],
    )


def _refresh_scope(runtime: AppRuntime) -> None:
    """Draw what was just played, so a patch can be watched as well as heard."""
    trace = runtime.audio.scope_trace()
    _draw_trace(trace, OUTPUT_SCOPE_TRACE, SCOPE_POINTS_DRAWN, SCOPE_HEIGHT)
    _draw_trace(trace, BAR_SCOPE_TRACE, BAR_SCOPE_WIDTH, BAR_SCOPE_HEIGHT)


CONSOLE_BALLISTICS: list[MeterBallistics] = []
"""One peak-programme meter per strip, made when the console is."""
RETURN_BALLISTICS: list[MeterBallistics] = []

PORT_TEXTS: dict[tuple[str, str], tuple[int | str, str]] = {}
"""Each output jack's label and signal type, for lighting it with its signal."""
INPUT_TEXTS: dict[tuple[str, str], int | str] = {}
"""Each input jack's label, for drawing a send cable to it."""
PORT_ACTIVITY: dict[tuple[str, str], float] = {}
PORT_STEPS: dict[tuple[str, str], int] = {}
PORT_INDEX_KEY: list[tuple[str, ...]] = []
ACTIVITY_STEPS = 6
ACTIVITY_RELEASE = 0.85
"""How much of a jack's glow survives from one frame to the next."""

KNOB_STATES: dict[int | str, str] = {}
KNOB_ARC_HOVER = tuple(min(255, c + 40) for c in SCALE_ACCENT[:3]) + (255,)
KNOB_TRACK_HOVER = (84, 81, 72, 255)

EMPTY_RACK_STATUS = (
    "EMPTY RACK  ·  DRAG A MODULE FROM THE LIBRARY  ·  ⌘K TO SEARCH  ·  "
    "FILE → OPEN EXAMPLE TO HEAR SOMETHING"
)


def _index_port_texts(runtime: AppRuntime) -> None:
    """Find the label of every output jack on every mounted module, once per
    change to what is mounted, so the glow has something to paint."""
    key = tuple(sorted(INSTANCE_NODE_TAGS))
    if PORT_INDEX_KEY and PORT_INDEX_KEY[0] == key and PORT_TEXTS:
        return
    PORT_INDEX_KEY[:] = [key]
    PORT_TEXTS.clear()
    PORT_STEPS.clear()
    INPUT_TEXTS.clear()
    for instance_id, node in INSTANCE_NODE_TAGS.items():
        module = runtime.patch.modules.get(instance_id)
        if module is None:
            continue
        for port in module.manifest.ports:
            attribute = f"{node}.{port.id}"
            if not dpg.does_item_exist(attribute):
                continue
            text = _first_text_in(attribute)
            if text is None:
                continue
            if port.direction is PortDirection.OUTPUT:
                PORT_TEXTS[(instance_id, port.id)] = (text, port.signal_type.value)
            else:
                INPUT_TEXTS[(instance_id, port.id)] = text


def _first_text_in(item: int | str) -> int | str | None:
    """The first text anywhere under an item -- a port label, wherever it sits."""
    pending = list(dpg.get_item_children(item).get(1, ()))
    while pending:
        child = pending.pop(0)
        if dpg.get_item_type(child).endswith("mvText"):
            return child
        pending.extend(dpg.get_item_children(child).get(1, ()))
    return None


def _link_glow_theme(signal: str, step: int) -> str:
    return f"noodler.theme.link.{signal}.glow{step}"


CABLE_SOURCES: dict[int | str, tuple[str, str, str]] = {}
"""Each drawn cable, by the output that feeds it and the signal it carries."""
CABLE_INDEX_KEY: list[int] = []
CABLE_STEPS: dict[int | str, int] = {}


def _index_cables() -> None:
    """Know which output feeds each drawn cable, re-read when the count changes."""
    if not dpg.does_item_exist(RACK):
        return
    links = dpg.get_item_children(RACK).get(0, ())
    if CABLE_INDEX_KEY and CABLE_INDEX_KEY[0] == len(links) and CABLE_SOURCES:
        return
    CABLE_INDEX_KEY[:] = [len(links)]
    CABLE_SOURCES.clear()
    CABLE_STEPS.clear()
    for link in links:
        route = dpg.get_item_user_data(link)
        source = getattr(route, "source", None)
        if source is None or _is_console_route(route):
            continue
        signal = "cv"
        if ACTIVE_RUNTIME:
            signal = _endpoint_signal(ACTIVE_RUNTIME[0].patch, source)
        CABLE_SOURCES[link] = (source.module_id, source.port_id, signal)


def _glow(colour: tuple[int, int, int, int], step: int) -> tuple[int, int, int, int]:
    """A jack colour between dim and lit, in a few even steps."""
    weight = 0.38 + 0.62 * (step / ACTIVITY_STEPS)
    background = (38, 36, 32)
    return tuple(
        int(round(background[i] + (colour[i] - background[i]) * weight)) for i in range(3)
    ) + (255,)


def _activity_of(block: object) -> float:
    """How lit a jack should be for what is on it, zero to one.

    Audio and control blocks light by their peak. A musical object -- a scale
    crossing a cable -- is not a number at all; it is simply present, so its
    jack is simply lit.
    """
    if block is None:
        return 0.0
    array = np.asarray(block)
    if array.dtype.kind not in "fiub":
        return 1.0
    if array.ndim == 0:
        return min(1.0, abs(float(array)))
    if array.size == 0:
        return 0.0
    return min(1.0, float(np.max(np.abs(array))))


def _refresh_jack_activity(runtime: AppRuntime) -> None:
    """Light every output jack as brightly as the signal on it.

    The rack is alive when its jacks are: an oscillator's saw glows, a gate
    blinks, a quiet output goes dim. Read from the last rendered block, which
    the audio thread has already moved on from, and repainted only when a
    jack changes step -- so a rack of a hundred jacks costs a handful of
    configure calls a frame rather than a hundred.
    """
    _index_port_texts(runtime)
    if not PORT_TEXTS:
        return
    playing = runtime.audio.is_running
    rendered = runtime.patch.last_rendered if playing else {}
    for (instance_id, port_id), (text, signal) in PORT_TEXTS.items():
        level = 0.0
        if playing:
            block = rendered.get(instance_id, {}).get(port_id)
            level = _activity_of(block)
        held = max(level, PORT_ACTIVITY.get((instance_id, port_id), 0.0) * ACTIVITY_RELEASE)
        PORT_ACTIVITY[(instance_id, port_id)] = held
        step = min(ACTIVITY_STEPS, int(round(held * ACTIVITY_STEPS)))
        if PORT_STEPS.get((instance_id, port_id)) == step:
            continue
        PORT_STEPS[(instance_id, port_id)] = step
        if dpg.does_item_exist(text):
            dpg.configure_item(text, color=_glow(SIGNAL_COLORS.get(signal, TEXT), step))
    _refresh_cable_glow()


def _refresh_cable_glow() -> None:
    """Rebind each cable to the glow of the jack that feeds it, on change."""
    _index_cables()
    for link, (module_id, port_id, signal) in CABLE_SOURCES.items():
        step = PORT_STEPS.get((module_id, port_id), 0)
        if CABLE_STEPS.get(link) == step:
            continue
        CABLE_STEPS[link] = step
        if dpg.does_item_exist(link):
            dpg.bind_item_theme(link, _link_glow_theme(signal if signal in SIGNAL_COLORS else "cv", step))


def _console_pin_position(post: str) -> tuple[float, float] | None:
    text = POST_TEXTS.get(post)
    if text is None or not (dpg.does_item_exist(post) and dpg.does_item_exist(text)):
        return None
    try:
        if post in POST_OUTPUTS:
            edge = float(dpg.get_item_rect_max(post)[0])
        else:
            edge = float(dpg.get_item_rect_min(post)[0])
        top = float(dpg.get_item_rect_min(text)[1])
        height = float(dpg.get_item_rect_size(text)[1])
    except (KeyError, SystemError):
        return None
    if height <= 0.0:
        return None
    return edge, top + height * 0.5


def _source_pin_position(module_id: str, port_id: str) -> tuple[float, float] | None:
    node = INSTANCE_NODE_TAGS.get(module_id)
    entry = PORT_TEXTS.get((module_id, port_id))
    if node is None or entry is None or not dpg.does_item_exist(node):
        return None
    text = entry[0]
    if not dpg.does_item_exist(text):
        return None
    try:
        right = float(dpg.get_item_rect_max(node)[0])
        top = float(dpg.get_item_rect_min(text)[1])
        height = float(dpg.get_item_rect_size(text)[1])
    except (KeyError, SystemError):
        return None
    if height <= 0.0:
        return None
    return right, top + height * 0.5


def _send_cable_points(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[tuple[float, float], ...]:
    """A cable that rises out of a send jack and arrives at a module from the left."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(1.0, math.hypot(dx, dy))
    rise = max(50.0, 0.6 * abs(dy))
    reach = min(80.0, max(30.0, 0.2 * length))
    return (
        start,
        (start[0], start[1] - rise),
        (end[0] - reach, end[1]),
        end,
    )


def _target_pin_position(module_id: str, port_id: str) -> tuple[float, float] | None:
    """Where a module's input pin is: its left edge, at the port label's height."""
    node = INSTANCE_NODE_TAGS.get(module_id)
    entry = INPUT_TEXTS.get((module_id, port_id))
    if node is None or entry is None or not dpg.does_item_exist(node):
        return None
    if not dpg.does_item_exist(entry):
        return None
    try:
        left = float(dpg.get_item_rect_min(node)[0])
        top = float(dpg.get_item_rect_min(entry)[1])
        height = float(dpg.get_item_rect_size(entry)[1])
    except (KeyError, SystemError):
        return None
    if height <= 0.0:
        return None
    return left, top + height * 0.5


def _console_cable_points(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[tuple[float, float], ...]:
    """A cable that leaves a module to the right and drops into a jack from above."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(1.0, math.hypot(dx, dy))
    # A short reach to the right, as every cable leaves an output, then a
    # drop that arrives vertically: the drop is most of the vertical distance
    # so the last stretch into the jack is straight down.
    reach = min(80.0, max(30.0, 0.2 * length))
    drop = max(50.0, 0.6 * abs(dy))
    return (
        start,
        (start[0] + reach, start[1]),
        (end[0], end[1] - drop),
        end,
    )


def _bezier_point(points: tuple[tuple[float, float], ...], t: float) -> tuple[float, float]:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    u = 1.0 - t
    return (
        u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3,
        u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3,
    )


CONSOLE_CABLE_PATHS: dict[int | str, tuple[tuple[float, float], ...]] = {}


def _console_cable_near(position: tuple[float, float]) -> int | str | None:
    """The drawn console cable under the pointer, if one is."""
    best, best_distance = None, CONSOLE_CABLE_HOVER_PX
    for link, points in CONSOLE_CABLE_PATHS.items():
        for step in range(25):
            x, y = _bezier_point(points, step / 24.0)
            distance = math.hypot(x - position[0], y - position[1])
            if distance < best_distance:
                best, best_distance = link, distance
    return best


SELECTION_LAYER = "noodler.selection_layer"
SELECTION_COLOR = (211, 145, 57)
"""Amber, the marquee's colour: a selected module wears the same."""
SELECTION_ROUNDING = 8.0


def _rack_screen_rect() -> tuple[float, float, float, float] | None:
    """The editor's rectangle on screen, as (left, top, right, bottom).

    The node editor reports no rectangle of its own -- rect_min and rect_max
    come back zero -- but it fills the right-hand end of its row, so its box
    is the row's bottom-right corner less the editor's size.
    """
    if not dpg.does_item_exist(RACK):
        return None
    try:
        width, height = (float(v) for v in dpg.get_item_rect_size(RACK))
        parent = dpg.get_item_parent(RACK)
        right, bottom = (float(v) for v in dpg.get_item_rect_max(parent))
    except (KeyError, SystemError):
        return None
    if width <= 1.0 or height <= 1.0:
        return None
    return right - width, bottom - height, right, bottom


def _refresh_selection() -> None:
    """Show what is selected: an amber outline on each selected module, and
    the marquee itself while a shift-drag is sweeping one out.

    imnodes draws neither in a way that reads here -- its selected colours
    are the module's own, and its box selector took no colour from any theme
    it was offered -- so both are drawn on a layer over the rack, clipped to
    the editor so nothing bleeds into the outline or the console.
    """
    if not dpg.does_item_exist(SELECTION_LAYER):
        dpg.add_viewport_drawlist(tag=SELECTION_LAYER, front=True)
    dpg.delete_item(SELECTION_LAYER, children_only=True)
    rect = _rack_screen_rect()
    if rect is None:
        return
    left, top, right, bottom = rect
    for item in dpg.get_selected_nodes(RACK):
        node = _node_tag_for_item(item)
        if node is None or _is_pinned(node) or not dpg.does_item_exist(node):
            continue
        try:
            x0, y0 = (float(v) for v in dpg.get_item_rect_min(node))
            x1, y1 = (float(v) for v in dpg.get_item_rect_max(node))
        except (KeyError, SystemError):
            continue
        if x1 <= x0 or y1 <= y0 or x1 < left or x0 > right or y1 < top or y0 > bottom:
            continue
        # The editor reports the content box; the panel's edge is its padding
        # further out, and the outline should sit on the edge.
        x0, y0, x1, y1 = x0 - 6.0, y0 - 3.0, x1 + 6.0, y1 + 4.0
        for pad, alpha, thickness in ((5.0, 26, 6.0), (2.5, 78, 3.0), (1.0, 235, 1.5)):
            dpg.draw_rectangle(
                (max(left, x0 - pad), max(top, y0 - pad)),
                (min(right, x1 + pad), min(bottom, y1 + pad)),
                color=(*SELECTION_COLOR, alpha),
                thickness=thickness,
                rounding=SELECTION_ROUNDING + pad,
                parent=SELECTION_LAYER,
            )
    origin = CANVAS_INTERACTION.marquee_origin
    if origin is None:
        return
    if not dpg.is_mouse_button_down(dpg.mvMouseButton_Left):
        CANVAS_INTERACTION.marquee_origin = None
        return
    mouse_x, mouse_y = (float(v) for v in dpg.get_mouse_pos(local=False))
    x0, x1 = sorted((origin[0], mouse_x))
    y0, y1 = sorted((origin[1], mouse_y))
    x0, y0 = max(left, x0), max(top, y0)
    x1, y1 = min(right, x1), min(bottom, y1)
    if x1 - x0 < 1.0 or y1 - y0 < 1.0:
        return
    dpg.draw_rectangle((x0, y0), (x1, y1), color=(0, 0, 0, 0), fill=(*SELECTION_COLOR, 34), parent=SELECTION_LAYER)
    dpg.draw_rectangle((x0, y0), (x1, y1), color=(*SELECTION_COLOR, 190), thickness=1.0, parent=SELECTION_LAYER)


def _refresh_console_cables(runtime: AppRuntime) -> None:
    """Draw every cable that lands on the console, entering its jack from above.

    imnodes draws every link arriving at an input from the left, offset by a
    quarter of the cable's length, so a cable dropped from a module onto a
    strip below overshoots left and hooks back into the jack. These are drawn
    by hand instead -- leaving the module to the right as every other cable
    does, then dropping into the jack from above -- on a layer over the rack,
    with the same glow as any cable, and the editor's own copy hidden.
    """
    if not dpg.does_item_exist(RACK):
        return
    if not dpg.does_item_exist(CONSOLE_CABLES):
        dpg.add_viewport_drawlist(tag=CONSOLE_CABLES, front=True)
    mouse = tuple(float(v) for v in dpg.get_mouse_pos(local=False))
    hovered = _console_cable_near(mouse) if _mouse_is_over_rack() else None
    live: set[int | str] = set()
    for link in dpg.get_item_children(RACK).get(0, ()):
        route = dpg.get_item_user_data(link)
        if not _is_console_route(route):
            continue
        if route.target.module_id == MASTER_ID:
            post = CONSOLE_POST.format(name=route.target.port_id)
            start = _source_pin_position(route.source.module_id, route.source.port_id)
            end = _console_pin_position(post)
            if start is None or end is None:
                continue
            points = _console_cable_points(start, end)
        else:
            post = CONSOLE_POST.format(name=route.source.port_id)
            start = _console_pin_position(post)
            end = _target_pin_position(route.target.module_id, route.target.port_id)
            if start is None or end is None:
                continue
            points = _send_cable_points(start, end)
        live.add(link)
        CONSOLE_CABLE_PATHS[link] = points
        signal = _endpoint_signal(runtime.patch, route.source)
        step = PORT_STEPS.get((route.source.module_id, route.source.port_id), 0)
        colour = TEXT if link == hovered else _glow(SIGNAL_COLORS.get(signal, TEXT), step)
        thickness = 4.0 if link == hovered else 3.0
        item = CONSOLE_CABLE_ITEMS.get(link)
        if item is None or not dpg.does_item_exist(item):
            CONSOLE_CABLE_ITEMS[link] = dpg.draw_bezier_cubic(
                *points, color=colour, thickness=thickness, parent=CONSOLE_CABLES
            )
        else:
            dpg.configure_item(
                item, p1=points[0], p2=points[1], p3=points[2], p4=points[3],
                color=colour, thickness=thickness,
            )
    for link in tuple(CONSOLE_CABLE_ITEMS):
        if link not in live:
            item = CONSOLE_CABLE_ITEMS.pop(link)
            CONSOLE_CABLE_PATHS.pop(link, None)
            if dpg.does_item_exist(item):
                dpg.delete_item(item)


def _refresh_knob_hover() -> None:
    """Brighten the knob under the pointer, and the one being turned."""
    hovered = _hovered_knob()
    hovered_knob = hovered[0] if hovered is not None else None
    active = KNOB_INTERACTION.active_knob
    for knob, art in KNOB_INTERACTION.art.items():
        state = "active" if knob == active else "hover" if knob == hovered_knob else "idle"
        if KNOB_STATES.get(knob) == state:
            continue
        KNOB_STATES[knob] = state
        if not dpg.does_item_exist(art.arc):
            continue
        if state == "active":
            dpg.configure_item(art.arc, color=TEXT)
            dpg.configure_item(art.track, color=KNOB_TRACK_HOVER)
        elif state == "hover":
            dpg.configure_item(art.arc, color=KNOB_ARC_HOVER)
            dpg.configure_item(art.track, color=KNOB_TRACK_HOVER)
        else:
            dpg.configure_item(art.arc, color=KNOB_ARC)
            dpg.configure_item(art.track, color=KNOB_TRACK)


def _refresh_console_meters(runtime: AppRuntime, dt: float, master_level: float) -> None:
    """Light each strip's ring as far round as its channel reaches."""
    master = runtime.patch.modules.get(MASTER_ID)
    peaks = getattr(master, "channel_peaks", ()) if master is not None else ()
    while len(CONSOLE_BALLISTICS) < MASTER_CHANNELS:
        CONSOLE_BALLISTICS.append(MeterBallistics())
    for index, meter in enumerate(CONSOLE_BALLISTICS):
        ring = f"{CONSOLE_LEVEL.format(channel=index + 1)}.meter"
        if not dpg.does_item_exist(ring):
            continue
        peak = float(peaks[index]) if index < len(peaks) else 0.0
        level = min(1.0, meter.advance(peak, dt))
        dpg.configure_item(ring, points=_meter_ring_points(level), color=_meter_colour(level))
    return_peaks = getattr(master, "return_peaks", (0.0, 0.0)) if master is not None else (0.0, 0.0)
    while len(RETURN_BALLISTICS) < len(SENDS):
        RETURN_BALLISTICS.append(MeterBallistics())
    for index, bus in enumerate(SENDS):
        ring = f"{CONSOLE_RETURN_LEVEL.format(bus=bus)}.meter"
        if not dpg.does_item_exist(ring):
            continue
        level = min(1.0, RETURN_BALLISTICS[index].advance(float(return_peaks[index]), dt))
        dpg.configure_item(ring, points=_meter_ring_points(level), color=_meter_colour(level))
    ring = f"{CONSOLE_MASTER_LEVEL}.meter"
    if dpg.does_item_exist(ring):
        dpg.configure_item(
            ring,
            points=_meter_ring_points(master_level),
            color=_meter_colour(master_level),
        )


def _refresh_ui(runtime: AppRuntime, dt: float = 1.0 / 60.0) -> None:
    """Copy inexpensive audio telemetry onto the UI thread."""
    _refresh_scope(runtime)
    if not dpg.does_item_exist(OUTPUT_METER):
        return
    # The engine reports a per-block peak, which flickers when drawn raw.
    # Peak-programme ballistics rise instantly and fall on a known slope.
    level = min(1.0, METER_BALLISTICS.advance(runtime.audio.last_peak, dt))
    dpg.set_value(OUTPUT_METER, level)
    _refresh_console_meters(runtime, dt, level)
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


LAST_FRAME_ERROR: list[str] = [""]


def _report_frame_error(exc: BaseException) -> None:
    message = f"{type(exc).__name__}: {exc}"
    if LAST_FRAME_ERROR[0] == message:
        return
    LAST_FRAME_ERROR[0] = message
    _set_patch_status(f"FRAME ERROR  ·  {message}"[:110], error=True)
    print(f"noodler: frame error: {message}", file=sys.stderr)


def _refresh_frame(
    _sender: str,
    _app_data: object,
    runtime: AppRuntime,
) -> None:
    # One clamped timestep drives every animation, so the rack feels the same
    # on a 60 Hz monitor as on a 120 Hz panel, and a frame hitch resumes
    # motion rather than teleporting it.
    replacement = _consume_pending_open()
    if replacement is not None:
        ACTIVE_RUNTIME[:] = [replacement]
        dpg.set_frame_callback(
            dpg.get_frame_count() + 1, _refresh_frame, user_data=replacement
        )
        return
    if ACTIVE_RUNTIME:
        runtime = ACTIVE_RUNTIME[0]
    dt = clamp_timestep(dpg.get_delta_time())
    try:
        _release_stale_key_latches()
        _settle_space_tap()
        _consume_scroll()
        _reveal_rack_once()
        _settle_library_layout()
        _consume_macos_magnification()
        _glide_rack(dt)
        _settle_recenter(dt)
        _settle_rack_zoom(dt)
        _settle_rack_rails(dt)
        _settle_console()
        _park_default_effects()
        _refresh_clock(dt)
        _refresh_ui(runtime, dt)
        _refresh_transport_button(runtime)
        _refresh_jack_activity(runtime)
        _refresh_console_cables(runtime)
        _refresh_selection()
        _show_export_messages()
        _refresh_outline_parameters()
        _refresh_outline_links()
        _refresh_knob_hover()
        _refresh_window_title_if_changed()
        _refresh_module_close_buttons()
    except Exception as exc:  # noqa: BLE001 - the heartbeat must not stop
        # One bad frame must not take the interface with it: everything that
        # moves -- scroll-to-pan, glide, the springs, the meters -- runs from
        # here, and an exception that escaped would never schedule the next
        # frame. Say what happened, once, and keep going.
        _report_frame_error(exc)
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
    """Every jack shows on an open module; only the patched ones on a collapsed one."""
    connected = _connected_port_ids(binding.patch, binding.module_id)
    collapsed = MODULE_COLLAPSE.is_collapsed(binding.node_tag)
    for port_id in binding.port_ids:
        tag = f"{binding.node_tag}.{port_id}"
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=not collapsed or port_id in connected)
    if dpg.does_item_exist(binding.status_tag):
        dpg.set_value(binding.status_tag, _patch_bay_flow_label(binding, connected))


def _refresh_patch_bays(patch: PatchGraph) -> None:
    _console_titles(patch)
    _refresh_patch_bay_labels(patch)


def _refresh_patch_bay_labels(patch: PatchGraph) -> None:
    for binding in PATCH_BAYS.values():
        if binding.patch is patch:
            _refresh_patch_bay(binding)


def _add_patch_bay_toggle(
    patch: PatchGraph,
    module_id: str,
    node_tag: str,
    port_ids: tuple[str, ...],
) -> None:
    """Add the signal-path row that says how many jacks are in use."""
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
    dpg.add_text(
        _patch_bay_flow_label(binding, connected),
        tag=binding.status_tag,
        color=MUTED_TEXT,
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
    rect = _rack_screen_rect()
    if rect is None:
        return False
    mouse_x, mouse_y = screen_position
    left, top, right, bottom = rect
    return left <= mouse_x <= right and top <= mouse_y <= bottom


def _mouse_is_over_rack() -> bool:
    if not dpg.does_item_exist(RACK):
        return False
    if bool(dpg.get_item_state(RACK).get("hovered", False)):
        return True
    return _point_is_over_rack(tuple(dpg.get_mouse_pos(local=False)))


NODE_HIT_MARGIN_X = 14.0
NODE_HIT_MARGIN_Y = 8.0
"""How far past a module's reported box a press still belongs to the module.

The editor reports a module's content box, not its panel: the padding, the
border and -- most of all -- the jacks, drawn astride the panel's edge, lie
outside it. A press on a jack that counted as empty canvas armed a pan, and
dragging the cable out dragged the whole rack with it.
"""


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
        try:
            if dpg.is_item_hovered(node):
                return False
            minimum_x, minimum_y = dpg.get_item_rect_min(node)
            maximum_x, maximum_y = dpg.get_item_rect_max(node)
        except (KeyError, SystemError):
            continue
        if (
            minimum_x - NODE_HIT_MARGIN_X <= mouse_x <= maximum_x + NODE_HIT_MARGIN_X
            and minimum_y - NODE_HIT_MARGIN_Y <= mouse_y <= maximum_y + NODE_HIT_MARGIN_Y
        ):
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
    if _is_pinned(node):
        # The console does not zoom with the rack: a fader is a fader.
        return
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
        if _is_pinned(node) or not dpg.does_item_exist(node):
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
        _resize_knob(knob, round(binding.size * new_zoom))

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


WHEEL_LINES = 48.0
"""Rack pixels one notch of a plain mouse wheel is worth."""


def _capture_macos_scroll(delta_x: float, delta_y: float) -> None:
    """Collect native two-axis scrolling for the next frame."""
    interaction = CANVAS_INTERACTION
    interaction.native_scroll = True
    if math.isfinite(delta_x):
        interaction.pending_scroll_x += float(delta_x)
    if math.isfinite(delta_y):
        interaction.pending_scroll_y += float(delta_y)


SCROLL_SWEEP_PIXELS = 1_600.0
"""How far the wheel travels to take a knob from one end to the other. A click
of a mouse wheel is 48 of these, so about three per cent a click; a trackpad
gives fractions of it and turns the knob smoothly."""
SCROLL_TURN: dict[str, object] = {"knob": None, "start": 0.0, "at": 0.0}
SCROLL_TURN_SETTLE = 0.6
"""A pause this long ends a scroll-turn, and the whole of it becomes one edit."""


def _turn_knob_by_scroll(knob: int | str, delta_y: float) -> None:
    """Scrolling over a knob turns it. Up is more; shift is finer."""
    binding = KNOB_INTERACTION.bindings.get(knob)
    if binding is None:
        return
    minimum, maximum = _knob_bounds(binding)
    span = maximum - minimum
    fine = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
    step = delta_y / SCROLL_SWEEP_PIXELS * span * (0.2 if fine else 1.0)
    now = time.monotonic()
    if SCROLL_TURN["knob"] != knob:
        _close_scroll_turn()
        SCROLL_TURN.update(knob=knob, start=_knob_position(knob), at=now)
    SCROLL_TURN["at"] = now
    position = min(maximum, max(minimum, _knob_position(knob) + step))
    _move_knob(knob, position)
    if dpg.does_item_exist(CONTROL_STATUS):
        value = _control_value(position, binding)
        dpg.set_value(
            CONTROL_STATUS,
            f"{binding.label.upper()}  {binding.formatter(value)}  ·  "
            + ("FINE" if fine else "SCROLL  ·  SHIFT = FINE"),
        )


def _close_scroll_turn(force: bool = False) -> None:
    """Record a finished scroll-turn as one edit."""
    knob = SCROLL_TURN["knob"]
    if knob is None:
        return
    if not force and time.monotonic() - float(SCROLL_TURN["at"]) < SCROLL_TURN_SETTLE:
        return
    SCROLL_TURN["knob"] = None
    _record_knob_turn(knob, float(SCROLL_TURN["start"]), _knob_position(knob))


def _consume_scroll() -> None:
    """Apply one frame of scrolling to the rack.

    Scrolling moves the rack -- unless it is over a knob, in which case it
    turns the knob. It is not a second way to zoom: zooming is what pinching
    does, and what the − / + controls do, and a gesture that means two things
    means neither reliably.
    """
    interaction = CANVAS_INTERACTION
    delta_x = interaction.pending_scroll_x
    delta_y = interaction.pending_scroll_y
    interaction.pending_scroll_x = 0.0
    interaction.pending_scroll_y = 0.0
    _close_scroll_turn()
    if not (delta_x or delta_y):
        return
    hovered = _hovered_knob()
    if hovered is not None and delta_y:
        _turn_knob_by_scroll(hovered[0], delta_y)
        return
    interaction.stop_glide()
    _translate_rack(delta_x, delta_y)


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


def _scroll_rack(
    _sender: int | str,
    delta: float,
    _user_data: object = None,
) -> None:
    """Scroll the rack from Dear PyGui's wheel, where nothing native reports it."""
    if CANVAS_INTERACTION.native_scroll or not _mouse_is_over_rack():
        return
    _capture_macos_scroll(0.0, float(delta) * WHEEL_LINES)
    CANVAS_INTERACTION.native_scroll = False


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


CONSOLE_BAND_ESTIMATE = 150.0
"""Height reserved along the bottom for the console before it is measured."""


def _console_band() -> float:
    """How much of the canvas, from the bottom, the console occupies."""
    tallest = 0.0
    for node in PINNED_NODES:
        if dpg.does_item_exist(node):
            height = float(dpg.get_item_rect_size(node)[1])
            tallest = max(tallest, height)
    if tallest <= 1.0:
        return CONSOLE_BAND_ESTIMATE
    return tallest + JACK_POST_LIFT + CONSOLE_MARGIN * 2.0


def _rack_view_size() -> tuple[float, float]:
    """The part of the canvas the rack may use: everything above the console.

    Centring, framing and revealing all reason about "the visible area", and
    the console is furniture standing in the bottom of it. Placing a module
    where the console is puts it underneath the console.
    """
    view_width, view_height = (float(v) for v in dpg.get_item_rect_size(RACK))
    if view_height > 1.0:
        view_height = max(1.0, view_height - _console_band())
    return view_width, view_height


def _is_pinned(node: int | str) -> bool:
    """Whether a node belongs to the console rather than to the rack.

    OUTPUT_NODE is the master's tag and has no node of its own any more; it
    still counts, so nothing tries to move or remove the console through it.
    """
    return node == OUTPUT_NODE or node in PINNED_NODES


def _is_console_control(knob: int | str) -> bool:
    return isinstance(knob, str) and knob.startswith(CONSOLE_PREFIX)


def _rack_content_bounds() -> tuple[float, float, float, float] | None:
    """Return the editor-local box containing every mounted module.

    Not the master: it is pinned to the corner, so including it would mean the
    camera framed a box that is partly nailed to the window and partly not.
    """
    boxes = []
    for node in RACK_NODES:
        if _is_pinned(node) or not dpg.does_item_exist(node):
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
    view_width, view_height = _rack_view_size()
    pan_x, pan_y = _editor_pan()
    content_width = max(1.0, maximum_x - minimum_x)
    content_height = max(1.0, maximum_y - minimum_y)

    if view_width > 1.0 and view_height > 1.0:
        fit = min(
            (view_width - FRAME_MARGIN * 2.0) / content_width,
            (view_height - FRAME_MARGIN * 2.0) / content_height,
        )
        _queue_rack_zoom(interaction.zoom * max(0.05, fit), screen_anchor=None)
        target_x = view_width * 0.5 - pan_x
        target_y = view_height * 0.5 - pan_y
    else:
        # Without a laid-out viewport, centring is all that can be honoured.
        target_x = (minimum_x + maximum_x) * 0.5
        target_y = (minimum_y + maximum_y) * 0.5

    interaction.recenter_x.snap(0.0)
    interaction.recenter_y.snap(0.0)
    interaction.recenter_x.retarget(target_x - (minimum_x + maximum_x) * 0.5)
    interaction.recenter_y.retarget(target_y - (minimum_y + maximum_y) * 0.5)
    _set_patch_status("FRAMED THE RACK  ·  PRESS F ANY TIME")


MIN_REVEAL_VIEWPORT = 320.0
"""Editor size below which a reveal is not believable, in pixels.

A viewport reports a small non-zero size for the first frames of its life. Two
pixels passes any "is it laid out yet" test that only rejects zero, and centring
against it moves the rack almost exactly as far left as the panel started —
which is precisely where the system output kept appearing, clipped by the edge.
"""

DRAG_EVIDENCE = 2.5
"""Pixels a panel must depart from its spring to count as dragged."""

REVEAL_PATIENCE = 240
"""Frames to wait for panels to be measured before centring anyway."""


def _rack_content_is_measured() -> bool:
    """Report whether every panel has been drawn at least once.

    Dear PyGui gives an item a size only after it has been rendered, so on the
    frames before that a panel measures zero by zero. Centring then centres a
    point rather than a rack, which puts the panel wherever its own corner
    happens to land — off the edge, as often as not.
    """
    measured = False
    for node in RACK_NODES:
        if _is_pinned(node) or not dpg.does_item_exist(node):
            continue
        width, height = dpg.get_item_rect_size(node)
        if float(width) <= 1.0 or float(height) <= 1.0:
            return False
        measured = True
    return measured


EDITOR_PAN_BASELINE: list[tuple[tuple[float, float], tuple[float, float]]] = []
"""What the editor's grid origin measured as, on screen, when nothing was panned:
(origin, rack size). Re-taken when the rack's size or layout changes."""


def _reset_editor_pan_baseline() -> None:
    EDITOR_PAN_BASELINE.clear()


def _editor_pan() -> tuple[float, float]:
    """How far imnodes has panned the whole editor by itself, on screen.

    Dear PyGui does not expose the editor's own panning -- middle-drag, or a
    trackpad gesture that lands there -- and it moves every node's picture
    without changing any node's position. It is measured instead: a strip's
    screen rectangle less its grid position is the grid origin plus the pan,
    and the pan is that less what it measured when nothing had been panned.
    """
    strip = CONSOLE_STRIP.format(channel=1)
    if not (dpg.does_item_exist(strip) and dpg.does_item_exist(RACK)):
        return 0.0, 0.0
    try:
        screen = dpg.get_item_rect_min(strip)
        grid = dpg.get_item_pos(strip)
        size = dpg.get_item_rect_size(RACK)
    except (KeyError, SystemError):
        return 0.0, 0.0
    if float(size[0]) <= 1.0 or float(size[1]) <= 1.0:
        return 0.0, 0.0
    origin = (float(screen[0]) - float(grid[0]), float(screen[1]) - float(grid[1]))
    measured_size = (float(size[0]), float(size[1]))
    if not EDITOR_PAN_BASELINE or EDITOR_PAN_BASELINE[0][1] != measured_size:
        # A new size means a new layout; take the origin as it is now.
        EDITOR_PAN_BASELINE[:] = [(origin, measured_size)]
        return 0.0, 0.0
    baseline = EDITOR_PAN_BASELINE[0][0]
    return origin[0] - baseline[0], origin[1] - baseline[1]


def _settle_console() -> None:
    """Hold the console strips in a row along the bottom edge of the canvas.

    Where everything goes should not be somewhere you can lose. The rack pans
    and zooms underneath; the strips stay put, left to right in channel order
    with the master at the end, so there is always somewhere to drag a cable.
    """
    if not dpg.does_item_exist(RACK):
        return
    view_width, view_height = (float(v) for v in dpg.get_item_rect_size(RACK))
    if view_width < MIN_REVEAL_VIEWPORT or view_height < MIN_REVEAL_VIEWPORT:
        return
    pan_x, pan_y = _editor_pan()
    x = CONSOLE_MARGIN
    for node in PINNED_NODES:
        if node in POST_ANCHORS or not dpg.does_item_exist(node):
            continue
        width, height = (float(v) for v in dpg.get_item_rect_size(node))
        if width <= 1.0 or height <= 1.0:
            return
        # Wanted on screen, less whatever the editor has panned by itself.
        wanted = [x - pan_x, view_height - height - CONSOLE_MARGIN - pan_y]
        if [round(v) for v in dpg.get_item_pos(node)] != [round(v) for v in wanted]:
            dpg.set_item_pos(node, wanted)
        x += width + CONSOLE_GAP
    # Then the jacks, standing on their strips: the post's left edge -- where
    # its pin is drawn -- at the strip's middle, its pin over the title bar.
    for post, (strip, across) in POST_ANCHORS.items():
        if not (dpg.does_item_exist(post) and dpg.does_item_exist(strip)):
            continue
        strip_x, strip_y = (float(v) for v in dpg.get_item_pos(strip))
        strip_width = float(dpg.get_item_rect_size(strip)[0])
        x = strip_x + strip_width * across
        if post in POST_OUTPUTS:
            x -= float(dpg.get_item_rect_size(post)[0])
        wanted = [x, strip_y - JACK_POST_LIFT]
        if [round(v) for v in dpg.get_item_pos(post)] != [round(v) for v in wanted]:
            dpg.set_item_pos(post, wanted)


def _reveal_rack_once() -> None:
    """Centre the rack the first frame it can actually be measured.

    Start-up positions are chosen before anything is laid out, against a window
    whose size is not known yet, so a coordinate that fits one machine puts the
    system output past the edge of another. Rather than tune the number, wait
    for a real viewport and real panels, then put the rack in the middle of it —
    once, so it never fights the user afterwards.
    """
    interaction = CANVAS_INTERACTION
    if not interaction.pending_reveal or not dpg.does_item_exist(RACK):
        return
    view_width, view_height = _rack_view_size()
    if view_width < MIN_REVEAL_VIEWPORT or view_height < MIN_REVEAL_VIEWPORT:
        return

    interaction.reveal_attempts += 1
    patient = interaction.reveal_attempts < REVEAL_PATIENCE
    if patient and not _rack_content_is_measured():
        return

    bounds = _rack_content_bounds()
    interaction.pending_reveal = False
    if bounds is None:
        return
    minimum_x, minimum_y, maximum_x, maximum_y = bounds
    pan_x, pan_y = _editor_pan()
    _translate_rack(
        view_width * 0.5 - pan_x - (minimum_x + maximum_x) * 0.5,
        view_height * 0.5 - pan_y - (minimum_y + maximum_y) * 0.5,
    )


def _reveal_node(node: int | str) -> bool:
    """Bring one module into view if it arrived outside the window.

    A module added while the rack is panned away lands somewhere the user is
    not looking, which reads as nothing having happened. The camera moves the
    shortest distance that makes the whole module visible, rather than
    re-framing everything and losing the user's place.
    """
    if not dpg.does_item_exist(RACK) or not dpg.does_item_exist(node):
        return False
    view_width, view_height = _rack_view_size()
    if view_width <= 1.0 or view_height <= 1.0:
        return False

    node_x, node_y = (float(value) for value in dpg.get_item_pos(node))
    pan_x, pan_y = _editor_pan()
    node_x += pan_x
    node_y += pan_y
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
    """Make room around an active module while leaving placement alone.

    Packing every rail on every frame did keep the rack tidy, but it took the
    one thing a rack is for: putting a module where you want it. A drag has to
    mean a position. Tidying is a thing the user asks for, not a rule the
    layout enforces -- see TIDY_TARGETS.
    """
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


def _module_depths(patch: PatchGraph) -> dict[str, int]:
    """How far along the signal each module sits, in cables from a source.

    The graph already knows: `processing_order` is a topological sort, so one
    pass over it in order settles the longest path to every module.
    """
    depths = {module_id: 0 for module_id in patch.modules}
    outgoing: dict[str, list[str]] = {module_id: [] for module_id in patch.modules}
    for cable in patch.cables:
        if cable.source.module_id in outgoing:
            outgoing[cable.source.module_id].append(cable.target.module_id)
    for module_id in patch.processing_order:
        for target in outgoing.get(module_id, ()):
            depths[target] = max(depths.get(target, 0), depths[module_id] + 1)
    return depths


def _tidy_rack(
    _sender: int | str = 0,
    _app_data: object = None,
    runtime: AppRuntime | None = None,
) -> None:
    """Order every rail by the way signal actually runs through the patch.

    Left to right is the one thing a rack layout has to say, and the patch
    already knows it. Ordering by depth means the arrangement is a reading of
    the instrument rather than a record of what was added when — and packing
    does the spacing, so this never has to touch a coordinate.
    """
    if runtime is None or _keyboard_is_captured():
        return
    depths = _module_depths(runtime.patch)
    furthest = max(depths.values(), default=0)
    node_depth = {
        node: depths.get(instance_id, 0)
        for instance_id, node in INSTANCE_NODE_TAGS.items()
    }
    TIDY_TARGETS.clear()
    gap = RACK_RAIL_GAP * CANVAS_INTERACTION.zoom
    ordered = sorted(
        (
            node
            for node in RACK_NODES
            if not _is_pinned(node) and dpg.does_item_exist(node)
        ),
        key=lambda node: (
            node_depth.get(node, 0),
            float(dpg.get_item_pos(node)[0]),
        ),
    )
    if not ordered:
        return
    view_width = float(dpg.get_item_rect_size(RACK)[0]) or 1_200.0
    origin_x = min(float(dpg.get_item_pos(node)[0]) for node in ordered)
    origin_y = min(float(dpg.get_item_pos(node)[1]) for node in ordered)
    cursor_x, cursor_y, row_height = origin_x, origin_y, 0.0
    for node in ordered:
        size = dpg.get_item_rect_size(node)
        width = max(120.0, float(size[0]))
        height = max(80.0, float(size[1]))
        if cursor_x > origin_x and cursor_x + width > origin_x + view_width - gap:
            cursor_x = origin_x
            cursor_y += row_height + gap
            row_height = 0.0
        TIDY_TARGETS[node] = (cursor_x, cursor_y)
        cursor_x += width + gap
        row_height = max(row_height, height)
    _set_patch_status("TIDIED  ·  RAILS NOW FOLLOW THE SIGNAL")


def _reflow_rail_lanes() -> None:
    """Keep the audio lane clear of whatever height the control lane needs.

    The lanes sat at fixed heights chosen when panels were short, so a tall
    control module simply grew down through the audio path. Overlapping panels
    are not only hard to read: they make every drag ambiguous, because two
    modules claim the same pointer.
    """
    rail_y = CANVAS_INTERACTION.rail_y
    if CONTROL_RAIL not in rail_y or AUDIO_RAIL not in rail_y:
        return
    tallest = 0.0
    for node in RACK_RAILS[CONTROL_RAIL]:
        if dpg.does_item_exist(node):
            tallest = max(tallest, float(dpg.get_item_rect_size(node)[1]))
    if tallest <= 1.0:
        return
    rail_y[AUDIO_RAIL] = (
        rail_y[CONTROL_RAIL]
        + tallest
        + RACK_RAIL_GAP * CANVAS_INTERACTION.zoom
    )


def _item_reports(item: int | str, state: str) -> bool:
    """Read one interaction state, for items that publish it.

    Dear PyGui's is_item_active indexes the state dictionary directly, and a
    node does not publish an "active" key at all — so asking raised KeyError
    every frame rather than answering False.
    """
    try:
        return bool(dpg.get_item_state(item).get(state, False))
    except (KeyError, SystemError, TypeError):
        return False


def _dragged_rack_node() -> int | str | None:
    """Return the module the pointer is actually dragging.

    Asking which rectangle contains the pointer answers the wrong question once
    panels overlap: the first module in list order wins every drag, and every
    other module is sprung back as though it had never been touched. A node
    does report whether it is hovered, which is the same question asked of the
    one item that can answer it; geometry, front to back, is the fallback.
    """
    if CANVAS_INTERACTION.panning or not dpg.is_mouse_button_dragging(
        dpg.mvMouseButton_Left,
        threshold=1.0,
    ):
        return None
    for node in reversed(RACK_NODES):
        if dpg.does_item_exist(node) and _item_reports(node, "hovered"):
            return node
    mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
    for node in reversed(RACK_NODES):
        if not dpg.does_item_exist(node):
            continue
        minimum_x, minimum_y = dpg.get_item_rect_min(node)
        maximum_x, maximum_y = dpg.get_item_rect_max(node)
        if minimum_x <= mouse_x <= maximum_x and minimum_y <= mouse_y <= maximum_y:
            return node
    return None


def _node_that_moved() -> int | str | None:
    """Find the module that has left its spring behind.

    Identifying a drag by asking which item is hovered, or which rectangle holds
    the pointer, is inference — and it has been wrong in every arrangement where
    panels sit close together or a new one has just been added. Dear PyGui moves
    a dragged node itself, so the node whose position no longer matches the
    spring that was driving it *is* the one under the pointer. That is evidence
    rather than a guess, and it needs no state the item may not publish.
    """
    if CANVAS_INTERACTION.panning or not dpg.is_mouse_button_dragging(
        dpg.mvMouseButton_Left,
        threshold=1.0,
    ):
        return None
    moved: int | str | None = None
    furthest = DRAG_EVIDENCE
    for node, (spring_x, spring_y) in RAIL_SPRINGS.items():
        if not dpg.does_item_exist(node):
            continue
        position = dpg.get_item_pos(node)
        distance = abs(spring_x.value - float(position[0])) + abs(
            spring_y.value - float(position[1])
        )
        if distance > furthest:
            moved, furthest = node, distance
    return moved


def _settle_rack_rails(dt: float = 1.0 / 60.0) -> None:
    """Carry modules to wherever TIDY asked them to go, and nowhere else.

    The rails are gone. They snapped a module to a lane and shuffled its
    neighbours aside, which meant a rack could be arranged but never trusted:
    the layout kept having opinions after the hand had let go. A module now
    stays exactly where it was put, and rearranging is something asked for.
    """
    if CANVAS_INTERACTION.panning or not TIDY_TARGETS:
        return
    active_node = _dragged_rack_node() or _node_that_moved()
    for node, (target_x, target_y) in tuple(TIDY_TARGETS.items()):
        if not dpg.does_item_exist(node) or node == active_node:
            TIDY_TARGETS.pop(node, None)
            continue
        position = dpg.get_item_pos(node)
        current_x, current_y = float(position[0]), float(position[1])
        spring_x, spring_y = _rail_springs(node, current_x, current_y)
        if abs(spring_x.value - current_x) > 1.0:
            spring_x.snap(current_x)
        if abs(spring_y.value - current_y) > 1.0:
            spring_y.snap(current_y)
        spring_x.retarget(target_x)
        spring_y.retarget(target_y)
        next_x = spring_x.advance(dt)
        next_y = spring_y.advance(dt)
        if round(next_x) != round(current_x) or round(next_y) != round(current_y):
            dpg.set_item_pos(node, [next_x, next_y])
        if spring_x.settled and spring_y.settled:
            TIDY_TARGETS.pop(node, None)


def _clear_rack_selection() -> None:
    if dpg.does_item_exist(RACK):
        dpg.clear_selected_nodes(RACK)
        dpg.clear_selected_links(RACK)


def _add_module_context_menus(runtime: AppRuntime) -> None:
    """Give every mounted module its right-click menu."""
    for instance_id, node in INSTANCE_NODE_TAGS.items():
        if instance_id in runtime.patch.modules and not _is_pinned(node):
            _add_module_context_menu(node, runtime)


def _context_menu_tag(node: int | str) -> str:
    return f"{node}.context"


def _add_module_context_menu(node: int | str, runtime: AppRuntime) -> None:
    """Right-click a module for the four things done to one.

    Fold it away, put its controls back where they were built, pull every
    cable out of it, or remove it -- each already existed as a gesture or a
    menu, and each was one more thing to know. A right-click on the module is
    where a hand goes to ask.
    """
    if _is_pinned(node) or not dpg.does_item_exist(node):
        return
    tag = _context_menu_tag(node)
    if dpg.does_item_exist(tag):
        return
    with dpg.popup(node, mousebutton=dpg.mvMouseButton_Right, tag=tag):
        dpg.add_menu_item(
            label="Fold / Unfold",
            callback=lambda: _set_module_collapsed(
                node, not MODULE_COLLAPSE.is_collapsed(node), runtime
            ),
        )
        dpg.add_menu_item(
            label="Duplicate",
            callback=lambda: _duplicate_module(node, runtime),
        )
        dpg.add_menu_item(
            label="Reset controls",
            callback=lambda: _reset_module_controls(node),
        )
        dpg.add_menu_item(
            label="Unplug all cables",
            callback=lambda: _unplug_module(node, runtime),
        )
        dpg.add_separator()
        dpg.add_menu_item(
            label="Remove",
            callback=lambda: _remove_module_node(node, runtime),
        )


def _knobs_in_node(node: int | str) -> list[int | str]:
    """Every rotary control that lives on one module panel."""
    found: list[int | str] = []
    pending = [node]
    while pending:
        item = pending.pop()
        for slot in dpg.get_item_children(item).values():
            for child in slot:
                if child in KNOB_INTERACTION.bindings:
                    found.append(child)
                else:
                    alias = dpg.get_item_alias(child)
                    if alias and alias in KNOB_INTERACTION.bindings:
                        found.append(alias)
                        continue
                    pending.append(child)
    return found


def _reset_module_controls(node: int | str) -> None:
    """Every knob on the panel back to the value it was built with."""
    count = 0
    for knob in _knobs_in_node(node):
        binding = KNOB_INTERACTION.bindings.get(knob)
        if binding is not None and _reset_knob_to_default(knob, binding):
            count += 1
    _set_patch_status(f"RESET  {count} CONTROL{'S' if count != 1 else ''}")


def _unplug_module(node: int | str, runtime: AppRuntime) -> None:
    """Pull every cable out of one module, as one undoable edit."""
    instance_id = _module_id_for_node(node)
    if instance_id is None:
        return
    routes = _routes_touching(runtime.patch, instance_id)
    if not routes:
        _set_patch_status("NOTHING PATCHED HERE")
        return
    _erase_routes(runtime, routes)
    _record_edit(
        f"UNPLUG {instance_id.upper()}",
        undo=lambda: _restore_routes(runtime, routes),
        redo=lambda: _erase_routes(runtime, routes),
    )
    noun = "CABLE" if len(routes) == 1 else "CABLES"
    _set_patch_status(f"UNPLUGGED  {instance_id.upper()}  ·  {len(routes)} {noun}")


def _node_attributes(node: int | str) -> tuple[int | str, ...]:
    """Return the immediate node attributes that make up a module panel."""
    return tuple(
        child
        for child in dpg.get_item_children(node).get(1, ())
        if dpg.get_item_type(child) == "mvAppItemType::mvNodeAttribute"
    )


def _route_node_tags(route: Cable | OutputTap) -> set[int | str]:
    if isinstance(route, Cable):
        return {
            INSTANCE_NODE_TAGS[route.source.module_id],
            INSTANCE_NODE_TAGS[route.target.module_id],
        }
    return {INSTANCE_NODE_TAGS[route.source.module_id], OUTPUT_NODE}


def _module_title_height() -> float:
    return max(24.0, min(44.0, 32.0 * CANVAS_INTERACTION.zoom))


def _module_close_bounds(
    node: int | str,
) -> tuple[float, float, float, float] | None:
    """Return the screen-space close target at a module title's right edge."""
    if (
        _is_pinned(node)
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


def _set_attribute_text_shown(attribute: int | str, shown: bool) -> None:
    """Show or hide what is written beside a jack, leaving the jack itself."""
    if not dpg.does_item_exist(attribute):
        return
    for child in dpg.get_item_children(attribute, 1) or ():
        dpg.configure_item(child, show=shown)


def _patched_attributes(node: int | str, patch: PatchGraph) -> set[int | str]:
    """The jacks on one module that currently have a cable in them."""
    instance_id = _module_id_for_node(node)
    tags: set[str] = set()
    if instance_id is not None:
        for cable in patch.cables:
            if cable.source.module_id == instance_id:
                tags.add(f"{node}.{cable.source.port_id}")
            if cable.target.module_id == instance_id:
                tags.add(f"{node}.{cable.target.port_id}")
        for tap in patch.output_taps:
            if tap.source.module_id == instance_id:
                tags.add(f"{node}.{tap.source.port_id}")
    # Attributes are handled by item id, so resolve the tags to ids: comparing
    # the two kinds silently matched nothing.
    live: set[int | str] = set()
    for tag in tags:
        if dpg.does_item_exist(tag):
            live.add(dpg.get_alias_id(tag))
            live.add(tag)
    return live


def _attribute_port_id(attribute: int | str) -> str | None:
    alias = dpg.get_item_alias(attribute)
    return alias.rsplit(".", 1)[-1] if alias else None


def _apply_collapse(node: int | str, runtime: AppRuntime) -> None:
    """Show a collapsed module as its title and the jacks with cables in them.

    Everything else -- controls, the open jacks, the signal-path row -- is put
    away. What stays is what the module is *doing*: the cables still land
    somewhere visible, and the name says what it is.
    """
    instance_id = _module_id_for_node(node)
    connected = (
        _connected_port_ids(runtime.patch, instance_id) if instance_id else set()
    )
    for attribute in _node_attributes(node):
        kind = dpg.get_item_configuration(attribute).get("attribute_type")
        if kind == dpg.mvNode_Attr_Static:
            dpg.configure_item(attribute, show=False)
            continue
        port_id = _attribute_port_id(attribute)
        dpg.configure_item(attribute, show=port_id in connected)


def _set_module_collapsed(
    node: int | str,
    collapsed: bool,
    runtime: AppRuntime,
) -> None:
    """Collapse a module to its title and its patched jacks, or open it again.

    Collapsed, a module is what it is doing: its name, and the jacks that have
    cables in them. Open, it is everything -- every control and every jack,
    patched or not. There is no third state; a jack with nothing in it is
    hidden by collapsing and shown by opening, which is what "hide open" was.
    """
    if not dpg.does_item_exist(node):
        return
    state = MODULE_COLLAPSE
    label = str(dpg.get_item_configuration(node)["label"])
    if collapsed:
        if state.is_collapsed(node):
            return
        state.attributes[node] = {
            attribute: bool(dpg.get_item_configuration(attribute)["show"])
            for attribute in _node_attributes(node)
        }
        state.labels[node] = label
        _apply_collapse(node, runtime)
        _set_patch_status(f"COLLAPSED  {label}")
        return

    visibility = state.attributes.pop(node, None)
    state.labels.pop(node, None)
    if visibility is None:
        return
    for attribute in visibility:
        if dpg.does_item_exist(attribute):
            # Open means open: every control and every jack.
            dpg.configure_item(attribute, show=True)
            _set_attribute_text_shown(attribute, True)
    _refresh_patch_bays(runtime.patch)
    _set_patch_status(f"OPENED  {label}")


def _move_knob(knob: int | str, position: float) -> None:
    """Put a knob at a position and tell its module: what undo and redo do."""
    binding = KNOB_INTERACTION.bindings.get(knob)
    if binding is None or not dpg.does_item_exist(knob):
        return
    _set_knob_position(knob, position)
    _set_knob_value(str(knob), position, binding)


def _record_knob_turn(knob: int | str, before: float, after: float) -> None:
    """One whole turn of a knob is one edit, however many frames it took."""
    if abs(after - before) < 1e-9:
        return
    binding = KNOB_INTERACTION.bindings.get(knob)
    if binding is None:
        return
    _record_edit(
        f"TURN {binding.label.upper()}",
        undo=lambda: _move_knob(knob, before),
        redo=lambda: _move_knob(knob, after),
    )


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
    before = _knob_position(knob)
    _set_knob_position(knob, position)
    _set_knob_value(str(knob), position, binding)
    _record_knob_turn(knob, before, position)
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

    Over a control it restores the default; over a cable it unpatches; over a
    module title it collapses the module to its title and its patched jacks
    (or opens it again). Pulling a cable out is
    the commonest edit in a rack and the least discoverable one here, since a
    node editor gives no way to drag a plug back out of its jack.
    """
    hovered = _hovered_knob()
    if hovered is not None and _reset_knob_to_default(*hovered):
        return
    console_cable = _console_cable_near(tuple(float(v) for v in dpg.get_mouse_pos(local=False)))
    if console_cable is not None:
        _patch_link_deleted(RACK, console_cable, runtime)
        return
    if dpg.does_item_exist(RACK):
        selected = tuple(dpg.get_selected_links(RACK))
        if selected:
            for link in selected:
                _patch_link_deleted(RACK, link, runtime)
            _clear_rack_selection()
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
        label="HIDE LIBRARY",
        tag=LIBRARY_PANE_BUTTON,
        callback=_toggle_library_pane,
    )
    with dpg.tooltip(LIBRARY_PANE_BUTTON):
        dpg.add_text("Collapse the library pane and give the room to the rack.  ·  L")
    dpg.add_button(
        label="TIDY",
        tag=TIDY_RACK_BUTTON,
        callback=_tidy_rack,
        user_data=runtime,
    )
    with dpg.tooltip(TIDY_RACK_BUTTON):
        dpg.add_text("Order the rails by the way signal flows.  ·  T")
    dpg.add_button(
        label="UNPLUG ALL",
        tag=UNPLUG_ALL_BUTTON,
        callback=_unplug_all,
        user_data=runtime,
    )
    with dpg.tooltip(UNPLUG_ALL_BUTTON):
        dpg.add_text("Disconnect every cable from the live patch.  ·  ⌘Z undoes it.")



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


SPACE_TAP: dict[str, float | bool] = {"down_at": 0.0, "panned": False, "down": False}
SPACE_TAP_SECONDS = 0.35
"""A press of space shorter than this, with no pan in it, is a tap: play or stop.

Space held while dragging is the pan modifier and stays so; a tap that turned
into a pan is not a tap. This is the one gesture every DAW shares.
"""


def _space_pressed(_sender: int | str, _app_data: object, _runtime: AppRuntime) -> None:
    if _keyboard_is_captured():
        return
    SPACE_TAP["down"] = True
    SPACE_TAP["down_at"] = time.monotonic()
    SPACE_TAP["panned"] = False


def _space_released(_sender: int | str = 0, _app_data: object = None, runtime: AppRuntime | None = None) -> None:
    if not SPACE_TAP["down"]:
        return
    SPACE_TAP["down"] = False
    held = time.monotonic() - float(SPACE_TAP["down_at"])
    if SPACE_TAP["panned"] or held > SPACE_TAP_SECONDS or _keyboard_is_captured():
        return
    _toggle_playback(0, None, runtime)


def _settle_space_tap() -> None:
    """Notice space coming up, from the frame loop.

    The key-release handler is kept, but the frame loop asks the key state
    directly as well -- the same question the pan modifier asks, and one that
    is known to be answered -- so a tap is never lost to a release event that
    did not arrive.
    """
    if SPACE_TAP["down"] and not dpg.is_key_down(dpg.mvKey_Spacebar):
        _space_released()


def _release_stale_key_latches() -> None:
    """Let go of any latched key that is no longer down.

    Reconciling against the real key state each frame means a press whose
    release never arrives — a lost focus, a window switch — cannot leave a
    shortcut stuck.
    """
    for key in tuple(KEY_LATCH):
        if not dpg.is_key_down(key):
            KEY_LATCH.discard(key)


def _library_pane_is_inline() -> bool:
    """Report whether this rack has a library pane at all."""
    return dpg.does_item_exist(MODULE_SELECTOR)


def _set_library_pane(visible: bool) -> None:
    """Show or hide the side pane, letting the canvas take the room back."""
    if not _library_pane_is_inline():
        return
    dpg.configure_item(MODULE_SELECTOR, show=visible)
    if dpg.does_item_exist(LIBRARY_PANE_BUTTON):
        dpg.configure_item(
            LIBRARY_PANE_BUTTON,
            label="HIDE LIBRARY" if visible else "SHOW LIBRARY",
        )


def _toggle_library_pane(
    _sender: int | str = 0,
    _app_data: object = None,
    _user_data: object = None,
) -> None:
    """Collapse the whole side pane, and bring it back."""
    if _keyboard_is_captured() or not _library_pane_is_inline():
        return
    visible = not dpg.is_item_shown(MODULE_SELECTOR)
    _set_library_pane(visible)
    _set_patch_status(
        "LIBRARY SHOWN  ·  L HIDES IT" if visible else "LIBRARY HIDDEN  ·  L BRINGS IT BACK"
    )


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
    CANVAS_INTERACTION.pan_moved = False
    RACK_CURSOR.grab()
    CANVAS_INTERACTION.last_mouse_x = float(mouse_x)
    CANVAS_INTERACTION.last_mouse_y = float(mouse_y)
    # The selection is not cleared here. A press on empty canvas may be a
    # click on a cable -- which selects it, so that a double-click can unpatch
    # it -- and only a press that goes on to move is a pan.
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
        # The console is pinned to the bottom edge; the camera does not carry it.
        if _is_pinned(node) or not dpg.does_item_exist(node):
            continue
        node_x, node_y = dpg.get_item_pos(node)
        dpg.set_item_pos(node, [node_x + delta_x, node_y + delta_y])
    for rail in tuple(CANVAS_INTERACTION.rail_y):
        CANVAS_INTERACTION.rail_y[rail] += delta_y
    # Carry the springs with the camera so they keep owning the sub-pixel
    # position rather than re-syncing to a truncated one.
    TIDY_TARGETS.clear()
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
    if (delta_x or delta_y) and not interaction.pan_moved:
        # The first frame that actually moves is when a press became a pan,
        # and the moment a selection made by that press is let go of.
        interaction.pan_moved = True
        _clear_rack_selection()
    _translate_rack(delta_x, delta_y)
    _track_pan_velocity(delta_x, delta_y)
    interaction.last_mouse_x = float(mouse_x)
    interaction.last_mouse_y = float(mouse_y)


def _add_rack_menu(runtime: AppRuntime) -> None:
    """Add the window menu, for the actions a toolbar should not carry.

    Framing is a recovery action rather than a working one: needed rarely, and
    worth a key rather than permanent space beside the controls used constantly.
    """
    with dpg.menu_bar(tag=RACK_MENU_BAR):
        with dpg.menu(label="File"):
            dpg.add_menu_item(
                label="New",
                tag=NEW_PATCH_MENU_ITEM,
                shortcut="⌘N",
                callback=_new_patch,
            )
            dpg.add_menu_item(
                label="Open…",
                tag=OPEN_PATCH_MENU_ITEM,
                shortcut="⌘O",
                callback=_show_open_patch_dialog,
            )
            with dpg.menu(label="Open Recent", tag=RECENT_MENU):
                pass
            _refresh_recent_menu()
            examples = _example_documents()
            if examples:
                with dpg.menu(label="Open Example", tag=EXAMPLES_MENU):
                    for document in examples:
                        dpg.add_menu_item(
                            label=document.stem.replace("-", " ").title(),
                            callback=_open_example,
                            user_data=document,
                        )
            dpg.add_separator()
            dpg.add_menu_item(
                label="Save",
                tag=SAVE_PATCH_MENU_ITEM,
                shortcut="⌘S",
                callback=_save_patch,
                user_data=runtime,
            )
            dpg.add_menu_item(
                label="Save As…",
                tag=SAVE_AS_MENU_ITEM,
                shortcut="⌘⇧S",
                callback=_show_save_patch_dialog,
                user_data=runtime,
            )
            dpg.add_separator()
            with dpg.menu(label="Export Audio", tag=EXPORT_MENU):
                for bars in EXPORT_BAR_CHOICES:
                    dpg.add_menu_item(
                        label=f"{bars} bars…",
                        callback=_choose_export,
                        user_data=(runtime, bars),
                    )
            dpg.add_separator()
            dpg.add_menu_item(
                label="Exit",
                tag=EXIT_MENU_ITEM,
                shortcut="⌘Q",
                callback=_exit_noodler,
            )
        with dpg.menu(label="View"):
            dpg.add_menu_item(
                label="Frame All",
                tag=FRAME_RACK_MENU_ITEM,
                shortcut="F",
                callback=_frame_rack,
                user_data=runtime,
            )
            dpg.add_menu_item(
                label="Tidy Rails",
                shortcut="T",
                callback=_tidy_rack,
                user_data=runtime,
            )
            dpg.add_menu_item(
                label="Library Pane",
                shortcut="L",
                callback=_toggle_library_pane,
                user_data=runtime,
            )
        with dpg.menu(label="Edit"):
            dpg.add_menu_item(
                label="Undo",
                shortcut="⌘Z",
                callback=lambda: _apply_history(False),
            )
            dpg.add_menu_item(
                label="Redo",
                shortcut="⌘⇧Z",
                callback=lambda: _apply_history(True),
            )
            dpg.add_separator()
            dpg.add_menu_item(
                label="Remove Selected",
                shortcut="⌫",
                callback=_delete_rack_selection,
                user_data=runtime,
            )
            dpg.add_menu_item(
                label="Unplug All",
                callback=_unplug_all,
                user_data=runtime,
            )
        with dpg.menu(label="Clock"):
            dpg.add_slider_float(
                tag=CLOCK_BPM_INPUT,
                label="Tempo",
                default_value=TRANSPORT.bpm,
                min_value=MIN_BPM,
                max_value=MAX_BPM,
                format="%.0f BPM",
                width=190,
                callback=_set_clock_bpm,
            )
            dpg.add_input_int(
                tag=CLOCK_BEATS_INPUT,
                label="Beats per bar",
                default_value=TRANSPORT.beats_per_bar,
                min_value=1,
                max_value=MAX_BEATS_PER_BAR,
                min_clamped=True,
                max_clamped=True,
                width=110,
                callback=_set_clock_signature,
            )
            dpg.add_combo(
                [str(unit) for unit in BEAT_UNITS],
                tag=CLOCK_UNIT_INPUT,
                label="Beat unit",
                default_value=str(TRANSPORT.beat_unit),
                width=110,
                callback=_set_clock_signature,
            )
            dpg.add_menu_item(
                label="Run / Stop",
                tag=CLOCK_RUN_ITEM,
                callback=_toggle_clock,
            )
            dpg.add_menu_item(
                label="Return to bar one",
                tag=CLOCK_REWIND_ITEM,
                callback=_rewind_clock,
            )
        # Pushed to the right edge each frame, where a transport belongs:
        # play, then the clock it runs.
        dpg.add_spacer(tag=CLOCK_SPACER, width=1)
        dpg.add_button(
            label="▶  PLAY",
            tag=TRANSPORT_BUTTON,
            callback=_toggle_playback,
            user_data=runtime,
        )
        dpg.add_text("", tag=CLOCK_READOUT, color=MUTED_TEXT)


def _settle_library_layout() -> None:
    """Give the rack outline whatever room the library is not using.

    A collapsed section that stays where it was leaves dead space above the
    fold; sending it to the bottom means folding the catalog away actually buys
    something — a longer view of the rack that is being built.
    """
    if not (
        dpg.does_item_exist(RACK_OUTLINE_BODY)
        and dpg.does_item_exist(MODULE_LIBRARY_HEADER)
    ):
        return
    open_library = bool(dpg.get_value(MODULE_LIBRARY_HEADER))
    wanted = RACK_OUTLINE_HEIGHT if open_library else -LIBRARY_HEADER_ROOM
    if dpg.get_item_configuration(RACK_OUTLINE_BODY)["height"] != wanted:
        dpg.configure_item(RACK_OUTLINE_BODY, height=wanted)


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
    if interaction.panning:
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
    if (
        CANVAS_INTERACTION.panning
        or CANVAS_INTERACTION.press_consumed
        or CANVAS_INTERACTION.press_classified
    ):
        # Dear PyGui repeats the mouse-down callback for every frame the button
        # is held. Beginning the pan again would move its origin to the current
        # pointer each frame, leaving the drag with nothing to travel; a press
        # already spent on a one-shot control must not become a drag; and a
        # press that began on a module -- a jack, say, with a cable being drawn
        # out of it -- must not be re-read as a press on empty canvas once the
        # pointer has left the module. What a press is, is decided on its
        # first frame.
        return
    CANVAS_INTERACTION.press_classified = True
    # Any press on the rack catches a gliding canvas, the way a finger does.
    CANVAS_INTERACTION.stop_glide()
    mouse_position = tuple(dpg.get_mouse_pos(local=False))
    close_node = _module_close_at(mouse_position)
    if runtime is not None and close_node is not None:
        CANVAS_INTERACTION.press_consumed = True
        _remove_module_node(close_node, runtime)
        return
    if dpg.is_key_down(dpg.mvKey_Spacebar) and _mouse_is_over_rack():
        # Dragging pans. Space is not a second way to pan: it is the modifier
        # that lets the same drag start from over a module rather than only
        # from empty background. And a space that panned was not a tap.
        SPACE_TAP["panned"] = True
        CANVAS_INTERACTION.arm_pan(mouse_position)
        _begin_canvas_pan(mouse_position)
        return
    for knob, binding in reversed(tuple(interaction.bindings.items())):
        if dpg.does_item_exist(knob) and dpg.is_item_hovered(knob):
            interaction.active_knob = knob
            interaction.drag_position = _knob_position(knob)
            interaction.drag_start = interaction.drag_position
            minimum, maximum = _knob_bounds(binding)
            interaction.drag.minimum = minimum
            interaction.drag.maximum = maximum
            interaction.drag.begin(interaction.drag_position)
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
        if dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift):
            # Panning owns a plain background drag, so box selection keeps the
            # modified one -- and only then is the marquee drawn, from here.
            _show_box_selector(True)
            CANVAS_INTERACTION.marquee_origin = (float(mouse_position[0]), float(mouse_position[1]))
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
        if canvas.press_consumed or canvas.marquee_origin is not None:
            # Spent on a control, or sweeping a marquee: neither is a pan.
            return
        if not canvas.drag_classified:
            # What a gesture is gets decided once, on the frame it starts, and
            # by the press: a drag pans only if the press armed it, from empty
            # background or with Space held. Re-deciding here from a recovered
            # origin was how a click on a module now and then became a pan.
            canvas.drag_classified = True
            canvas.drag_pans = canvas.pan_candidate
        if not canvas.drag_pans:
            return
        _begin_canvas_pan((canvas.press_x, canvas.press_y))
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
    _set_knob_position(knob, position)
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
    CANVAS_INTERACTION.marquee_origin = None
    CANVAS_INTERACTION.press_consumed = False
    CANVAS_INTERACTION.press_classified = False
    RACK_CURSOR.reset()
    if CANVAS_INTERACTION.panning:
        if CANVAS_INTERACTION.pan_moved:
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
    knob = interaction.active_knob
    interaction.active_knob = None
    _record_knob_turn(knob, interaction.drag_start, interaction.drag_position)
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
    if _is_pinned(node):
        _set_patch_status("THE CONSOLE CANNOT BE REMOVED", error=True)
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
    # Focus is the wrong question: Dear PyGui reports a field as focused for as
    # long as its window is, so asking that handed every shortcut to the search
    # box forever after the user went near it — L stopped bringing the library
    # back, having promised in writing that it would. A field only holds the
    # keyboard while it is being typed into, and a hidden one never is.
    if dpg.does_item_exist(MODULE_SELECTOR) and not dpg.is_item_shown(
        MODULE_SELECTOR
    ):
        # A collapsed pane cannot be typed into, whatever its field reports:
        # visibility is not inherited from a hidden ancestor.
        return False
    return (
        dpg.does_item_exist(MODULE_SELECTOR_SEARCH)
        and dpg.is_item_active(MODULE_SELECTOR_SEARCH)
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
    _apply_history(dpg.is_key_down(dpg.mvKey_ModShift))


def _apply_history(forward: bool) -> None:
    """Step the rack back or forward through its reversible edits."""
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


def _commanded() -> bool:
    """Whether a command chord is being held, on either platform's key."""
    return dpg.is_key_down(dpg.mvKey_ModSuper) or dpg.is_key_down(dpg.mvKey_ModCtrl)


def _quit_shortcut(
    sender: int | str,
    app_data: object,
    _runtime: AppRuntime,
) -> None:
    if _commanded():
        _exit_noodler(sender, app_data, None)


def _open_shortcut(
    sender: int | str,
    app_data: object,
    _runtime: AppRuntime,
) -> None:
    if _commanded() and not _keyboard_is_captured():
        _show_open_patch_dialog(sender, app_data, None)


def _new_shortcut(
    sender: int | str,
    app_data: object,
    _runtime: AppRuntime,
) -> None:
    if _commanded() and not _keyboard_is_captured():
        _new_patch(sender, app_data, None)


def _save_shortcut(
    sender: int | str,
    app_data: object,
    runtime: AppRuntime,
) -> None:
    """Command-S saves; adding Shift asks where to put it."""
    if not _commanded() or _keyboard_is_captured():
        return
    if dpg.is_key_down(dpg.mvKey_ModShift):
        _show_save_patch_dialog(sender, app_data, runtime)
    else:
        _save_patch(sender, app_data, runtime)


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
        dpg.add_mouse_wheel_handler(callback=_scroll_rack)
        # The rack has always advertised these keys; now they are wired.
        for key, action in (
            (dpg.mvKey_Delete, _delete_rack_selection),
            (dpg.mvKey_Back, _delete_rack_selection),
            (dpg.mvKey_Escape, _dismiss_rack_focus),
            (dpg.mvKey_K, _open_module_selector_shortcut),
            (dpg.mvKey_F, _frame_rack),
            (dpg.mvKey_T, _tidy_rack),
            (dpg.mvKey_L, _toggle_library_pane),
            (dpg.mvKey_Z, _undo_or_redo_rack_edit),
            (dpg.mvKey_Q, _quit_shortcut),
            (dpg.mvKey_O, _open_shortcut),
            (dpg.mvKey_N, _new_shortcut),
            (dpg.mvKey_Return, _play_shortcut),
            (dpg.mvKey_S, _save_shortcut),
        ):
            dpg.add_key_press_handler(
                key,
                callback=_press_once(key, action),
                user_data=runtime,
            )
        # A tap of space plays or stops; space held while dragging still pans.
        dpg.add_key_press_handler(
            dpg.mvKey_Spacebar,
            callback=_press_once(dpg.mvKey_Spacebar, _space_pressed),
            user_data=runtime,
        )
        dpg.add_key_release_handler(
            dpg.mvKey_Spacebar, callback=_space_released, user_data=runtime
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
    size: int = KNOB_SIZE,
    tag: int | str = 0,
    compact: bool = False,
    inset: float = 0.0,
) -> int | str:
    """Add a compact rotary control with a separate live value readout.

    ``compact`` drops the label above and the readout below, for a strip of
    knobs that share a header row -- a mixer channel -- where the value shows
    in the status bar while it is dragged and the arc says the rest.

    The knob is a drawlist, not Dear PyGui's knob widget: that one is drawn at
    a fixed forty pixels and ignores its width, which is how four rounds of
    "make the knobs smaller" changed nothing. This one is exactly the size it
    is asked to be. It keeps no value of its own -- the position lives in
    KNOB_INTERACTION and the picture is repainted from it -- and the drag
    gesture, the reset and the tooltip all go through the same helpers a
    widget's own callbacks would have.
    """
    size = max(KNOB_SIZE_MINIMUM, int(size))
    position = _control_position(value, minimum, maximum, logarithmic)
    plain_formatter = formatter
    formatter = lambda shown, inner=plain_formatter: _fit_column(inner(shown))
    with dpg.group() as cluster:
        if not compact:
            dpg.add_text(_fit_column(label.upper()), color=MUTED_TEXT)
        knob = dpg.add_drawlist(width=size, height=size, tag=tag)
        value_label = dpg.add_text(formatter(value), color=TEXT, show=not compact)
    binding = KnobBinding(
        setter=setter,
        label=label,
        value_label=value_label,
        minimum=minimum,
        maximum=maximum,
        formatter=formatter,
        logarithmic=logarithmic,
        size=size,
        default_value=value,
        inset=inset,
    )
    dpg.configure_item(knob, callback=_set_knob_value, user_data=binding)
    KNOB_INTERACTION.bindings[knob] = binding
    KNOB_INTERACTION.positions[knob] = position
    _paint_knob(knob, size)
    del cluster
    return knob


def _knob_geometry(
    knob: int | str, size: int
) -> tuple[tuple[float, float], float, float, list[tuple[float, float]]]:
    """Centre, radius, pointer angle and value-arc points for one knob."""
    binding = KNOB_INTERACTION.bindings[knob]
    minimum, maximum = _knob_bounds(binding)
    span = maximum - minimum
    position = KNOB_INTERACTION.positions.get(knob, minimum)
    fraction = 0.0 if span <= 0.0 else (position - minimum) / span
    fraction = min(1.0, max(0.0, fraction))
    centre = (size * 0.5, size * 0.5)
    radius = size * 0.5 - 1.0 - binding.inset
    sweep = KNOB_SWEEP_END - KNOB_SWEEP_START
    angle = KNOB_SWEEP_START + fraction * sweep
    # A bipolar knob -- pan, a polarizing gain -- draws its arc from zero, so
    # nothing is lit at rest and the arc says which way and how far. When the
    # range is symmetric, zero is straight up.
    if minimum < 0.0 < maximum and not binding.logarithmic:
        rest = KNOB_SWEEP_START + (0.0 - minimum) / span * sweep
    else:
        rest = KNOB_SWEEP_START
    start, end = (rest, angle) if angle >= rest else (angle, rest)
    steps = max(2, int(24 * abs(angle - rest) / sweep))
    arc = [
        (
            centre[0] + radius * math.cos(theta),
            centre[1] + radius * math.sin(theta),
        )
        for theta in (start + (end - start) * step / steps for step in range(steps + 1))
    ]
    return centre, radius, angle, arc


def _knob_track_points(size: int, inset: float = 0.0) -> list[tuple[float, float]]:
    centre = size * 0.5
    radius = size * 0.5 - 1.0 - inset
    return [
        (
            centre + radius * math.cos(theta),
            centre + radius * math.sin(theta),
        )
        for theta in (
            KNOB_SWEEP_START + (KNOB_SWEEP_END - KNOB_SWEEP_START) * step / 32
            for step in range(33)
        )
    ]


def _paint_knob(knob: int | str, size: int) -> None:
    """Draw a knob from scratch at a size: body, track, value arc, pointer."""
    art = KNOB_INTERACTION.art.get(knob)
    if art is not None:
        for part in (art.body, art.track, art.arc, art.pointer):
            if dpg.does_item_exist(part):
                dpg.delete_item(part)
    centre, radius, angle, arc = _knob_geometry(knob, size)
    thickness = max(1.0, size / 12.0)
    body = dpg.draw_circle(
        centre, radius, color=(0, 0, 0, 0), fill=KNOB_BODY, parent=knob
    )
    track = dpg.draw_polyline(
        _knob_track_points(size, KNOB_INTERACTION.bindings[knob].inset),
        color=KNOB_TRACK,
        thickness=thickness,
        parent=knob,
    )
    arc_item = dpg.draw_polyline(
        arc, color=KNOB_ARC, thickness=thickness, parent=knob
    )
    pointer = dpg.draw_line(
        (
            centre[0] + radius * 0.25 * math.cos(angle),
            centre[1] + radius * 0.25 * math.sin(angle),
        ),
        (
            centre[0] + radius * 0.85 * math.cos(angle),
            centre[1] + radius * 0.85 * math.sin(angle),
        ),
        color=TEXT,
        thickness=thickness,
        parent=knob,
    )
    KNOB_INTERACTION.art[knob] = KnobArt(size, body, track, arc_item, pointer)


def _repaint_knob(knob: int | str) -> None:
    """Move the value arc and the pointer; the body and track do not change."""
    art = KNOB_INTERACTION.art.get(knob)
    if art is None or not dpg.does_item_exist(art.pointer):
        return
    centre, radius, angle, arc = _knob_geometry(knob, art.size)
    dpg.configure_item(art.arc, points=arc)
    dpg.configure_item(
        art.pointer,
        p1=(
            centre[0] + radius * 0.25 * math.cos(angle),
            centre[1] + radius * 0.25 * math.sin(angle),
        ),
        p2=(
            centre[0] + radius * 0.85 * math.cos(angle),
            centre[1] + radius * 0.85 * math.sin(angle),
        ),
    )


def _knob_position(knob: int | str) -> float:
    """Where a knob is, in the units its binding drags in."""
    return KNOB_INTERACTION.positions.get(knob, 0.0)


def _set_knob_position(knob: int | str, position: float) -> None:
    """Move a knob's picture. Says nothing to the module: that is the setter's job."""
    KNOB_INTERACTION.positions[knob] = float(position)
    _repaint_knob(knob)


def _resize_knob(knob: int | str, size: int) -> None:
    """Draw a knob again at a new size, as zooming asks for."""
    size = max(KNOB_SIZE_MINIMUM, int(size))
    if _is_console_control(knob) or not dpg.does_item_exist(knob):
        return
    art = KNOB_INTERACTION.art.get(knob)
    if art is not None and art.size == size:
        return
    dpg.configure_item(knob, width=size, height=size)
    _paint_knob(knob, size)


def _set_attribute(target: object, attribute: str) -> Callable[[float], None]:
    return lambda value: setattr(target, attribute, value)


def _item_constraints(field_info: object) -> tuple[object, ...]:
    """The constraints on the *items* of a tuple field, if its annotation has
    them: ``tuple[Annotated[float, Field(ge=-1, le=1)], ...]`` says what one
    gain may be, and the panel should believe it over guessing from a value."""
    annotation = getattr(field_info, "annotation", None)
    for argument in typing.get_args(annotation) or ():
        if argument is Ellipsis:
            continue
        if typing.get_origin(argument) is typing.Annotated:
            found: list[object] = []
            for entry in getattr(argument, "__metadata__", ()):
                # A Field(...) inside Annotated is a FieldInfo whose own
                # metadata holds the Ge/Le constraints; anything else is one.
                inner = getattr(entry, "metadata", None)
                found.extend(inner if isinstance(inner, (list, tuple)) else [entry])
            return tuple(found)
    return ()


def _dynamic_parameter_bounds(
    field_info: object,
    value: float,
    *,
    item: bool = False,
) -> tuple[float, float]:
    lower: float | None = None
    upper: float | None = None
    constraints = tuple(getattr(field_info, "metadata", ()))
    if item:
        constraints = _item_constraints(field_info) or constraints
    for constraint in constraints:
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
    """Write a control's value through the model that validates it.

    A model refusing a value is an answer, not a crash. Dragging a knob past a
    declared bound used to raise a validation error all the way out and print a
    traceback over the rack; it is reported on the status line instead.
    """
    try:
        _write_dynamic_parameter(module, path, value)
    except (ValueError, TypeError) as error:
        _set_patch_status(
            f"REFUSED: {str(error).splitlines()[0][:88]}", error=True
        )


def _write_dynamic_parameter(
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


def _fit_column(text: str, width: int = KNOB_COLUMN_CHARS) -> str:
    """Pad or trim one cell so control columns align down the panel."""
    if len(text) > width:
        return text[: max(1, width - 1)] + "…"
    return text.ljust(width)


def _control_label_and_unit(field_name: str) -> tuple[str, str]:
    """Turn a parameter name into a short label and the unit it implies.

    A generated panel took its labels straight from the field names, so a row
    of three knobs read "FREQUENCY FINE TUNE CENTS AMPLITUDE" — three labels
    with nothing between them and their values somewhere underneath. Units move
    to the readout, where the number they describe actually is.
    """
    name = field_name
    unit = ""
    for suffix, symbol in UNIT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            unit = symbol
            break
    name = name.removesuffix("_amount")
    words = [
        LABEL_ABBREVIATIONS.get(word, word) for word in name.split("_") if word
    ]
    return " ".join(words).title(), unit


def _format_dynamic_value(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000.0:
        return f"{value:,.0f}"
    if magnitude >= 10.0:
        return f"{value:.1f}"
    return f"{value:.3f}"


def _control_tag(module: object, field_path: tuple[str | int, ...]) -> int | str:
    """A stable tag for one module's control, so it can be found again.

    ``<node>.control.<field.path>`` -- the same shape the hand-built panels
    use, so anything that addresses a knob by name addresses every knob.
    """
    for instance_id, node in INSTANCE_NODE_TAGS.items():
        if module is _module_by_instance(instance_id):
            return f"{node}.control.{'.'.join(str(part) for part in field_path)}"
    return 0


def _module_by_instance(instance_id: str) -> object | None:
    if ACTIVE_RUNTIME:
        return ACTIVE_RUNTIME[0].patch.modules.get(instance_id)
    return None


def _add_dynamic_float_control(
    module: object,
    field_info: object,
    value: float,
    field_path: tuple[str | int, ...],
    label: str,
    unit: str = "",
) -> int | str:
    minimum, maximum = _dynamic_parameter_bounds(field_info, value)
    logarithmic = minimum > 0.0 and maximum / minimum >= 100.0
    tag = _control_tag(module, field_path)
    if tag and dpg.does_item_exist(tag):
        tag = 0
    return _add_knob(
        value,
        label,
        minimum,
        maximum,
        lambda shown, suffix=unit: _format_dynamic_value(shown) + suffix,
        lambda changed, target=module, target_path=field_path: (
            _set_dynamic_parameter(target, target_path, changed)
        ),
        logarithmic=logarithmic,
        size=KNOB_SIZE,
        tag=tag,
    )


def _add_rate_sync_control(
    module: object,
    field_path: tuple[str | int, ...],
    knob: int | str,
    kind: str = "rate",
) -> None:
    """Offer the clock as an alternative to setting a rate by hand."""
    binding = KNOB_INTERACTION.bindings.get(knob)
    if binding is None:
        return
    RATE_SYNCS[knob] = RateSync(module=module, path=field_path, binding=binding, kind=kind)
    dpg.add_combo(
        list(CLOCK_CHOICES),
        default_value=FREE,
        width=KNOB_COLUMN_CHARS * 9,
        callback=_set_rate_division,
        user_data=knob,
    )


def _add_dynamic_parameter_controls(
    module: object,
    parameters: BaseModel,
    path: tuple[str | int, ...] = (),
) -> None:
    pending_floats: list[
        tuple[object, float, tuple[str | int, ...], str, str]
    ] = []

    def flush_float_row() -> None:
        if not pending_floats:
            return
        with dpg.group(horizontal=True):
            for field_info, value, field_path, label, unit in pending_floats:
                knob = _add_dynamic_float_control(
                    module,
                    field_info,
                    value,
                    field_path,
                    label,
                    unit,
                )
                kind = clock_kind(str(field_path[-1]))
                if kind is not None:
                    _add_rate_sync_control(module, field_path, knob, kind)
        pending_floats.clear()

    for field_name, field_info in type(parameters).model_fields.items():
        value = getattr(parameters, field_name)
        field_path = (*path, field_name)
        label, unit = _control_label_and_unit(field_name)
        if isinstance(value, float):
            pending_floats.append((field_info, value, field_path, label, unit))
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
        if isinstance(value, str) and not isinstance(value, StrEnum):
            choices = list(
                getattr(module, "choices_for", lambda _field: ())(field_name)
            )
            dpg.add_text(_fit_column(label.upper()), color=MUTED_TEXT)
            if choices:
                combo = dpg.add_combo(
                    choices,
                    default_value=value if value in choices else choices[0],
                    width=KNOB_COLUMN_CHARS * 14,
                    callback=lambda sender, chosen, _u: _set_word_parameter(
                        sender, chosen
                    ),
                )
                WORD_CONTROLS[combo] = (module, field_path, field_name)
            else:
                dpg.add_input_text(
                    default_value=value,
                    width=KNOB_COLUMN_CHARS * 14,
                    on_enter=True,
                    callback=lambda _s, typed, data=(module, field_path): (
                        _set_dynamic_parameter(data[0], data[1], typed)
                    ),
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
                        item=True,
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
                        size=KNOB_SIZE,
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
                    size=KNOB_SIZE_LARGE,
                    tag=f"{VCO_NODE}.control.frequency",
                )
                _add_knob(
                    parameters.fine_tune_cents,
                    "Fine",
                    -100.0,
                    100.0,
                    lambda value: f"{value:+.0f} ct",
                    _set_attribute(parameters, "fine_tune_cents"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.amplitude,
                    "Level",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "amplitude"),
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.frequency_cv_2_amount,
                    "FM 2",
                    -1.0,
                    1.0,
                    lambda value: f"{value:+.2f}",
                    _set_attribute(parameters, "frequency_cv_2_amount"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.linear_fm_amount,
                    "Lin FM",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "linear_fm_amount"),
                    size=KNOB_SIZE,
                )
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.pulse_width,
                    "Pulse",
                    0.01,
                    0.99,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "pulse_width"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.morph,
                    "Morph",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "morph"),
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
                    tag=f"{WOGGLE_NODE}.control.rate",
                )
                _add_knob(
                    parameters.chaos,
                    "Chaos",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "chaos"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.ego_id_balance,
                    "Ego / Id",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "ego_id_balance"),
                    size=KNOB_SIZE,
                )
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.woggle,
                    "Woggle",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "woggle"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.audio_level,
                    "Audio",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "audio_level"),
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
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
            size=KNOB_SIZE,
        )
        _add_knob(
            parameters.fall_seconds,
            "Fall",
            MIN_FUNCTION_STAGE_SECONDS,
            MAX_FUNCTION_STAGE_SECONDS,
            _format_duration,
            _set_attribute(parameters, "fall_seconds"),
            logarithmic=True,
            size=KNOB_SIZE,
        )
        _add_knob(
            parameters.curve,
            "Shape",
            -1.0,
            1.0,
            lambda value: f"{value:+.2f}",
            _set_attribute(parameters, "curve"),
            size=KNOB_SIZE,
        )
        _add_knob(
            parameters.attenuverter,
            "Level",
            -1.0,
            1.0,
            lambda value: f"{value:+.2f}",
            _set_attribute(parameters, "attenuverter"),
            size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
                )
                _add_knob(
                    utility.parameters.channel_3_attenuverter,
                    "Channel 3",
                    -1.0,
                    1.0,
                    lambda value: f"{value:+.2f}",
                    _set_attribute(utility.parameters, "channel_3_attenuverter"),
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.brightness,
                    "Light",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "brightness"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.character,
                    "Wood",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "character"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.level,
                    "Level",
                    0.0,
                    1.0,
                    lambda value: f"{value:.2f}",
                    _set_attribute(parameters, "level"),
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
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
                    size=KNOB_SIZE,
                    tag=f"{REVERB_NODE}.control.decay",
                )
                _add_knob(
                    parameters.damping,
                    "Damp",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "damping"),
                    size=KNOB_SIZE,
                )
            with dpg.group(horizontal=True):
                _add_knob(
                    parameters.diffusion,
                    "Diffuse",
                    0.0,
                    1.0,
                    lambda value: f"{value * 100:.0f}%",
                    _set_attribute(parameters, "diffusion"),
                    size=KNOB_SIZE,
                )
                _add_knob(
                    parameters.pre_delay_ms,
                    "Pre-delay",
                    0.0,
                    250.0,
                    lambda value: f"{value:.0f} ms",
                    _set_attribute(parameters, "pre_delay_ms"),
                    size=KNOB_SIZE,
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


def _format_pan(value: float) -> str:
    if abs(value) < 0.005:
        return "C"
    return f"{'L' if value < 0 else 'R'}{abs(value) * 100:.0f}"


def _fader_readout(level: float) -> str:
    """The level in decibels, the unit understood: "-6", "0", "-∞"."""
    return _decibels(level)


def _add_level_dial(
    tag: str, value: float, label: str, setter: Callable[[float], None]
) -> None:
    """A level dial with a meter ring drawn around it in its own margin."""
    _add_knob(
        value,
        label,
        0.0,
        1.0,
        lambda level: _fader_readout(level),
        setter,
        size=LEVEL_DIAL_SIZE,
        tag=tag,
        compact=True,
        inset=LEVEL_DIAL_INSET,
    )
    dpg.draw_polyline(
        _meter_ring_points(0.0),
        color=METER_QUIET,
        thickness=2.0,
        parent=tag,
        tag=f"{tag}.meter",
    )


def _meter_ring_points(fraction: float) -> list[tuple[float, float]]:
    """The outer ring of a level dial, lit as far round as the signal reaches."""
    fraction = min(1.0, max(0.0, fraction))
    centre = LEVEL_DIAL_SIZE * 0.5
    radius = LEVEL_DIAL_SIZE * 0.5 - 1.0
    steps = max(1, int(28 * fraction))
    return [
        (
            centre + radius * math.cos(theta),
            centre + radius * math.sin(theta),
        )
        for theta in (
            KNOB_SWEEP_START
            + (KNOB_SWEEP_END - KNOB_SWEEP_START) * fraction * step / steps
            for step in range(steps + 1)
        )
    ]


def _meter_colour(level: float) -> tuple[int, int, int, int]:
    if level >= 0.98:
        return METER_CLIP
    if level >= 0.7:
        return METER_HOT
    return METER_QUIET


def _build_strip(channel: int, master: MasterMixer) -> None:
    """One console strip: the jack at the top, then level, then pan, A, B."""
    with dpg.node(tag=CONSOLE_STRIP.format(channel=channel), label=f"{channel}"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            level = master.parameters.levels[channel - 1]
            # Stacked narrow -- dial and readout, then M S, then pan A B -- so
            # eleven strips fit across the rack of a default-sized window.
            with dpg.group(horizontal=True, horizontal_spacing=4) as dial_row:
                _add_level_dial(
                    CONSOLE_LEVEL.format(channel=channel),
                    level,
                    f"Ch {channel} level",
                    lambda value, channel=channel: _channel_level_changed(
                        master, channel, value
                    ),
                )
                dpg.add_text(
                    _fader_readout(level),
                    tag=CONSOLE_READOUT.format(channel=channel),
                    color=MUTED_TEXT,
                )
            with dpg.group(horizontal=True, horizontal_spacing=3):
                # Centred under the dial: the knob row below is the strip's
                # width, and M S together are about forty pixels of it.
                dpg.add_spacer(width=max(0, (3 * STRIP_KNOB_SIZE + 8 - 41) // 2))
                mute = dpg.add_button(
                    label="M",
                    tag=CONSOLE_MUTE.format(channel=channel),
                    small=True,
                    callback=_toggle_mute,
                    user_data=(master, channel),
                )
                solo = dpg.add_button(
                    label="S",
                    tag=CONSOLE_SOLO.format(channel=channel),
                    small=True,
                    callback=_toggle_solo,
                    user_data=(master, channel),
                )
                _paint_mute_solo(master, channel)
                del mute, solo
            with dpg.group(horizontal=True, horizontal_spacing=4) as knob_row:
                _add_knob(
                    master.parameters.pans[channel - 1],
                    f"Ch {channel} pan",
                    -1.0,
                    1.0,
                    _format_pan,
                    lambda value, channel=channel: master.set_pan(channel, value),
                    tag=CONSOLE_PREFIX + f"pan_{channel}",
                    compact=True,
                    size=STRIP_KNOB_SIZE,
                )
                for bus in SENDS:
                    _add_knob(
                        getattr(master.parameters, f"sends_{bus}")[channel - 1],
                        f"Ch {channel} send {bus.upper()}",
                        0.0,
                        1.0,
                        lambda value: f"{value:.2f}",
                        lambda value, channel=channel, bus=bus: master.set_send(
                            bus, channel, value
                        ),
                        tag=CONSOLE_PREFIX + f"send_{bus}_{channel}",
                        compact=True,
                        size=STRIP_KNOB_SIZE,
                    )


def _paint_mute_solo(master: MasterMixer, channel: int) -> None:
    """Colour a strip's M and S for what they are doing."""
    mute = CONSOLE_MUTE.format(channel=channel)
    solo = CONSOLE_SOLO.format(channel=channel)
    if dpg.does_item_exist(mute):
        dpg.bind_item_theme(
            mute, MUTE_ON_THEME if master.parameters.mutes[channel - 1] else TOGGLE_OFF_THEME
        )
    if dpg.does_item_exist(solo):
        dpg.bind_item_theme(
            solo, SOLO_ON_THEME if master.parameters.solos[channel - 1] else TOGGLE_OFF_THEME
        )


def _toggle_mute(_sender: int | str, _app_data: object, data: tuple[MasterMixer, int]) -> None:
    master, channel = data
    master.set_mute(channel, not master.parameters.mutes[channel - 1])
    _paint_mute_solo(master, channel)
    _set_patch_status(
        f"CHANNEL {channel}  {'MUTED' if master.parameters.mutes[channel - 1] else 'UNMUTED'}"
    )


def _toggle_solo(_sender: int | str, _app_data: object, data: tuple[MasterMixer, int]) -> None:
    master, channel = data
    master.set_solo(channel, not master.parameters.solos[channel - 1])
    _paint_mute_solo(master, channel)
    soloed = [index + 1 for index, on in enumerate(master.parameters.solos) if on]
    _set_patch_status(
        "SOLO  " + "  ".join(str(c) for c in soloed) if soloed else "SOLO OFF"
    )


def _channel_level_changed(master: MasterMixer, channel: int, level: float) -> None:
    master.set_level(channel, float(level))
    readout = CONSOLE_READOUT.format(channel=channel)
    if dpg.does_item_exist(readout):
        dpg.set_value(readout, _fader_readout(float(level)))


def _master_level_changed(master: MasterMixer, level: float) -> None:
    master.parameters.master = float(level)
    if dpg.does_item_exist(CONSOLE_MASTER_READOUT):
        dpg.set_value(CONSOLE_MASTER_READOUT, _fader_readout(float(level)))


def _paint_return_mute(master: MasterMixer, bus: str) -> None:
    mute = CONSOLE_RETURN_MUTE.format(bus=bus)
    if dpg.does_item_exist(mute):
        on = master.parameters.return_mutes[SENDS.index(bus)]
        dpg.bind_item_theme(mute, MUTE_ON_THEME if on else TOGGLE_OFF_THEME)


def _toggle_return_mute(_sender: int | str, _app_data: object, data: tuple[MasterMixer, str]) -> None:
    master, bus = data
    on = not master.parameters.return_mutes[SENDS.index(bus)]
    master.set_return_mute(bus, on)
    _paint_return_mute(master, bus)
    _set_patch_status(f"RETURN {bus.upper()}  {'MUTED' if on else 'UNMUTED'}")


def _return_level_changed(master: MasterMixer, bus: str, level: float) -> None:
    master.set_return_level(bus, float(level))
    readout = CONSOLE_RETURN_READOUT.format(bus=bus)
    if dpg.does_item_exist(readout):
        dpg.set_value(readout, _fader_readout(float(level)))


def _build_return_strip(bus: str, master: MasterMixer) -> None:
    """A return: what came back from a send, in stereo, with a level and a mute."""
    left_port, right_port = RETURN_PORTS[bus]
    with dpg.node(tag=CONSOLE_RETURN.format(bus=bus), label=f"FX {bus.upper()}"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            # Three jacks stand on posts above -- the send out, then the
            # return's left and right in; this row only says which is which.
            with dpg.group(horizontal=True, horizontal_spacing=0):
                dpg.add_spacer(width=2)
                dpg.add_text("OUT", color=MUTED_TEXT)
                dpg.add_spacer(width=10)
                dpg.add_text("L", color=SIGNAL_COLORS["audio"])
                dpg.add_spacer(width=14)
                dpg.add_text("R", color=SIGNAL_COLORS["audio"])
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            level = master.parameters.return_levels[SENDS.index(bus)]
            with dpg.group(horizontal=True, horizontal_spacing=4) as dial_row:
                _add_level_dial(
                    CONSOLE_RETURN_LEVEL.format(bus=bus),
                    level,
                    f"Return {bus.upper()} level",
                    lambda value, bus=bus: _return_level_changed(master, bus, value),
                )
                dpg.add_text(
                    _fader_readout(level),
                    tag=CONSOLE_RETURN_READOUT.format(bus=bus),
                    color=MUTED_TEXT,
                )
            dpg.add_button(
                label="M",
                tag=CONSOLE_RETURN_MUTE.format(bus=bus),
                small=True,
                callback=_toggle_return_mute,
                user_data=(master, bus),
            )
            _paint_return_mute(master, bus)


POST_OUTPUTS: set[str] = set()
"""Posts whose jack is an output: the pin is drawn at the right edge."""


def _build_jack_post(
    name: str, attribute_tag: str, strip: str, across: float, *, output: bool = False
) -> None:
    """Stand a jack at a point along the top of a strip.

    The post is a node with an empty title and one row holding nothing,
    themed invisible, so all that shows is its pin -- drawn at the left edge
    for an input and the right for an output -- and the console's settle puts
    that edge where the jack should be.
    """
    post = CONSOLE_POST.format(name=name)
    kind = dpg.mvNode_Attr_Output if output else dpg.mvNode_Attr_Input
    with dpg.node(tag=post, label=""):
        with dpg.node_attribute(tag=attribute_tag, attribute_type=kind):
            # A text rather than a spacer: a text reports where it is, and the
            # pin is drawn at the centre of this row.
            POST_TEXTS[post] = dpg.add_text(" ")
    dpg.bind_item_theme(post, JACK_POST_THEME)
    POST_ANCHORS[post] = (strip, across)
    if output:
        POST_OUTPUTS.add(post)


def _build_console(engine: SystemAudioEngine, master: MasterMixer) -> None:
    """Build the console: eight strips and the master, pinned along the bottom.

    The mixer used to be one panel of knobs pinned in a corner, and it looked
    tacked on because it was. A mixer is a row of strips: each channel has its
    jack at the top -- so a cable can be dropped straight onto the slot it
    should play through -- a level dial with its meter drawn as a ring around
    it, and pan and two sends under that. The strips live inside the node
    editor because that is the only place a cable can land, and they are
    pinned so the rack pans and zooms underneath them.
    """
    POST_ANCHORS.clear()
    POST_TEXTS.clear()
    POST_OUTPUTS.clear()
    for channel in range(1, MASTER_CHANNELS + 1):
        _build_strip(channel, master)
    for bus in SENDS:
        _build_return_strip(bus, master)
    for node in PINNED_NODES:
        if not dpg.does_item_exist(node) or node in POST_ANCHORS:
            continue
        if str(node).startswith(CONSOLE_PREFIX + "return_"):
            theme = CONSOLE_RETURN_THEME
        else:
            theme = CONSOLE_STRIP_THEME
        dpg.bind_item_theme(node, theme)
    # The jacks: one post at the top centre of each strip, two on each return.
    # Built last so they draw above the strips.
    for channel in range(1, MASTER_CHANNELS + 1):
        _build_jack_post(
            f"channel_{channel}",
            f"{OUTPUT_NODE}.channel_{channel}",
            CONSOLE_STRIP.format(channel=channel),
            0.5,
        )
    for bus in SENDS:
        left_port, right_port = RETURN_PORTS[bus]
        strip = CONSOLE_RETURN.format(bus=bus)
        _build_jack_post(f"send_{bus}", f"{OUTPUT_NODE}.send_{bus}", strip, 0.2, output=True)
        _build_jack_post(left_port, f"{OUTPUT_NODE}.{left_port}", strip, 0.5)
        _build_jack_post(right_port, f"{OUTPUT_NODE}.{right_port}", strip, 0.78)


def _add_master_control(master: MasterMixer) -> None:
    """The master level, in the status bar: a dial with its ring meter.

    There is no master strip. What a master strip held was a level and a
    meter, and the bottom bar has room for both beside the scope, where the
    output is already being watched.
    """
    dpg.add_spacer(width=14)
    dpg.add_text("MASTER", color=MUTED_TEXT)
    level = master.parameters.master
    _add_level_dial(
        CONSOLE_MASTER_LEVEL,
        level,
        "Master",
        lambda value: _master_level_changed(master, value),
    )
    dpg.add_text(_fader_readout(level), tag=CONSOLE_MASTER_READOUT, color=MUTED_TEXT)
    # The peak-programme meter the tests read; the ring is what is seen.
    dpg.add_progress_bar(
        tag=OUTPUT_METER, default_value=0.0, overlay="", width=1, height=1, show=False
    )


def _console_titles(patch: PatchGraph) -> None:
    """Name each strip after what is patched into it.

    A row of numbers is a mixer nobody has used yet. Once a cable lands the
    strip says what it is playing -- the module's own instance name, cut to
    fit -- and goes back to its number when the cable is pulled.
    """
    feeding: dict[int, str] = {}
    for cable in patch.cables:
        if cable.target.module_id != MASTER_ID:
            continue
        if not cable.target.port_id.startswith("channel_"):
            continue
        try:
            channel = int(cable.target.port_id.rsplit("_", 1)[1])
        except ValueError:
            continue
        feeding.setdefault(channel, cable.source.module_id)
    for channel in range(1, MASTER_CHANNELS + 1):
        strip = CONSOLE_STRIP.format(channel=channel)
        if not dpg.does_item_exist(strip):
            continue
        source = feeding.get(channel)
        label = f"{channel}" if source is None else _strip_title(source)
        if dpg.get_item_configuration(strip)["label"] != label:
            dpg.configure_item(strip, label=label)


def _strip_title(instance_id: str, width: int = 8) -> str:
    """An instance name short enough for a strip: "P VOICE", "REVERB", "ECHO 2"."""
    words = [word for word in instance_id.replace("-", "_").split("_") if word]
    if not words:
        return instance_id.upper()[:width]
    joined = " ".join(words).upper()
    if len(joined) <= width:
        return joined
    if len(words) >= 2:
        initials = "".join(word[0] for word in words[:-1]).upper()
        short = f"{initials} {words[-1].upper()}"
        if len(short) <= width:
            return short
        return short[:width].rstrip()
    return joined[:width].rstrip()


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


OUTLINE_LINK_THEME = "noodler.theme.outline_link"
OUTLINE_ARROW_THEME = "noodler.theme.outline_arrow"
OUTLINE_DETAIL_INDENT = 22
OUTLINE_LINKS: dict[int | str, int] = {}
"""Each outline link and how wide its name is, for the underline on hover."""
OUTLINE_LAYER = "noodler.outline_layer"


def _refresh_outline_links() -> None:
    """Underline the outline link under the pointer, and only that one.

    Drawn on an overlay at the link's own rectangle, two pixels above its
    bottom edge, so it sits against the letters rather than a row below.
    """
    if not dpg.does_item_exist(OUTLINE_LAYER):
        dpg.add_viewport_drawlist(tag=OUTLINE_LAYER, front=True)
    dpg.delete_item(OUTLINE_LAYER, children_only=True)
    for link, width in tuple(OUTLINE_LINKS.items()):
        if not dpg.does_item_exist(link):
            OUTLINE_LINKS.pop(link, None)
            continue
        if not dpg.is_item_hovered(link):
            continue
        try:
            left, _top = dpg.get_item_rect_min(link)
            _right, bottom = dpg.get_item_rect_max(link)
        except (KeyError, SystemError):
            continue
        y = float(bottom) - 2.0
        dpg.draw_line(
            (float(left), y), (float(left) + width, y),
            color=SCALE_ACCENT, thickness=1.0, parent=OUTLINE_LAYER,
        )
        break
OUTLINE_CHAR_PX = 9
"""The rack's monospace face at sixteen pixels is nine wide: an underline
drawn as a rule under a label of n characters is nine n long."""


def _add_module_link(
    parent: int | str, runtime: AppRuntime, instance_id: str, connection: str | None = None
) -> None:
    """The module's name in the outline as a link: underlined, and a click on
    it brings the module to the middle of the view.

    The outline is where the rack is *read*, and reading a name should lead
    to the thing. The tree's own arrow still opens the ports beneath.
    """
    module = runtime.patch.modules[instance_id]
    name = f"{module.manifest.name.upper()}  [{instance_id}]"
    with dpg.group(parent=parent):
        with dpg.group(horizontal=True, horizontal_spacing=0):
            link = dpg.add_selectable(
                label=name,
                width=len(name) * OUTLINE_CHAR_PX + 4,
                callback=_centre_module_from_outline,
                user_data=(runtime, instance_id),
            )
            dpg.bind_item_theme(link, OUTLINE_LINK_THEME)
            if connection:
                dpg.add_text(f"  ·  {connection}", color=MUTED_TEXT)
    # The underline appears only under the pointer, as a web link's does, drawn
    # on the overlay right against the letters; the colour says link otherwise.
    OUTLINE_LINKS[link] = len(name) * OUTLINE_CHAR_PX


def _add_module_row(
    parent: int | str, runtime: AppRuntime, instance_id: str, connection: str | None = None
) -> int | str:
    """One module in the outline, as one line: a disclosure arrow, the name as
    a link, what it feeds, and the remove button. Beneath, hidden until the
    arrow is clicked, the group its details go in -- which is returned.

    The name is what the tree's arrow used to be. There was a DETAILS row
    under every name that opened to the ports and parameters; the arrow now
    sits at the front of the name's own row, and there is nothing to read
    twice.
    """
    row = dpg.add_group(parent=parent, horizontal=True, horizontal_spacing=2)
    details = dpg.add_group(parent=parent, indent=OUTLINE_DETAIL_INDENT, show=False)
    arrow = dpg.add_button(
        parent=row,
        arrow=True,
        direction=dpg.mvDir_Right,
        callback=_toggle_outline_details,
        user_data=details,
    )
    dpg.bind_item_theme(arrow, OUTLINE_ARROW_THEME)
    _add_module_link(row, runtime, instance_id, connection)
    _add_rack_outline_remove_button(row, runtime, instance_id)
    return details


def _toggle_outline_details(sender: int | str, _app_data: object, details: int | str) -> None:
    """Open or close the details under a module's row; the arrow turns."""
    if not dpg.does_item_exist(details):
        return
    opening = not dpg.is_item_shown(details)
    dpg.configure_item(details, show=opening)
    if dpg.does_item_exist(sender):
        dpg.configure_item(sender, direction=dpg.mvDir_Down if opening else dpg.mvDir_Right)


def _centre_module_from_outline(
    _sender: int | str, _app_data: object, data: tuple[AppRuntime, str]
) -> None:
    runtime, instance_id = data
    node = INSTANCE_NODE_TAGS.get(instance_id)
    if node is None or not dpg.does_item_exist(node):
        return
    _centre_node(node)
    _clear_rack_selection()
    try:
        dpg.set_value(f"{node}.selected", True)
    except Exception:
        pass
    label = runtime.patch.modules[instance_id].manifest.name.upper()
    _set_patch_status(f"HERE  ·  {label}  [{instance_id}]")


def _centre_node(node: int | str) -> None:
    """Glide the camera so one module sits in the middle of the view."""
    if not dpg.does_item_exist(RACK):
        return
    view_width, view_height = _rack_view_size()
    if view_width <= 1.0 or view_height <= 1.0:
        return
    node_x, node_y = (float(v) for v in dpg.get_item_pos(node))
    width, height = (float(v) for v in dpg.get_item_rect_size(node))
    centre_x = node_x + max(width, 1.0) * 0.5
    centre_y = node_y + max(height, 1.0) * 0.5
    pan_x, pan_y = _editor_pan()
    interaction = CANVAS_INTERACTION
    interaction.stop_glide()
    interaction.recenter_x.snap(0.0)
    interaction.recenter_y.snap(0.0)
    interaction.recenter_x.retarget(view_width * 0.5 - pan_x - centre_x)
    interaction.recenter_y.retarget(view_height * 0.5 - pan_y - centre_y)


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


OUTLINE_PARAMETER_TEXTS: dict[tuple[str, str], tuple[int | str, object, tuple[str | int, ...]]] = {}
"""Each parameter readout in the outline: its text item, module and field path,
so the values can be kept current while the tree is open."""


def _outline_parameter_rows(module: object) -> list[tuple[str, tuple[str | int, ...], object]]:
    """(label, field path, value) for every leaf of a module's parameters."""
    parameters = getattr(module, "parameters", None)
    if not isinstance(parameters, BaseModel):
        return []
    rows: list[tuple[str, tuple[str | int, ...], object]] = []

    def walk(model: BaseModel, path: tuple[str | int, ...]) -> None:
        for name in type(model).model_fields:
            value = getattr(model, name)
            if isinstance(value, BaseModel):
                walk(value, (*path, name))
            elif isinstance(value, tuple) and value and all(isinstance(v, (int, float, bool)) for v in value):
                rows.append((name, (*path, name), value))
            else:
                rows.append((name, (*path, name), value))

    walk(parameters, ())
    return rows


def _outline_value_text(value: object) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return _format_dynamic_value(value)
    if isinstance(value, tuple):
        return "  ".join(_outline_value_text(v) for v in value)
    if isinstance(value, StrEnum):
        return str(value.value)
    return str(value)


def _add_rack_outline_parameters(parent: int | str, runtime: AppRuntime, instance_id: str) -> None:
    """List every parameter with its current value, under the ports."""
    module = runtime.patch.modules[instance_id]
    rows = _outline_parameter_rows(module)
    if not rows:
        return
    root = dpg.add_tree_node(label=f"PARAMETERS  ·  {len(rows)}", parent=parent, default_open=False)
    for label, path, value in rows:
        with dpg.group(parent=root, horizontal=True):
            dpg.add_text(label.replace("_", " ").upper() + "  ", color=MUTED_TEXT)
            text = dpg.add_text(_outline_value_text(value), color=TEXT)
        OUTLINE_PARAMETER_TEXTS[(instance_id, ".".join(str(p) for p in path))] = (text, module, path)


def _refresh_outline_parameters() -> None:
    """Keep the outline's parameter readouts current, a few times a second."""
    if dpg.get_frame_count() % 8:
        return
    for key, (text, module, path) in tuple(OUTLINE_PARAMETER_TEXTS.items()):
        if not dpg.does_item_exist(text):
            OUTLINE_PARAMETER_TEXTS.pop(key, None)
            continue
        value: object = getattr(module, "parameters", None)
        try:
            for part in path:
                value = value[part] if isinstance(part, int) else getattr(value, part)
        except (AttributeError, IndexError, TypeError):
            continue
        shown = _outline_value_text(value)
        if dpg.get_value(text) != shown:
            dpg.set_value(text, shown)


def _add_rack_outline_ports(
    parent: int | str,
    runtime: AppRuntime,
    instance_id: str,
) -> None:
    """List every module jack and whether the live graph currently uses it."""
    _add_rack_outline_parameters(parent, runtime, instance_id)
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
    if instance_id == MASTER_ID:
        # The console is not a module in the rack: it has no panel to go to
        # and cannot be removed, so it is named and left at that.
        dpg.add_text(
            f"CONSOLE  ·  {connection}" if connection else "CONSOLE",
            parent=parent,
            color=MUTED_TEXT,
        )
        return
    # One line: the arrow, the name as a link that goes to the module, what it
    # feeds. Under it, closed, its parameters, its ports and what feeds it.
    branch = _add_module_row(parent, runtime, instance_id, connection)
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
    # The console is furniture: it is never "unpatched", and never removable.
    for heading in grouped:
        grouped[heading] = [i for i in grouped[heading] if i != MASTER_ID]
    return grouped


def _stray_taps(patch: PatchGraph) -> int:
    """Count output taps the user made, which is none of the master's own.

    The master's bus is connected because every rack's is; counting it would
    report two cables in a rack with nothing in it.
    """
    return sum(1 for tap in patch.output_taps if tap.source.module_id != MASTER_ID)


def _rack_summary_text(runtime: AppRuntime) -> str:
    """Describe the rack in the words the header should be using right now."""
    modules = sum(
        1 for instance_id in runtime.patch.modules if instance_id != MASTER_ID
    )
    connections = len(runtime.patch.cables) + _stray_taps(runtime.patch)
    if not modules:
        return "EMPTY RACK  ·  ADD A MODULE TO BEGIN"
    panels = "1 MODULE" if modules == 1 else f"{modules} MODULES"
    cables = "1 CABLE" if connections == 1 else f"{connections} CABLES"
    return f"{panels}  ·  {cables}"


def _refresh_rack_outline(runtime: AppRuntime) -> None:
    """Rebuild the left outline from the real graph after a topology edit."""
    if dpg.does_item_exist(RACK_SUMMARY):
        # The header described the rack it was built with, not the one in front
        # of the user: it still read "empty" over three mounted modules.
        dpg.set_value(RACK_SUMMARY, _rack_summary_text(runtime))
    if not dpg.does_item_exist(RACK_OUTLINE_BODY):
        return
    dpg.delete_item(RACK_OUTLINE_BODY, children_only=True)
    OUTLINE_PARAMETER_TEXTS.clear()
    OUTLINE_LINKS.clear()
    reachable: set[str] = set()
    signal_flow = dpg.add_tree_node(
        label="SIGNAL FLOW",
        parent=RACK_OUTLINE_BODY,
        default_open=True,
    )
    system_output = dpg.add_tree_node(
        label="CONSOLE",
        parent=signal_flow,
        default_open=True,
    )
    # What reaches the speakers is what is in the master, so the outline shows
    # the modules feeding it rather than the master feeding itself.
    feeding: dict[str, list[str]] = {}
    for cable in runtime.patch.cables:
        if cable.target.module_id != MASTER_ID:
            continue
        feeding.setdefault(cable.source.module_id, []).append(
            f"{cable.source.port_id}  →  {cable.target.port_id}"
        )
    for tap in runtime.patch.output_taps:
        if tap.source.module_id != MASTER_ID:
            feeding.setdefault(tap.source.module_id, []).append(
                f"{tap.source.port_id}  →  {tap.channel.value}"
            )
    if feeding:
        for instance_id, destinations in feeding.items():
            _add_rack_outline_signal_branch(
                system_output,
                runtime,
                instance_id,
                "  ·  ".join(destinations),
                reachable,
            )
        reachable.add(MASTER_ID)
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
                branch = _add_module_row(lane, runtime, instance_id)
                _add_rack_outline_ports(branch, runtime, instance_id)

    panels = len(runtime.patch.modules)
    connections = len(runtime.patch.cables) + _stray_taps(runtime.patch)
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


def _mount_new_module(
    runtime: AppRuntime,
    module_id: str,
    parameters: Mapping[str, object] | None = None,
    *,
    beside: int | str | None = None,
) -> int | str:
    """Create a module, mount its panel, and make the addition undoable.

    With ``parameters`` it is a copy rather than a fresh one, and ``beside``
    puts it a little down and right of another node instead of on the rail.
    """
    provider = BuiltinProvider()
    module = provider.create(module_id, parameters)
    manifest = module.manifest
    instance_id = _next_module_instance_id(module_id, runtime.patch)
    _edit_patch(runtime, lambda: runtime.patch.add_module(instance_id, module))
    node, rail, theme = _register_dynamic_node(instance_id, module_id, manifest.category)
    _build_generic_module_node(instance_id, module, runtime.patch)
    dpg.bind_item_theme(node, theme)
    _bind_rack_node_font(node)
    _add_module_context_menu(node, runtime)
    if beside is not None and dpg.does_item_exist(beside):
        x, y = dpg.get_item_pos(beside)
        dpg.set_item_pos(node, [x + 36, y + 36])
    else:
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
    return node


def _add_selected_module(
    _sender: int | str,
    _app_data: object,
    selection: tuple[AppRuntime, str],
) -> None:
    runtime, module_id = selection
    try:
        node = _mount_new_module(runtime, module_id)
        instance_id = _module_id_for_node(node)
        manifest = runtime.patch.modules[instance_id].manifest
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


def _duplicate_module(node: int | str, runtime: AppRuntime) -> None:
    """A copy of a module, settings and all, a little down and right of it.

    Cables are not copied: a copy that came already patched into the same
    places would double every signal it received and sent, which is never
    what a copy is for. The settings are the point.
    """
    instance_id = _module_id_for_node(node)
    if instance_id is None:
        return
    module = runtime.patch.modules.get(instance_id)
    parameters = getattr(module, "parameters", None)
    if module is None or not isinstance(parameters, BaseModel):
        return
    try:
        copy = _mount_new_module(
            runtime,
            module.manifest.id,
            parameters.model_dump(mode="json"),
            beside=node,
        )
    except Exception as exc:
        _set_patch_status(f"COULD NOT DUPLICATE: {exc}", error=True)
        return
    _set_patch_status(
        f"DUPLICATED  {module.manifest.name.upper()}  ·  {_module_id_for_node(copy)}"
    )


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
    if not dpg.does_item_exist(MODULE_SELECTOR_SEARCH):
        _set_patch_status("THIS RACK HAS NO LIBRARY PANE")
        return
    dpg.set_value(MODULE_SELECTOR_SEARCH, "")
    _filter_module_selector("", "", None)
    dpg.show_item(MODULE_SELECTOR)
    if _library_pane_is_inline():
        _set_library_pane(True)
        if dpg.does_item_exist(MODULE_LIBRARY_HEADER):
            dpg.set_value(MODULE_LIBRARY_HEADER, True)
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
        with dpg.collapsing_header(
            tag=MODULE_LIBRARY_HEADER,
            label="MODULE LIBRARY",
            default_open=True,
        ):
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
    adopt_output_taps(patch)
    ensure_master(patch)

    return AppRuntime(
        patch=patch,
        audio=SystemAudioEngine(
            patch,
            master_gain=preset.system_output.master_gain,
            transport=TRANSPORT,
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
        ensure_master(patch)
        return AppRuntime(
            patch=patch,
            audio=SystemAudioEngine(patch, master_gain=0.8, transport=TRANSPORT),
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
    # The starter reaches the speakers the way anything else does: through the
    # master, on channels that can be turned down.
    master = ensure_master(patch)
    patch.connect("reverb", "left", MASTER_ID, "channel_1")
    patch.connect("reverb", "right", MASTER_ID, "channel_2")
    master.set_pan(1, -1.0)
    master.set_pan(2, 1.0)
    return AppRuntime(
        vco=vco,
        mixer=mixer,
        utility=utility,
        wogglebug=wogglebug,
        scale_generator=scale_generator,
        low_pass_gate=low_pass_gate,
        reverb=reverb,
        patch=patch,
        audio=SystemAudioEngine(patch, master_gain=0.72, transport=TRANSPORT),
    )


def _build_empty_rack_ui(
    runtime: AppRuntime,
    *,
    patch_name: str = "Untitled Patch",
    console: bool = True,
) -> AppRuntime:
    """Build the library rack around one permanent output module."""
    module_count = len(runtime.patch.modules)
    connection_count = len(runtime.patch.cables) + len(runtime.patch.output_taps)
    rack_summary = (
        "EMPTY RACK  ·  ADD A MODULE TO BEGIN"
        if module_count == 0
        else f"{module_count} MODULES  ·  {connection_count} CABLES"
    )
    with dpg.window(tag=PRIMARY_WINDOW, label="Noodler", menubar=True):
        _add_rack_menu(runtime)
        with dpg.group(horizontal=True):
            dpg.add_text(patch_name.upper(), color=SCALE_ACCENT)
            dpg.add_text(rack_summary, tag=RACK_SUMMARY, color=TEXT)
            dpg.add_spacer(width=24)
            for signal in ("audio", "cv", "gate", "musical"):
                dpg.add_text(signal.upper(), color=SIGNAL_COLORS[signal])
            _add_rack_controls(runtime)
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
                    minimap=False,
                ):
                    if console:
                        _build_console(runtime.audio, ensure_master(runtime.patch))
                    _add_module_context_menus(runtime)
        dpg.add_separator()
        with dpg.group(horizontal=True):
            dpg.add_text(
                DEFAULT_CONTROL_STATUS,
                tag=CONTROL_STATUS,
                color=MUTED_TEXT,
            )
            _add_bar_scope()
            _add_master_control(ensure_master(runtime.patch))
            dpg.add_text("", tag=AUDIO_STATUS, color=MUTED_TEXT)
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
    with dpg.file_dialog(
        tag=OPEN_PATCH_DIALOG,
        label="Open Noodler Patch",
        show=False,
        modal=True,
        width=720,
        height=460,
        callback=_open_patch_dialog,
        user_data=runtime,
    ):
        dpg.add_file_extension(".noodler", color=SCALE_ACCENT)
        dpg.add_file_extension(".*")
    with dpg.file_dialog(
        tag=EXPORT_DIALOG,
        label="Export Audio",
        show=False,
        modal=True,
        width=720,
        height=460,
        default_filename=f"{Path(patch_name).name}.wav",
        callback=_export_dialog,
        user_data=runtime,
    ):
        dpg.add_file_extension(".wav", color=SCALE_ACCENT)
        dpg.add_file_extension(".*")
    _configure_rack_theme()
    _configure_knob_handlers(runtime)
    ACTIVE_RUNTIME[:] = [runtime]
    return runtime


def _mount_preset_ui(runtime: AppRuntime, preset: PatchPreset) -> None:
    """Build panels, cables, and camera state for an instantiated document."""
    saved_nodes = {node.node_id: node for node in preset.view.nodes}
    CANVAS_INTERACTION.rail_y.update(preset.view.rails)

    for saved_module in preset.modules:
        if saved_module.instance_id == MASTER_ID:
            # The master is saved with the document for its levels, but it is
            # never a panel in the rack: the console already stands for it.
            continue
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
        _add_module_context_menu(node, runtime)
        saved_node = saved_nodes.get(saved_module.instance_id)
        if saved_node is None:
            _place_dynamic_node(node, rail)
        else:
            dpg.set_item_pos(
                node,
                [saved_node.position.x, saved_node.position.y],
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
        _resize_knob(knob, round(binding.size * zoom))
    dpg.configure_item(ZOOM_RESET_BUTTON, label=f"{zoom:.0%}")

    # The console is built after the document's modules, so that at first draw
    # it is above them rather than under them; the cables need its jacks.
    if not dpg.does_item_exist(CONSOLE_STRIP.format(channel=1)):
        dpg.push_container_stack(RACK)
        try:
            _build_console(runtime.audio, ensure_master(runtime.patch))
        finally:
            dpg.pop_container_stack()

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
    if preset is not None:
        # The clock travels with the document: a patch with a beat in it is
        # not the same patch at another tempo. Set before the menu is built,
        # so its controls come up reading what the document says.
        TRANSPORT.set_bpm(preset.transport.bpm)
        TRANSPORT.set_signature(preset.transport.beats_per_bar, preset.transport.beat_unit)
        TRANSPORT.rewind()
    _reset_rack_registry(starter_patch=starter_patch and preset is None)
    KNOB_INTERACTION.reset()
    KNOB_STATES.clear()
    PORT_TEXTS.clear()
    INPUT_TEXTS.clear()
    PORT_ACTIVITY.clear()
    PORT_STEPS.clear()
    PORT_INDEX_KEY.clear()
    CABLE_SOURCES.clear()
    CABLE_INDEX_KEY.clear()
    CABLE_STEPS.clear()
    CONSOLE_CABLE_ITEMS.clear()
    CONSOLE_CABLE_PATHS.clear()
    if dpg.does_item_exist(CONSOLE_CABLES):
        dpg.delete_item(CONSOLE_CABLES, children_only=True)
    CONSOLE_BALLISTICS.clear()
    RETURN_BALLISTICS.clear()
    CANVAS_INTERACTION.reset()
    MODULE_COLLAPSE.reset()
    dpg.set_global_font_scale(1.0)
    PATCH_BAYS.clear()
    RAIL_SPRINGS.clear()
    TIDY_TARGETS.clear()
    METER_BALLISTICS.reset()
    RACK_HISTORY.clear()
    PATCH_NAME[:] = [preset.name if preset is not None else "Untitled Patch"]
    SAVED_REVISION[:] = [RACK_HISTORY.revision]
    LAST_TITLE[:] = [""]
    RATE_SYNCS.clear()
    WORD_CONTROLS.clear()
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
    if preset is not None:
        # The console is built after the document's modules, so that at first
        # draw it is above them rather than under them.
        _build_empty_rack_ui(runtime, patch_name=preset.name, console=False)
        _mount_preset_ui(runtime, preset)
        return runtime
    if not starter_patch:
        built = _build_empty_rack_ui(runtime)
        # An empty rack should say what to do with itself.
        _set_patch_status(EMPTY_RACK_STATUS)
        return built
    with dpg.window(tag=PRIMARY_WINDOW, label="Noodler", menubar=True):
        _add_rack_menu(runtime)
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
            minimap=False,
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
            _build_console(runtime.audio, ensure_master(runtime.patch))
            _add_module_context_menus(runtime)
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
                f"{OUTPUT_NODE}.channel_1",
                _default_cable(runtime.patch, "reverb", "left", MASTER_ID, "channel_1"),
                "audio",
                tag=REVERB_LEFT_OUTPUT_LINK,
            )
            _add_visual_link(
                f"{REVERB_NODE}.right",
                f"{OUTPUT_NODE}.channel_2",
                _default_cable(runtime.patch, "reverb", "right", MASTER_ID, "channel_2"),
                "audio",
                tag=REVERB_RIGHT_OUTPUT_LINK,
            )
            _refresh_patch_bays(runtime.patch)
        dpg.add_separator()
        with dpg.group(horizontal=True):
            dpg.add_text(
                DEFAULT_CONTROL_STATUS,
                tag=CONTROL_STATUS,
                color=MUTED_TEXT,
            )
            _add_bar_scope()
            _add_master_control(ensure_master(runtime.patch))
            dpg.add_text("", tag=AUDIO_STATUS, color=MUTED_TEXT)
        dpg.bind_item_theme(FUNCTION_NODE, UTILITY_THEME)
        dpg.bind_item_theme(VCO_NODE, VCO_THEME)
        dpg.bind_item_theme(MIXER_NODE, MIXER_THEME)
        dpg.bind_item_theme(WOGGLE_NODE, WOGGLE_THEME)
        dpg.bind_item_theme(SCALE_NODE, SCALE_THEME)
        dpg.bind_item_theme(LPG_NODE, LPG_THEME)
        dpg.bind_item_theme(REVERB_NODE, REVERB_THEME)
        dpg.set_item_pos(FUNCTION_NODE, [20, 20])
        dpg.set_item_pos(WOGGLE_NODE, [430, 20])
        dpg.set_item_pos(SCALE_NODE, [860, 20])
        dpg.set_item_pos(VCO_NODE, [330, 570])
        dpg.set_item_pos(MIXER_NODE, [690, 570])
        dpg.set_item_pos(LPG_NODE, [960, 570])
        dpg.set_item_pos(REVERB_NODE, [1_280, 570])
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
    with dpg.file_dialog(
        tag=OPEN_PATCH_DIALOG,
        label="Open Noodler Patch",
        show=False,
        modal=True,
        width=720,
        height=460,
        callback=_open_patch_dialog,
        user_data=runtime,
    ):
        dpg.add_file_extension(".noodler", color=SCALE_ACCENT)
        dpg.add_file_extension(".*")
    with dpg.file_dialog(
        tag=EXPORT_DIALOG,
        label="Export Audio",
        show=False,
        modal=True,
        width=720,
        height=460,
        default_filename="Hirajoshi Garden.wav",
        callback=_export_dialog,
        user_data=runtime,
    ):
        dpg.add_file_extension(".wav", color=SCALE_ACCENT)
        dpg.add_file_extension(".*")
    _configure_rack_theme()
    _configure_knob_handlers(runtime)
    ACTIVE_RUNTIME[:] = [runtime]
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
    # Before any window: the menu bar takes the process's name once.
    name_the_process()
    width, height, x_position, y_position = default_window(visible_screen())
    gesture_monitor = MacMagnifyMonitor(_capture_macos_magnification)
    scroll_monitor = MacScrollMonitor(_capture_macos_scroll)
    dpg.create_context()
    try:
        placement = {} if x_position is None or y_position is None else {"x_pos": x_position, "y_pos": y_position}
        dpg.create_viewport(
            title=(
                f"Noodler — {preset.name}"
                if preset is not None
                else "Noodler"
            ),
            width=width,
            height=height,
            min_width=900,
            min_height=600,
            **placement,
        )
        if preset is None:
            PARK_EFFECTS[:] = [True]
        runtime = build_ui(preset=preset if preset is not None else default_rack_preset())
        dpg.setup_dearpygui()
        dpg.set_primary_window(PRIMARY_WINDOW, True)
        dpg.show_viewport()
        gesture_monitor.start()
        CANVAS_INTERACTION.native_scroll = scroll_monitor.start()
        dpg.set_frame_callback(1, _refresh_frame, user_data=runtime)
        # Audio does not start on its own. The button in the menu bar says
        # PLAY when a patch opens, and pressing it is what opens the device
        # and starts the clock -- so a patch never makes a sound before it
        # is asked to, and the button always says what it will do next.
        dpg.start_dearpygui()
    finally:
        RACK_CURSOR.reset()
        scroll_monitor.stop()
        gesture_monitor.stop()
        if runtime is not None:
            runtime.audio.close()
        dpg.destroy_context()


if __name__ == "__main__":
    main()
