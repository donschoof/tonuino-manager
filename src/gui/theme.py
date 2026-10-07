"""
Farbpalette (Catppuccin Mocha) - einzige Quelle fuer Farben im Python-Code
(Icons, Painter) und im Qt-Stylesheet: styles.py nutzt Platzhalter @NAME@, die
apply() durch die Werte unten ersetzt.
"""

BASE = "#1e1e2e"
MANTLE = "#181825"
SURFACE0 = "#313244"
SURFACE1 = "#45475a"
SURFACE2 = "#585b70"
OVERLAY0 = "#6c7086"
OVERLAY1 = "#7f849c"
OVERLAY2 = "#9399b2"
SUBTEXT0 = "#a6adc8"
TEXT = "#cdd6f4"
BLUE = "#89b4fa"
BLUE_HOVER = "#b4d0fb"
RED = "#f38ba8"
RED_HOVER = "#f5a0b8"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
WHITE = "#ffffff"
SURFACE_DEEP = "#282838"
MENU_BG = "#2b2c3f"
HOVER_MID = "#3b3d52"
HOVER_STRONG = "#4a4c63"


_PALETTE = {name: value for name, value in globals().items() if name.isupper() and not name.startswith("_")}


def apply(template: str) -> str:
    """Ersetzt die Platzhalter @NAME@ im Stylesheet durch die Palettenwerte"""
    # Laengere Namen zuerst, damit z.B. @BLUE_HOVER@ nie als @BLUE@ + Rest gelesen wird
    for name in sorted(_PALETTE, key=len, reverse=True):
        template = template.replace(f"@{name}@", _PALETTE[name])
    return template
