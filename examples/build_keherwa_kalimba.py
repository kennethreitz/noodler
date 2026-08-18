"""Build Keherwa Kalimba: highlife lilt, tabla in front, kalimba and sitar in khamaj.

Run from the repository root:  uv run python examples/build_keherwa_kalimba.py

Two of PyTheory's rhythm presets play at once, both locked to the transport:
keherwa -- the eight-beat tabla cycle, dha ge na tin -- carries the groove,
and the highlife kit lilts underneath it. Highlife is a six-beat pattern in
12/8, keherwa is eight in 4/4, so the two come round together only every six
bars: the lilt never quite repeats. A Clock module drives every brain --
chords on the bar, the kalimba arpeggio in eighths, the sitar melody in
sixteenths, the bass and a pumping harmonium on every beat -- and one Key in
raga khamaj on the twenty-two-shruti grid tunes all four voices, which are
PyTheory's own kalimba, sitar, harmonium and upright bass. The room and the
echo hang off the master's sends and come back on the returns.
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
add("tabla", "pytheory_beats", (40, 300), pattern="keherwa", level=0.7, swing=0.0)
add("kit", "pytheory_beats", (40, 560), pattern="highlife", level=0.34, swing=0.1)

# ------------------------------------------------------------------- the key
add("key", "key", (40, 860), system="shruti", tonic="Sa", scale_name="khamaj",
    octave=3, reference_frequency_hz=220.0)

# ---------------------------------------------------------------- the brains
add("harmony", "harmony_brain", (400, 860), style="dream changes", mode="major",
    length=4, register_octave=3, gate_length=0.9, seed=1947)
add("arp", "arpeggio_brain", (760, 860), pattern="up", octave_range=2,
    gate_length=0.45, seed=22)
add("melody", "melody_brain", (400, 300), system="japanese", tonic="A",
    scale_name="yo", style="motif and answer", phrase_length=16,
    octave_range=2, density=0.42, gate_length=0.35, seed=1971)

add("kalimba_pitch", "quantizer", (1120, 860), reference_frequency_hz=220.0,
    transpose_octaves=1.0)
add("sitar_pitch", "quantizer", (760, 300), reference_frequency_hz=220.0)
add("harmonium_pitch", "quantizer", (1120, 560), reference_frequency_hz=220.0)
add("bass_pitch", "quantizer", (1120, 1160), reference_frequency_hz=220.0,
    transpose_octaves=-1.0)

# ---------------------------------------------------------------- the voices
add("kalimba", "pytheory_voice", (1480, 860), instrument="kalimba", level=0.42,
    release_ms=420.0, reference_frequency_hz=220.0)
add("sitar", "pytheory_voice", (1120, 300), instrument="sitar", level=0.38,
    release_ms=700.0, reference_frequency_hz=220.0)
add("harmonium", "pytheory_voice", (1480, 560), instrument="harmonium", level=0.26,
    release_ms=900.0, reference_frequency_hz=220.0)
add("bass", "pytheory_voice", (1480, 1160), instrument="upright_bass", level=0.5,
    release_ms=520.0, reference_frequency_hz=220.0)

add("space", "reverb", (1840, 300), mix=1.0, decay_seconds=5.0, damping=0.5,
    diffusion=0.86, pre_delay_ms=30.0)
add("echo", "echo_delay", (1840, 620), time_seconds=0.45, feedback=0.4,
    mix=1.0, damping=0.55)

master = ensure_master(patch)

routes = [
    # One clock, three brains.
    ("clock", "bar", "harmony", "clock"),
    ("clock", "eighth", "arp", "clock"),
    ("clock", "sixteenth", "melody", "clock"),
    ("clock", "bar", "melody", "reset"),

    # One key, four quantizers.
    ("key", "scale", "kalimba_pitch", "scale"),
    ("key", "scale", "sitar_pitch", "scale"),
    ("key", "scale", "harmonium_pitch", "scale"),
    ("key", "scale", "bass_pitch", "scale"),

    # Chords -> arpeggio -> kalimba.
    ("harmony", "voice_1", "arp", "voice_1"),
    ("harmony", "voice_2", "arp", "voice_2"),
    ("harmony", "voice_3", "arp", "voice_3"),
    ("harmony", "voice_4", "arp", "voice_4"),
    ("arp", "pitch", "kalimba_pitch", "cv"),
    ("kalimba_pitch", "pitch", "kalimba", "pitch"),
    ("arp", "gate", "kalimba", "gate"),

    # The sitar carries the melody.
    ("melody", "pitch", "sitar_pitch", "cv"),
    ("sitar_pitch", "pitch", "sitar", "pitch"),
    ("melody", "gate", "sitar", "gate"),

    # The harmonium pumps the chord's top voice on every beat.
    ("harmony", "voice_3", "harmonium_pitch", "cv"),
    ("harmonium_pitch", "pitch", "harmonium", "pitch"),
    ("clock", "beat", "harmonium", "gate"),

    # The bass plays the chord root on every beat.
    ("harmony", "bass", "bass_pitch", "cv"),
    ("bass_pitch", "pitch", "bass", "pitch"),
    ("clock", "beat", "bass", "gate"),

    # Into the console.
    ("tabla", "audio", MASTER_ID, "channel_1"),
    ("kit", "audio", MASTER_ID, "channel_2"),
    ("bass", "audio", MASTER_ID, "channel_3"),
    ("kalimba", "audio", MASTER_ID, "channel_4"),
    ("sitar", "audio", MASTER_ID, "channel_5"),
    ("harmonium", "audio", MASTER_ID, "channel_6"),
    (MASTER_ID, "send_a", "space", "audio"),
    (MASTER_ID, "send_b", "echo", "audio"),
    ("space", "left", MASTER_ID, "return_a_left"),
    ("space", "right", MASTER_ID, "return_a_right"),
    ("echo", "output", MASTER_ID, "return_b_left"),
]
for source, source_port, target, target_port in routes:
    patch.connect(source, source_port, target, target_port)

master.set_level(1, 0.85); master.set_pan(1, 0.1);   master.set_send("a", 1, 0.25)
master.set_level(2, 0.6);  master.set_pan(2, -0.15)
master.set_level(3, 0.7);  master.set_pan(3, 0.0)
master.set_level(4, 0.6);  master.set_pan(4, 0.5);   master.set_send("a", 4, 0.5); master.set_send("b", 4, 0.35)
master.set_level(5, 0.62); master.set_pan(5, -0.4);  master.set_send("a", 5, 0.4); master.set_send("b", 5, 0.55)
master.set_level(6, 0.5);  master.set_pan(6, 0.25);  master.set_send("a", 6, 0.6)
master.set_return_level("a", 0.55)
master.set_return_level("b", 0.45)
master.parameters.master = 0.5

view = RackViewPreset(
    zoom=0.7,
    rails={},
    nodes=tuple(
        RackNodePreset(node_id=name, position=Point(x=float(x), y=float(y)))
        for name, (x, y) in places.items()
    ),
)
preset = capture_patch_preset(
    name="Keherwa Kalimba",
    patch=patch,
    master_gain=0.7,
    view=view,
    transport=TransportPreset(bpm=100.0, beats_per_bar=4, beat_unit=4),
)
destination = write_patch_preset(preset, Path("examples/keherwa-kalimba.noodler"))
print("wrote", destination, "|", len(preset.modules), "modules,", len(preset.cables), "cables, at", preset.transport.bpm, "BPM")
