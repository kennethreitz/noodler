# Noodler documentation

Noodler is a macOS modular music environment built in Python. Its initial
direction is a GPU-rendered rack interface backed by PyTheory's music-theory,
sequencing, MIDI, and synthesis capabilities.

The project has reached its first audible prototype and a 19-module built-in
catalog. Decisions in these documents describe the intended first version and
should be revisited when measurements or hands-on prototypes give us better
evidence.

Noodler opens to a quiet, mostly empty rack: System Output is present, while
the executable graph contains no DSP modules or cables. A live tree of the
current rack stays on the left, with the searchable module catalog beneath it,
while the freeform patch rack occupies the right. A new instrument can be
assembled without repeatedly opening and closing a catalog.

## Documents

- [Architecture](ARCHITECTURE.md) — application structure, runtime boundaries,
  signal types, dependency management, and vertical-slice follow-ups.
- [Technology decisions](TECHNOLOGY.md) — accepted choices, alternatives, and
  the reasons behind them.
- [Module interoperability](MODULES.md) — provider manifests, typed ports, and
  audio/CV cross-linking rules.
- [Patch graph and system audio](AUDIO.md) — empty-rack startup, the composed
  reference patch, Core Audio output, and current real-time limitations.
- [Motion](MOTION.md) — why the rack settles in continuous time, and the
  spring model the rails, camera, knobs, and meter share.
- [Editing the rack](EDITING.md) — the editing keys, and the undo history
  that makes patching safe to explore.
