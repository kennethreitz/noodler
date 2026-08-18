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
library's own synthesis: notes are rendered by PyTheory and read back in real
time, because rendering one costs about as long as an entire audio callback.
It renders a note per semitone, so playing a pitch barely resamples it — and
because the cost of a note is a property of the instrument rather than the
library (a tenth of a millisecond for a music box, twenty for a piano), how
much it renders before it answers is decided by a time budget, and the rest
arrives on a worker while the instrument is already playing. **PyTheory Beats**
plays any of the library's hundred rhythm presets — funk, teental, bossa nova,
trap — through its own drum synthesis, locked to the rack's clock so beat one
is beat one; and a **Clock** module turns that clock into triggers and a ramp,
so anything with a clock input can be patched to the tempo in the menu bar.
**PyTheory Score** plays a phrase written down — `E5:q D5:e C5:e r:q
[A3,C4,E4]:h` — round and round on the clock, PyTheory reading the note names,
so what a bar contains is decided rather than drawn. **PyTheory Raga** improvises in
any of the library's fifty-four ragas the way a raga is played — up by the
aroha, down by the avaroha, sometimes the pakad — in just intonation from the
raga's own ratios; **PyTheory Maqam** walks any of its ten maqamat the way a
maqam is played, quarter-tones and all, justly tuned from a tonic; a **Tone
Row** steps through a twelve-tone row in any of its forms; **PyTheory
Progression** plays any of the library's thirty-odd chord progressions — or
numerals you write — in any key and mode, a chord every so many bars on the
clock, voiced close, open, drop-two or inverted, as four pitches with a root,
a gate and a trigger, or wanders, each chord one PyTheory suggests after the
last; the **PyTheory Chord Ear** names the chord the pitches patched into it
make and puts out its root and its dissonance; **PyTheory Negative Harmony**
mirrors a line about a key's axis, so major turns minor and a rising line
falls, still in the key. **PyTheory FX** streams the library's chorus, phaser, tremolo,
overdrive, tape saturation and cabinet. **PyTheory Reverb** puts a
signal in any of the library's rooms — Schroeder's
algorithm, or an impulse response it synthesises for a hall, a plate, a
spring, a cathedral, a cave, a canyon, a parking garage or the Taj Mahal —
convolved in real time, a twelve-second room for a fifth of a millisecond a
block. A new rack opens with a delay on send A and one of these rooms on send
B, already returning. PyTheory is not a menu hidden behind
the synthesizer; it is part of the synthesizer.

**Audio and CV are cousins.** Noodler distinguishes signal meaning and warns
about surprising connections, but it deliberately supports audio-rate
modulation and CV/audio cross-patching. An LFO is only slow until it is not.

**The graph is real.** Moving a cable changes the executable `PatchGraph` that
feeds the audio callback. The visible rack and the sounding instrument are two
views of the same patch. Patching an output back into something that already
feeds it is a technique, not a mistake: a loop closes on the previous block, the
way a real-time graph has always closed one.

**The interface should feel like an instrument.** Modules stay where the hand
puts them, while an explicit **Tidy** command can read the patch and arrange its
signal flow. The rack moves beneath a pinned mixing console, live jacks and
cables glow with their signals, and dense technical detail can collapse away.
The aim is legibility and touch, not an engineering debugger.

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

Noodler opens to a quiet rack with the **console** along the bottom: eight
channel strips and a master, pinned inside the rack so the camera never carries
them away. Each strip has its jack at the top — drag a module's audio output
onto it and that is the slot it plays through — its number with M and S on
the title row, a level dial with its meter drawn as a ring around it, and pan
and two sends beneath, labelled L/R, FXA and FXB. The strip takes the
name of whatever is patched into it. Press **▶ PLAY** in the menu bar — or tap
space, or ⌘↩ — to open the audio device and start the clock; audio never starts
on its own. Patch a send into a reverb and the reverb goes fully wet by itself,
since the dry sound is already on the channel.
Every output jack and cable glows with the signal on it — and cables hang,
sagging with their length like patch cords do, out of the output to the right
and into the input from the left. Click a cable to pick it, double-click to
unpatch it. A right-click on any module offers its local actions: collapse,
duplicate, reset, unplug, group, or remove.

Each strip has **M** and **S**. To the right of the channels sit two **effect
strips**, FX A and FX B, each with its send jack out and its return L and R in
standing above it; the master's level is a dial in the status bar, beside the
scope: patch FX A's send
into a reverb and the reverb's outputs back into its L and R, and every strip
that turns its A up is in the same room, while the eight channels stay free
for sources. A return is stereo, has a level and a mute of its own, and goes
straight to the bus; the loop it closes through the master runs one block
late, which is what a reverb is. A new rack opens with a delay on A and a hall
on B already patched.

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
  require repeatedly opening a modal browser. The entire pane can be collapsed
  when the rack needs the room.

The freeform rack occupies the rest of the window. Position belongs to the
user: a module remains where it is dragged, and nothing silently snaps it back.
Order belongs to the patch: **Tidy** is the deliberate act that reads the
executable graph and lays its signal flow out from left to right. Panning,
zooming, framing, and revealing new modules treat the console band as reserved
space, so the camera does not hide modules beneath it. A module added from the
library lands in the middle of the view — or, if something is already there,
at the nearest free spot that still fits in view, so a run of additions fans
out around the middle rather than piling up on it.

Modules can be **grouped**: select some and press ⌘G, and from then on
dragging any one of them carries the others — a name over some modules, the
way a board on Muse holds cards, logical only: nothing is boxed in, no signal
changes, positions and cables are untouched. Groups nest — group over a grouped
module and its whole group comes in, a board on a board — and each is drawn as
a soft line round its modules with its name at the top left; drag the name to
move the group whole, Option-drag a member to move it alone, ⌘⇧G to ungroup.
Groups are saved with the document.

Every declared jack is visible by default. Modules can be dragged, removed
from their right-click menu (or the Delete key), or collapsed by double-clicking
the title bar. A collapsed module keeps its title and connected jacks visible while its
open jacks and controls get out of the way. Its DSP and cables continue to run.

The rack also shows what it is doing. Output jacks and cables brighten with
their current signal, gates blink, and each console strip draws its meter around
its level dial. Playback going dark is visible before it needs to be diagnosed.

### Rack controls

| Gesture or key | Action |
| --- | --- |
| Background drag or scroll | Pan the rack |
| Space + drag | Pan even when the gesture begins over a module |
| Space tap or Command-Return | Play / stop audio and the transport |
| Pinch or − / 100% / + | Smooth, pointer-anchored zoom |
| Shift + background drag | Box-select modules |
| Command-G / Command-Shift-G | Group the selection / ungroup it |
| Drag a grouped module | The whole group comes along; Option-drag moves it alone |
| Drag a group's name | Move the group, nested groups and all |
| Module title drag | Move a module along the rack |
| Module title double-click | Collapse or open the module |
| Module right-click | Collapse, duplicate, reset, unplug, group, or remove it |
| Knob drag up/down | Adjust a value; movement accelerates with speed |
| Scroll over a knob | Turn it without moving the rack |
| Shift + knob drag or scroll | Fine adjustment |
| Knob double-click | Restore the parameter default |
| Double-click a cable | Unpatch it |
| Delete / Backspace | Remove selected cables or modules |
| Command-K | Focus the module library |
| Command-Z / Command-Shift-Z | Undo / redo |
| T | Tidy the rack by signal flow |
| L | Collapse or restore the library pane |
| F | Frame the whole rack |
| Escape | Clear the selection |

**File → Export Audio** bounces the patch to a stereo WAV — so many bars at the
document's tempo from bar one, then a tail for the rooms to ring out — on a
thread, with progress in the status bar. The rack outline on the left names
every module as a link: click it and the module glides to the middle of the
view and opens; the arrow at the front of its row opens its parameters, kept
current, and its ports beneath — and the row and the panel are one state:
open the row and the module opens on the canvas, fold the module and its row
folds.

`Unplug All` removes every module cable as one graph edit, so experiments remain
easy to unwind. The master's own bus survives it: that is not a cable anyone
patched, and it is not one anyone can pull out.

Patching, unplugging, adding, duplicating, removing, resetting, and turning a
knob all participate in the same undo history. A knob sweep is one musical
gesture and therefore one undo—not hundreds of tiny values. The window title
shows a dot when the patch differs from its last save; New, Open, and Quit ask
before losing that work, and **File → Open Recent** remembers the last eight
documents.

## Modules

The built-in provider currently contains 35 modules, grouped around the way a
patch is made rather than around implementation details.

| Shelf | Modules |
| --- | --- |
| Compose & Modulate | Key / Scale, Scale Quantizer, Melody Brain, Harmony Brain, Arpeggio Brain, Clock, PyTheory Beats, PyTheory Score, PyTheory Raga, PyTheory Maqam, PyTheory Progression, PyTheory Chord Ear, PyTheory Negative Harmony, Tone Row, Scale Generator, Function Utility, Wogglebug |
| Generate | PyTheory Voice, Instrument Voice, Triangle Core Complex VCO, Classic VCO, FM Voice, Supersaw, Noise Source |
| Shape & Control | State Variable Filter, Ladder Filter, ADSR Envelope, VCA, Low-Pass Gate |
| Mix & Space | Master Mixer, Polarizing Mixer, Echo Delay, Stereo Reverb, PyTheory Reverb, PyTheory FX |

PyTheory brains prepare musical structures on the control path. Oscillators,
filters, dynamics, utilities, and effects implement the block-processing
contract used by the live graph. Pydantic models describe their parameters and
typed ports so the same definitions can support the UI, persistence, provider
interchange, and validation.

## Patch documents

A `.noodler` document stores:

- stable provider, module-type, and instance identifiers;
- validated module parameters;
- directed cables and the master's stereo taps;
- console levels, pan, sends, returns, mute, solo, and master gain;
- tempo and time signature; and
- module positions, collapsed state, and rack viewport.

It intentionally does not serialize audio device handles, sample buffers,
oscillator phase, random-generator progress, delay memory, or a running audio
device. Loading a patch creates fresh DSP state from the saved instrument.

The format is human-readable and friendly to source control. See the
[version-one patch contract](DOCS/PATCH_FORMAT.md) and the
[example patches](examples/) for the complete shape — including a set of
seven tone-system patches (pelog, slendro, Bohlen-Pierce, carnatic, shruti,
19-TET, makam), every one played by PyTheory's own synthesis and tuned by a
single Key. **Highlife Kalimba** and **Keherwa Kalimba** add clocked arrangements:
PyTheory drums, melodic brains, and voices share the sample clock while groove,
sends, and tempo remain part of the document. All examples are available under
**File → Open Example**.

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
- [Interaction model](DOCS/INTERACTION.md)
- [Editing and undo](DOCS/EDITING.md)
- [Patch file format](DOCS/PATCH_FORMAT.md)

Questions remain: how far Python can carry the real-time path, whether the
eventual macOS surface should stay in Dear PyGui, how providers remain
compatible across releases, and how MIDI, MPE, OSC, clock, recording, and
offline rendering should enter the instrument. Those are design pressures,
not reasons to erase the strange and useful center of the idea.

*Not a DAW with cables. Not Eurorack trapped on a screen. A place where sound,
voltage, chance, and musical thought can touch.*
