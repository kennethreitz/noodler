"""The rack: modules in rows, cables between them, and nothing to get lost in.

Modules are not placed, they are ordered. The rack owns position and derives it
from that order and its own width, so a module is always on screen, panels never
overlap, and a drag can only mean one thing — move this through the order.

Because panels cannot overlap, the pointer is never ambiguous, which removes
most of what an editor canvas usually has to defend against.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import math

import dearpygui.dearpygui as dpg

from noodler.engine import SystemAudioEngine
from noodler.motion import MeterBallistics, Spring, clamp_timestep, pixel_spring
from noodler.patch import Cable, Endpoint, OutputChannel, PatchError, PatchGraph
from noodler.ui import panel as panels
from noodler.ui import theme
from noodler.ui.layout import Panel, content_height, flow, insertion_index, reorder


EDITOR = "noodler.ui.editor"
OUTPUT_ID = "system_output"
OUTPUT_PORTS = (
    ("mono", "MONO", OutputChannel.BOTH),
    ("left", "LEFT", OutputChannel.LEFT),
    ("right", "RIGHT", OutputChannel.RIGHT),
)
TITLE_GRAB_HEIGHT = 34.0
KNOB_TRAVEL = 190.0


def node_tag(instance_id: str) -> str:
    return f"noodler.ui.node.{instance_id}"


def port_tag(instance_id: str, port_id: str) -> str:
    return f"{node_tag(instance_id)}.{port_id}"


@dataclass(slots=True)
class Knob:
    """A live control, bound to the parameter it edits."""

    instance_id: str
    control: panels.Control
    readout: int | str
    apply: Callable[[float], None]
    position: float = 0.0


@dataclass(slots=True)
class Rack:
    """Everything the rack view needs to exist."""

    patch: PatchGraph
    audio: SystemAudioEngine
    order: list[str] = field(default_factory=list)
    specs: dict[str, panels.PanelSpec] = field(default_factory=dict)
    springs: dict[str, tuple[Spring, Spring]] = field(default_factory=dict)
    knobs: dict[int | str, Knob] = field(default_factory=dict)
    meter: MeterBallistics = field(default_factory=MeterBallistics)
    scroll: float = 0.0
    dragging: str | None = None
    announce: Callable[[str], None] = lambda message: None
    on_change: Callable[[], None] = lambda: None


def _module_of(rack: Rack, instance_id: str) -> object | None:
    return rack.patch.modules.get(instance_id)


def _viewport_width(rack: Rack) -> float:
    if not dpg.does_item_exist(EDITOR):
        return 1200.0
    width = float(dpg.get_item_rect_size(EDITOR)[0])
    return width if width > 1.0 else 1200.0


def _viewport_height(rack: Rack) -> float:
    if not dpg.does_item_exist(EDITOR):
        return 800.0
    height = float(dpg.get_item_rect_size(EDITOR)[1])
    return height if height > 1.0 else 800.0


def placements(rack: Rack):
    """Where every module sits right now."""
    return flow(
        [
            Panel(
                instance_id,
                rack.specs[instance_id].width,
                rack.specs[instance_id].height,
            )
            for instance_id in rack.order
            if instance_id in rack.specs
        ],
        view_width=_viewport_width(rack),
    )


# ---------------------------------------------------------------- controls


def _format(control: panels.Control, value: float) -> str:
    if control.integral:
        shown = f"{value:,.0f}"
    elif abs(value) >= 1_000.0:
        shown = f"{value:,.0f}"
    elif abs(value) >= 10.0:
        shown = f"{value:.1f}"
    else:
        shown = f"{value:.3f}"
    return panels.fit(f"{shown} {control.unit}".strip())


def _position_of(control: panels.Control, value: float) -> float:
    if not control.logarithmic:
        span = control.maximum - control.minimum
        return 0.0 if span <= 0 else (value - control.minimum) / span
    low = math.log(control.minimum)
    return (math.log(max(value, control.minimum)) - low) / (
        math.log(control.maximum) - low
    )


def _value_of(control: panels.Control, position: float) -> float:
    position = min(1.0, max(0.0, position))
    if not control.logarithmic:
        value = control.minimum + (control.maximum - control.minimum) * position
    else:
        low = math.log(control.minimum)
        span = math.log(control.maximum) - low
        value = math.exp(low + position * span)
    return round(value) if control.integral else value


def _apply_control(
    rack: Rack, instance_id: str, control: panels.Control
) -> Callable[[float], None]:
    module = _module_of(rack, instance_id)

    def apply(value: float) -> None:
        target = getattr(module, "parameters", None)
        if target is None:
            return
        try:
            if isinstance(control.path[-1], int):
                setter = getattr(module, "set_gain", None)
                if setter is not None:
                    setter(int(control.path[-1]) + 1, value)
                return
            panels.set_panel_value(target, control.path, value)
        except Exception as error:  # a model refusing a value is not a crash
            rack.announce(f"{control.label}: {error}".split("\n")[0][:90])

    return apply


def _add_control(rack: Rack, instance_id: str, control: panels.Control) -> None:
    if control.kind == "choice":
        dpg.add_text(panels.fit(control.label), color=theme.MUTED)
        dpg.add_combo(
            list(control.choices),
            default_value=str(control.value),
            width=panels.COLUMN_CHARS * 9,
            callback=lambda _s, chosen, _u: _apply_control(
                rack, instance_id, control
            )(chosen),
        )
        return
    if control.kind == "toggle":
        dpg.add_checkbox(
            label=control.label.title(),
            default_value=bool(control.value),
            callback=lambda _s, on, _u: _apply_control(rack, instance_id, control)(on),
        )
        return

    value = float(control.value)
    position = _position_of(control, value)
    with dpg.group():
        dpg.add_text(panels.fit(control.label), color=theme.MUTED)
        knob = dpg.add_knob_float(
            label="",
            default_value=position,
            min_value=0.0,
            max_value=1.0,
            width=58,
        )
        readout = dpg.add_text(_format(control, value), color=theme.INK)
    rack.knobs[knob] = Knob(
        instance_id=instance_id,
        control=control,
        readout=readout,
        apply=_apply_control(rack, instance_id, control),
        position=position,
    )


# ------------------------------------------------------------------ panels


def _add_port(rack: Rack, instance_id: str, port: panels.Port) -> None:
    with dpg.node_attribute(
        tag=port_tag(instance_id, port.id),
        attribute_type=dpg.mvNode_Attr_Input if port.is_input else dpg.mvNode_Attr_Output,
    ):
        text = dpg.add_text(port.name, color=theme.SIGNAL.get(port.signal, theme.MUTED))
        with dpg.tooltip(text):
            dpg.add_text(port.signal.upper(), color=theme.SIGNAL.get(port.signal))
            if port.description:
                dpg.add_text(port.description, color=theme.MUTED, wrap=280)


def build_panel(rack: Rack, instance_id: str) -> None:
    """Draw one module, entirely from its derived panel."""
    spec = rack.specs[instance_id]
    accent = theme.accent_for(spec.category)
    with dpg.node(
        tag=node_tag(instance_id),
        label=spec.title,
        parent=EDITOR,
        draggable=False,
    ):
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            row: list[panels.Control] = []
            for control in spec.controls:
                row.append(control)
                if len(row) == panels.CONTROL_COLUMNS:
                    with dpg.group(horizontal=True):
                        for item in row:
                            _add_control(rack, instance_id, item)
                    row = []
            if row:
                with dpg.group(horizontal=True):
                    for item in row:
                        _add_control(rack, instance_id, item)
        for port in spec.inputs:
            _add_port(rack, instance_id, port)
        for port in spec.outputs:
            _add_port(rack, instance_id, port)
    dpg.bind_item_theme(
        node_tag(instance_id), theme.panel_theme(f"noodler.ui.theme.{spec.module_id}", accent)
    )


def build_output(rack: Rack) -> None:
    """The system output is the one panel the rack always has."""
    with dpg.node(
        tag=node_tag(OUTPUT_ID),
        label="SYSTEM OUT",
        parent=EDITOR,
        draggable=False,
    ):
        for port_id, name, _channel in OUTPUT_PORTS:
            with dpg.node_attribute(
                tag=port_tag(OUTPUT_ID, port_id),
                attribute_type=dpg.mvNode_Attr_Input,
            ):
                dpg.add_text(name, color=theme.SIGNAL["audio"])
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text(panels.fit("MASTER"), color=theme.MUTED)
            dpg.add_slider_float(
                tag="noodler.ui.master",
                default_value=rack.audio.master_gain,
                min_value=0.0,
                max_value=1.0,
                width=150,
                format="%.2f",
                callback=lambda _s, value, _u: setattr(
                    rack.audio, "master_gain", float(value)
                ),
            )
            dpg.add_progress_bar(
                tag="noodler.ui.meter", default_value=0.0, width=150, overlay="-∞ dB"
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="START", callback=lambda: _start(rack))
                dpg.add_button(label="STOP", callback=lambda: _stop(rack))
    dpg.bind_item_theme(
        node_tag(OUTPUT_ID),
        theme.panel_theme("noodler.ui.theme.output", theme.OUTPUT_ACCENT),
    )


def _start(rack: Rack) -> None:
    try:
        rack.audio.start()
        rack.announce(f"PLAYING · {rack.audio.output_device_name}")
    except Exception as error:
        rack.announce(f"AUDIO ERROR · {error}")


def _stop(rack: Rack) -> None:
    rack.audio.stop()
    rack.announce("STOPPED")


# ------------------------------------------------------------------ layout


def _springs_for(rack: Rack, instance_id: str, x: float, y: float):
    pair = rack.springs.get(instance_id)
    if pair is None:
        pair = (pixel_spring(x), pixel_spring(y))
        rack.springs[instance_id] = pair
    return pair


def settle(rack: Rack, dt: float) -> None:
    """Move every panel toward where the rack says it belongs."""
    if not dpg.does_item_exist(EDITOR):
        return
    laid_out = placements(rack)
    limit = max(0.0, content_height(laid_out) - _viewport_height(rack))
    rack.scroll = min(limit, max(0.0, rack.scroll))

    for place in laid_out:
        tag = node_tag(place.module_id)
        if not dpg.does_item_exist(tag):
            continue
        spring_x, spring_y = _springs_for(rack, place.module_id, place.x, place.y)
        target_y = place.y - rack.scroll
        if rack.dragging == place.module_id:
            spring_x.snap(place.x)
            spring_y.snap(target_y)
        spring_x.retarget(place.x)
        spring_y.retarget(target_y)
        x = spring_x.advance(dt)
        y = spring_y.advance(dt)
        current = dpg.get_item_pos(tag)
        if round(x) != round(current[0]) or round(y) != round(current[1]):
            dpg.set_item_pos(tag, [x, y])


def refresh(rack: Rack) -> None:
    """Re-derive the rack after anything structural changed."""
    for instance_id in list(rack.springs):
        if instance_id not in rack.order:
            del rack.springs[instance_id]
    rack.on_change()


# ------------------------------------------------------------------ cables


def _endpoint_for(attribute: int | str) -> tuple[str, str] | None:
    alias = dpg.get_item_alias(attribute) or attribute
    text = str(alias)
    prefix = "noodler.ui.node."
    if not text.startswith(prefix):
        return None
    body = text[len(prefix) :]
    instance_id, _, port_id = body.partition(".")
    return (instance_id, port_id) if port_id else None


def _edit(rack: Rack, operation: Callable[[], object]) -> object:
    """Make a graph change while the callback cannot be reading it."""
    running = rack.audio.is_running
    if running:
        rack.audio.stop()
    try:
        return operation()
    finally:
        if running:
            try:
                rack.audio.start()
            except Exception:
                pass


def link_created(_sender, attributes, rack: Rack) -> None:
    """Turn a dragged cable into a real route, or say why it cannot be one."""
    try:
        source = _endpoint_for(attributes[0])
        target = _endpoint_for(attributes[1])
        if source is None or target is None:
            raise PatchError("that is not a jack")
        if target[0] == OUTPUT_ID:
            channel = next(
                channel for port, _name, channel in OUTPUT_PORTS if port == target[1]
            )
            route = _edit(
                rack,
                lambda: rack.patch.connect_output(
                    source[0], source[1], channel=channel
                ),
            )
            signal = "audio"
        else:
            route = _edit(
                rack,
                lambda: rack.patch.connect(source[0], source[1], target[0], target[1]),
            )
            signal = _signal_of(rack, source[0], source[1])
        link = dpg.add_node_link(
            attributes[0], attributes[1], parent=EDITOR, user_data=route
        )
        dpg.bind_item_theme(link, theme.link_theme(f"noodler.ui.link.{signal}", signal))
        rack.announce(f"PATCHED {source[1].upper()} → {target[1].upper()}")
        refresh(rack)
    except (PatchError, ValueError, StopIteration) as error:
        rack.announce(f"CAN'T PATCH · {error}")


def link_deleted(_sender, link, rack: Rack) -> None:
    route = dpg.get_item_user_data(link)
    try:
        if isinstance(route, Cable):
            _edit(rack, lambda: rack.patch.disconnect(route))
        else:
            _edit(rack, lambda: rack.patch.disconnect_output(route))
        dpg.delete_item(link)
        rack.announce("UNPATCHED")
        refresh(rack)
    except (PatchError, ValueError) as error:
        rack.announce(f"CAN'T UNPATCH · {error}")


def _signal_of(rack: Rack, instance_id: str, port_id: str) -> str:
    module = _module_of(rack, instance_id)
    if module is not None:
        for port in module.manifest.ports:
            if port.id == port_id:
                return port.signal_type.value
    return "cv"


def remove_module(rack: Rack, instance_id: str) -> bool:
    """Take a module out of the rack, with everything patched into it."""
    if instance_id == OUTPUT_ID or instance_id not in rack.patch.modules:
        return False
    for link in tuple(dpg.get_item_children(EDITOR, 0) or ()):
        route = dpg.get_item_user_data(link)
        if isinstance(route, Cable) and instance_id in (
            route.source.module_id,
            route.target.module_id,
        ):
            dpg.delete_item(link)
        elif route is not None and getattr(route, "source", None) is not None:
            if route.source.module_id == instance_id and not isinstance(route, Cable):
                dpg.delete_item(link)
    _edit(rack, lambda: rack.patch.remove_module(instance_id))
    if dpg.does_item_exist(node_tag(instance_id)):
        dpg.delete_item(node_tag(instance_id))
    rack.order.remove(instance_id)
    rack.specs.pop(instance_id, None)
    for knob, binding in list(rack.knobs.items()):
        if binding.instance_id == instance_id:
            del rack.knobs[knob]
    refresh(rack)
    return True


__all__ = [
    "EDITOR",
    "OUTPUT_ID",
    "Knob",
    "Rack",
    "build_output",
    "build_panel",
    "link_created",
    "link_deleted",
    "node_tag",
    "placements",
    "port_tag",
    "refresh",
    "remove_module",
    "settle",
]
