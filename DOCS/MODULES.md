# Module interoperability

**Status:** Initial contract, accepted 2026-08-17

Noodler modules may come from the application itself or from separately
distributed provider packages. Providers describe their catalogs with frozen
Pydantic models exported by `noodler.module_providers`.

Pydantic is the boundary for discovery and persistence because it gives us
runtime validation, generated JSON Schema, and deterministic JSON round trips.
It does not imply that Pydantic models will be passed through the real-time
audio callback.

## Provider contract

A provider exposes a `ProviderManifest`. The manifest has a schema version,
provider identity and version, and a catalog of `ModuleManifest` objects. Each
module manifest contains stable metadata and typed input and output ports.

The provider-neutral `ModuleProvider` protocol still exposes only this
manifest. Noodler's built-in provider now also implements
`create(module_id, parameters=None)`, backed by a registry whose keys are the
same stable IDs published in its manifest. The in-app module browser uses that
factory today, and the patch loader can share the same construction path later
without prematurely requiring external providers to adopt an untested factory
protocol.

## Module library

The default workspace keeps a live tree of the current rack on the left and
the freeform patch rack on the right. Its `Signal Flow` branch follows cables
backward from System Output through every upstream module. Modules that have
not reached an output appear separately under `Unpatched`, divided into
control/modulation and audio-path lanes. This tree is rebuilt from the real
`PatchGraph` after every add, remove, patch, unpatch, or unplug-all operation.
Each module entry includes a small removal button backed by the same graph-safe
operation as the close target on the module's rack title. System Output is the
one permanent entry and cannot be removed.

The searchable module catalog sits beneath that rack outline. It is derived
directly from the provider manifest, so the visible catalog cannot silently
drift from the constructible module registry. Its high-level shelves follow
musical intent: `Compose & Modulate`, `Generate`, `Shape & Control`, and `Mix &
Space`. Provider categories remain nested beneath those shelves, and search
opens only the relevant branches.

Selecting an entry adds it directly to the rack without dismissing the tree.
It creates a unique instance such as `state_variable_filter` or
`state_variable_filter_2`, places it on the control or audio rail, and exposes
its declared ports through the same compact patch bay used elsewhere. Entries
also retain their manifest descriptions and patch-point counts as tooltips.

For modules without a bespoke panel, Noodler generates controls from the
module's Pydantic parameter model. Nested models, validated numeric ranges,
enums, booleans, strings, and numeric tuples all remain attached to the real
module state. Consecutive numeric controls are packed three across and the
manifest description moves into the category tooltip, keeping generated
modules closer to Eurorack proportions than to vertical settings inspectors.
Bespoke musical panels can progressively replace these generated views without
changing the module or preset contracts.

## Signal compatibility

Ports declare a semantic signal type:

- audio;
- CV;
- gate;
- trigger; or
- musical.

Audio and CV are deliberately interoperable. Both ultimately carry changing
numeric values, and useful modular patches often blur the distinction: an
oscillator can modulate a parameter, and a sufficiently fast control signal
can become audible.

An audio/CV crossing therefore has three policies at each endpoint:

- `allow` — the module explicitly expects the crossing;
- `warn` — allow it but show an advisory; this is the default; or
- `reject` — the crossing is inappropriate for this endpoint.

If either endpoint rejects the crossing, no cable is created. If either
endpoint retains the default warning policy, the connection is accepted with
an advisory about range, rate, and DC behavior. If both endpoints opt in, the
connection is accepted without that advisory.

The warning is meaningful rather than ceremonial. Audio is commonly bipolar,
while module control ranges may be unipolar, normalized, stepped, or expressed
in domain-specific units. Later manifest versions may add explicit range and
unit metadata. Noodler should not silently clamp or rescale a cross-link unless
a module or adapter explicitly declares that behavior.

Other mismatched signal types remain incompatible for now. We can add explicit
adapters or additional compatibility rules when a real module requires them.

## Built-in catalog

The built-in provider currently publishes 19 modules. Twelve are part of the
first library expansion:

| Category | Module ID | Musical or DSP role |
| --- | --- | --- |
| Musical Brains | `melody_brain` | Seeded PyTheory phrases with rests, accents, mutation, and several contour grammars |
| Musical Brains | `harmony_brain` | Key-aware progressions, functional next-chord choices, and four cached voice-led pitches |
| Musical Brains | `arpeggio_brain` | Four-voice CV sampling with up, down, up/down, patched-order, and random traversal |
| Oscillators | `classic_vco` | Sine, triangle, saw, pulse, sub, PWM, FM, and hard sync |
| Oscillators | `fm_voice` | Two-operator ratio/index FM with feedback and external modulation |
| Oscillators | `supersaw` | Three to eleven curved-detune saw voices, center voice, and sub output |
| Noise & Random | `noise_source` | Seeded white, pink, brown, crackle, and clocked sample-and-hold outputs |
| Filters | `state_variable_filter` | Simultaneous two-pole low, band, high, and notch outputs |
| Filters | `ladder_filter` | Driven resonant 6, 12, 18, and 24 dB ladder taps plus band and high outputs |
| Envelopes & Dynamics | `adsr_envelope` | Retriggerable ADSR, inverse contour, global time CV, and end pulse |
| Envelopes & Dynamics | `vca` | DC-coupled linear/exponential VCA with bias and soft drive |
| Effects | `echo_delay` | Fractional four-second echo with bipolar feedback, damping, drive, CV, and freeze |

The provider factory and patch graph can instantiate and connect every catalog
entry. The persistent library exposes that same catalog while the default rack
starts with no DSP modules at all, avoiding both a hard-coded showroom and a
cosmetic picker disconnected from the executable graph.

## PyTheory musical brains

`Melody Brain` prepares its tone range and complete phrase when configured.
Weighted wander, rising arch, motif/answer, and free-random styles all remain
inside the selected PyTheory scale. Its phrase memory includes composed rests
and accents; `Mutate` changes one interior tone while the audio callback keeps
running. The outputs preserve separate musical note, 1 V/oct, raw frequency,
degree, accent, gate, trigger, and phrase-boundary signals.

`Harmony Brain` asks PyTheory for a selected key's chords and functional
successors on the control path. Tonic journey, circle motion, dream changes,
and seeded functional-choice styles are cached as a progression. A small
voice-leading search chooses four ascending pitches with minimum movement from
the prior chord. Bass, individual voices, progression position, harmonic
function, change, and cadence are all separately patchable.

`Arpeggio Brain` is the bridge from polyphonic harmonic intent back to an
ordinary monophonic Eurorack voice. It samples four pitch CV inputs, traverses
them across one to four octaves, and emits musical note, pitch, position, gate,
and trigger. Harmony Brain can therefore drive four oscillators directly or
feed one Arpeggio Brain and a single oscillator.

All PyTheory scale, chord, progression, and voicing preparation happens outside
the real-time callback. Live blocks contain only numeric arrays; no `Chord`,
`Tone`, or Pydantic object is constructed or passed while rendering audio.

## Built-in triangle-core complex VCO

The first built-in module takes its signal architecture from the Plan B and
Subconscious Communications Model 15 Complex VCO. It is a single,
phase-continuous triangle core rather than the dual-oscillator architecture
common in newer complex oscillators. Noodler is inspired by the Model 15's
behavior and panel, but does not claim circuit-level emulation.

The control paths are:

- coarse frequency and fine tuning;
- a calibrated one-volt-per-octave input;
- two exponential frequency CV inputs with independent bipolar attenuverters;
- a dedicated linear FM input and amount;
- hard sync on a rising trigger edge;
- pulse-width offset and PWM input; and
- voltage-controlled morphing from sine toward selectable ramp or pulse.

The shared core produces independent sine, triangle, rising ramp, pulse, and
morph outputs. All audio and CV ports explicitly allow cross-linking, making
audio-rate modulation and use as a low-frequency control source first-class
patches.

The initial implementation produces mono NumPy blocks and preserves core and
sync state between calls. It is not yet band-limited, so ramp and pulse outputs
will alias at higher frequencies. It also allocates while processing. These
are known prototype constraints to address when the audio engine establishes
its real-time buffer lifecycle.

References used to establish the initial behavior:

- [Big City Music product panel](https://www.bigcitymusic.com/products/model-15-complex-vco)
- [Subconscious Communications Model 15 listing](https://modulargrid.net/e/subconscious-communications-model-15-complex-vco)
- [Plan B Model 15 calibration procedure](https://www.timstinchcombe.co.uk/synth/m15_mod/planb_m15_cal_procedure.pdf)

## N-channel polarizing mixer

The polarizing mixer is created with a channel count `n`, currently validated
from 1 through 64. Its instance manifest contains exactly `n` audio/CV inputs,
one unclipped sum output, and one bipolar gain from -1 to +1 per input. A gain
of zero silences a channel, positive values attenuate it, and negative values
attenuate and invert it.

The channel count is a creation parameter because it changes the module's port
shape. It is not a live panel control. The initial rack creates a four-channel
instance, while providers and saved patches may request any supported count.
Parameters are immutable Pydantic snapshots so a gain edit replaces the state
atomically rather than partially mutating it during block processing.

The sum is deliberately not clipped or normalized. Audio and CV may exceed the
nominal unit range when combined; a downstream limiter, scaler, or waveshaper
must make any desired range policy explicit.

## Function and logic utility

The four-channel function utility borrows the functional grammar of Make
Noise MATHS without claiming a circuit emulation or copying its identity.
Channels 1 and 4 are rise/fall function generators that can produce triggered
transients, cycle continuously, or slew a direct-coupled signal. Each has:

- separate rise and fall times;
- a continuously variable logarithmic-to-exponential response control;
- rise, fall, and exponential both-time CV inputs;
- trigger and cycle inputs;
- unity and attenuverted outputs; and
- an endpoint gate: EOR for Channel 1 and EOC for Channel 4.

Rise and fall each span 0.5 milliseconds through 750 seconds. With equal
settings, cycle mode therefore ranges from a 1 kHz audio-rate oscillator down
to one 25-minute cycle. The panel maps this unusually broad timing range
logarithmically so audio-rate, ordinary envelope, and multi-minute settings
remain reachable from the same controls. This follows Make Noise's published
range; CV modulation is clamped to the same digital limits.

Channels 2 and 3 are polarizing channels. When unpatched they generate
normalized DC offsets of +1.0 and +0.5, corresponding conceptually to the
hardware's +10 V and +5 V references. All four attenuverted channels feed:

- `SUM`, an unclipped arithmetic sum;
- `INV`, the exact inverse of `SUM`; and
- `OR`, the greatest non-negative channel value at each sample.

The hardware removes a variable channel from its SUM/OR buses when a cable is
inserted into that channel's output. Noodler does not yet reproduce that
normalization: individual outputs and the combined buses are simultaneously
available. Supporting jack-normal behavior belongs in the future patch-graph
connection model rather than hidden inside the DSP module.

The initial timing and response curves are useful digital interpretations, not
component-level models. Output levels are normalized rather than expressed as
physical Eurorack voltages.

Reference:

- [Make Noise MATHS manual](https://www.makenoisemusic.com/wp-content/uploads/2024/03/MATHSmanual2013.pdf)

## Complex random voltage source

The Wogglebug-inspired random source is a family of correlated signals rather
than a white-noise module. Its internal or external clock creates a held
`Stepped` value. `Smooth` glides toward those values, while `Woggle` chases the
smooth path with decaying, irregular movement. `Ego / Id` controls the spread
of the internal source or blends an external audio/CV source into the sample
path. `Chaos` controls irregularity and burst probability, and `Woggle`
controls how quickly the chasing voltage catches up. `Disturb` schedules an
immediate uncertainty event at the next safe audio block.

The module exposes all related signals simultaneously:

- `Stepped`, `Smooth`, and `Woggle` bipolar CV;
- the master `Clock` and probabilistic `Burst` gates; and
- `Smooth VCO`, `Woggle VCO`, and `Ring Mod` audio.

An external clock replaces internal clock edges while connected. `Clock CV`
changes the internal rate exponentially. `Influence` shifts Woggle CV, bends
both audio oscillators, and replaces the Smooth VCO as the Ring Mod source,
so it intentionally accepts both slow control and audio-rate signals.

This is a deterministic digital interpretation of the instrument's musical
relationships, not a model of its VCO, PLL, vactrol, or sample-and-hold
circuitry. The random stream has a serializable seed, block boundaries do not
change its results, and nominal 0–10 V hardware signals are represented in
Noodler's normalized range. Square oscillators are not yet band-limited.

References:

- [Make Noise Wogglebug](https://www.makenoisemusic.com/modules/wogglebug/)
- [Make Noise Wogglebug manual](https://www.makenoisemusic.com/wp-content/uploads/2024/03/wogglebugmanual.pdf)

## PyTheory scale generator

The scale generator turns a selected PyTheory scale into clocked musical and
control signals. System, tonic, octave, named scale, and traversal pattern are
creation or panel parameters. Scale tones, spellings, frequencies, and MIDI
note numbers come from `pytheory.TonedScale`; they are prepared when the
selection changes, not constructed in the real-time callback.

The panel currently offers the PyTheory systems that accept Western note-name
tonics in the installed API: Western, blues, Japanese, 19-TET, 31-TET, and
Bohlen–Pierce. Available scale names update when the system changes. Traversal
may move up, down, bounce up/down, choose deterministic seeded random degrees,
or use `Melodic Wander`. Wander is a phrase-aware random walk: adjacent tones
are favored over leaps, mid-phrase events visit characteristic inner scale
tones, and alternating eight-event phrases cadence on the upper and lower
tonics. It remains deterministic across audio block boundaries.

The module has its own clock, but a patched clock gate takes over. Reset returns
to the tonic and transpose applies a continuous octave offset. Outputs are:

- `Note`, a provisional block of MIDI-compatible PyTheory note numbers marked
  as a musical signal;
- `1 V/oct`, relative to a configurable frequency reference;
- raw PyTheory `Frequency` in hertz and normalized `Degree` CV; and
- a held `Gate` plus one-sample change `Trigger`.

The Hirajoshi Garden reference patch uses a 220 Hz voltage reference matching
the VCO's base frequency. Wogglebug Clock advances a seeded A3 Hirajoshi
melodic wander and the generator's pitch output drives the VCO, while Woggle
CV adds a much smaller layer of pitch movement. Rich object-valued musical
blocks remain a future protocol change; the initial numeric Note output makes
the semantic cable type testable without placing Python objects in the
callback.

Reference: [PyTheory](https://pytheory.org)

## Organic low-pass gate

Bloom is a struck dynamics module influenced by the coupled amplitude and
spectral decay of optical low-pass gates. A rising `Strike` opens immediately,
then a two-part exponential response closes both level and filter cutoff.
`Light` controls the open cutoff, `Wood` lengthens and saturates the quiet tail,
and `Decay` spans short percussive ticks through long resonances. `Level CV` and
exponential `Decay CV` keep both dimensions patchable.

The module exposes its response as an `Envelope` CV as well as its shaped audio
output. It is an intentionally playable digital interpretation, not a vactrol
or circuit model. In the Hirajoshi Garden reference patch, each scale-generator
trigger strikes the mixed voice before it enters the reverb, giving the phrase
acoustic breath instead of a permanently open oscillator.

## Stereo space reverb

The reverb deliberately has one `Audio In`: it accepts a mono voice or mix,
then synthesizes stereo internally rather than requiring a stereo source. Two
banks of six damped feedback combs use slightly different delay lengths, and
three serial all-pass stages on each side diffuse those echoes into
decorrelated left and right late fields.

The panel exposes wet/dry mix, decay time, damping, diffusion, pre-delay, and
freeze. `Mix CV` and `Decay CV` keep the effect playable from the rack, while a
gate can engage freeze. Four outputs make its intent explicit:

- `Wet Left` and `Wet Right` carry only the stereo late field;
- `Left` and `Right` use equal-power wet/dry blending and feed the corresponding
  system output channels in the Hirajoshi Garden reference patch.

Delay storage is prepared at the audio device's actual sample rate before the
stream starts. The design is a compact digital Schroeder/Freeverb-family
instrument, not an emulation of a particular hardware reverb or physical room.
