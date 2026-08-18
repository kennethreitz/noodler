"""Build the Pelog Bell Garden: PyTheory's tone systems and its own synthesis."""

from pathlib import Path

from noodler.app import MASTER_ID, ensure_master
from noodler.module_providers.builtin import BuiltinProvider
from noodler.patch import PatchGraph
from noodler.preset import (
    Point,
    RackNodePreset,
    RackViewPreset,
    capture_patch_preset,
    write_patch_preset,
)

provider = BuiltinProvider()
patch = PatchGraph()


def add(instance: str, module_id: str, **parameters):
    # Built in one go rather than field by field: a scale name is only valid
    # for the system it belongs to, so setting them one at a time means going
    # through a state that is not a real key.
    module = provider.create(module_id, parameters)
    patch.add_module(instance, module)
    return module


# ------------------------------------------------------------------ the key
# Pelog is a seven-tone Javanese system whose intervals are nothing like equal
# temperament -- the reason to reach for PyTheory rather than a note table.
# One Key module holds it, and every voice in the patch reads from that one.
add("key", "key", system="pelog", tonic="nem", scale_name="pelog barang",
    octave=3, reference_frequency_hz=220.0)

# --------------------------------------------------------------- the players
# The brains do not know pelog -- they reach six systems, the Key reaches all
# sixteen -- so they think in shapes and the quantizers do the tuning.
add("melody", "melody_brain", system="japanese", tonic="A", scale_name="in",
    style="motif and answer", phrase_length=11, octave_range=3, density=0.58,
    rate_hz=2.1, gate_length=0.3, seed=17)
add("harmony", "harmony_brain", style="tonic journey", length=6,
    register_octave=3, rate_hz=0.22, gate_length=0.85, seed=451)
add("arp", "arpeggio_brain", pattern="up / down", octave_range=2,
    rate_hz=5.6, gate_length=0.22, seed=1904)
add("drift", "wogglebug", clock_rate_hz=0.14, chaos=0.28,
    ego_id_balance=0.4, woggle=0.5, audio_level=0.0, seed=8675)

add("bell_pitch", "quantizer", reference_frequency_hz=220.0)
add("kalimba_pitch", "quantizer", reference_frequency_hz=220.0,
    transpose_octaves=1.0)
# No transposition: the harmony's bass is already low, and an octave below it
# is below the lowest note PyTheory was asked to render.
add("bowl_pitch", "quantizer", reference_frequency_hz=220.0)

# ---------------------------------------------------------------- the voices
# PyTheory renders these notes itself. Instrument Voice would rebuild them from
# oscillators; these are the library's own algorithms, played back.
add("bells", "pytheory_voice", instrument="tubular_bells", level=0.42,
    release_ms=900.0, reference_frequency_hz=220.0)
add("kalimba", "pytheory_voice", instrument="kalimba", level=0.42,
    release_ms=260.0, reference_frequency_hz=220.0)
add("bowl", "pytheory_voice", instrument="singing_bowl", level=0.5,
    release_ms=2400.0, reference_frequency_hz=220.0)

add("echo", "echo_delay", time_seconds=0.42, feedback=0.38, mix=0.3, damping=0.55)
add("space", "reverb", mix=0.55, decay_seconds=7.5, damping=0.5,
    diffusion=0.88, pre_delay_ms=40.0)

master = ensure_master(patch)

# ------------------------------------------------------------------ patching
routes = [
    # One key, three quantizers: changing it retunes the whole garden.
    ("key", "scale", "bell_pitch", "scale"),
    ("key", "scale", "kalimba_pitch", "scale"),
    ("key", "scale", "bowl_pitch", "scale"),

    # A melody, thought in one system and tuned into another.
    ("melody", "pitch", "bell_pitch", "cv"),
    ("bell_pitch", "pitch", "bells", "pitch"),
    ("melody", "gate", "bells", "gate"),

    # Chords become an arpeggio, and the arpeggio becomes a kalimba.
    ("harmony", "voice_1", "arp", "voice_1"),
    ("harmony", "voice_2", "arp", "voice_2"),
    ("harmony", "voice_3", "arp", "voice_3"),
    ("harmony", "voice_4", "arp", "voice_4"),
    ("arp", "pitch", "kalimba_pitch", "cv"),
    ("kalimba_pitch", "pitch", "kalimba", "pitch"),
    ("arp", "gate", "kalimba", "gate"),

    # The bass of each chord, an octave down, held under everything.
    ("harmony", "bass", "bowl_pitch", "cv"),
    ("bowl_pitch", "pitch", "bowl", "pitch"),
    ("harmony", "gate", "bowl", "gate"),

    # Very slow chance moves the kalimba between registers.
    ("drift", "smooth", "kalimba_pitch", "transpose"),

    # Effects, then the master.
    ("kalimba", "audio", "echo", "audio"),
    ("bells", "audio", "space", "audio"),

    ("space", "left", MASTER_ID, "channel_1"),
    ("space", "right", MASTER_ID, "channel_2"),
    ("echo", "output", MASTER_ID, "channel_3"),
    ("bowl", "audio", MASTER_ID, "channel_4"),
]
for source, source_port, target, target_port in routes:
    patch.connect(source, source_port, target, target_port)

master.set_level(1, 0.62); master.set_pan(1, -0.7)
master.set_level(2, 0.62); master.set_pan(2, 0.7)
master.set_level(3, 0.5); master.set_pan(3, 0.35)
master.set_level(4, 0.55); master.set_pan(4, -0.2)
master.parameters.master = 0.5

# ------------------------------------------------------------------ the rack
places = {
    "key": (40, 40), "melody": (40, 330), "harmony": (40, 680), "drift": (40, 1020),
    "arp": (400, 680),
    "bell_pitch": (420, 330), "kalimba_pitch": (760, 680), "bowl_pitch": (420, 1020),
    "bells": (800, 330), "kalimba": (1120, 680), "bowl": (800, 1020),
    "space": (1160, 330), "echo": (1480, 680),
}
view = RackViewPreset(
    zoom=0.75,
    rails={},
    nodes=tuple(
        RackNodePreset(node_id=name, position=Point(x=float(x), y=float(y)))
        for name, (x, y) in places.items()
    ),
)
preset = capture_patch_preset(
    name="Pelog Bell Garden", patch=patch, master_gain=0.7, view=view
)
destination = write_patch_preset(preset, Path("examples/pelog-bell-garden.noodler"))
print("wrote", destination)
print("modules:", len(preset.modules), "| cables:", len(preset.cables))
