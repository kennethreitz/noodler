"""Stable visual tokens shared by Noodler's UI components."""

import math
from pathlib import Path


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
BOX_SELECTOR_FILL_COLOR = (211, 145, 57, 38)
BOX_SELECTOR_OUTLINE_COLOR = (211, 145, 57, 170)

TEXT = (235, 230, 216, 255)
MUTED_TEXT = (157, 153, 142, 255)
UTILITY_ACCENT = (211, 145, 57, 255)
VCO_ACCENT = (63, 153, 161, 255)
MIXER_ACCENT = (103, 151, 108, 255)
OUTPUT_ACCENT = (191, 91, 73, 255)
METER_QUIET = (98, 168, 112, 255)
METER_HOT = (214, 164, 72, 255)
METER_CLIP = OUTPUT_ACCENT
WOGGLE_ACCENT = (191, 102, 159, 255)
SCALE_ACCENT = (135, 119, 211, 255)
LPG_ACCENT = (194, 154, 79, 255)
REVERB_ACCENT = (92, 129, 184, 255)

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

KNOB_COLUMN_CHARS = 8
KNOB_SIZE_MINIMUM = 12
KNOB_SIZE = 24
KNOB_SIZE_LARGE = 30
KNOB_SWEEP_START = 0.75 * math.pi
KNOB_SWEEP_END = 2.25 * math.pi
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

LABEL_ABBREVIATIONS = {
    "frequency": "freq",
    "modulation": "mod",
    "reference": "ref",
    "instrument": "instr",
    "octaves": "oct",
    "transposition": "transp",
    "progression": "prog",
    "chance": "%",
    "length": "len",
    "brightness": "bright",
    "distortion": "dist",
    "diffusion": "diffuse",
    "resonance": "reso",
    "threshold": "thresh",
}

MIN_RACK_ZOOM = 0.55
MAX_RACK_ZOOM = 1.65
RACK_ZOOM_STEP = 1.12
FRAME_MARGIN = 56.0
RACK_FONT_PREFIX = "noodler.font.rack"
RACK_FONT_SIZES = tuple(range(9, 27))

SCOPE_DISPLAY_SIZE = (200, 72)
KEYS_DISPLAY_SIZE = (216, 50)
SCOPE_BACKGROUND = (18, 19, 17, 255)
SCOPE_RULE = (58, 56, 50, 255)
KEY_WHITE = (78, 74, 66, 255)
KEY_WHITE_HELD = (224, 208, 169, 255)
KEY_BLACK = (30, 29, 27, 255)
KEY_BLACK_HELD = (211, 145, 57, 255)
