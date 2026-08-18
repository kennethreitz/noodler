"""Text formatting shared by generated panels and rack furniture."""

import math

from .style import KNOB_COLUMN_CHARS, LABEL_ABBREVIATIONS, UNIT_SUFFIXES


def decibels(level: float) -> str:
    return "-∞" if level <= 0.00001 else f"{20.0 * math.log10(level):.0f}"


def format_duration(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f} us"
    if seconds < 1.0:
        return f"{seconds * 1_000:.1f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    return f"{seconds / 60.0:.2f} min"


def format_frequency(frequency: float) -> str:
    if frequency < 1.0:
        return f"{frequency:.2f} Hz"
    if frequency < 1_000.0:
        return f"{frequency:.1f} Hz"
    return f"{frequency / 1_000.0:.2f} kHz"


def fit_column(text: str, width: int = KNOB_COLUMN_CHARS) -> str:
    """Pad or trim one cell so control columns align down the panel."""
    if len(text) > width:
        return text[: max(1, width - 1)] + "…"
    return text.ljust(width)


def control_label_and_unit(field_name: str) -> tuple[str, str]:
    """Turn a model field into a compact control label and its unit."""
    name = field_name
    unit = ""
    for suffix, symbol in UNIT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            unit = symbol
            break
    name = name.removesuffix("_amount")
    words = [
        LABEL_ABBREVIATIONS.get(word, word) for word in name.split("_") if word
    ]
    return " ".join(words).title(), unit


def format_dynamic_value(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000.0:
        return f"{value:,.0f}"
    if magnitude >= 10.0:
        return f"{value:.1f}"
    return f"{value:.3f}"


def strip_title(instance_id: str, module: object = None, width: int = 4) -> str:
    """Return a module name short enough for a console strip title."""
    said = getattr(module, "strip_name", None)
    if isinstance(said, str) and said.strip():
        return said.strip().upper()[:width]
    words = [word for word in instance_id.replace("-", "_").split("_") if word]
    if not words:
        return instance_id.upper()[:width]
    number = ""
    if words[-1].isdigit() and len(words) > 1:
        number = words[-1]
        words = words[:-1]
    stem = words[-1].upper()
    room = max(1, width - len(number))
    return f"{stem[:room]}{number}"


def library_slug(label: str) -> str:
    """Return a stable Dear PyGui tag fragment for a library heading."""
    normalized = "".join(
        character.lower() if character.isalnum() else " " for character in label
    )
    return "_".join(normalized.split())
