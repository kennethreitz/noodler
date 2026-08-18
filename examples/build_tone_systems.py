"""Build the tone-system examples, each one showing a different PyTheory idea.

Run from the repository root:  uv run python examples/build_tone_systems.py

Every patch is the same shape -- a Key that decides the tuning, brains that
think in shapes, quantizers that turn shapes into that tuning, and PyTheory
Voices that render the notes with the library's own synthesis -- so what varies
between them is the music rather than the wiring.
"""

from dataclasses import dataclass, field
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

PROVIDER = BuiltinProvider()


@dataclass
class Voice:
    """One instrument, and how its notes are chosen."""

    name: str
    instrument: str
    source: str                 # "melody" | "arp" | "bass"
    level: float = 0.45
    release_ms: float = 400.0
    transpose: float = 0.0
    pan: float = 0.0
    channel_level: float = 0.7
    through: str | None = None  # "echo" | "space" | None


@dataclass
class Example:
    name: str
    filename: str
    system: str
    tonic: str
    scale_name: str
    octave: int
    voices: list[Voice]
    melody: dict = field(default_factory=dict)
    harmony: dict = field(default_factory=dict)
    arp: dict = field(default_factory=dict)
    drift: dict = field(default_factory=dict)
    echo: dict = field(default_factory=dict)
    space: dict = field(default_factory=dict)
    master: float = 0.5
    reference_hz: float = 220.0


def build(example: Example) -> Path:
    patch = PatchGraph()
    places: dict[str, tuple[int, int]] = {}

    def add(instance: str, module_id: str, where: tuple[int, int], **parameters):
        # Built in one go: a scale name is only valid for the system it belongs
        # to, so setting them one at a time passes through states that are not
        # a real key.
        module = PROVIDER.create(module_id, parameters)
        patch.add_module(instance, module)
        places[instance] = where
        return module

    routes: list[tuple[str, str, str, str]] = []

    add("key", "key", (40, 40), system=example.system, tonic=example.tonic,
        scale_name=example.scale_name, octave=example.octave,
        reference_frequency_hz=example.reference_hz)

    needed = {voice.source for voice in example.voices}

    if "melody" in needed:
        add("melody", "melody_brain", (40, 320), **{
            "system": "japanese", "tonic": "A", "scale_name": "in",
            "style": "motif and answer", "phrase_length": 11, "octave_range": 3,
            "density": 0.58, "rate_hz": 2.1, "gate_length": 0.3, "seed": 17,
            **example.melody})
    if {"arp", "bass"} & needed:
        add("harmony", "harmony_brain", (40, 660), **{
            "style": "tonic journey", "length": 6, "register_octave": 3,
            "rate_hz": 0.22, "gate_length": 0.85, "seed": 451, **example.harmony})
    if "arp" in needed:
        add("arp", "arpeggio_brain", (400, 660), **{
            "pattern": "up / down", "octave_range": 2, "rate_hz": 5.6,
            "gate_length": 0.22, "seed": 1904, **example.arp})
        for index in range(1, 5):
            routes.append(("harmony", f"voice_{index}", "arp", f"voice_{index}"))

    add("drift", "wogglebug", (40, 1000), **{
        "clock_rate_hz": 0.14, "chaos": 0.28, "ego_id_balance": 0.4,
        "woggle": 0.5, "audio_level": 0.0, "seed": 8675, **example.drift})

    wants_echo = any(voice.through == "echo" for voice in example.voices)
    wants_space = any(voice.through == "space" for voice in example.voices)
    if wants_echo:
        add("echo", "echo_delay", (1480, 660), **{
            "time_seconds": 0.42, "feedback": 0.38, "mix": 0.3,
            "damping": 0.55, **example.echo})
    if wants_space:
        add("space", "reverb", (1160, 320), **{
            "mix": 0.55, "decay_seconds": 7.5, "damping": 0.5,
            "diffusion": 0.88, "pre_delay_ms": 40.0, **example.space})

    master = ensure_master(patch)
    channel = 0

    for row, voice in enumerate(example.voices):
        pitch_node = f"{voice.name}_pitch"
        add(pitch_node, "quantizer", (420, 320 + row * 340),
            reference_frequency_hz=example.reference_hz,
            transpose_octaves=voice.transpose)
        add(voice.name, "pytheory_voice", (800, 320 + row * 340),
            instrument=voice.instrument, level=voice.level,
            release_ms=voice.release_ms,
            reference_frequency_hz=example.reference_hz)

        routes.append(("key", "scale", pitch_node, "scale"))
        routes.append((pitch_node, "pitch", voice.name, "pitch"))
        if voice.source == "melody":
            routes.append(("melody", "pitch", pitch_node, "cv"))
            routes.append(("melody", "gate", voice.name, "gate"))
        elif voice.source == "arp":
            routes.append(("arp", "pitch", pitch_node, "cv"))
            routes.append(("arp", "gate", voice.name, "gate"))
        else:
            routes.append(("harmony", "bass", pitch_node, "cv"))
            routes.append(("harmony", "gate", voice.name, "gate"))

    # Effects are shared. A reverb has one input, so more than one voice going
    # into it needs somewhere to be summed first -- which is a mixer, and is
    # what a send is.
    for send, where in (("space", (1160, 120)), ("echo", (1480, 460))):
        feeding = [v for v in example.voices if v.through == send]
        if not feeding:
            continue
        if len(feeding) == 1:
            routes.append((feeding[0].name, "audio", send, "audio"))
            continue
        bus = f"{send}_send"
        add(bus, "polarizing_mixer", where,
            channels=len(feeding), gains=tuple([0.8] * len(feeding)))
        for index, voice in enumerate(feeding, start=1):
            routes.append((voice.name, "audio", bus, f"input_{index}"))
        routes.append((bus, "output", send, "audio"))

    for voice in example.voices:
        if voice.through is not None:
            continue
        channel += 1
        routes.append((voice.name, "audio", MASTER_ID, f"channel_{channel}"))
        master.set_level(channel, voice.channel_level)
        master.set_pan(channel, voice.pan)

    if wants_space:
        for side, pan in (("left", -0.7), ("right", 0.7)):
            channel += 1
            routes.append(("space", side, MASTER_ID, f"channel_{channel}"))
            master.set_level(channel, 0.62)
            master.set_pan(channel, pan)
    if wants_echo:
        channel += 1
        routes.append(("echo", "output", MASTER_ID, f"channel_{channel}"))
        master.set_level(channel, 0.5)
        master.set_pan(channel, 0.35)

    # Very slow chance moves whichever voice is highest between registers.
    if example.voices:
        routes.append(("drift", "smooth", f"{example.voices[0].name}_pitch", "transpose"))

    for source, source_port, target, target_port in routes:
        patch.connect(source, source_port, target, target_port)
    master.parameters.master = example.master

    view = RackViewPreset(
        zoom=0.75,
        rails={},
        nodes=tuple(
            RackNodePreset(node_id=name, position=Point(x=float(x), y=float(y)))
            for name, (x, y) in places.items()
        ),
    )
    preset = capture_patch_preset(
        name=example.name, patch=patch, master_gain=0.7, view=view
    )
    return write_patch_preset(preset, Path("examples") / example.filename)


# --------------------------------------------------------------------------
# The examples themselves

EXAMPLES = [
    Example(
        # A scale that repeats at a twelfth rather than an octave. Nothing in
        # twelve-tone music has an interval to compare it to.
        name="Bohlen-Pierce Chapel",
        filename="bohlen-pierce-chapel.noodler",
        system="bohlen-pierce", tonic="A", scale_name="chromatic", octave=3,
        melody={"style": "rising arch", "rate_hz": 1.1, "phrase_length": 13,
                "octave_range": 2, "density": 0.5, "gate_length": 0.5, "seed": 313},
        harmony={"rate_hz": 0.13, "length": 4, "gate_length": 0.9, "seed": 77},
        arp={"rate_hz": 3.1, "pattern": "up", "gate_length": 0.3, "seed": 29},
        space={"decay_seconds": 14.0, "mix": 0.62, "pre_delay_ms": 70.0},
        voices=[
            Voice("bowls", "singing_bowl_ring", "melody", level=0.42,
                  release_ms=2600.0, through="space"),
            Voice("crotales", "crotales", "arp", level=0.3,
                  release_ms=1400.0, transpose=1.0, through="space"),
            Voice("drone", "theremin", "bass", level=0.28,
                  release_ms=3000.0, transpose=-1.0, pan=-0.25,
                  channel_level=0.5),
        ],
        master=0.5,
    ),
    Example(
        # Seventy-two melakarta ragas, of which this is one.
        name="Carnatic Loom",
        filename="carnatic-loom.noodler",
        system="carnatic", tonic="Sa", scale_name="kalyani", octave=3,
        melody={"rate_hz": 3.4, "phrase_length": 9, "octave_range": 2,
                "density": 0.66, "gate_length": 0.28, "seed": 108},
        harmony={"rate_hz": 0.09, "length": 4, "gate_length": 0.97, "seed": 216},
        arp={"rate_hz": 6.5, "pattern": "up / down", "gate_length": 0.18, "seed": 4},
        echo={"time_seconds": 0.31, "feedback": 0.42, "mix": 0.28},
        space={"decay_seconds": 6.5, "mix": 0.45},
        voices=[
            Voice("sitar", "sitar", "melody", level=0.4, release_ms=520.0,
                  through="echo"),
            Voice("harp", "harp", "arp", level=0.3, release_ms=340.0,
                  transpose=1.0, through="space"),
            Voice("tambura", "harmonium", "bass", level=0.3, release_ms=4000.0,
                  transpose=-1.0, pan=0.2, channel_level=0.55),
        ],
        master=0.5,
    ),
    Example(
        # Twenty-two shrutis: the microtonal grid Indian classical music is
        # actually tuned to, rather than the twelve it is usually written in.
        name="Shruti Drone",
        filename="shruti-drone.noodler",
        system="shruti", tonic="Sa", scale_name="bhairavi", octave=3,
        melody={"style": "weighted wander", "rate_hz": 1.6, "phrase_length": 7,
                "octave_range": 1, "density": 0.48, "gate_length": 0.55, "seed": 22},
        harmony={"rate_hz": 0.06, "length": 3, "gate_length": 0.99, "seed": 1008},
        drift={"clock_rate_hz": 0.07, "chaos": 0.18},
        space={"decay_seconds": 11.0, "mix": 0.5, "damping": 0.62},
        voices=[
            Voice("koto", "koto", "melody", level=0.5, release_ms=900.0,
                  through="space"),
            Voice("drone", "harmonium", "bass", level=0.26, release_ms=3800.0,
                  pan=-0.6, channel_level=0.55),
            Voice("shadow", "mellotron_choir", "bass", level=0.2,
                  release_ms=3800.0, transpose=1.0, pan=0.6, channel_level=0.5),
        ],
        master=0.85,
    ),
    Example(
        # Nineteen equal steps. Ordinary chord shapes, remapped into a grid
        # that has no twelve-tone equivalent -- the thirds are noticeably
        # sweeter and the sharps and flats stop being the same note.
        name="Nineteen",
        filename="nineteen.noodler",
        system="19-tet", tonic="C", scale_name="minor", octave=3,
        melody={"rate_hz": 2.8, "phrase_length": 8, "octave_range": 2,
                "density": 0.6, "gate_length": 0.32, "seed": 1900},
        harmony={"style": "circle motion", "mode": "minor", "rate_hz": 0.3,
                 "length": 8, "gate_length": 0.8, "seed": 19},
        arp={"rate_hz": 4.2, "pattern": "as patched", "gate_length": 0.26, "seed": 91},
        echo={"time_seconds": 0.36, "feedback": 0.34, "mix": 0.3},
        space={"decay_seconds": 5.0, "mix": 0.4},
        voices=[
            Voice("rhodes", "electric_piano", "arp", level=0.34,
                  release_ms=700.0, through="echo"),
            Voice("strings", "string_ensemble", "melody", level=0.3,
                  release_ms=1200.0, through="space"),
            Voice("bass", "upright_bass", "bass", level=0.4, release_ms=500.0,
                  transpose=-1.0, pan=-0.15, channel_level=0.7),
        ],
        master=0.48,
    ),
    Example(
        # Five tones to the octave, and none of them where a piano has one.
        name="Slendro Rain",
        filename="slendro-rain.noodler",
        system="slendro", tonic="nem", scale_name="slendro", octave=3,
        melody={"style": "free random", "rate_hz": 4.5, "phrase_length": 5,
                "octave_range": 3, "density": 0.42, "gate_length": 0.14, "seed": 5},
        harmony={"rate_hz": 0.16, "length": 5, "gate_length": 0.9, "seed": 55},
        arp={"rate_hz": 7.8, "pattern": "random", "gate_length": 0.12, "seed": 555},
        space={"decay_seconds": 9.0, "mix": 0.58, "diffusion": 0.92},
        echo={"time_seconds": 0.27, "feedback": 0.46, "mix": 0.34},
        voices=[
            Voice("box", "music_box", "melody", level=0.4, release_ms=600.0,
                  transpose=1.0, through="space"),
            Voice("kalimba", "kalimba", "arp", level=0.32, release_ms=300.0,
                  through="echo"),
            Voice("marimba", "marimba", "bass", level=0.36, release_ms=500.0,
                  pan=-0.3, channel_level=0.6),
        ],
        master=0.5,
    ),
    Example(
        # Fifty-three commas to the octave. Hicaz is the maqam a European ear
        # hears as "the exotic one", and it is exotic because those intervals
        # are not available in twelve.
        name="Makam Divan",
        filename="makam-divan.noodler",
        system="makam", tonic="La", scale_name="hicaz", octave=3,
        melody={"style": "motif and answer", "rate_hz": 2.6, "phrase_length": 12,
                "octave_range": 2, "density": 0.62, "gate_length": 0.3, "seed": 53},
        harmony={"rate_hz": 0.11, "length": 4, "gate_length": 0.93, "seed": 1453},
        arp={"rate_hz": 5.0, "pattern": "down", "gate_length": 0.2, "seed": 800},
        echo={"time_seconds": 0.38, "feedback": 0.4, "mix": 0.29},
        space={"decay_seconds": 8.0, "mix": 0.5},
        voices=[
            Voice("oud", "oud", "melody", level=0.42, release_ms=600.0,
                  through="echo"),
            Voice("ney", "flute", "arp", level=0.26, release_ms=800.0,
                  transpose=1.0, through="space"),
            Voice("bass", "contrabass", "bass", level=0.36, release_ms=900.0,
                  transpose=-1.0, pan=0.2, channel_level=0.65),
        ],
        master=0.5,
    ),
]

if __name__ == "__main__":
    for example in EXAMPLES:
        path = build(example)
        print(f"  wrote {path}")
