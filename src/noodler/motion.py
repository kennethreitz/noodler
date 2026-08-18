"""Frame-rate independent motion for the rack camera, rails, and controls.

Every animated surface in Noodler settles toward a target: modules spring onto
their semantic rails, the camera eases into a new zoom, the output meter falls
back after a transient. Doing that with a fixed per-frame fraction —
``value += (target - value) * 0.24`` — ties the *feel* of the instrument to the
refresh rate of the display it happens to be on. The same code settles twice as
fast on a 120 Hz ProMotion panel as it does on a 60 Hz external monitor, and it
never quite arrives, so it needs a snap threshold that pops the last pixel.

This module solves the same motion in continuous time instead. A critically
damped spring is integrated in closed form, so it is exact for any timestep,
unconditionally stable across frame hitches, and reaches its target with zero
overshoot. Motion is specified as a *half-life* — the time to cover half the
remaining distance — because that is the number a designer can actually feel,
and it stays true whatever the frame rate.

Nothing here imports Dear PyGui or touches global state: each helper takes an
explicit timestep, which makes the instrument's feel directly testable.
"""

from dataclasses import dataclass, field
import math


CRITICAL_DAMPING_CONSTANT = 1.6783469900166608
"""Angular frequency per unit half-life for a critically damped spring.

Released from rest, a critically damped spring covers half its distance when
``(1 + u)·e**-u == 0.5``. This is that ``u``: ``omega = u / half_life``.
"""

MAX_TIMESTEP = 0.05
"""Longest timestep the animation layer will believe, in seconds.

A garbage-collection pause, a window resize, or a patch edit that briefly stops
the audio device can hand the UI a large delta. Clamping keeps a hitch from
teleporting every module across the rack; motion resumes rather than jumping.
"""

RAIL_HALF_LIFE = 0.06
"""Rail settling. Weighty enough to read as a rack, quick enough to obey.

Chosen to match the settle time the current per-frame easing happens to produce
on a 60 Hz display, so the rack does not become slower — only consistent.
"""

ZOOM_HALF_LIFE = 0.05
"""Camera zoom. The viewport should feel attached to the pointer."""

PAN_GLIDE_HALF_LIFE = 0.32
"""Momentum left behind by a released canvas flick."""

METER_RELEASE_HALF_LIFE = 0.28
"""Output-meter fallback, in the tradition of a peak-programme meter."""

KNOB_TRAVEL_PIXELS = 180.0
"""Pointer travel for one full parameter sweep at nominal drag speed."""


def clamp_timestep(dt: float, maximum: float = MAX_TIMESTEP) -> float:
    """Reject non-positive and implausibly long frames before integrating."""
    if not math.isfinite(dt) or dt <= 0.0:
        return 0.0
    return min(float(dt), maximum)


def smoothstep(edge_0: float, edge_1: float, value: float) -> float:
    """Ease a value between two edges with zero slope at both ends."""
    if edge_0 == edge_1:
        return 0.0 if value < edge_0 else 1.0
    position = min(1.0, max(0.0, (value - edge_0) / (edge_1 - edge_0)))
    return position * position * (3.0 - 2.0 * position)


def advance_spring(
    value: float,
    velocity: float,
    target: float,
    dt: float,
    half_life: float,
) -> tuple[float, float]:
    """Integrate one critically damped spring step in closed form.

    The error term of a critically damped oscillator is ``(A + B·t)·e**-wt``,
    which can be evaluated exactly rather than stepped numerically. That makes
    the result identical for one long frame or many short ones, and it cannot
    diverge the way an explicit Euler spring does when a frame runs long.
    """
    if half_life <= 0.0:
        return target, 0.0
    step = clamp_timestep(dt)
    if step == 0.0:
        return value, velocity

    omega = CRITICAL_DAMPING_CONSTANT / half_life
    error = value - target
    coefficient = velocity + omega * error
    decay = math.exp(-omega * step)
    next_value = target + (error + coefficient * step) * decay
    next_velocity = (velocity - coefficient * omega * step) * decay
    return next_value, next_velocity


@dataclass(slots=True)
class Spring:
    """A scalar that chases a target without overshooting it.

    The spring carries velocity, so a target that moves while the spring is in
    flight — a module dragged past its neighbours, a zoom nudged again before it
    lands — is absorbed as a change of course rather than a restart.

    Settling thresholds are expressed in the target's own units, so prefer the
    ``pixel_spring`` and ``unit_spring`` constructors below over raw defaults:
    half a pixel is invisible on the rack but would swallow the whole zoom
    range.
    """

    value: float = 0.0
    target: float = 0.0
    velocity: float = 0.0
    half_life: float = RAIL_HALF_LIFE
    settle_distance: float = 0.0005
    settle_velocity: float = 0.005

    @property
    def settled(self) -> bool:
        """Report whether the spring has arrived and stopped moving."""
        return (
            abs(self.value - self.target) <= self.settle_distance
            and abs(self.velocity) <= self.settle_velocity
        )

    def snap(self, value: float | None = None) -> float:
        """Place the spring at rest, cancelling any motion in progress."""
        if value is not None:
            self.target = float(value)
        self.value = self.target
        self.velocity = 0.0
        return self.value

    def retarget(self, target: float) -> None:
        """Aim at a new target while preserving the current velocity."""
        self.target = float(target)

    def advance(self, dt: float) -> float:
        """Advance by one timestep and return the new value."""
        self.value, self.velocity = advance_spring(
            self.value,
            self.velocity,
            self.target,
            dt,
            self.half_life,
        )
        if self.settled:
            return self.snap()
        return self.value


def pixel_spring(value: float, half_life: float = RAIL_HALF_LIFE) -> Spring:
    """Build a spring for rack coordinates, settling below half a pixel."""
    return Spring(
        value=value,
        target=value,
        half_life=half_life,
        settle_distance=0.5,
        settle_velocity=2.0,
    )


def unit_spring(value: float, half_life: float = ZOOM_HALF_LIFE) -> Spring:
    """Build a spring for normalized quantities such as the zoom factor."""
    return Spring(
        value=value,
        target=value,
        half_life=half_life,
        settle_distance=0.0005,
        settle_velocity=0.002,
    )


def glide(velocity: float, dt: float, half_life: float = PAN_GLIDE_HALF_LIFE) -> float:
    """Decay a released velocity by half every ``half_life`` seconds."""
    if half_life <= 0.0:
        return 0.0
    step = clamp_timestep(dt)
    if step == 0.0:
        return velocity
    return velocity * 0.5 ** (step / half_life)


@dataclass(slots=True)
class Glide:
    """Momentum for a flicked canvas, in one axis.

    A drag that ends while the pointer is still moving should keep moving. The
    rack is large and mostly empty; without inertia every pan costs the user a
    second gesture to reach the same place.
    """

    velocity: float = 0.0
    half_life: float = PAN_GLIDE_HALF_LIFE
    minimum_speed: float = 8.0

    @property
    def moving(self) -> bool:
        return abs(self.velocity) > self.minimum_speed

    def release(self, velocity: float) -> None:
        """Hand the glide the pointer velocity measured at release."""
        self.velocity = float(velocity)

    def stop(self) -> None:
        self.velocity = 0.0

    def advance(self, dt: float) -> float:
        """Return the offset travelled this frame, decaying the velocity."""
        step = clamp_timestep(dt)
        if step == 0.0 or not self.moving:
            self.velocity = 0.0
            return 0.0
        offset = self.velocity * step
        self.velocity = glide(self.velocity, step, self.half_life)
        if not self.moving:
            self.velocity = 0.0
        return offset


@dataclass(slots=True)
class PointerTracker:
    """A smoothed estimate of how fast the pointer is currently moving.

    Per-frame pointer deltas are noisy enough that using them directly to scale
    a control makes the control feel unstable. This keeps a short exponential
    average, in pixels per second, that a knob can read without chattering.
    """

    speed: float = 0.0
    half_life: float = 0.06

    def reset(self) -> None:
        self.speed = 0.0

    def sample(self, distance: float, dt: float) -> float:
        """Fold one frame's pointer travel into the running speed estimate."""
        step = clamp_timestep(dt)
        if step == 0.0:
            return self.speed
        instantaneous = abs(distance) / step
        blend = 1.0 - 0.5 ** (step / self.half_life) if self.half_life > 0 else 1.0
        self.speed += (instantaneous - self.speed) * blend
        return self.speed


def drag_gain(
    speed: float,
    *,
    fine: bool = False,
    slow_speed: float = 90.0,
    fast_speed: float = 1_400.0,
    minimum_gain: float = 0.32,
    maximum_gain: float = 2.4,
    fine_gain: float = 0.1,
) -> float:
    """Scale a knob's pixels-to-value ratio by how fast the pointer is moving.

    A slow, deliberate movement should resolve small changes; a fast sweep
    should cross the whole range. Adapting to pointer speed gives both from one
    gesture, so reaching for a modifier becomes a choice rather than a
    requirement. Holding Shift still drops into a deliberately fine ratio.
    """
    eased = smoothstep(slow_speed, fast_speed, max(0.0, speed))
    gain = minimum_gain + (maximum_gain - minimum_gain) * eased
    return gain * fine_gain if fine else gain


@dataclass(slots=True)
class KnobDrag:
    """Accumulate a vertical drag into a normalized control position.

    Position is integrated rather than derived from the press origin, because
    the pixels-to-value ratio changes with pointer speed within a single drag.
    """

    position: float = 0.0
    minimum: float = 0.0
    maximum: float = 1.0
    travel_pixels: float = KNOB_TRAVEL_PIXELS
    pointer: PointerTracker = field(default_factory=PointerTracker)

    def begin(self, position: float) -> None:
        """Start a drag from the control's current position."""
        self.position = min(self.maximum, max(self.minimum, float(position)))
        self.pointer.reset()

    def advance(self, delta_y: float, dt: float, *, fine: bool = False) -> float:
        """Apply one frame of pointer movement and return the new position."""
        if self.travel_pixels <= 0.0:
            return self.position
        speed = self.pointer.sample(delta_y, dt)
        gain = drag_gain(speed, fine=fine)
        span = self.maximum - self.minimum
        self.position -= delta_y * gain * span / self.travel_pixels
        self.position = min(self.maximum, max(self.minimum, self.position))
        return self.position


@dataclass(slots=True)
class MeterBallistics:
    """Peak-programme ballistics for the output meter.

    An audio level drawn straight from the callback flickers, because it is a
    per-block peak. Meters are readable when they rise instantly and fall on a
    known slope, with the recent maximum held above the falling bar.
    """

    level: float = 0.0
    peak: float = 0.0
    release_half_life: float = METER_RELEASE_HALF_LIFE
    peak_hold_seconds: float = 1.4
    peak_release_half_life: float = 0.9
    _held_for: float = 0.0

    def reset(self) -> None:
        self.level = 0.0
        self.peak = 0.0
        self._held_for = 0.0

    def advance(self, sample: float, dt: float) -> float:
        """Fold one block peak into the displayed level and return it."""
        step = clamp_timestep(dt)
        value = 0.0 if not math.isfinite(sample) else max(0.0, float(sample))

        if value >= self.level:
            self.level = value
        elif step > 0.0 and self.release_half_life > 0.0:
            self.level *= 0.5 ** (step / self.release_half_life)

        if value >= self.peak:
            self.peak = value
            self._held_for = 0.0
        elif step > 0.0:
            self._held_for += step
            if self._held_for > self.peak_hold_seconds:
                self.peak = max(
                    self.level,
                    self.peak * 0.5 ** (step / self.peak_release_half_life),
                )
        return self.level


__all__ = [
    "CRITICAL_DAMPING_CONSTANT",
    "Glide",
    "KNOB_TRAVEL_PIXELS",
    "KnobDrag",
    "MAX_TIMESTEP",
    "METER_RELEASE_HALF_LIFE",
    "MeterBallistics",
    "PAN_GLIDE_HALF_LIFE",
    "PointerTracker",
    "RAIL_HALF_LIFE",
    "Spring",
    "pixel_spring",
    "unit_spring",
    "ZOOM_HALF_LIFE",
    "advance_spring",
    "clamp_timestep",
    "drag_gain",
    "glide",
    "smoothstep",
]
