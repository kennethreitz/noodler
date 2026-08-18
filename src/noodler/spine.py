"""Book-spine textures for visually folded rack modules."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True, slots=True)
class SpineTexture:
    width: int
    height: int
    pixels: tuple[float, ...]


def render_spine_texture(
    title: str,
    accent: tuple[int, int, int, int],
    font_path: str | Path,
    *,
    font_size: int = 16,
) -> SpineTexture:
    """Render a bottom-to-top title like lettering on a narrow book spine."""
    font = ImageFont.truetype(str(font_path), font_size)
    padding_x = 11
    padding_y = 14
    bounds = font.getbbox(title)
    text_width = max(1, bounds[2] - bounds[0])
    text_height = max(1, bounds[3] - bounds[1])
    horizontal = Image.new(
        "RGBA",
        (text_width + padding_x * 2, text_height + padding_y * 2),
        accent,
    )
    draw = ImageDraw.Draw(horizontal)
    draw.text(
        (padding_x - bounds[0], padding_y - bounds[1]),
        title,
        fill=(245, 241, 229, 255),
        font=font,
    )
    vertical = horizontal.rotate(90, expand=True)
    pixels = tuple(channel / 255.0 for channel in vertical.tobytes())
    return SpineTexture(vertical.width, vertical.height, pixels)


__all__ = ["SpineTexture", "render_spine_texture"]
