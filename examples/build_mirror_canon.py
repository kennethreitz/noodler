"""Build Mirror Canon: Pachelbel's changes, their negative, an oud over the top.

Run from the repository root:  uv run python examples/build_mirror_canon.py

PyTheory Progression plays Pachelbel's eight chords in D, a chord a bar on the
clock in the menu bar, voiced open on an electric piano. The same four voices
go through PyTheory Negative Harmony -- mirrored about D major's axis, so the
canon's major turns minor and its rising lines fall -- and into a second,
softer piano an octave down, so the progression and its negative sound at
once, and the Chord Ear names what the two make together in its label. Over
that, PyTheory Maqam walks Hijaz on D -- the maqam whose augmented second sits
against Pachelbel's diatonic bass most strangely -- justly tuned, on an oud,
stepping in eighths. The bass plays the progression's root on every beat.
"""

from pathlib import Path

from noodler.app import MASTER_ID, ensure_master
from noodler.module_providers.builtin import BuiltinProvider
from noodler.patch import PatchGraph
from noodler.preset import (
    Point,
    RackNodePreset,
    RackViewPreset,
    TransportPreset,
    capture_patch_preset,
    write_patch_preset,
)

provider = BuiltinProvider()
patch = PatchGraph()
places: dict[str, tuple[int, int]] = {}


def add(instance: str, module_id: str, where: tuple[int, int], **parameters):
    module = provider.create(module_id, parameters)
    patch.add_module(instance, module)
    places[instance] = where
    return module


# ------------------------------------------------------------------ the time
add("clock", "clock", (40, 40), trigger_ms=6.0)

# ---------------------------------------------------------------- the brains
add("changes", "pytheory_progression", (40, 320), progression="Pachelbel", tonic="D",
    mode="major", voicing="open", octave=4, bars_per_chord=1, gate_length=0.95,
    reference_frequency_hz=220.0)
add("mirror_1", "pytheory_negative_harmony", (420, 300), tonic="D", mode="major")
add("mirror_2", "pytheory_negative_harmony", (420, 570), tonic="D", mode="major")
add("mirror_3", "pytheory_negative_harmony", (420, 840), tonic="D", mode="major")
add("mirror_4", "pytheory_negative_harmony", (420, 1110), tonic="D", mode="major")
add("ear", "pytheory_chord_ear", (760, 40), reference_frequency_hz=220.0)
add("hijaz", "pytheory_maqam", (40, 900), maqam="Hijaz", tonic="D3", style="walk",
    rest_chance=0.25, density=0.7, gate_length=0.55, span_octaves=2,
    reference_frequency_hz=220.0, seed=5)

# ---------------------------------------------------------------- the voices
add("piano", "pytheory_voice", (760, 320), instrument="electric_piano", level=0.34,
    release_ms=900.0, reference_frequency_hz=220.0)
add("piano_2", "pytheory_voice", (760, 570), instrument="electric_piano", level=0.28,
    release_ms=900.0, reference_frequency_hz=220.0)
add("piano_3", "pytheory_voice", (760, 840), instrument="electric_piano", level=0.28,
    release_ms=900.0, reference_frequency_hz=220.0)
add("piano_4", "pytheory_voice", (760, 1110), instrument="electric_piano", level=0.28,
    release_ms=900.0, reference_frequency_hz=220.0)
add("shadow_1", "pytheory_voice", (1120, 320), instrument="piano", level=0.2,
    release_ms=1200.0, reference_frequency_hz=440.0)
add("shadow_2", "pytheory_voice", (1120, 570), instrument="piano", level=0.2,
    release_ms=1200.0, reference_frequency_hz=440.0)
add("shadow_3", "pytheory_voice", (1120, 840), instrument="piano", level=0.2,
    release_ms=1200.0, reference_frequency_hz=440.0)
add("shadow_4", "pytheory_voice", (1120, 1110), instrument="piano", level=0.2,
    release_ms=1200.0, reference_frequency_hz=440.0)
add("oud", "pytheory_voice", (40, 1380), instrument="oud", level=0.4,
    release_ms=500.0, reference_frequency_hz=220.0)
add("bass", "pytheory_voice", (1480, 320), instrument="contrabass", level=0.5,
    release_ms=600.0, reference_frequency_hz=220.0)

# Four voices to a chord, one strip to a piano: two little mixers sum them.
add("piano_sum", "polarizing_mixer", (1120, 40), channels=4, gains=(0.5, 0.5, 0.5, 0.5))
add("shadow_sum", "polarizing_mixer", (1480, 40), channels=4, gains=(0.5, 0.5, 0.5, 0.5))

add("room", "pytheory_reverb", (1480, 620), space="hall", mix=1.0, decay_seconds=3.5, width=0.9)
add("echo", "echo_delay", (1480, 900), time_seconds=0.375, feedback=0.3, mix=1.0, damping=0.55)

master = ensure_master(patch)

routes = [
    # The maqam steps in eighths, from the clock; the changes follow the bars themselves.
    ("clock", "eighth", "hijaz", "clock"),
    ("clock", "bar", "hijaz", "reset"),

    # The progression, voice by voice, on the electric piano...
    ("changes", "voice_1", "piano", "pitch"),
    ("changes", "voice_2", "piano_2", "pitch"),
    ("changes", "voice_3", "piano_3", "pitch"),
    ("changes", "voice_4", "piano_4", "pitch"),
    ("changes", "change", "piano", "gate"),
    ("changes", "change", "piano_2", "gate"),
    ("changes", "change", "piano_3", "gate"),
    ("changes", "change", "piano_4", "gate"),

    # ...and mirrored, on the shadow piano an octave down (its reference is 440).
    ("changes", "voice_1", "mirror_1", "pitch"),
    ("changes", "voice_2", "mirror_2", "pitch"),
    ("changes", "voice_3", "mirror_3", "pitch"),
    ("changes", "voice_4", "mirror_4", "pitch"),
    ("mirror_1", "out", "shadow_1", "pitch"),
    ("mirror_2", "out", "shadow_2", "pitch"),
    ("mirror_3", "out", "shadow_3", "pitch"),
    ("mirror_4", "out", "shadow_4", "pitch"),
    ("changes", "change", "shadow_1", "gate"),
    ("changes", "change", "shadow_2", "gate"),
    ("changes", "change", "shadow_3", "gate"),
    ("changes", "change", "shadow_4", "gate"),

    # The ear listens to the progression and its lowest mirrored voice together.
    ("changes", "voice_1", "ear", "pitch_1"),
    ("changes", "voice_2", "ear", "pitch_2"),
    ("changes", "voice_3", "ear", "pitch_3"),
    ("mirror_1", "out", "ear", "pitch_4"),
    ("changes", "change", "ear", "listen"),

    # The maqam on the oud; the root on the bass, every beat.
    ("hijaz", "pitch", "oud", "pitch"),
    ("hijaz", "gate", "oud", "gate"),
    ("changes", "root", "bass", "pitch"),
    ("clock", "beat", "bass", "gate"),

    # The pianos summed, then into the console.
    ("piano", "audio", "piano_sum", "input_1"),
    ("piano_2", "audio", "piano_sum", "input_2"),
    ("piano_3", "audio", "piano_sum", "input_3"),
    ("piano_4", "audio", "piano_sum", "input_4"),
    ("shadow_1", "audio", "shadow_sum", "input_1"),
    ("shadow_2", "audio", "shadow_sum", "input_2"),
    ("shadow_3", "audio", "shadow_sum", "input_3"),
    ("shadow_4", "audio", "shadow_sum", "input_4"),
    ("piano_sum", "output", MASTER_ID, "channel_1"),
    ("shadow_sum", "output", MASTER_ID, "channel_2"),
    ("oud", "audio", MASTER_ID, "channel_3"),
    ("bass", "audio", MASTER_ID, "channel_4"),
    (MASTER_ID, "send_a", "echo", "audio"),
    (MASTER_ID, "send_b", "room", "audio"),
    ("echo", "output", MASTER_ID, "return_a_left"),
    ("room", "wet_left", MASTER_ID, "return_b_left"),
    ("room", "wet_right", MASTER_ID, "return_b_right"),
]
for source, source_port, target, target_port in routes:
    patch.connect(source, source_port, target, target_port)

master.set_level(1, 0.65); master.set_pan(1, -0.35); master.set_send("b", 1, 0.5)
master.set_level(2, 0.55); master.set_pan(2, 0.4);   master.set_send("b", 2, 0.7)
master.set_level(3, 0.65); master.set_pan(3, 0.1);   master.set_send("a", 3, 0.45); master.set_send("b", 3, 0.35)
master.set_level(4, 0.7);  master.set_pan(4, 0.0)
master.set_return_level("a", 0.4)
master.set_return_level("b", 0.55)
master.parameters.master = 0.5

view = RackViewPreset(
    zoom=0.66,
    rails={},
    nodes=tuple(
        RackNodePreset(node_id=name, position=Point(x=float(x), y=float(y)))
        for name, (x, y) in places.items()
    ),
)
preset = capture_patch_preset(
    name="Mirror Canon",
    patch=patch,
    master_gain=0.7,
    view=view,
    transport=TransportPreset(bpm=72.0, beats_per_bar=4, beat_unit=4),
)
destination = write_patch_preset(preset, Path("examples/mirror-canon.noodler"))
print("wrote", destination, "|", len(preset.modules), "modules,", len(preset.cables), "cables, at", preset.transport.bpm, "BPM")
