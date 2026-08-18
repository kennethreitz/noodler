# Patch graph and system audio

**Status:** First audible vertical slice, implemented 2026-08-17

Noodler now has a concrete block-processing contract, a validated directed
patch graph, and callback-driven output to the default system audio device.

## Default patch

The application starts with this prepared patch:

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

The init patch is a deterministic generative instrument named **Hirajoshi
Garden**. PyTheory prepares A Hirajoshi and a seeded melodic-wander traversal.
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

Audio does not start automatically. The System Output node has explicit Start
and Stop controls so opening the app cannot produce a surprise tone. Its init
gain is 0.72, after deliberately conservative levels throughout the patch.

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
The initial engine requests stereo float32 output with a 256-frame block size
and low latency.

"System Output" currently means the default macOS output device. A virtual
audio driver can be used by making it the system default. Explicit device and
channel selection belongs in a later audio settings panel.

To hear the default patch:

```console
uv run noodler
```

Then click **Start** in the System Output node. Frequency, level, mixer gain,
reverb controls, and master level changes are audible while the stream is
running.

## Real-time limitations

This slice proves the end-to-end boundary; it is not yet a hardened real-time
engine. Module processing and graph rendering allocate NumPy arrays and Python
dictionaries in the callback, and topology changes do not yet use immutable
snapshot handoff. The graph should remain structurally unchanged while audio
is running.

Before targeting very small buffers, Noodler should add reusable buffers,
compile input routing outside the callback, measure callback load and xruns,
and atomically swap prepared graph snapshots at block boundaries.
