from pathlib import Path

from noodler.spine import render_spine_texture


SYSTEM_MONO_FONT = Path("/System/Library/Fonts/SFNSMono.ttf")


def test_spine_texture_is_tall_narrow_and_opaque() -> None:
    texture = render_spine_texture(
        "WOGGLEBUG / UNCERTAINTY",
        (191, 102, 159, 255),
        SYSTEM_MONO_FONT,
    )

    assert texture.height > texture.width * 3
    assert len(texture.pixels) == texture.width * texture.height * 4
    assert min(texture.pixels[3::4]) == 1.0
