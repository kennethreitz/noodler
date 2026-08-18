"""One place that decides what Noodler looks like."""

import dearpygui.dearpygui as dpg


INK = (232, 227, 214, 255)
MUTED = (150, 146, 136, 255)
FAINT = (104, 101, 94, 255)
SURFACE = (30, 30, 28, 255)
PANEL = (41, 40, 37, 255)
RAISED = (52, 50, 46, 255)
LINE = (72, 69, 63, 255)

SIGNAL = {
    "audio": (94, 196, 190, 255),
    "cv": (226, 174, 78, 255),
    "gate": (222, 112, 82, 255),
    "trigger": (222, 112, 82, 255),
    "musical": (168, 132, 208, 255),
}

CATEGORY_ACCENT = {
    "Musical Brains": (168, 132, 208, 255),
    "Sequencers": (150, 140, 214, 255),
    "Oscillators": (94, 172, 178, 255),
    "Sources": (94, 172, 178, 255),
    "Noise & Random": (198, 118, 166, 255),
    "Random & Chaos": (198, 118, 166, 255),
    "Filters": (198, 158, 84, 255),
    "Envelopes & Dynamics": (214, 150, 62, 255),
    "Dynamics": (214, 150, 62, 255),
    "Effects": (104, 138, 190, 255),
    "Utilities": (152, 160, 148, 255),
    "Utility": (152, 160, 148, 255),
}

OUTPUT_ACCENT = (198, 96, 78, 255)

APP_THEME = "noodler.ui.theme"
EDITOR_THEME = "noodler.ui.theme.editor"
FONT = "noodler.ui.font"
MONO = "/System/Library/Fonts/SFNSMono.ttf"


def accent_for(category: str) -> tuple[int, int, int, int]:
    """A module's colour comes from what it is for, so kinds read as kinds."""
    return CATEGORY_ACCENT.get(category, MUTED)


def _dim(color: tuple[int, int, int, int], amount: float) -> tuple[int, ...]:
    return (*(round(channel * amount) for channel in color[:3]), color[3])


def configure() -> None:
    """Build the application theme and the rack's own editor theme."""
    if not dpg.does_item_exist(FONT):
        try:
            with dpg.font_registry():
                dpg.add_font(MONO, 15, tag=FONT)
            dpg.bind_font(FONT)
        except Exception:  # pragma: no cover - a host without that face
            pass

    if not dpg.does_item_exist(APP_THEME):
        with dpg.theme(tag=APP_THEME):
            with dpg.theme_component(dpg.mvAll):
                for target, color in (
                    (dpg.mvThemeCol_WindowBg, SURFACE),
                    (dpg.mvThemeCol_ChildBg, SURFACE),
                    (dpg.mvThemeCol_PopupBg, PANEL),
                    (dpg.mvThemeCol_Text, INK),
                    (dpg.mvThemeCol_TextDisabled, FAINT),
                    (dpg.mvThemeCol_Border, LINE),
                    (dpg.mvThemeCol_FrameBg, RAISED),
                    (dpg.mvThemeCol_FrameBgHovered, _dim(RAISED, 1.2)),
                    (dpg.mvThemeCol_FrameBgActive, _dim(RAISED, 1.35)),
                    (dpg.mvThemeCol_Button, RAISED),
                    (dpg.mvThemeCol_ButtonHovered, _dim(RAISED, 1.25)),
                    (dpg.mvThemeCol_ButtonActive, _dim(RAISED, 1.4)),
                    (dpg.mvThemeCol_Header, _dim(RAISED, 1.1)),
                    (dpg.mvThemeCol_HeaderHovered, _dim(RAISED, 1.25)),
                    (dpg.mvThemeCol_HeaderActive, _dim(RAISED, 1.35)),
                    (dpg.mvThemeCol_MenuBarBg, PANEL),
                    (dpg.mvThemeCol_ScrollbarBg, SURFACE),
                    (dpg.mvThemeCol_ScrollbarGrab, LINE),
                    (dpg.mvThemeCol_TitleBg, PANEL),
                    (dpg.mvThemeCol_TitleBgActive, PANEL),
                ):
                    dpg.add_theme_color(target, color)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 10, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 7, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 5)
        dpg.bind_theme(APP_THEME)

    if not dpg.does_item_exist(EDITOR_THEME):
        with dpg.theme(tag=EDITOR_THEME):
            with dpg.theme_component(dpg.mvNodeEditor):
                for target, color in (
                    (dpg.mvNodeCol_GridBackground, (24, 24, 22, 255)),
                    (dpg.mvNodeCol_GridLine, (38, 38, 35, 255)),
                    # Modules cannot overlap and are never dragged loose, so a
                    # marquee has nothing to select and never needs drawing.
                    (dpg.mvNodeCol_BoxSelector, (0, 0, 0, 0)),
                    (dpg.mvNodeCol_BoxSelectorOutline, (0, 0, 0, 0)),
                ):
                    dpg.add_theme_color(
                        target, color, category=dpg.mvThemeCat_Nodes
                    )
                dpg.add_theme_style(
                    dpg.mvNodeStyleVar_GridSpacing, 28, category=dpg.mvThemeCat_Nodes
                )


def panel_theme(tag: str, accent: tuple[int, int, int, int]) -> str:
    """A per-module theme, so a panel wears the colour of what it is."""
    if dpg.does_item_exist(tag):
        return tag
    with dpg.theme(tag=tag):
        with dpg.theme_component(dpg.mvNode):
            for target, color in (
                (dpg.mvNodeCol_NodeBackground, PANEL),
                (dpg.mvNodeCol_NodeBackgroundHovered, _dim(PANEL, 1.12)),
                (dpg.mvNodeCol_NodeBackgroundSelected, _dim(PANEL, 1.2)),
                (dpg.mvNodeCol_NodeOutline, _dim(accent, 0.55)),
                (dpg.mvNodeCol_TitleBar, _dim(accent, 0.5)),
                (dpg.mvNodeCol_TitleBarHovered, _dim(accent, 0.72)),
                (dpg.mvNodeCol_TitleBarSelected, _dim(accent, 0.72)),
                (dpg.mvNodeCol_Pin, accent),
                (dpg.mvNodeCol_PinHovered, INK),
            ):
                dpg.add_theme_color(target, color, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_NodeCornerRounding,
                7,
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_NodePadding, 9, 6, category=dpg.mvThemeCat_Nodes
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_PinCircleRadius,
                5,
                category=dpg.mvThemeCat_Nodes,
            )
    return tag


def link_theme(tag: str, signal: str) -> str:
    """Cables are coloured by what they carry."""
    if dpg.does_item_exist(tag):
        return tag
    color = SIGNAL.get(signal, SIGNAL["cv"])
    with dpg.theme(tag=tag):
        with dpg.theme_component(dpg.mvNodeLink):
            dpg.add_theme_color(
                dpg.mvNodeCol_Link, color, category=dpg.mvThemeCat_Nodes
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_LinkHovered, INK, category=dpg.mvThemeCat_Nodes
            )
            dpg.add_theme_color(
                dpg.mvNodeCol_LinkSelected, INK, category=dpg.mvThemeCat_Nodes
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_LinkThickness,
                3,
                category=dpg.mvThemeCat_Nodes,
            )
    return tag


__all__ = [
    "APP_THEME",
    "EDITOR_THEME",
    "FAINT",
    "INK",
    "LINE",
    "MUTED",
    "OUTPUT_ACCENT",
    "PANEL",
    "SIGNAL",
    "SURFACE",
    "accent_for",
    "configure",
    "link_theme",
    "panel_theme",
]
