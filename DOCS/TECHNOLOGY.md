# Technology decisions

**Status:** Initial direction, accepted 2026-08-17

## Python and `uv`

Noodler will be implemented in Python and managed by `uv` from the repository
root. Application code, the UI, the engine, and tests share one environment
and lockfile.

Initial direct dependencies:

```toml
dependencies = [
    "dearpygui",
    "pydantic",
    "pytheory",
    "sounddevice",
]
```

Additional packages should only become direct dependencies when Noodler imports
or configures them itself; dependencies used solely inside PyTheory should
remain PyTheory's responsibility.

## Dear PyGui

[Dear PyGui](https://github.com/hoffstadt/dearpygui) is the selected UI
framework. It is a compiled C/C++ immediate-mode interface rendered with Metal
on macOS. It currently supports Python 3.14 and supplies several primitives
that closely match Noodler's needs:

- a [node editor](https://dearpygui.readthedocs.io/en/latest/documentation/node-editor.html)
  for the rack and patch cables;
- fast plotting for scopes and meters;
- custom drawing, themes, controls, and drag interactions; and
- a Python-facing API without a separate JavaScript or Swift frontend.

The implementation language of the renderer is less important than its fit:
we want a responsive, compiled, GPU-backed interface that leaves the product
logic in Python.

## PyTheory

[PyTheory](https://pytheory.org) is a first-class dependency rather than an
optional bridge. Noodler should build on its theory types, score and rhythm
model, synthesis, effects, live MIDI engine, CC mapping, recording, and
Ableton Link support where appropriate.

PyTheory-aware modules are expected to be a differentiator, especially when
they operate on semantic musical signals rather than raw MIDI alone.

## Sounddevice and Core Audio

[`sounddevice`](https://python-sounddevice.readthedocs.io/) is the initial
audio-device boundary. It provides NumPy-aware PortAudio callbacks, supports
macOS through Core Audio, and ships as a universal2 wheel. Noodler opens the
system's default output at its default sample rate rather than imposing a rate
that might require conversion.

Only the device adapter depends on sounddevice. Patch graphs and modules render
ordinary float32 NumPy blocks, so a future native engine or plugin host can
replace the adapter without changing their public signal model.

## Alternatives considered

### Pygame

Pygame would provide a drawing surface and input loop, but Noodler would need to
implement its own node editor, controls, layout, text behavior, plots, docking,
and much of its interaction model. It remains useful for games and completely
custom canvases, but it does not reduce the hard UI work in this application.

### SwiftUI and a Python helper

A Swift frontend could provide deeper native macOS integration, while a
Python helper preserved PyTheory access. It also introduces two languages, an
interprocess protocol, interpreter bundling, and duplicated state ownership.
That trade may become worthwhile later, but it is unnecessary for proving the
instrument.

### PyTauri

[PyTauri](https://pytauri.github.io/pytauri/latest/) combines Python with a
Tauri/Rust shell and a web frontend. It is genuinely Rust-backed, but its
current documentation classifies macOS as a lower support tier, and it would
also add frontend web technology. It is not the right foundation for a
Mac-first audio application today.

### Dear ImGui Bundle

[Dear ImGui Bundle](https://github.com/pthom/imgui_bundle) is a strong runner-up
with node editing, knobs, plots, docking, and Python bindings. Dear PyGui has a
smaller conceptual surface for the initial application and a direct Metal
backend on macOS. We can revisit the bundle if Dear PyGui's widgets or node
editor prove too restrictive in the vertical slice.

### Emerging Rust-backed Python interfaces

Bindings around egui and Azul are promising, but their Python ecosystems and
macOS packaging are younger than the immediate-mode C++ options. Noodler should
not select a renderer solely because it is implemented in Rust.

## Decision review triggers

Revisit these choices if testing shows any of the following:

- Dear PyGui cannot deliver the required rack interactions or visual quality;
- UI activity causes measurable audio instability despite a correct runtime
  boundary;
- Python block processing cannot meet the target buffer size;
- native menus, accessibility, document behavior, or plugin hosting become
  primary product requirements; or
- shipping a signed and notarized Python application proves impractical.
