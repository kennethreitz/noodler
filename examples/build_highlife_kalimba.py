"""Build Highlife Kalimba: a groove that follows the clock in the menu bar.

Run from the repository root:  uv run python examples/build_highlife_kalimba.py

Everything here keeps time with the transport. PyTheory Beats plays the
library's highlife pattern through its own drum synthesis, bar-locked; the
Clock module turns the same transport into triggers, and every brain is
clocked from it -- chords change on the bar, the arpeggio runs in eighths, the
melody steps in sixteenths -- so changing the tempo changes everything at
once and beat one is beat one for all of it. The voices are PyTheory's own
kalimba, marimba and upright bass, tuned by one Key in yo, the Japanese
pentatonic that highlife guitar lines happen to sit in comfortably. The room
and the echo hang off the master's sends.
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
add("drums", "pytheory_beats", (40, 300), pattern="highlife", level=0.62, swing=0.12)

# ------------------------------------------------------------------- the key
add("key", "key", (40, 620), system="japanese", tonic="D", scale_name="yo",
    octave=3, reference_frequency_hz=220.0)

# ---------------------------------------------------------------- the brains
# Clocked from the Clock rather than free-running: the harmony changes chord
# on every bar, the arpeggio steps in eighths, the melody in sixteenths.
add("harmony", "harmony_brain", (400, 620), style="circle motion", mode="major",
    length=4, register_octave=3, gate_length=0.9, seed=1957)
add("arp", "arpeggio_brain", (760, 620), pattern="up / down", octave_range=2,
    gate_length=0.4, seed=64)
add("melody", "melody_brain", (400, 300), system="japanese", tonic="D",
    scale_name="yo", style="motif and answer", phrase_length=16,
    octave_range=2, density=0.55, gate_length=0.4, seed=1988)

add("kalimba_pitch", "quantizer", (1120, 620), reference_frequency_hz=220.0,
    transpose_octaves=1.0)
add("marimba_pitch", "quantizer", (760, 300), reference_frequency_hz=220.0)
add("bass_pitch", "quantizer", (1120, 900), reference_frequency_hz=220.0,
    transpose_octaves=-1.0)

# ---------------------------------------------------------------- the voices
add("kalimba", "pytheory_voice", (1480, 620), instrument="kalimba", level=0.42,
    release_ms=420.0, reference_frequency_hz=220.0)
add("marimba", "pytheory_voice", (1120, 300), instrument="marimba", level=0.36,
    release_ms=380.0, reference_frequency_hz=220.0)
add("bass", "pytheory_voice", (1480, 900), instrument="upright_bass", level=0.5,
    release_ms=520.0, reference_frequency_hz=220.0)

add("space", "reverb", (1840, 300), mix=1.0, decay_seconds=4.5, damping=0.55,
    diffusion=0.85, pre_delay_ms=25.0)
add("echo", "echo_delay", (1840, 620), time_seconds=0.2778, feedback=0.36,
    mix=1.0, damping=0.5)

master = ensure_master(patch)

routes = [
    # One clock, three brains.
    ("clock", "bar", "harmony", "clock"),
    ("clock", "eighth", "arp", "clock"),
    ("clock", "sixteenth", "melody", "clock"),
    ("clock", "bar", "melody", "reset"),

    # One key, three quantizers.
    ("key", "scale", "kalimba_pitch", "scale"),
    ("key", "scale", "marimba_pitch", "scale"),
    ("key", "scale", "bass_pitch", "scale"),

    # Chords -> arpeggio -> kalimba.
    ("harmony", "voice_1", "arp", "voice_1"),
    ("harmony", "voice_2", "arp", "voice_2"),
    ("harmony", "voice_3", "arp", "voice_3"),
    ("harmony", "voice_4", "arp", "voice_4"),
    ("arp", "pitch", "kalimba_pitch", "cv"),
    ("kalimba_pitch", "pitch", "kalimba", "pitch"),
    ("arp", "gate", "kalimba", "gate"),

    # The melody, on the marimba.
    ("melody", "pitch", "marimba_pitch", "cv"),
    ("marimba_pitch", "pitch", "marimba", "pitch"),
    ("melody", "gate", "marimba", "gate"),

    # The bass plays the chord root on every beat.
    ("harmony", "bass", "bass_pitch", "cv"),
    ("bass_pitch", "pitch", "bass", "pitch"),
    ("clock", "beat", "bass", "gate"),

    # Into the master: drums, bass, kalimba, marimba; the room and echo return.
    ("drums", "audio", MASTER_ID, "channel_1"),
    ("bass", "audio", MASTER_ID, "channel_2"),
    ("kalimba", "audio", MASTER_ID, "channel_3"),
    ("marimba", "audio", MASTER_ID, "channel_4"),
    (MASTER_ID, "send_a", "space", "audio"),
    (MASTER_ID, "send_b", "echo", "audio"),
    ("space", "left", MASTER_ID, "channel_5"),
    ("space", "right", MASTER_ID, "channel_6"),
    ("echo", "output", MASTER_ID, "channel_7"),
]
for source, source_port, target, target_port in routes:
    patch.connect(source, source_port, target, target_port)

master.set_level(1, 0.8);  master.set_pan(1, 0.0)
master.set_level(2, 0.7);  master.set_pan(2, -0.1)
master.set_level(3, 0.6);  master.set_pan(3, 0.45);  master.set_send("a", 3, 0.5); master.set_send("b", 3, 0.6)
master.set_level(4, 0.55); master.set_pan(4, -0.45); master.set_send("a", 4, 0.7)
master.set_level(5, 0.5);  master.set_pan(5, -0.7)
master.set_level(6, 0.5);  master.set_pan(6, 0.7)
master.set_level(7, 0.4);  master.set_pan(7, 0.3)
master.parameters.master = 0.5

view = RackViewPreset(
    zoom=0.72,
    rails={},
    nodes=tuple(
        RackNodePreset(node_id=name, position=Point(x=float(x), y=float(y)))
        for name, (x, y) in places.items()
    ),
)
preset = capture_patch_preset(
    name="Highlife Kalimba",
    patch=patch,
    master_gain=0.7,
    view=view,
    transport=TransportPreset(bpm=108.0, beats_per_bar=4, beat_unit=4),
)
destination = write_patch_preset(preset, Path("examples/highlife-kalimba.noodler"))
print("wrote", destination, "|", len(preset.modules), "modules,", len(preset.cables), "cables, at", preset.transport.bpm, "BPM")
