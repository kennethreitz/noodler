"""Pure drawing geometry for patch cables, controls, and keybeds."""

import math


CABLE_SAG_PER_PX = 0.16
CABLE_SAG_MIN = 10.0
CABLE_SAG_MAX = 110.0
CABLE_SEGMENTS = 28


def cable_sag(length: float) -> float:
    return min(
        CABLE_SAG_MAX,
        max(CABLE_SAG_MIN, CABLE_SAG_PER_PX * length + 8.0),
    )


def hanging_cable_points(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[tuple[float, float], ...]:
    """A cable between two modules, hanging under its apparent weight."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(1.0, math.hypot(dx, dy))
    reach = min(120.0, max(24.0, 0.25 * length))
    sag = cable_sag(length)
    return (
        start,
        (start[0] + reach, start[1] + sag),
        (end[0] - reach, end[1] + sag),
        end,
    )


def console_cable_points(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[tuple[float, float], ...]:
    """A cable that leaves a module sideways and enters a console jack above."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(1.0, math.hypot(dx, dy))
    reach = min(80.0, max(30.0, 0.2 * length))
    drop = max(50.0, 0.6 * abs(dy))
    droop = min(40.0, 0.4 * cable_sag(length))
    return (
        start,
        (start[0] + reach, start[1] + droop),
        (end[0], end[1] - drop),
        end,
    )


def bezier_point(
    points: tuple[tuple[float, float], ...], t: float
) -> tuple[float, float]:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    one = 1.0 - t
    return (
        one**3 * x0 + 3 * one**2 * t * x1 + 3 * one * t**2 * x2 + t**3 * x3,
        one**3 * y0 + 3 * one**2 * t * y1 + 3 * one * t**2 * y2 + t**3 * y3,
    )


def clip_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Liang-Barsky clipping for one line segment against a rectangle."""
    left, top, right, bottom = rect
    x1, y1 = start
    dx, dy = end[0] - x1, end[1] - y1
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, x1 - left), (dx, right - x1), (-dy, y1 - top), (dy, bottom - y1)):
        if p == 0.0:
            if q < 0.0:
                return None
            continue
        ratio = q / p
        if p < 0.0:
            lo = max(lo, ratio)
        else:
            hi = min(hi, ratio)
        if lo > hi:
            return None
    return ((x1 + lo * dx, y1 + lo * dy), (x1 + hi * dx, y1 + hi * dy))


def clipped_cable_runs(
    control_points: tuple[tuple[float, float], ...],
    rect: tuple[float, float, float, float],
    *,
    segments: int = CABLE_SEGMENTS,
) -> list[list[tuple[float, float]]]:
    """Visible polyline runs of a cable inside the rack rectangle."""
    sampled = [bezier_point(control_points, index / segments) for index in range(segments + 1)]
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for start, end in zip(sampled, sampled[1:]):
        clipped = clip_segment(start, end, rect)
        if clipped is None:
            if current:
                runs.append(current)
                current = []
            continue
        visible_start, visible_end = clipped
        if not current or current[-1] != visible_start:
            if current:
                runs.append(current)
            current = [visible_start]
        current.append(visible_end)
    if current:
        runs.append(current)
    return [run for run in runs if len(run) >= 2]


def knob_track_points(
    size: int, sweep_start: float, sweep_end: float, inset: float = 0.0
) -> list[tuple[float, float]]:
    centre = size * 0.5
    radius = size * 0.5 - 1.0 - inset
    return [
        (
            centre
            + radius * math.cos(
                sweep_start + (sweep_end - sweep_start) * step / 32
            ),
            centre
            + radius * math.sin(
                sweep_start + (sweep_end - sweep_start) * step / 32
            ),
        )
        for step in range(33)
    ]


def keybed_geometry(
    w: int,
    h: int,
    semitone_count: int,
    black_semitones: frozenset[int] | set[int],
) -> list[tuple[int, bool, float, float, float, float]]:
    """Return semitone, colour, and rectangle for a compact piano keybed."""
    whites = [s for s in range(semitone_count) if s not in black_semitones]
    white_width = w / len(whites)
    keys: list[tuple[int, bool, float, float, float, float]] = []
    white_index = {s: i for i, s in enumerate(whites)}
    for semitone in range(semitone_count):
        if semitone in black_semitones:
            below = white_index[semitone - 1]
            left = (below + 1) * white_width - white_width * 0.3
            keys.append(
                (semitone, True, left, 0.0, left + white_width * 0.6, h * 0.6)
            )
        else:
            index = white_index[semitone]
            keys.append(
                (
                    semitone,
                    False,
                    index * white_width,
                    0.0,
                    (index + 1) * white_width,
                    float(h),
                )
            )
    return keys
