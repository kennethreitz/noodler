# Noodler motion

**Status:** Proposed, 2026-08-17

Noodler is an instrument, so its interface is judged the way an instrument is
judged: by how it responds, not by what it can do. This document describes why
the current animation feels inconsistent, the model that replaces it in
`noodler.motion`, and the specific places in `app.py` that should adopt it.

## The problem

Every animated surface in the rack settles with a fixed fraction of the
remaining distance, applied once per frame:

```python
easing = 0.24                                    # _settle_rack_rails
next_x = current_x + (target_x - current_x) * easing
if abs(next_x - target_x) < 0.75:                # ...and a snap, because
    next_x = target_x                            #    it never actually lands

next_zoom = interaction.zoom + remaining * 0.3   # _settle_rack_zoom
```

Two consequences follow, and both are felt rather than seen.

**The instrument's feel is tied to the display.** A per-frame fraction has no
concept of elapsed time, so its speed is whatever the refresh rate happens to
be. Measured from the constants above:

| motion | half-life | at 60 Hz | at 120 Hz |
| --- | --- | --- | --- |
| rail settle (`0.24`) | 2.53 frames | 42.1 ms | 21.0 ms |
| camera zoom (`0.30`) | 1.94 frames | 32.4 ms | 16.2 ms |

A 400 px module displacement settles in 383 ms on a 60 Hz external monitor and
191 ms on the ProMotion panel of the laptop next to it. That is the same code,
running twice as fast, on the machine the app is being designed on. It is also
why the feel is hard to tune: every adjustment is being made against a moving
reference.

**First-order lag has no arrival.** `value += error * k` decays exponentially
toward the target and never reaches it, so it needs the `0.75` px snap to
finish — a small visible pop at the end of every settle. It also has no
velocity: it starts at maximum speed and only decelerates. Physical objects
accelerate, and a rack of modules reads as physical.

A frame hitch makes both worse. Because the step ignores elapsed time, a long
frame animates exactly as far as a short one, so motion silently stalls
whenever the audio device is restarted for a patch edit.

## The model

`noodler.motion` solves the same motion in continuous time.

**Critically damped springs.** Rails, camera, and controls settle on a spring
that carries velocity and is tuned to the boundary between overshooting and
crawling. A retarget mid-flight becomes a change of course rather than a
restart, motion eases in *and* out, and nothing ever bounces past a target —
modules making room for a dragged neighbour must not oscillate.

The step is the closed-form solution of the critically damped oscillator rather
than a numerical integration:

```python
omega = CRITICAL_DAMPING_CONSTANT / half_life
error = value - target
coefficient = velocity + omega * error
decay = math.exp(-omega * dt)
value = target + (error + coefficient * dt) * decay
velocity = (velocity - coefficient * omega * dt) * decay
```

Because it is exact, one long frame and ten short ones produce the same result,
and it cannot diverge the way an explicit Euler spring does when a frame runs
long. Frame-rate independence is a property of the solution, not a correction
applied on top of it — and it is asserted directly in `tests/test_motion.py`,
which settles the same spring at 30, 60, 120, 144, and 240 Hz and requires the
results to agree.

**Half-life, not stiffness.** Motion is specified as the time to cover half the
remaining distance, because that is the number that can be felt and reasoned
about. `RAIL_HALF_LIFE` is 60 ms, chosen so the rack settles in about the time
it already does on a 60 Hz display: the goal is consistency, not slowness.

**Clamped timesteps.** `MAX_TIMESTEP` (50 ms) bounds what the animation layer
will believe. A garbage collection pause or a device restart resumes motion
instead of teleporting every module across the rack.

**Domain-specific constructors.** Settle thresholds are in the target's own
units, so `pixel_spring` (settles below half a pixel) and `unit_spring`
(normalized quantities such as zoom) exist to keep a rack threshold from being
applied to the 0.55–1.65 zoom range, where it would swallow the entire travel.

## Adoption in `app.py`

Each of these is independent and can be taken separately.

**1. A timestep.** `_refresh_frame` is already the per-frame hook. Give it a
delta and pass it to the settle functions:

```python
dt = clamp_timestep(dpg.get_delta_time())
```

**2. Rails.** Keep one spring pair per node beside `CANVAS_INTERACTION`, reset
in `build_ui` alongside the other interaction resets, and drop entries when a
module is removed:

```python
RAIL_SPRINGS: dict[int | str, tuple[Spring, Spring]] = {}

# inside the _settle_rack_rails loop, replacing `easing` and the 0.75 snap:
spring_x, spring_y = _rail_springs(node, current_x, current_y)
if node == active_node:
    spring_x.snap(current_x)      # the pointer owns a dragged module
    spring_y.snap(current_y)
    continue
spring_x.value = current_x        # the item position stays the source of truth
spring_y.value = current_y
spring_x.retarget(target_x)
spring_y.retarget(target_y)
next_x = spring_x.advance(dt)
next_y = spring_y.advance(dt)
```

Assigning `.value` each frame re-syncs the spring if anything else moved the
node — a drag, a loaded preset — while preserving the velocity it had.

**3. Zoom.** Replace `remaining * 0.3` and the `0.001` snap with a
`unit_spring(zoom, ZOOM_HALF_LIFE)` whose target is `zoom_target`; advance it
and hand the result to `_set_rack_zoom` with the existing anchor, so the
pointer-anchored behaviour is unchanged.

**4. Pan momentum.** `_pan_rack` moves every node by the pointer delta and
stops dead on release. Track pointer velocity while panning, hand it to a
`Glide` pair in `_end_knob_drag`, and apply `glide.advance(dt)` per frame using
the same offset loop `_pan_rack` already uses — including the `rail_y` shift.
The rack is large and mostly empty; without inertia every pan across it costs a
second gesture.

**5. Knobs.** `_drag_knob` is already incremental, so `KnobDrag` drops into the
place `_vertical_drag_position` occupies, with `interaction.drag_position`
becoming the `KnobDrag`. It adds velocity-adaptive resolution: a slow,
deliberate movement resolves fine detail and a fast sweep crosses the range,
from one gesture. Shift stays, as a deliberate choice rather than a
requirement.

**6. Meter.** `_refresh_ui` writes the raw per-block peak into the progress
bar, which flickers. `MeterBallistics` gives it instant attack, a 280 ms
release, and a held recent maximum, which is how a peak-programme meter is
read.

## Deliberately not here

Cable rendering, module fold/unfold, and browser transitions are left alone
until the settling model above is in place; they should use the same springs
rather than grow their own constants.

One unrelated observation belongs with the feel work: the rack's own status
line advertises `SELECT CABLE + DELETE TO UNPATCH`, but `app.py` registers no
key handlers at all — only mouse ones. The instrument currently tells the user
to press a key that does nothing.
