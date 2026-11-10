# Changelog

## 0.2.0

The first release. Theory is patchable, and a patch is a document you can write.

- PyTheory 0.59. A **Fretboard** module uses `Fretboard.guitar(tuning, capo=)`. A chord name asks `Fretboard.chord(name, multiple=True)` for the ranked grips in that tuning and under that capo. Voicing 0 is the one PyTheory puts first, which is what plays if you never touch the control.
- A **Sequencer** takes a phrase as scale degrees (`0 2 4 3  4 . 0 .`). A **Chord** holds a name and hands four voices to the arpeggiator. **MIDI Out** turns a pitch and a gate into a `.mid` file.
- `Patch` is the short way to say it: a module, a cable, `hear`, `save`, `render`.
- `.noodler` stays JSON. `.toml` is the same document. The rack opens either.
- `noodler check`, `noodler render -o file.wav`, `noodler midi -o file.mid`, and `noodler modules`. `noodler` still opens the rack. Audio is Core Audio, and a WAV when you render. MIDI is a file.
- Two patches to start from: DADGAD Chapel, and Open G with a capo on 2.
