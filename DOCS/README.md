# Noodler documentation

Noodler is a macOS modular music environment built in Python. Its initial
direction is a GPU-rendered rack interface backed by PyTheory's music-theory,
sequencing, MIDI, and synthesis capabilities.

The project has reached its first audible prototype and a 19-module built-in
catalog. Decisions in these documents describe the intended first version and
should be revisited when measurements or hands-on prototypes give us better
evidence.

## Documents

- [Architecture](ARCHITECTURE.md) — application structure, runtime boundaries,
  signal types, dependency management, and vertical-slice follow-ups.
- [Technology decisions](TECHNOLOGY.md) — accepted choices, alternatives, and
  the reasons behind them.
- [Module interoperability](MODULES.md) — provider manifests, typed ports, and
  audio/CV cross-linking rules.
- [Patch graph and system audio](AUDIO.md) — runtime module contract, default
  audible patch, Core Audio output, and current real-time limitations.
