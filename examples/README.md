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

`hijaz-machine` is the earlier generative showcase (arabic hijaz, oscillator
voices), and `somesound` is a two-module starter.

## Rebuilding them

The set is generated, so it can be regenerated after a change to the modules:

```console
uv run python examples/build_tone_systems.py
uv run python examples/build_pelog_bell_garden.py
```

Both scripts write over the documents here.
