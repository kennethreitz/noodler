"""Build Night Market: the biggest patch in the box, everything on the clock.

Run from the repository root:  uv run python examples/build_night_market.py

Two of PyTheory's rhythms at once -- teental, the sixteen-beat tabla cycle, in
front, and an afrobeat kit lilting under it. A Clock drives every brain: the
harmony changes chord on the bar, an arpeggio runs the chord in sixteenths on
a celesta, an electric piano stabs the chord's top voice on every beat, and
two melody brains -- one in sixteenths on a sitar, one in eighths on a flute a
register up -- answer each other over it. A bass plays the root on the beat. A
pad holds each chord under everything, filtered by a state-variable filter
whose cutoff a slow function sweeps and whose resonance a Wogglebug worries;
the sitar goes through a low-pass gate the melody strikes, so it plucks. One
Key in makam nihavend tunes all six pitched voices, five of which are
PyTheory's own synthesis and one of which is a PyTheory recipe realised in
Noodler's oscillators. Eight channels, delay on send A, a cathedral on send B.
Twenty-eight modules, at 96 BPM.
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


BPM = 96.0
BEAT = 60.0 / BPM

# ------------------------------------------------------------------ the time
add("clock", "clock", (40, 40), trigger_ms=6.0)
add("tabla", "pytheory_beats", (40, 300), pattern="teental", level=0.7, swing=0.0)
add("kit", "pytheory_beats", (40, 560), pattern="afrobeat", level=0.32, swing=0.08)

# ------------------------------------------------------------------- the key
add("key", "key", (40, 860), system="makam", tonic="La", scale_name="nihavend",
    octave=3, reference_frequency_hz=220.0)

# ---------------------------------------------------------------- the brains
add("harmony", "harmony_brain", (400, 860), style="functional choices", mode="minor",
    length=8, register_octave=3, gate_length=0.9, seed=1001)
add("arp", "arpeggio_brain", (760, 860), pattern="random", octave_range=2,
    gate_length=0.4, seed=77)
add("melody", "melody_brain", (400, 300), system="western", tonic="A",
    scale_name="minor", style="motif and answer", phrase_length=16,
    octave_range=2, density=0.5, gate_length=0.35, seed=2020)
add("answer", "melody_brain", (400, 560), system="western", tonic="A",
    scale_name="minor", style="weighted wander", phrase_length=8,
    octave_range=1, density=0.38, gate_length=0.55, seed=303)

# ------------------------------------------------------------- the modulation
shape = add("sweep", "function_utility", (40, 1180))
shape.parameters.channel_1 = shape.parameters.channel_1.model_copy(
    update={"rise_seconds": 8 * BEAT * 4, "fall_seconds": 8 * BEAT * 4, "curve": 0.2,
            "cycle": True, "attenuverter": 0.7}
)
add("worry", "wogglebug", (400, 1180), clock_rate_hz=0.6, chaos=0.4,
    ego_id_balance=0.5, woggle=0.6, audio_level=0.0, seed=99)

# ------------------------------------------------------------ the quantizers
add("celesta_pitch", "quantizer", (1120, 860), reference_frequency_hz=220.0, transpose_octaves=1.0)
add("stab_pitch", "quantizer", (1120, 1060), reference_frequency_hz=220.0)
add("sitar_pitch", "quantizer", (760, 300), reference_frequency_hz=220.0)
add("flute_pitch", "quantizer", (760, 560), reference_frequency_hz=220.0, transpose_octaves=1.0)
add("bass_pitch", "quantizer", (1120, 1260), reference_frequency_hz=220.0, transpose_octaves=-1.0)
add("pad_pitch", "quantizer", (1120, 1460), reference_frequency_hz=220.0, transpose_octaves=-1.0)

# ---------------------------------------------------------------- the voices
add("celesta", "pytheory_voice", (1480, 860), instrument="celesta", level=0.36,
    release_ms=500.0, reference_frequency_hz=220.0)
add("stab", "instrument_voice", (1480, 1060), instrument="electric_piano", level=0.3,
    brightness=-0.5, reference_frequency_hz=220.0)
add("sitar", "pytheory_voice", (1120, 300), instrument="sitar", level=0.44,
    release_ms=650.0, reference_frequency_hz=220.0)
add("pluck", "low_pass_gate", (1480, 300), decay_seconds=0.7, brightness=0.8,
    character=0.5, level=0.95)
add("flute", "pytheory_voice", (1120, 560), instrument="flute", level=0.3,
    release_ms=420.0, reference_frequency_hz=220.0)
add("bass", "pytheory_voice", (1480, 1260), instrument="upright_bass", level=0.5,
    release_ms=520.0, reference_frequency_hz=220.0)
add("pad", "pytheory_voice", (1480, 1460), instrument="analog_pad", level=0.42,
    release_ms=2400.0, reference_frequency_hz=220.0)
add("haze", "state_variable_filter", (1840, 1460), cutoff_hz=900.0, resonance=0.35, drive=1.2)

# --------------------------------------------------------------- the effects
add("delay", "echo_delay", (1840, 300), time_seconds=BEAT * 0.75, feedback=0.4,
    mix=1.0, damping=0.5)
add("cathedral", "pytheory_reverb", (1840, 620), space="cathedral", mix=1.0,
    decay_seconds=4.5, width=1.0, pre_delay_ms=25.0)

master = ensure_master(patch)

routes = [
    # One clock, four brains.
    ("clock", "bar", "harmony", "clock"),
    ("clock", "sixteenth", "arp", "clock"),
    ("clock", "sixteenth", "melody", "clock"),
    ("clock", "eighth", "answer", "clock"),
    ("clock", "bar", "melody", "reset"),

    # One key, six quantizers.
    ("key", "scale", "celesta_pitch", "scale"),
    ("key", "scale", "stab_pitch", "scale"),
    ("key", "scale", "sitar_pitch", "scale"),
    ("key", "scale", "flute_pitch", "scale"),
    ("key", "scale", "bass_pitch", "scale"),
    ("key", "scale", "pad_pitch", "scale"),

    # Chords -> arpeggio -> celesta.
    ("harmony", "voice_1", "arp", "voice_1"),
    ("harmony", "voice_2", "arp", "voice_2"),
    ("harmony", "voice_3", "arp", "voice_3"),
    ("harmony", "voice_4", "arp", "voice_4"),
    ("arp", "pitch", "celesta_pitch", "cv"),
    ("celesta_pitch", "pitch", "celesta", "pitch"),
    ("arp", "gate", "celesta", "gate"),

    # The chord's top voice, stabbed on every beat by an electric piano.
    ("harmony", "voice_3", "stab_pitch", "cv"),
    ("stab_pitch", "pitch", "stab", "pitch"),
    ("clock", "beat", "stab", "gate"),

    # A melody on the sitar, plucked through a low-pass gate.
    ("melody", "pitch", "sitar_pitch", "cv"),
    ("sitar_pitch", "pitch", "sitar", "pitch"),
    ("melody", "gate", "sitar", "gate"),
    ("sitar", "audio", "pluck", "audio"),
    ("melody", "trigger", "pluck", "strike"),

    # An answer on the flute, a register up.
    ("answer", "pitch", "flute_pitch", "cv"),
    ("flute_pitch", "pitch", "flute", "pitch"),
    ("answer", "gate", "flute", "gate"),

    # The bass plays the root on every beat.
    ("harmony", "bass", "bass_pitch", "cv"),
    ("bass_pitch", "pitch", "bass", "pitch"),
    ("clock", "beat", "bass", "gate"),

    # The pad holds each chord under everything, through a filter that a slow
    # function sweeps and a Wogglebug worries.
    ("harmony", "voice_1", "pad_pitch", "cv"),
    ("pad_pitch", "pitch", "pad", "pitch"),
    ("clock", "bar", "pad", "gate"),
    ("pad", "audio", "haze", "audio"),
    ("sweep", "channel_1", "haze", "cutoff_cv"),
    ("worry", "smooth", "haze", "resonance_cv"),

    # Into the console: eight channels.
    ("tabla", "audio", MASTER_ID, "channel_1"),
    ("kit", "audio", MASTER_ID, "channel_2"),
    ("bass", "audio", MASTER_ID, "channel_3"),
    ("celesta", "audio", MASTER_ID, "channel_4"),
    ("stab", "audio", MASTER_ID, "channel_5"),
    ("pluck", "output", MASTER_ID, "channel_6"),
    ("flute", "audio", MASTER_ID, "channel_7"),
    ("haze", "low", MASTER_ID, "channel_8"),

    # Sends and returns.
    (MASTER_ID, "send_a", "delay", "audio"),
    (MASTER_ID, "send_b", "cathedral", "audio"),
    ("delay", "output", MASTER_ID, "return_a_left"),
    ("cathedral", "wet_left", MASTER_ID, "return_b_left"),
    ("cathedral", "wet_right", MASTER_ID, "return_b_right"),
]
for source, source_port, target, target_port in routes:
    patch.connect(source, source_port, target, target_port)

master.set_level(1, 0.85); master.set_pan(1, 0.05);  master.set_send("b", 1, 0.2)
master.set_level(2, 0.55); master.set_pan(2, -0.1)
master.set_level(3, 0.7);  master.set_pan(3, 0.0)
master.set_level(4, 0.5);  master.set_pan(4, 0.55);  master.set_send("a", 4, 0.45); master.set_send("b", 4, 0.5)
master.set_level(5, 0.5);  master.set_pan(5, -0.35); master.set_send("a", 5, 0.3); master.set_send("b", 5, 0.3)
master.set_level(6, 0.6);  master.set_pan(6, -0.5);  master.set_send("a", 6, 0.5); master.set_send("b", 6, 0.35)
master.set_level(7, 0.5);  master.set_pan(7, 0.4);   master.set_send("b", 7, 0.6)
master.set_level(8, 0.45); master.set_pan(8, 0.0);   master.set_send("b", 8, 0.7)
master.set_return_level("a", 0.5)
master.set_return_level("b", 0.6)
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
    name="Night Market",
    patch=patch,
    master_gain=0.7,
    view=view,
    transport=TransportPreset(bpm=BPM, beats_per_bar=4, beat_unit=4),
)
destination = write_patch_preset(preset, Path("examples/night-market.noodler"))
print("wrote", destination, "|", len(preset.modules), "modules,", len(preset.cables), "cables, at", preset.transport.bpm, "BPM")
