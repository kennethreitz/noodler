"""The fixed bottom console: strips, returns, meters, and jack posts."""

from collections.abc import Callable
from dataclasses import dataclass
import math

import dearpygui.dearpygui as dpg

from ..module_providers.builtin import (
    MASTER_CHANNELS,
    RETURN_PORTS,
    SENDS,
    MasterMixer,
)
from ..patch import PatchGraph
from .formatting import decibels, strip_title
from .style import (
    KNOB_SWEEP_END,
    KNOB_SWEEP_START,
    METER_CLIP,
    METER_HOT,
    METER_QUIET,
    MUTED_TEXT,
    RACK_FONT_PREFIX,
    SIGNAL_COLORS,
    TEXT,
)


OUTPUT_NODE = "noodler.system_output"
OUTPUT_METER = "noodler.output_meter"

CONSOLE_PREFIX = "noodler.console."
CONSOLE_STRIP = CONSOLE_PREFIX + "strip_{channel}"
CONSOLE_MARGIN = 14.0
CONSOLE_GAP = 4.0
LEVEL_DIAL_SIZE = 32
LEVEL_DIAL_INSET = 4.0
STRIP_KNOB_SIZE = 20
STRIP_KNOB_LABELS = ("L/R", "FXA", "FXB")
STRIP_LABEL_FONT_SIZE = 10
STRIP_LABEL_CHAR_PX = 6
CONSOLE_TOGGLE_SIZE = 15.0
CONSOLE_TITLE_HEIGHT = 24.0
CONSOLE_TOGGLE_LAYER = "noodler.console_toggle_layer"
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
CONSOLE_CABLES = "noodler.console_cables"
CONSOLE_LINK_HIDDEN_THEME = "noodler.theme.link.console_hidden"
CONSOLE_CABLE_HOVER_PX = 7.0
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
POST_ANCHORS: dict[str, tuple[str, float]] = {}
POST_TEXTS: dict[str, int | str] = {}
POST_OUTPUTS: set[str] = set()
CONSOLE_CABLE_ITEMS: dict[int | str, int | str] = {}
CONSOLE_MASTER: list[MasterMixer] = []


@dataclass(frozen=True, slots=True)
class ConsoleHooks:
    """The two application services the console calls back into."""

    add_knob: Callable[..., int | str]
    set_patch_status: Callable[..., None]
    rack_tag: int | str
    master_id: str


_HOOKS: list[ConsoleHooks] = []


def configure_console(hooks: ConsoleHooks) -> None:
    """Attach the console to the application that owns its rack."""
    _HOOKS[:] = [hooks]


def _hooks() -> ConsoleHooks:
    if not _HOOKS:
        raise RuntimeError("the console has not been attached to the application")
    return _HOOKS[0]


def _format_pan(value: float) -> str:
    if abs(value) < 0.005:
        return "C"
    return f"{'L' if value < 0 else 'R'}{abs(value) * 100:.0f}"


def _fader_readout(level: float) -> str:
    return decibels(level)


def _add_level_dial(
    tag: str, value: float, label: str, setter: Callable[[float], None]
) -> None:
    _hooks().add_knob(
        value,
        label,
        0.0,
        1.0,
        _fader_readout,
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
    fraction = min(1.0, max(0.0, fraction))
    centre = LEVEL_DIAL_SIZE * 0.5
    radius = LEVEL_DIAL_SIZE * 0.5 - 1.0
    steps = max(1, int(28 * fraction))
    return [
        (centre + radius * math.cos(theta), centre + radius * math.sin(theta))
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
    with dpg.node(tag=CONSOLE_STRIP.format(channel=channel), label=f"{channel}"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            level = master.parameters.levels[channel - 1]
            with dpg.group(horizontal=True, horizontal_spacing=4):
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
            with dpg.group(horizontal=True, horizontal_spacing=4):
                _hooks().add_knob(
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
                    _hooks().add_knob(
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
            _add_strip_knob_labels()


def _add_strip_knob_labels() -> None:
    with dpg.group(horizontal=True, horizontal_spacing=0) as labels:
        last = len(STRIP_KNOB_LABELS) - 1
        for index, label in enumerate(STRIP_KNOB_LABELS):
            text_width = len(label) * STRIP_LABEL_CHAR_PX
            lead = max(0, (STRIP_KNOB_SIZE - text_width) // 2)
            trail = max(0, STRIP_KNOB_SIZE - text_width - lead) + (
                4 if index < last else 0
            )
            if lead:
                dpg.add_spacer(width=lead)
            dpg.add_text(label, color=MUTED_TEXT)
            if trail:
                dpg.add_spacer(width=trail)
    small = f"{RACK_FONT_PREFIX}.{STRIP_LABEL_FONT_SIZE}"
    if dpg.does_item_exist(small):
        dpg.bind_item_font(labels, small)


def _console_toggle_boxes() -> list[
    tuple[tuple[float, float, float, float], str, str | int]
]:
    boxes: list[tuple[tuple[float, float, float, float], str, str | int]] = []
    size = CONSOLE_TOGGLE_SIZE
    gap = 3.0

    def title_boxes(node: str, kinds: tuple[str, ...], who: str | int) -> None:
        if not dpg.does_item_exist(node):
            return
        try:
            left, top = (float(value) for value in dpg.get_item_rect_min(node))
            right, _bottom = (
                float(value) for value in dpg.get_item_rect_max(node)
            )
        except (KeyError, SystemError):
            return
        if right <= left:
            return
        right += 6.0
        y = top + (CONSOLE_TITLE_HEIGHT - size) * 0.5 - 1.0
        x = right - 5.0
        for kind in reversed(kinds):
            boxes.append(((x - size, y, x, y + size), kind, who))
            x -= size + gap

    for channel in range(1, MASTER_CHANNELS + 1):
        title_boxes(
            CONSOLE_STRIP.format(channel=channel), ("mute", "solo"), channel
        )
    for bus in SENDS:
        title_boxes(CONSOLE_RETURN.format(bus=bus), ("return_mute",), bus)
    return boxes


def _console_toggle_at(
    screen_position: tuple[float, float],
) -> tuple[str, str | int] | None:
    x, y = screen_position
    for (left, top, right, bottom), kind, who in _console_toggle_boxes():
        if left <= x <= right and top <= y <= bottom:
            return kind, who
    return None


def _press_console_toggle(kind: str, who: str | int) -> None:
    if not CONSOLE_MASTER:
        return
    master = CONSOLE_MASTER[0]
    if kind == "mute":
        _toggle_mute(0, None, (master, int(who)))
    elif kind == "solo":
        _toggle_solo(0, None, (master, int(who)))
    elif kind == "return_mute":
        _toggle_return_mute(0, None, (master, str(who)))


def _refresh_console_toggles() -> None:
    if not dpg.does_item_exist(CONSOLE_TOGGLE_LAYER):
        dpg.add_viewport_drawlist(tag=CONSOLE_TOGGLE_LAYER, front=True)
    dpg.delete_item(CONSOLE_TOGGLE_LAYER, children_only=True)
    if not CONSOLE_MASTER or not dpg.does_item_exist(_hooks().rack_tag):
        return
    master = CONSOLE_MASTER[0]
    hovered = _console_toggle_at(
        tuple(float(value) for value in dpg.get_mouse_pos(local=False))
    )
    for (left, top, right, bottom), kind, who in _console_toggle_boxes():
        if kind == "mute":
            on = bool(master.parameters.mutes[int(who) - 1])
            lit, letter = METER_HOT, "M"
        elif kind == "solo":
            on = bool(master.parameters.solos[int(who) - 1])
            lit, letter = METER_QUIET, "S"
        else:
            on = bool(master.parameters.return_mutes[SENDS.index(str(who))])
            lit, letter = METER_HOT, "M"
        is_hovered = hovered == (kind, who)
        if on:
            fill = lit
            ink = (28, 26, 22, 255)
        else:
            fill = (52, 50, 46, 255) if is_hovered else (36, 36, 34, 255)
            ink = TEXT if is_hovered else MUTED_TEXT
        dpg.draw_rectangle(
            (left, top),
            (right, bottom),
            fill=fill,
            color=(0, 0, 0, 0),
            rounding=3.0,
            parent=CONSOLE_TOGGLE_LAYER,
        )
        dpg.draw_text(
            (left + 3.5, top + 0.5),
            letter,
            size=13,
            color=ink,
            parent=CONSOLE_TOGGLE_LAYER,
        )


def _paint_mute_solo(master: MasterMixer, channel: int) -> None:
    mute = CONSOLE_MUTE.format(channel=channel)
    solo = CONSOLE_SOLO.format(channel=channel)
    if dpg.does_item_exist(mute):
        dpg.bind_item_theme(
            mute,
            MUTE_ON_THEME
            if master.parameters.mutes[channel - 1]
            else TOGGLE_OFF_THEME,
        )
    if dpg.does_item_exist(solo):
        dpg.bind_item_theme(
            solo,
            SOLO_ON_THEME
            if master.parameters.solos[channel - 1]
            else TOGGLE_OFF_THEME,
        )


def _toggle_mute(
    _sender: int | str, _app_data: object, data: tuple[MasterMixer, int]
) -> None:
    master, channel = data
    master.set_mute(channel, not master.parameters.mutes[channel - 1])
    _paint_mute_solo(master, channel)
    _hooks().set_patch_status(
        f"CHANNEL {channel}  "
        f"{'MUTED' if master.parameters.mutes[channel - 1] else 'UNMUTED'}"
    )


def _toggle_solo(
    _sender: int | str, _app_data: object, data: tuple[MasterMixer, int]
) -> None:
    master, channel = data
    master.set_solo(channel, not master.parameters.solos[channel - 1])
    _paint_mute_solo(master, channel)
    soloed = [
        index + 1 for index, on in enumerate(master.parameters.solos) if on
    ]
    _hooks().set_patch_status(
        "SOLO  " + "  ".join(str(channel) for channel in soloed)
        if soloed
        else "SOLO OFF"
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


def _toggle_return_mute(
    _sender: int | str, _app_data: object, data: tuple[MasterMixer, str]
) -> None:
    master, bus = data
    on = not master.parameters.return_mutes[SENDS.index(bus)]
    master.set_return_mute(bus, on)
    _paint_return_mute(master, bus)
    _hooks().set_patch_status(f"RETURN {bus.upper()}  {'MUTED' if on else 'UNMUTED'}")


def _return_level_changed(master: MasterMixer, bus: str, level: float) -> None:
    master.set_return_level(bus, float(level))
    readout = CONSOLE_RETURN_READOUT.format(bus=bus)
    if dpg.does_item_exist(readout):
        dpg.set_value(readout, _fader_readout(float(level)))


def _build_return_strip(bus: str, master: MasterMixer) -> None:
    left_port, right_port = RETURN_PORTS[bus]
    with dpg.node(tag=CONSOLE_RETURN.format(bus=bus), label=f"FX {bus.upper()}"):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            with dpg.group(horizontal=True, horizontal_spacing=0):
                dpg.add_spacer(width=2)
                dpg.add_text("OUT", color=MUTED_TEXT)
                dpg.add_spacer(width=10)
                dpg.add_text("L", color=SIGNAL_COLORS["audio"])
                dpg.add_spacer(width=14)
                dpg.add_text("R", color=SIGNAL_COLORS["audio"])
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            level = master.parameters.return_levels[SENDS.index(bus)]
            with dpg.group(horizontal=True, horizontal_spacing=4):
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


def _build_jack_post(
    name: str,
    attribute_tag: str,
    strip: str,
    across: float,
    *,
    output: bool = False,
) -> None:
    post = CONSOLE_POST.format(name=name)
    kind = dpg.mvNode_Attr_Output if output else dpg.mvNode_Attr_Input
    with dpg.node(tag=post, label=""):
        with dpg.node_attribute(tag=attribute_tag, attribute_type=kind):
            POST_TEXTS[post] = dpg.add_text(" ")
    dpg.bind_item_theme(post, JACK_POST_THEME)
    POST_ANCHORS[post] = (strip, across)
    if output:
        POST_OUTPUTS.add(post)


def _build_console(_engine: object, master: MasterMixer) -> None:
    POST_ANCHORS.clear()
    POST_TEXTS.clear()
    POST_OUTPUTS.clear()
    CONSOLE_MASTER[:] = [master]
    for channel in range(1, MASTER_CHANNELS + 1):
        _build_strip(channel, master)
    for bus in SENDS:
        _build_return_strip(bus, master)
    for node in PINNED_NODES:
        if not dpg.does_item_exist(node) or node in POST_ANCHORS:
            continue
        theme = (
            CONSOLE_RETURN_THEME
            if str(node).startswith(CONSOLE_PREFIX + "return_")
            else CONSOLE_STRIP_THEME
        )
        dpg.bind_item_theme(node, theme)
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
        _build_jack_post(
            f"send_{bus}",
            f"{OUTPUT_NODE}.send_{bus}",
            strip,
            0.2,
            output=True,
        )
        _build_jack_post(left_port, f"{OUTPUT_NODE}.{left_port}", strip, 0.5)
        _build_jack_post(right_port, f"{OUTPUT_NODE}.{right_port}", strip, 0.78)


def _add_master_control(master: MasterMixer) -> None:
    dpg.add_spacer(width=14)
    dpg.add_text("MASTER", color=MUTED_TEXT)
    level = master.parameters.master
    _add_level_dial(
        CONSOLE_MASTER_LEVEL,
        level,
        "Master",
        lambda value: _master_level_changed(master, value),
    )
    dpg.add_text(
        _fader_readout(level), tag=CONSOLE_MASTER_READOUT, color=MUTED_TEXT
    )
    dpg.add_progress_bar(
        tag=OUTPUT_METER,
        default_value=0.0,
        overlay="",
        width=1,
        height=1,
        show=False,
    )


def _console_titles(patch: PatchGraph) -> None:
    feeding: dict[int, str] = {}
    for cable in patch.cables:
        if cable.target.module_id != _hooks().master_id:
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
        label = (
            f"{channel}"
            if source is None
            else strip_title(source, patch.modules.get(source))
        )
        if dpg.get_item_configuration(strip)["label"] != label:
            dpg.configure_item(strip, label=label)
