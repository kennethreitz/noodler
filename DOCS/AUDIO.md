# Patch graph and system audio

**Status:** First audible vertical slice, implemented 2026-08-17

Noodler now has a concrete block-processing contract, a validated directed
patch graph, and callback-driven output to the default system audio device.

## Default patch

The application opens as **Untitled Patch** with an empty `PatchGraph`: no DSP
modules, cables, or system-output taps. The one permanent rack object is System
Output, placed at the end of the audio rail. This makes startup silent and
leaves the user's first musical decision to the `Add Module` browser instead
of presenting a large composition as a blank template.

System Output still has explicit Start and Stop controls, but starting an empty
patch produces silence. Its default master gain is 0.8. A first audible patch
can be as small as an oscillator connected directly to `Mono / Both`.

## Hirajoshi Garden reference patch

The earlier composed init remains available to tests and development through
`build_ui(starter_patch=True)`. It is a deterministic generative instrument,
not the application default:

```text
                         HIRAJOSHI GARDEN

Function Ch. 1 (11 s / 17 s) ───────────────> VCO morph
Woggle Woggle (depth +0.018) ───────────────> VCO pitch drift
Woggle Clock (0.47 Hz) ──> PyTheory A3 Hirajoshi ──> VCO 1 V/oct
                                  melodic wander       │
                                                       ├─ morph ──── +0.48 ─┐
                                                       └─ triangle ─ +0.14 ─┤
Woggle Ring Mod ──────────────────────────────────────────────── +0.12 ─────┤
                                                                          v
                                                                Polarizing Mix
                                                                          │
PyTheory note trigger ───────────────────────────────────────> Bloom LPG strike
                                                                          │
                                                                          v
Function Ch. 4 (31 s / 47 s) ─────────────────────────────> Reverb decay CV
Woggle Burst ──────────────────────────────────────────────> Reverb freeze
                                                       left / right ──> System
```

PyTheory prepares A Hirajoshi and a seeded melodic-wander traversal.
Unlike independent random-note selection, the walk favors neighboring tones,
visits interior anchors halfway through each phrase, and returns to a tonic at
eight-event boundaries. Wogglebug supplies its 0.47 Hz clock, so the same seed
always opens with the same recognizable piece.

Utility Channel 1 makes a 28-second asymmetrical timbre arc. Woggle CV adds no
more than a few cents of correlated pitch movement, while a small amount of
Woggle Ring Mod sits beneath the VCO's morph and triangle outputs. Their mix is
struck by each new PyTheory note through Bloom, a vactrol-inspired low-pass
gate. Amplitude and brightness therefore decay together instead of leaving the
oscillator as a continuous drone.

Utility Channel 4 makes a separate 78-second arc in the reverb decay. Woggle
Burst occasionally freezes the reverb tank, suspending a fragment of the
melody before allowing new sound back into the field. The reverb starts at a
52% equal-power mix with an 8.5-second tail and sends its decorrelated left and
right fields to the corresponding device channels.

Audio does not start automatically. The reference patch uses a 0.72 master
gain after deliberately conservative levels throughout its signal path.

The system bus preserves stereo. Its `Mono / Both` jack still makes a single
source available equally on both channels, while the separate `Left` and
`Right` jacks support stereo modules such as the reverb. Non-finite samples
become silence and the final device signal is clipped to the normalized
`[-1, +1]` range. Internal module cables and the patch output bus remain
unclipped.

## Patch contract

A runtime module exposes a manifest and one method:

```python
process(frame_count, sample_rate, inputs) -> outputs
```

Inputs and outputs are mappings from manifest port IDs to scalar values or
mono NumPy blocks. The graph validates port direction and signal compatibility,
allows the established audio/CV crossings, permits only one cable to drive an
input, and prepares a stable topological processing order. Fan-out is allowed.

Feedback loops are currently rejected. They require an explicit one-sample or
one-block delay module so their scheduling and behavior are unambiguous.

Patch endpoints, cables, and output taps are frozen Pydantic models. Runtime
module instances and their DSP state remain ordinary Python objects.

## Device layer

[`sounddevice`](https://python-sounddevice.readthedocs.io/) supplies the
PortAudio callback and uses Core Audio on macOS. Passing no device or sample
rate selects the system's current default output and its native default rate.
The engine requests stereo float32 output with a 256-frame render block and
low device latency. Patch rendering happens on a dedicated worker into an
adaptive sample reservoir; the Core Audio callback only drains already
prepared frames.

The reservoir begins three blocks ahead (about 16 ms at 48 kHz). A short read
or a PortAudio output-underflow flag doubles its target depth, up to 32 blocks
(about 171 ms). After twenty uninterrupted seconds it removes one block at a
time, so a difficult patch earns safety quickly and latency falls cautiously
when the machine settles. The storage is allocated once when playback starts;
recovery does not allocate or restart the device from inside the callback.

`SystemAudioEngine.buffered_frames`, `target_buffer_frames`,
`target_buffer_ms`, and `underrun_count` expose that behavior as inexpensive
telemetry. A finite reservoir cannot make sustained slower-than-real-time DSP
keep up, so a failed render worker still aborts the stream instead of silently
playing zeros forever.

"System Output" currently means the default macOS output device. A virtual
audio driver can be used by making it the system default. Explicit device and
channel selection belongs in a later audio settings panel.

To build a first patch:

```console
uv run noodler
```

Then click **Add Module**, choose an oscillator, and drag one of its visible
audio outputs to System Output's `Mono / Both` jack. Click **Start** only when
the route and levels are ready.

## Real-time limitations

This slice proves the end-to-end boundary; it is not yet a fully hardened
real-time engine. Module processing and graph rendering still allocate NumPy
arrays and Python dictionaries, but they now do so on the render-ahead worker
rather than on Core Audio's callback. Topology changes do not yet use immutable
snapshot handoff. The app therefore stops the stream around structural graph
edits.

Further hardening should add reusable module buffers, compile input routing
outside the render loop, measure render load alongside xruns, and atomically
swap prepared graph snapshots at block boundaries.

## Control-rate work stays off the sample clock

Rendering the reference patch was taking 92% of a 256-frame callback at the
median and passing 100% at the 95th percentile, which is audible as dropouts:
any scheduling jitter at all lands past the deadline. Raising the block size
bought nothing — the ratio held near 90% from 256 through 2048 frames — which
is the signature of a cost that is purely per-sample Python.

Nearly half of it was the function utility, a *control* source shaping contours
measured in tens of seconds while stepping its stage machine once per sample.
Running free it now advances in strides and interpolates between decisions,
which is inaudible on a slow contour and is asserted as such: the strided
output is compared against the per-sample one and must not drift.

The stride stands down whenever something sub-stride could change the outcome —
a signal to slew, a trigger, a cycle gate — and shrinks with the contour, since
these channels reach audio rate, where a stage lasts a handful of samples and
every one of them is the shape. A fast channel renders bit-for-bit identically
to the per-sample path.

Measured on the same patch afterwards: 51% of budget at the median, and 54% at
the maximum rather than 171%. The tail matters more than the median here — a
callback only has to miss once to be heard.

The remaining cost is in the modules that genuinely need a sample clock: the
reverb's delay network and the low-pass gate. Vectorising those is the next
move if the callback ever needs more room.

## Feedback closes on the previous block

The graph used to refuse a cycle outright, telling the user that feedback
required an explicit delay module. For an instrument inspired by Eurorack that
is close to backwards: patching an output into something that already feeds it
is a technique — self-oscillation, resonant networks, chaotic patches — and
refusing it made a whole family of patches unbuildable.

The order is now compiled as far as it can be, and whatever remains is a cycle.
The cable that closes it is marked as feedback and left out of the ordering;
those cables read the previous block rather than the current one, which is how a
real-time graph has always closed a loop — with a delay of one block, and no
algebraic loop to solve.

The newest cable in a cycle is the one chosen to close it, so cables already
carrying signal keep doing so and the one just patched becomes the feedback
path, which is what the hand that patched it expects. Only the outputs a loop
actually asks for are remembered between blocks, and a change of block size
starts the loop again rather than feeding a module the wrong number of samples.
