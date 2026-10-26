"""
Farbpaletten - einzige Quelle fuer Farben im Python-Code (Icons, Painter) und im
Qt-Stylesheet: styles.py nutzt Platzhalter @NAME@, die apply() durch die Werte der
aktiven Palette ersetzt.

Dunkel ist Catppuccin Mocha. Hell ist auf kraeftige Kontraste ausgelegt (Text
und Symbole mindestens 4,5:1, Rahmen und Bedienelemente mindestens 3:1 zum
jeweiligen Untergrund). Die Namen sind Rollen, keine Helligkeiten: BASE ist
immer der Hauptuntergrund, TEXT die Hauptschrift.

Die aktive Palette muss gewaehlt werden (set_theme), bevor andere gui-Module
importiert werden - einige lesen Farben schon beim Import.
"""

DARK = {
    "BASE": "#1e1e2e",
    "MANTLE": "#181825",
    "SURFACE0": "#313244",
    "SURFACE1": "#45475a",
    "SURFACE2": "#585b70",
    "OVERLAY0": "#6c7086",
    "OVERLAY1": "#7f849c",
    "OVERLAY2": "#9399b2",
    "SUBTEXT0": "#a6adc8",
    "TEXT": "#cdd6f4",
    "BLUE": "#89b4fa",
    "BLUE_HOVER": "#b4d0fb",
    "RED": "#f38ba8",
    "RED_HOVER": "#f5a0b8",
    "RED_RGB": "243, 139, 168",
    "GREEN": "#a6e3a1",
    "YELLOW": "#f9e2af",
    "WHITE": "#ffffff",
    "TEXT_HOVER": "#ffffff",
    "SCRIM_TEXT": "#cdd6f4",
    "BORDER": "#45475a",
    "BORDER_HOVER": "#585b70",
    "DISABLED": "#585b70",
    "DISABLED_ICON": "#45475a",
    "SYSTEM_TEXT": "#585b70",
    "SYSTEM_BORDER": "#313244",
    "SURFACE_DEEP": "#282838",
    "MENU_BG": "#2b2c3f",
    "HOVER_MID": "#3b3d52",
    "HOVER_STRONG": "#4a4c63",
}

LIGHT = {
    "BASE": "#ffffff",
    "MANTLE": "#eef0f6",
    "SURFACE0": "#e1e5ee",
    "SURFACE1": "#cbd1e0",
    "SURFACE2": "#b3bbcf",
    "OVERLAY0": "#5d657c",
    "OVERLAY1": "#4e566c",
    "OVERLAY2": "#434a60",
    "SUBTEXT0": "#363c51",
    "TEXT": "#161a29",
    "BLUE": "#1750c0",
    "BLUE_HOVER": "#103d96",
    "RED": "#b3123a",
    "RED_HOVER": "#8f0e2e",
    "RED_RGB": "179, 18, 58",
    "GREEN": "#146c2e",
    "YELLOW": "#8a5300",
    "WHITE": "#ffffff",
    "TEXT_HOVER": "#3a4160",
    "SCRIM_TEXT": "#ffffff",
    "BORDER": "#7d859b",
    "BORDER_HOVER": "#5d657c",
    "DISABLED": "#8a91a5",
    "DISABLED_ICON": "#a5adc0",
    "SYSTEM_TEXT": "#4e566c",
    "SYSTEM_BORDER": "#7d859b",
    "SURFACE_DEEP": "#e8ebf3",
    "MENU_BG": "#ffffff",
    "HOVER_MID": "#d5dae7",
    "HOVER_STRONG": "#c2c9db",
}

THEMES = {"dark": DARK, "light": LIGHT}
DEFAULT_THEME = "dark"
SETTINGS_KEY = "appearance/theme"

_PALETTE = dict(DARK)
current = DEFAULT_THEME

# Vorbelegung (Dunkel), damit die Namen auch ohne set_theme() existieren
globals().update(_PALETTE)


def set_theme(name: str) -> str:
    """Aktiviert die Palette 'dark' oder 'light' (unbekannt -> dark) und gibt den
    tatsaechlich gewaehlten Namen zurueck"""
    global current
    current = name if name in THEMES else DEFAULT_THEME
    _PALETTE.clear()
    _PALETTE.update(THEMES[current])
    globals().update(_PALETTE)
    return current


def apply(template: str) -> str:
    """Ersetzt die Platzhalter @NAME@ im Stylesheet durch die Palettenwerte"""
    # Laengere Namen zuerst, damit z.B. @BLUE_HOVER@ nie als @BLUE@ + Rest gelesen wird
    for name in sorted(_PALETTE, key=len, reverse=True):
        template = template.replace(f"@{name}@", _PALETTE[name])
    return template
