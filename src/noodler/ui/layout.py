"""Where modules sit, decided once, by the rack.

A Eurorack rack is rows. Modules fill a row left to right, and when a row runs
out the next module starts the row below. Nothing overlaps, because nothing can:
position is not a property a module carries around, it is a consequence of the
order modules are in and how wide the rack is.

That is the whole design, and it is worth stating why. A free canvas asks the
user to be a layout manager — to place, to space, to remember where things are,
and to go looking when they are not on screen. Every fix for that (magnetic
rails, packing, tidy, frame-all, pan, zoom, a minimap) is a fix for a problem
the canvas introduced. Rows do not have the problem: a module is always on
screen, always beside its neighbours, and always somewhere the eye can find by
reading.

What the user controls is *order*, which is the thing that carries meaning in a
patch — signal runs left to right, and dragging a module moves it through that
order. Nothing here draws; nothing here imports Dear PyGui. Layout is arithmetic
and should be testable as arithmetic.
"""

from collections.abc import Sequence
from dataclasses import dataclass


MODULE_GAP = 12.0
"""Space between neighbouring modules, in pixels."""

ROW_GAP = 16.0
"""Space between rows."""

RACK_MARGIN = 16.0
"""Space between the rack and the edge of its viewport."""

MIN_MODULE_WIDTH = 120.0
"""No panel is narrower than this, however few controls it has."""


@dataclass(frozen=True, slots=True)
class Panel:
    """A module asking for room: an identity and a natural width."""

    module_id: str
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class Placement:
    """Where one module ended up."""

    module_id: str
    row: int
    index: int
    x: float
    y: float
    width: float
    height: float

    @property
    def centre_x(self) -> float:
        return self.x + self.width * 0.5

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


def flow(
    panels: Sequence[Panel],
    *,
    view_width: float,
    margin: float = RACK_MARGIN,
    gap: float = MODULE_GAP,
    row_gap: float = ROW_GAP,
) -> tuple[Placement, ...]:
    """Lay panels into rows, wrapping when a row runs out of width.

    Row height follows the tallest panel in that row, so a row of compact
    utilities does not inherit the height of a reverb three rows down.
    """
    if not panels:
        return ()
    usable = max(MIN_MODULE_WIDTH, view_width - margin * 2.0)

    rows: list[list[Panel]] = [[]]
    used = 0.0
    for panel in panels:
        width = max(MIN_MODULE_WIDTH, panel.width)
        needed = width if not rows[-1] else used + gap + width
        if rows[-1] and needed > usable:
            rows.append([])
            used = width
        else:
            used = needed
        rows[-1].append(panel)

    placements: list[Placement] = []
    y = margin
    index = 0
    for row_number, row in enumerate(rows):
        x = margin
        height = max((panel.height for panel in row), default=0.0)
        for panel in row:
            width = max(MIN_MODULE_WIDTH, panel.width)
            placements.append(
                Placement(
                    module_id=panel.module_id,
                    row=row_number,
                    index=index,
                    x=x,
                    y=y,
                    width=width,
                    height=panel.height,
                )
            )
            x += width + gap
            index += 1
        y += height + row_gap
    return tuple(placements)


def content_height(placements: Sequence[Placement]) -> float:
    """Total height the rack needs, for the scroll region."""
    if not placements:
        return 0.0
    return max(placement.bottom for placement in placements) + RACK_MARGIN


def insertion_index(
    placements: Sequence[Placement],
    pointer_x: float,
    pointer_y: float,
    *,
    moving: str | None = None,
) -> int:
    """Return the order position a module dragged to this point should take.

    Order is what a drag means, so the answer is an index rather than a
    coordinate. The row is chosen first — a drag is mostly vertical when it
    means "put this on the next row" — and then the position within it, by
    which side of each panel's midpoint the pointer is on.
    """
    others = [
        placement for placement in placements if placement.module_id != moving
    ]
    if not others:
        return 0

    rows = sorted({placement.row for placement in others})
    row = rows[0]
    for candidate in rows:
        top = min(p.y for p in others if p.row == candidate)
        if pointer_y >= top:
            row = candidate

    index = 0
    for placement in others:
        if placement.row < row:
            index += 1
        elif placement.row == row and pointer_x > placement.centre_x:
            index += 1
    return index


def reorder(order: Sequence[str], module_id: str, index: int) -> tuple[str, ...]:
    """Move one module to a new position in the rack's order."""
    remaining = [item for item in order if item != module_id]
    index = max(0, min(index, len(remaining)))
    return tuple(remaining[:index] + [module_id] + remaining[index:])


__all__ = [
    "MIN_MODULE_WIDTH",
    "MODULE_GAP",
    "Panel",
    "Placement",
    "RACK_MARGIN",
    "ROW_GAP",
    "content_height",
    "flow",
    "insertion_index",
    "reorder",
]
