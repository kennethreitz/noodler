# Noodler architecture

**Status:** Initial direction, accepted 2026-08-17

Noodler is a macOS modular music environment inspired by Eurorack. It should
make patching playful and immediate while supporting modules that understand
musical concepts such as notes, chords, scales, progressions, and rhythm.

## Application shape

The first version will be one Python application:

```text
Dear PyGui interface
rack, modules, cables, controls, scopes
                    │
           commands and snapshots
                    │
Noodler engine
patch graph, transport, module lifecycle
          ┌─────────┴─────────┐
          │                   │
PyTheory modules       real-time callback
theory, MIDI,          prepared graph and
sequencing, synthesis  audio/CV processing
```

Dear PyGui owns the application window and event loop. The engine owns the
patch model, transport, module state, and communication with the audio device.
PyTheory is a direct application dependency and supplies musical primitives
and existing performance capabilities.

This is intentionally not a Swift application with an embedded or external
Python interpreter. A native shell remains an option if macOS integration
eventually requires one, but it is not part of the initial architecture.

## Rack hierarchy

The canvas uses two visual lanes. `Modulation / Control` contains
function generators, LFOs, random voltage, clocks, and PyTheory sources. Their
cables generally descend into parameters on the `Audio Path`, whose modules
read naturally from left to right toward system output.

The default workspace is split into a persistent outline/library sidebar on
the left and a freeform patch rack on the right. The outline is a live tree of
the current rack: it traces signal flow upstream from System Output and groups
anything not yet connected under `Unpatched`. The searchable module library
sits beneath that current-rack tree. The rack itself is intentionally quiet:
the executable graph has no modules, cables, or output taps, and only the
permanent System Output panel appears on the audio rail.

These lanes are now magnetic rails rather than initial-position suggestions.
Dragging a module leaves it free to travel horizontally, while a spring pulls
it back to its semantic rail and adjacent modules slide aside before they can
overlap. The defined order preserves the readable control and audio hierarchy.
Panning and zooming transform the rail coordinates with the modules, so the
layout cannot drift away from its organizing structure.

This placement describes a module's role in the current patch, not a hard
signal restriction. An LFO can run into the audio range, an oscillator can
become modulation, and audio/CV cross-patching remains part of the module
contract.

Each module starts with every declared jack visible, with inputs ordered before
outputs. A directional summary such as `2 IN -> 1 OUT` reflects the executable
graph, while the optional `Hide Open` filter reduces the faceplate to connected
jacks. Adding or removing a cable refreshes this view from the real
`PatchGraph`; visibility never creates a separate cosmetic routing state.
The rack-level `Unplug All` control removes every module cable and system-output
tap in one audio-safe graph edit, then clears the corresponding visual links.

The current-rack tree is rebuilt from the real `PatchGraph` after every module
or cable topology edit, so it cannot become a decorative outline that disagrees
with the sounding patch. Beneath it, the searchable library is generated from
the built-in provider manifest. Its 19 entries are first grouped into the
musical workflow shelves `Compose & Modulate`, `Generate`, `Shape & Control`,
and `Mix & Space`, then into their provider categories. `Add Module` and
Command-K focus this catalog's search field rather than opening a second
surface. Selecting an entry constructs a real DSP module, assigns a unique
instance ID, generates validated controls from its Pydantic parameter model,
and places it on the appropriate semantic rail while leaving the catalog
available for the next addition. The new module then participates in patching,
folding, camera movement, audio rendering, and patch saving exactly like any
other rack module; repeated selections create numbered instances instead of
replacing an existing voice.

Dragging empty rack background treats every module as one rack view,
preserving the lane hierarchy while moving around the canvas. Dear PyGui repeats
its mouse-down callback for every frame a button is held, so the pan is begun
once and then left alone; beginning it again each frame moved its origin to the
current pointer and left the drag with nothing to travel. The node editor's own
box selection cannot be turned off, so a plain background drag pans with the
marquee themed away, and Shift keeps box selection on the modified drag, where
the marquee is worth drawing. Those colours belong to the editor rather than to
a node, and had no effect until they were declared against `mvNodeEditor`.
Space-drag is also retained as a shortcut that can begin over a module. Background
detection uses the editor bounds and the known module rectangles; canvas pan
never mutates native module draggability, so module and knob interactions stay
distinct from empty-canvas drag. A small AppKit event monitor
bridges the native magnify gesture that Dear PyGui does not expose; both pinch
and wheel input queue a smooth, pointer-anchored zoom. Visible minus,
percentage/reset, and
plus controls provide the same camera operation without a gesture. The rack
camera scales node placement, typography, and rotary-control hit regions
together, while the bottom-right minimap retains a complete overview. Rack
fonts are bound per module, so the toolbar, zoom selector, current-rack tree,
and module library remain at a stable interface scale while the canvas moves.

Open modules favor horizontal control density over tall inspector-like stacks.
Rotary controls are slightly smaller, generated numeric parameters pack three
across, redundant faceplate descriptions live in tooltips, and tighter node
padding preserves the instrument character without wasting vertical space.
Every removable module also carries a close target at the right edge of its
colored title. The same removal action appears beside the module in the live
rack tree; both paths delete the executable module and every connected cable
or output tap. System Output remains permanent and has no close target.

Double-clicking a module's colored title bar folds every control and jack down
to a narrow, colored book spine with a rotated title. This is visual state
only: DSP parameters, executable cables, and audio continue unchanged. Visual
cables touching the folded module are hidden instead of dangling from stale
jack coordinates. Reopening restores the visibility of each attribute and
live cable as it was before folding, then reconciles the compact patch bay
with the current graph.

The versioned, Pydantic-validated `.noodler` JSON format stores the executable
graph, parameter models, system output, and rack view. See
[`PATCH_FORMAT.md`](PATCH_FORMAT.md) for the version-one contract.

## Repository and dependency layout

The repository root is the `uv` project root. There is one `pyproject.toml`
and one committed `uv.lock` for the application.

```text
noodler/
├── pyproject.toml
├── uv.lock
├── DOCS/
├── src/
│   └── noodler/
│       ├── app.py
│       ├── engine/
│       ├── modules/
│       ├── patch/
│       └── ui/
└── tests/
```

`engine` is an internal Python package, not an independently managed project.
A nested `engine/pyproject.toml` would only be justified if the engine became
a separately released package, used a different Python runtime, or needed an
independent dependency and release lifecycle.

Expected development commands are:

```console
uv sync
uv run noodler
uv run pytest
```

The lockfile, rather than hand-pinned transitive dependencies, is the source
of reproducible development environments. `uv` manages the project and its
Python environment; the mechanism used to produce a signed, self-contained
`.app` bundle will be selected and tested separately.

## Runtime boundary

Audio work has real-time deadlines even though the application is written in
Python. The UI must not perform audio processing, and the audio callback must
not wait for the UI.

The intended responsibilities are:

- **UI thread:** input, drawing, module placement, cable editing, and visual
  feedback.
- **Control path:** patch validation, graph changes, module configuration,
  transport changes, and preparation of state needed by the audio callback.
- **Audio callback:** processing an already prepared graph for the current
  block with bounded, predictable work.

The callback must not perform file access, dependency loading, UI operations,
or other blocking work. Graph edits and expensive preparation happen outside
the callback and become visible at a safe block boundary. The exact handoff
mechanism will be chosen through measurement; likely candidates are immutable
graph snapshots or double-buffered state.

PyTheory's current live engine already uses cached voices and block-based
processing. Noodler should reuse that work where it fits rather than porting it
preemptively. If profiling later identifies a native-code bottleneck, the
block processor may be replaced or accelerated without changing the module
model or user interface.

The first implementation uses sounddevice to open the default Core Audio
output. Its callback renders a prepared stereo `PatchGraph`, applies the
system-output gain and safety clamp, and preserves explicit left/right taps.
A `both` tap duplicates a mono source when desired. The prototype still
allocates during rendering; reusable buffers and graph-snapshot handoff remain
required before calling the callback path real-time hardened.

The engine also keeps time. It holds the rack's `Transport` and advances it
once per callback by `frame_count / sample_rate`, so the clock runs on the
sample clock rather than the frame rate; the UI reads the position and only
advances it itself while no audio is playing. Before rendering, the engine
writes a frozen `TransportFrame` — tempo, bar phase at the block's first
sample, bars elapsed, running — onto the graph, and the graph hands it to any
module that sets `uses_transport`. Nothing else sees it. A module rendered
without one (offline, in a test) runs free from its own rate, so clocked
modules are faithful to the transport when there is one and never dependent
on it. Divisions still reach ordinary rates through the control path as hertz.

## Signal types

Noodler should distinguish signal meaning instead of treating every cable as
an untyped value:

- **Audio:** block-sized sample buffers.
- **CV:** continuous floating-point control values, potentially at audio rate.
- **Gate/trigger:** discrete events with precise timing.
- **Musical:** semantic values such as notes, chords, scales, progressions,
  rhythms, and transport position.

Musical signals are a defining feature. They allow PyTheory-aware modules to
exchange intent before that intent is reduced to MIDI notes or audio samples.
Port compatibility should be visible in the rack and enforced by the patch
model.

## Module boundary

A module will eventually need to describe:

- stable type and instance identifiers;
- input and output ports with signal types;
- user-facing parameters and defaults;
- preparation needed for the sample rate and block size;
- control/event handling; and
- block processing when the module participates in the real-time graph.

The first working patch established the initial runtime interface:
`process(frame_count, sample_rate, inputs) -> outputs`. Named input and output
mappings carry scalar values or mono NumPy blocks using the stable port IDs in
the manifest. This API remains young, but it is now exercised by the VCO,
polarizing mixer, function utility, complex random source, PyTheory scale
generator, organic low-pass gate, patch graph, and system output tests.

The built-in provider has now grown into a 19-module catalog and supplies a
factory keyed by manifest module ID. Musical brains prepare PyTheory phrases,
progressions, and voicings on the control path; oscillators, noise, filters,
envelopes, dynamics, delay, and reverb implement the numeric block protocol.
The graph-level library test exercises a complete alternate voice from Harmony
Brain through arpeggiation, oscillator, filter, ADSR/VCA, and echo.

The module library creates instances directly through this factory. Generated
Pydantic-backed panels cover the complete catalog, while bespoke panels remain
available to the composed reference patch. The default rack consequently stays
empty without reducing the executable module library to a cosmetic catalog.

## Composed reference patch

The optional Hirajoshi Garden starter exercises a visible, executable patch:

```text
Function Utility Ch. 1 -> VCO morph CV
Wogglebug Woggle -> VCO frequency CV 2
Wogglebug Clock -> PyTheory A Hirajoshi Wander -> VCO pitch
Complex VCO morph + triangle + Woggle Ring Mod -> Polarizing Mixer
PyTheory trigger -> Bloom Low-Pass Gate strike
Polarizing Mixer -> Bloom -> Stereo Reverb -> System Output L/R
Function Utility Ch. 4 -> Reverb decay; Wogglebug Burst -> Reverb freeze
```

The two function channels make unrelated 28- and 78-second arcs, avoiding an
obvious shared repetition. Wogglebug adds restrained correlated pitch drift,
clocks the phrase-aware PyTheory melody, contributes a quiet audio undertone,
and probabilistically freezes the reverb field. Bloom gives every selected
tone a coupled amplitude and brightness contour. The graph validates all
twelve module cables, compiles utility, random, and musical sources before the
VCO, mixer, low-pass gate, and reverb, and renders a decorrelated stereo field
into the default macOS output device when the user presses Start. The System
Output node owns master level and explicit Start/Stop controls.

## Vertical-slice follow-ups

The composed reference patch and alternate library voice exercise the central
musical-to-audio path:

```text
Clock -> PyTheory Chord Sequencer -> Arpeggiator -> Oscillator
                                              │
LFO -------------------------------> Filter cutoff
                                              │
                                         Filter -> Output
```

The remaining product slice should improve:

- editing parameters with immediate audible feedback;
- starting and stopping transport;
- expanding the current output meter into scopes; and
- reopening saved patch documents.

The module library, browser, executable cable editing, and versioned patch
capture now meet on the same provider and graph boundaries. Continuous
small-buffer testing while the UI is being manipulated remains necessary.

## Open decisions

- The external-provider creation protocol beyond the built-in factory.
- The synchronization strategy between control state and the callback.
- Packaging, signing, notarization, and whether Mac App Store sandboxing is a
  goal.
- Support for hardware MIDI, Ableton Link, Audio Units, and physical Eurorack
  CV through a DC-coupled interface.
