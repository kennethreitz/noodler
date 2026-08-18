"""The window around the rack, and the handful of gestures it answers to.

One gesture means one thing:

    drag a jack          patch
    drag a title         move a module through the order
    drag a knob          change a value
    wheel                scroll the rack
    delete               remove what is selected
    ⌘Z / ⌘⇧Z             undo, redo

There is no pan, no zoom, no frame, no tidy and no minimap, because the rack
lays itself out and never puts a module somewhere the window is not.
"""

from dataclasses import dataclass, field
import math

import dearpygui.dearpygui as dpg

from noodler.engine import SystemAudioEngine
from noodler.history import Edit, EditHistory
from noodler.module_providers.builtin import (
    BUILTIN_PROVIDER_MANIFEST,
    BuiltinProvider,
)
from noodler.motion import KnobDrag, clamp_timestep
from noodler.patch import PatchGraph
from noodler.ui import panel as panels
from noodler.ui import rack as rack_view
from noodler.ui import theme
from noodler.ui.layout import insertion_index, reorder
from noodler.ui.rack import EDITOR, OUTPUT_ID, Rack


WINDOW = "noodler.ui.window"
SIDEBAR = "noodler.ui.sidebar"
SEARCH = "noodler.ui.search"
OUTLINE = "noodler.ui.outline"
LIBRARY = "noodler.ui.library"
STATUS = "noodler.ui.status"
SUMMARY = "noodler.ui.summary"
HANDLERS = "noodler.ui.handlers"
SIDEBAR_WIDTH = 300


@dataclass(slots=True)
class Shell:
    """Live interaction state for one window."""

    rack: Rack
    drag: KnobDrag = field(default_factory=KnobDrag)
    active_knob: int | str | None = None
    last_pointer_y: float = 0.0
    grabbed: str | None = None
    history: EditHistory = field(default_factory=EditHistory)
    keys_held: set[int] = field(default_factory=set)


def announce(message: str) -> None:
    if dpg.does_item_exist(STATUS):
        dpg.set_value(STATUS, message)


def _summarise(shell: Shell) -> None:
    rack = shell.rack
    modules = len(rack.patch.modules)
    cables = len(rack.patch.cables) + len(rack.patch.output_taps)
    if dpg.does_item_exist(SUMMARY):
        dpg.set_value(
            SUMMARY,
            "EMPTY RACK"
            if not modules
            else f"{modules} MODULE{'S' if modules != 1 else ''}"
            f"  ·  {cables} CABLE{'S' if cables != 1 else ''}",
        )
    if dpg.does_item_exist(OUTLINE):
        dpg.delete_item(OUTLINE, children_only=True)
        for instance_id in rack.order:
            spec = rack.specs.get(instance_id)
            if spec is None:
                continue
            wired = sum(
                1
                for cable in rack.patch.cables
                if instance_id in (cable.source.module_id, cable.target.module_id)
            )
            dpg.add_text(
                f"{spec.title[:22]:22s} {wired}",
                parent=OUTLINE,
                color=theme.accent_for(spec.category),
            )
        if not rack.order:
            dpg.add_text("NOTHING PATCHED YET", parent=OUTLINE, color=theme.FAINT)


# ------------------------------------------------------------------ modules


def _unique_id(patch: PatchGraph, module_id: str) -> str:
    if module_id not in patch.modules:
        return module_id
    suffix = 2
    while f"{module_id}_{suffix}" in patch.modules:
        suffix += 1
    return f"{module_id}_{suffix}"


def add_module(shell: Shell, module_id: str, *, record: bool = True) -> str | None:
    """Put a module in the rack, at the end of the order."""
    rack = shell.rack
    try:
        module = BuiltinProvider().create(module_id)
    except KeyError:
        announce(f"NO SUCH MODULE · {module_id}")
        return None
    instance_id = _unique_id(rack.patch, module_id)
    rack_view._edit(rack, lambda: rack.patch.add_module(instance_id, module))
    rack.specs[instance_id] = panels.describe(module)
    rack.order.insert(max(0, len(rack.order) - 1), instance_id)
    rack_view.build_panel(rack, instance_id)
    rack_view.refresh(rack)
    announce(f"ADDED {rack.specs[instance_id].title}")
    if record:
        shell.history.record(
            Edit(
                description=f"add {rack.specs[instance_id].title}",
                undo=lambda: rack_view.remove_module(rack, instance_id),
                redo=lambda: add_module(shell, module_id, record=False),
            )
        )
    return instance_id


def remove_selected(shell: Shell) -> None:
    """Delete whatever is selected: cables first, then modules."""
    rack = shell.rack
    for link in tuple(dpg.get_selected_links(EDITOR)):
        rack_view.link_deleted(EDITOR, link, rack)
    removed = 0
    for item in tuple(dpg.get_selected_nodes(EDITOR)):
        for instance_id in list(rack.order):
            tag = rack_view.node_tag(instance_id)
            if dpg.does_item_exist(tag) and dpg.get_alias_id(tag) == item:
                if rack_view.remove_module(rack, instance_id):
                    removed += 1
    if removed:
        announce(f"REMOVED {removed} MODULE{'S' if removed != 1 else ''}")
    dpg.clear_selected_nodes(EDITOR)
    dpg.clear_selected_links(EDITOR)


# ------------------------------------------------------------- interaction


def _editor_origin() -> tuple[float, float]:
    if not dpg.does_item_exist(EDITOR):
        return (0.0, 0.0)
    return tuple(float(value) for value in dpg.get_item_rect_min(EDITOR))


def _module_title_at(shell: Shell, x: float, y: float) -> str | None:
    """Which module's title strip is under this screen point."""
    for instance_id in shell.rack.order:
        tag = rack_view.node_tag(instance_id)
        if not dpg.does_item_exist(tag):
            continue
        left, top = dpg.get_item_rect_min(tag)
        right, _bottom = dpg.get_item_rect_max(tag)
        if left <= x <= right and top <= y <= top + TITLE_HEIGHT:
            return instance_id
    return None


TITLE_HEIGHT = 32.0


def on_press(_sender, _data, shell: Shell) -> None:
    if shell.active_knob is not None or shell.grabbed is not None:
        return
    x, y = (float(value) for value in dpg.get_mouse_pos(local=False))

    for knob, binding in reversed(list(shell.rack.knobs.items())):
        if dpg.does_item_exist(knob) and dpg.is_item_hovered(knob):
            shell.active_knob = knob
            binding.position = float(dpg.get_value(knob))
            shell.drag.minimum, shell.drag.maximum = 0.0, 1.0
            shell.drag.begin(binding.position)
            shell.last_pointer_y = y
            return

    grabbed = _module_title_at(shell, x, y)
    if grabbed is not None and grabbed != OUTPUT_ID:
        shell.grabbed = grabbed
        shell.rack.dragging = grabbed
        announce(f"MOVING {shell.rack.specs[grabbed].title}")


def on_drag(_sender, _data, shell: Shell) -> None:
    knob = shell.active_knob
    if knob is not None and dpg.does_item_exist(knob):
        binding = shell.rack.knobs[knob]
        y = float(dpg.get_mouse_pos(local=False)[1])
        fine = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
        position = shell.drag.advance(
            y - shell.last_pointer_y,
            clamp_timestep(dpg.get_delta_time()),
            fine=fine,
        )
        shell.last_pointer_y = y
        binding.position = position
        dpg.set_value(knob, position)
        value = rack_view._value_of(binding.control, position)
        binding.apply(value)
        dpg.set_value(binding.readout, rack_view._format(binding.control, value))
        announce(
            f"{binding.control.label} {rack_view._format(binding.control, value).strip()}"
        )
        return

    if shell.grabbed is None:
        return
    origin_x, origin_y = _editor_origin()
    x, y = (float(value) for value in dpg.get_mouse_pos(local=False))
    where = insertion_index(
        rack_view.placements(shell.rack),
        x - origin_x,
        y - origin_y + shell.rack.scroll,
        moving=shell.grabbed,
    )
    wanted = reorder(shell.rack.order, shell.grabbed, where)
    if wanted != tuple(shell.rack.order):
        shell.rack.order[:] = list(wanted)


def on_release(_sender, _data, shell: Shell) -> None:
    if shell.active_knob is not None:
        shell.active_knob = None
        announce("")
    if shell.grabbed is not None:
        shell.grabbed = None
        shell.rack.dragging = None
        _summarise(shell)
        announce("")


def on_wheel(_sender, amount, shell: Shell) -> None:
    shell.rack.scroll -= float(amount) * 60.0


def on_key(_sender, key, shell: Shell) -> None:
    if key in shell.keys_held:
        return
    shell.keys_held.add(key)
    command = dpg.is_key_down(dpg.mvKey_ModSuper) or dpg.is_key_down(dpg.mvKey_ModCtrl)
    searching = dpg.does_item_exist(SEARCH) and dpg.is_item_focused(SEARCH)

    if key in (dpg.mvKey_Delete, dpg.mvKey_Back) and not searching:
        remove_selected(shell)
    elif key == dpg.mvKey_Z and command:
        forward = dpg.is_key_down(dpg.mvKey_ModShift)
        edit = shell.history.redo() if forward else shell.history.undo()
        announce(
            f"{'REDID' if forward else 'UNDID'} {edit.description}"
            if edit
            else f"NOTHING TO {'REDO' if forward else 'UNDO'}"
        )
        _summarise(shell)
    elif key == dpg.mvKey_K and command:
        dpg.focus_item(SEARCH)
    elif key == dpg.mvKey_Escape:
        dpg.clear_selected_nodes(EDITOR)
        dpg.clear_selected_links(EDITOR)
        announce("")


def on_key_release(_sender, key, shell: Shell) -> None:
    shell.keys_held.discard(key)


# ------------------------------------------------------------------- build


def _filter_library(_sender, query: str, shell: Shell) -> None:
    needle = (query or "").strip().lower()
    for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
        tag = f"noodler.ui.library.{manifest.id}"
        if not dpg.does_item_exist(tag):
            continue
        haystack = f"{manifest.name} {manifest.category} {manifest.description}".lower()
        dpg.configure_item(tag, show=not needle or needle in haystack)


def build(shell: Shell) -> None:
    """Assemble the window: a sidebar, a rack, and one line of status."""
    theme.configure()
    rack = shell.rack
    rack.announce = announce
    rack.on_change = lambda: _summarise(shell)

    with dpg.window(tag=WINDOW):
        with dpg.group(horizontal=True):
            dpg.add_text("NOODLER", color=theme.accent_for("Musical Brains"))
            dpg.add_text("EMPTY RACK", tag=SUMMARY, color=theme.MUTED)

        with dpg.group(horizontal=True):
            with dpg.child_window(tag=SIDEBAR, width=SIDEBAR_WIDTH, height=-28):
                dpg.add_text("RACK", color=theme.MUTED)
                with dpg.child_window(tag=OUTLINE, height=150, border=False):
                    pass
                dpg.add_separator()
                dpg.add_input_text(
                    tag=SEARCH,
                    hint="Search modules…",
                    width=-1,
                    callback=_filter_library,
                    user_data=shell,
                )
                with dpg.child_window(tag=LIBRARY, border=False):
                    by_category: dict[str, list] = {}
                    for manifest in BUILTIN_PROVIDER_MANIFEST.modules:
                        by_category.setdefault(manifest.category, []).append(manifest)
                    for category, manifests in by_category.items():
                        dpg.add_text(category.upper(), color=theme.accent_for(category))
                        for manifest in manifests:
                            dpg.add_button(
                                label=manifest.name,
                                tag=f"noodler.ui.library.{manifest.id}",
                                width=-1,
                                callback=lambda _s, _d, chosen: add_module(
                                    shell, chosen
                                ),
                                user_data=manifest.id,
                            )

            with dpg.node_editor(
                tag=EDITOR,
                callback=lambda s, d: rack_view.link_created(s, d, rack),
                delink_callback=lambda s, d: rack_view.link_deleted(s, d, rack),
                width=-1,
                height=-28,
                minimap=False,
            ):
                rack_view.build_output(rack)

        dpg.add_text("", tag=STATUS, color=theme.MUTED)

    dpg.bind_item_theme(EDITOR, theme.EDITOR_THEME)
    if OUTPUT_ID not in rack.order:
        rack.order.append(OUTPUT_ID)
    rack.specs[OUTPUT_ID] = panels.PanelSpec(
        module_id=OUTPUT_ID,
        title="SYSTEM OUT",
        category="Utilities",
        description="",
        controls=(),
        inputs=tuple(
            panels.Port(port, name, "audio", "", True) for port, name, _c in
            rack_view.OUTPUT_PORTS
        ),
        outputs=(),
    )
    _summarise(shell)

    if not dpg.does_item_exist(HANDLERS):
        with dpg.handler_registry(tag=HANDLERS):
            dpg.add_mouse_down_handler(
                button=dpg.mvMouseButton_Left, callback=on_press, user_data=shell
            )
            dpg.add_mouse_drag_handler(
                button=dpg.mvMouseButton_Left,
                threshold=0.0,
                callback=on_drag,
                user_data=shell,
            )
            dpg.add_mouse_release_handler(
                button=dpg.mvMouseButton_Left, callback=on_release, user_data=shell
            )
            dpg.add_mouse_wheel_handler(callback=on_wheel, user_data=shell)
            for key in (
                dpg.mvKey_Delete,
                dpg.mvKey_Back,
                dpg.mvKey_Z,
                dpg.mvKey_K,
                dpg.mvKey_Escape,
            ):
                dpg.add_key_press_handler(key, callback=on_key, user_data=shell)
                dpg.add_key_release_handler(
                    key, callback=on_key_release, user_data=shell
                )


def frame(_sender, _data, shell: Shell) -> None:
    dt = clamp_timestep(dpg.get_delta_time())
    rack_view.settle(shell.rack, dt)
    if dpg.does_item_exist("noodler.ui.meter"):
        level = min(1.0, shell.rack.meter.advance(shell.rack.audio.last_peak, dt))
        dpg.set_value("noodler.ui.meter", level)
        dpg.configure_item(
            "noodler.ui.meter",
            overlay="-∞ dB" if level <= 1e-5 else f"{20.0 * math.log10(level):.0f} dB",
        )
    dpg.set_frame_callback(dpg.get_frame_count() + 1, frame, user_data=shell)


def create(patch: PatchGraph | None = None) -> Shell:
    """Build a shell around a fresh or given patch."""
    patch = patch or PatchGraph()
    return Shell(rack=Rack(patch=patch, audio=SystemAudioEngine(patch, master_gain=0.8)))


def main() -> None:
    """Run the rack."""
    shell = create()
    dpg.create_context()
    try:
        dpg.create_viewport(title="Noodler", width=1440, height=900, min_width=900)
        build(shell)
        dpg.setup_dearpygui()
        dpg.set_primary_window(WINDOW, True)
        dpg.show_viewport()
        dpg.set_frame_callback(1, frame, user_data=shell)
        dpg.start_dearpygui()
    finally:
        shell.rack.audio.close()
        dpg.destroy_context()


if __name__ == "__main__":
    main()
