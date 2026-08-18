# Noodler

> *A modular music environment where theory itself is patchable.*

Noodler is a macOS modular instrument inspired by Eurorack, built in Python so
[PyTheory](https://github.com/kennethreitz/pytheory) can live inside the rack as
a first-class musical material.

Most software synthesizers eventually reduce everything to notes, automation,
or audio. Noodler keeps those layers visible and lets them touch. A melody
generator can send musical intent into an oscillator; a slow function can move
a filter or rise into the audio range; an oscillator can become modulation;
chance can disturb harmony before harmony becomes voltage.

The question behind the project is simple:

> What does a modular instrument become when musical intelligence can be
> patched beside sound and voltage?

Noodler is not a DAW with decorative cables, and it is not an attempt to trap
physical Eurorack behind glass. It is a place for exploratory instruments:
patches that reward listening, nudging, rerouting, and coherent accidents.

## What makes it Noodler

**Musical meaning is a signal type.** Notes, scales, chords, progressions, and
rhythms travel through the graph before they are reduced to control voltage or
sound. A **Key / Scale** module sends a whole scale down a cable — any of
PyTheory's sixteen tone systems, from maqamat and melakarta ragas to gamelan,
shruti, 31-TET and Bohlen-Pierce — and a **Scale Quantizer** snaps any voltage
into it. Patch a random source through one and it becomes a melody in that
music; change the Key and everything downstream is retuned at once. An
**Instrument Voice** reads any of PyTheory's eighty-four instruments as a recipe
— oscillator, contour and filter chosen together — so "celesta" or "analog pad"
is a whole voice rather than a preset name, while **PyTheory Voice** runs the
library's own synthesis: notes are rendered by PyTheory on the control thread
and read back in real time, because rendering a note costs about as long as an
entire audio callback. PyTheory is not a menu hidden behind
the synthesizer; it is part of the synthesizer.

**Audio and CV are cousins.** Noodler distinguishes signal meaning and warns
about surprising connections, but it deliberately supports audio-rate
modulation and CV/audio cross-patching. An LFO is only slow until it is not.

**The graph is real.** Moving a cable changes the executable `PatchGraph` that
feeds the audio callback. The visible rack and the sounding instrument are two
views of the same patch. Patching an output back into something that already
feeds it is a technique, not a mistake: a loop closes on the previous block, the
way a real-time graph has always closed one.

**The interface should feel like an instrument.** Modules sit on magnetic
semantic rails, the rack moves as a single surface, and dense technical detail
can fold away. The aim is legibility and touch, not an engineering debugger.

**A patch is a document.** `.noodler` files are readable, versioned JSON. They
store the modules, controls, cables, output routing, and rack view needed to
reconstruct an instrument.

## Try it

Noodler currently targets macOS and Python 3.14. The project and its Python
installation are managed with [`uv`](https://docs.astral.sh/uv/).

```console
uv python install 3.14
uv sync
uv run noodler
```

Noodler opens to a quiet rack with a permanent **System Output** and no DSP
modules or cables. Add an oscillator from the library, patch an audio output to
`Mono / Both`, check the level, and then press **Start** on System Output.
Audio never starts automatically.

To open a saved patch directly:

```console
uv run noodler ./examples/somesound.noodler
```

Once installed in the environment, the equivalent command is:

```console
noodler ./examples/somesound.noodler
```

## The rack

The left sidebar has two related views:

- **Current Rack** is a live signal-flow tree derived from the executable
  graph. Expand a module to inspect its connected and open ports.
- **Module Library** is the catalog of instruments and utilities available to
  add. It stays present beneath the rack tree so building a patch does not
  require repeatedly opening a modal browser.

The freeform rack occupies the rest of the window. Control and modulation
modules settle onto one semantic rail; the audio path reads toward System
Output on another. These rails organize the current role of a module without
restricting what it may be patched into.

Every declared jack is visible by default. Modules can be dragged, removed
with the close target in their title, or folded by double-clicking the title
bar. A folded module becomes a narrow, sideways book spine while its DSP and
cables continue to run.

### Rack controls

| Gesture or key | Action |
| --- | --- |
| Background drag | Pan the rack |
| Space + pointer movement | Pan without holding a mouse button |
| Pinch or scroll | Smooth, pointer-anchored zoom |
| Shift + background drag | Box-select modules |
| Module title drag | Move a module along the rack |
| Module title double-click | Fold or unfold the module |
| Knob drag up/down | Adjust a value; movement accelerates with speed |
| Shift + knob drag | Fine adjustment |
| Knob double-click | Restore the parameter default |
| Double-click a cable | Unpatch it |
| Delete / Backspace | Remove selected cables or modules |
| Command-K | Focus the module library |
| Command-Z / Command-Shift-Z | Undo / redo |
| F | Frame the whole rack |
| Escape | Close the browser or clear selection |

`Unplug All` removes every module cable and System Output tap as one graph
edit, so experiments remain easy to unwind.

## Modules

The built-in provider currently contains 21 modules, grouped around the way a
patch is made rather than around implementation details.

| Shelf | Modules |
| --- | --- |
| Compose & Modulate | Key / Scale, Scale Quantizer, Melody Brain, Harmony Brain, Arpeggio Brain, Scale Generator, Function Utility, Wogglebug |
| Generate | PyTheory Voice, Instrument Voice, Triangle Core Complex VCO, Classic VCO, FM Voice, Supersaw, Noise Source |
| Shape & Control | State Variable Filter, Ladder Filter, ADSR Envelope, VCA, Low-Pass Gate |
| Mix & Space | Master Mixer, Polarizing Mixer, Echo Delay, Stereo Reverb |

PyTheory brains prepare musical structures on the control path. Oscillators,
filters, dynamics, utilities, and effects implement the block-processing
contract used by the live graph. Pydantic models describe their parameters and
typed ports so the same definitions can support the UI, persistence, provider
interchange, and validation.

## Patch documents

A `.noodler` document stores:

- stable provider, module-type, and instance identifiers;
- validated module parameters;
- directed cables and stereo System Output taps;
- master gain; and
- module positions, folded state, semantic rails, and rack zoom.

It intentionally does not serialize audio device handles, sample buffers,
oscillator phase, random-generator progress, delay memory, or a running audio
device. Loading a patch creates fresh DSP state from the saved instrument.

The format is human-readable and friendly to source control. See the
[version-one patch contract](DOCS/PATCH_FORMAT.md) and the
[example patches](examples/) for the complete shape.

## Architecture

Noodler is intentionally one Python application today:

```text
Dear PyGui rack
modules, cables, controls, camera
             │
      commands and state
             │
       Noodler engine
patch graph, history, persistence
       ┌─────┴─────┐
       │           │
PyTheory brains  block DSP
musical intent   audio and CV
       │           │
       └─────┬─────┘
             │
 SoundDevice / Core Audio
```

- **Dear PyGui** renders the GPU-backed rack and owns interaction.
- **Noodler's engine** owns the patch graph, module lifecycle, edit history,
  and document model.
- **PyTheory** supplies musical primitives for scale, melody, harmony, and
  sequencing modules.
- **SoundDevice** opens the default Core Audio output and asks the graph for
  stereo `float32` blocks.
- **Pydantic** validates manifests, ports, parameters, cables, and patch files
  at the boundaries between those pieces.

A native Swift shell or a lower-level DSP core remains possible if measured
needs justify one. Python is the compositional center of the project, not an
implementation detail to hide prematurely.

## Development

```console
uv sync
uv run pytest
uv run noodler
```

The repository root is the only `uv` project root. `src/noodler/engine` is an
internal package and shares the application's environment and lockfile.

The default rack is deliberately empty, but the deterministic **Hirajoshi
Garden** reference instrument remains available to tests and development with
`build_ui(starter_patch=True)`. It combines PyTheory melody, Wogglebug clocks
and uncertainty, a complex triangle-core voice, low-pass-gate articulation,
slow function modulation, and stereo reverb.

## Current state

Noodler is an audible prototype, not yet a finished macOS application.

- There is no signed, self-contained `.app` bundle yet.
- The third-party provider API is still young and should not be considered
  stable.
- The audio callback still allocates Python dictionaries and NumPy arrays, and
  topology changes do not yet use immutable graph-snapshot handoff.
- The graph should remain structurally unchanged while audio is running.

The next audio milestone is not merely more modules. It is reusable buffers,
precompiled routing, measured callback load and xruns, and atomic graph swaps
at block boundaries. The next interaction milestone is the same kind of rigor:
test what the rack actually feels like, not only what its callbacks claim to
do.

## Documentation

- [Project overview](DOCS/README.md)
- [Architecture](DOCS/ARCHITECTURE.md)
- [Technology decisions](DOCS/TECHNOLOGY.md)
- [Module interoperability](DOCS/MODULES.md)
- [Patch graph and system audio](DOCS/AUDIO.md)
- [Rack motion](DOCS/MOTION.md)
- [Editing and undo](DOCS/EDITING.md)
- [Patch file format](DOCS/PATCH_FORMAT.md)

Questions remain: how far Python can carry the real-time path, whether the
eventual macOS surface should stay in Dear PyGui, how providers remain
compatible across releases, and how MIDI, MPE, OSC, clock, recording, and
offline rendering should enter the instrument. Those are design pressures,
not reasons to erase the strange and useful center of the idea.

*Not a DAW with cables. Not Eurorack trapped on a screen. A place where sound,
voltage, chance, and musical thought can touch.*
