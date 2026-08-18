# Noodler example patches

Open an example directly from the repository root:

```console
uv run noodler ./examples/pelog-bell-garden.noodler
```

The examples are ordinary, human-readable `.noodler` documents. They can be
copied, edited, versioned, and opened with the installed `noodler` command.

## The tone-system set

Seven patches, each built the same way — one **Key** decides the tuning, the
brains think in shapes, quantizers turn those shapes into that tuning, and
**PyTheory Voices** render every note with the library's own synthesis — so
what changes between them is the music, not the wiring. Change the Key and the
whole patch retunes.

| Patch | System | What it shows |
| --- | --- | --- |
| `pelog-bell-garden` | pelog | Seven Javanese tones whose steps are nothing like semitones; tubular bells, kalimba and a singing bowl. |
| `slendro-rain` | slendro | Five tones to the octave and none of them where a piano has one; music box, kalimba, marimba. |
| `bohlen-pierce-chapel` | bohlen-pierce | A scale that repeats at a twelfth rather than an octave. Singing bowls, crotales, a theremin drone. |
| `carnatic-loom` | carnatic | Kalyani, one of the seventy-two melakarta ragas. Sitar through echo, harp, harmonium. |
| `shruti-drone` | shruti | Bhairavi on the twenty-two-shruti grid Indian music is actually tuned to. Koto over a harmonium drone. |
| `nineteen` | 19-tet | Ordinary chord shapes in nineteen equal steps: sweeter thirds, and sharps and flats stop being the same note. Rhodes, strings, upright bass. |
| `makam-divan` | makam | Hicaz on the fifty-three-comma octave. Oud, ney, contrabass. |

## Keeping time

`mirror-canon` is Pachelbel's changes, their negative, and an oud over the top.
PyTheory Progression plays the canon's eight chords in D, a chord a bar on the
clock, voiced open on an electric piano; the same four voices go through
PyTheory Negative Harmony — mirrored about D major's axis, so major turns minor
and rising lines fall — into a softer piano an octave down, so the progression
and its negative sound at once, and the Chord Ear names what they make together
in its label. Over that PyTheory Maqam walks Hijaz on D, justly tuned, on an
oud, in eighths; the bass plays each chord's root on every beat. Saved at 72 BPM.

`highlife-kalimba` is a groove that follows the clock in the menu bar. PyTheory
Beats plays the library's highlife pattern through its own drum synthesis; a
Clock module turns the same transport into triggers, and every brain is
clocked from it — chords change on the bar, the arpeggio runs in eighths, the
melody in sixteenths, the bass on every beat — so changing the tempo changes
everything at once. Kalimba, marimba and upright bass are PyTheory voices in
yo, and the room and the echo hang off the master's sends. It is saved at 108
BPM, and the tempo travels with the document.

`keherwa-kalimba` puts the tabla in front: PyTheory's keherwa (the eight-beat
tabla cycle) carries the groove and the highlife kit lilts under it — six beats
against eight, so they come round together only every six bars. Kalimba, sitar,
a harmonium pumping on the beat and an upright bass, all in raga khamaj on the
shruti grid, at 100 BPM.

## The big one

`night-market` is the biggest patch in the box: teental tabla in front and an
afrobeat kit under it, a Clock driving four brains — chords on the bar, a
random arpeggio on a celesta in sixteenths, an electric-piano stab on every
beat, a sitar melody plucked through a low-pass gate and a flute answering it a
register up — a bass on the beat, and a pad filtered by a slow sweep and a
Wogglebug, all in makam nihavend. Twenty-seven modules, fifty-one cables, all
eight channels, delay on A and a cathedral on B, at 96 BPM.

`hijaz-machine` is the earlier generative showcase (arabic hijaz, oscillator
voices), and `somesound` is a two-module starter.

## Rebuilding them

The set is generated, so it can be regenerated after a change to the modules:

```console
uv run python examples/build_tone_systems.py
uv run python examples/build_pelog_bell_garden.py
uv run python examples/build_highlife_kalimba.py
uv run python examples/build_keherwa_kalimba.py
uv run python examples/build_night_market.py
```

Both scripts write over the documents here.
