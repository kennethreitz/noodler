# Noodler motion

**Status:** Adopted, 2026-08-17

Noodler is an instrument, so its interface is judged the way an instrument is
judged: by how it responds, not by what it can do. This document describes why
the original animation felt inconsistent, the model in `noodler.motion` that
replaced it, and how `app.py` now uses it.

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

## Sub-pixel state and integer positions

Dear PyGui stores node positions as integers: `set_item_pos(node, [x, 570.75])`
reads back as `570`. Any animation that re-reads the item position each frame to
continue from it therefore discards its own sub-pixel state, and the truncation
bias accumulates — once per frame, so the error depends on how many frames the
motion took. That is a second, quieter way for a frame rate to change the
result, and it is part of why the original easing needed a snap threshold to
finish at all.

The same applies to moving the whole rack. A sprung or gliding camera asks for
a fraction of a pixel per frame, and truncating that on every module, every
frame, makes the camera fall short of where it was sent. `_translate_rack`
therefore carries the remainder and only ever writes whole pixels, so a slow
move arrives exactly where a fast one does.

The spring therefore owns the position and the node is only its rendering.
`_settle_rack_rails` re-syncs a spring from its item **only** when the two
differ by more than a pixel, which means something outside the animation moved
the module: a drag, a loaded preset. Camera moves are handled by transforming
the springs themselves — `_translate_rack` offsets them with the pan, and
`_set_rack_zoom` scales them about the same anchor as the nodes — so the camera
never looks like an external move.

## Adoption in `app.py`

All six points are in place, and `tests/test_rack_feel.py` covers them.

1. **A timestep.** `_refresh_frame` derives one `clamp_timestep(get_delta_time())`
   per frame and passes it to every settle function.
2. **Rails.** `RAIL_SPRINGS` holds one `pixel_spring` pair per node, cleared in
   `build_ui` and dropped when a module is removed. The `0.24` easing and the
   `0.75` px snap are gone; a settled module lands exactly on its rail.
3. **Zoom.** `CanvasInteraction.zoom_spring` is a `unit_spring`; pointer
   anchoring is unchanged. Rack nodes select a zoom-sized font locally instead
   of changing Dear PyGui's global font scale, so the toolbar, zoom selector,
   rack outline, and module library remain fixed workspace chrome.
4. **Pan momentum.** `_track_pan_velocity` smooths the pointer velocity during a
   drag, `_release_pan_momentum` hands it to a `Glide` pair on release, and
   `_glide_rack` carries the rack to rest in about 1.4 s. Any fresh press
   catches a gliding canvas, the way a finger does.
5. **Knobs.** `KnobDrag` replaced `_vertical_drag_position`. Resolution now
   follows pointer speed, so a slow movement resolves fine detail and a fast
   sweep crosses the range from the same gesture; Shift remains as a deliberate
   choice rather than a requirement. Double-clicking a control restores the
   value its module was built with.
6. **Meter.** `MeterBallistics` gives the output meter instant attack, a 280 ms
   release, and a held recent maximum shown as `PK` in the overlay.

## The camera has a way home

Momentum makes it possible to send the rack somewhere the window is not, and an
empty starting rack means a newly added module can land outside the view. Both
are answered by one sprung camera offset:

- `_frame_rack` (**F**) fits every module in the window and centres it, zoom
  included.
- `_reveal_node` moves the shortest distance that makes a single module fully
  visible, and runs whenever a module is added, so an add is never silent.
- Any press on the rack cancels a move in flight, so the camera never fights
  the pointer.

Both feed `CanvasInteraction.recenter_x/y`, advanced by `_settle_recenter` and
applied through `_translate_rack` — so framing obeys the same half-life, the
same clamped timestep, and the same sub-pixel accounting as everything else.

## The keyboard

The keys that edit a rack, and the history that makes them safe to try, are
described in [Editing the rack](EDITING.md).

## Deliberately not here

Cable rendering, module fold/unfold, and browser transitions still animate with
their own constants or not at all. They should adopt the same springs rather
than grow new ones.

**Pointer capture during a knob drag** is the one feel item deliberately left
out. Holding the pointer still — hiding the cursor, disassociating it, and
reading raw AppKit deltas — is what stops a long sweep dying at the top of the
screen, and `macos_gestures.py` is the right home for it. It is left undone
because none of it can be verified without a real window and a real cursor, and
a half-correct version leaves the user's pointer hidden or frozen. It wants a
hands-on pass, with an unconditional release in `_end_knob_drag`, in `main`'s
`finally`, and a per-frame watchdog for a lost mouse-up.
