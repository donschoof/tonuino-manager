"""Baut die gebuendelte Icon-Schrift (Teilmenge von Material Symbols Outlined)

Quelle ist die variable Schrift aus google/material-design-icons:
variablefont/MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].ttf

Aufruf: python tools/make_icon_font.py <Pfad zur variablen Schrift>
"""
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

OUTPUT = Path(__file__).resolve().parent.parent / "src" / "resources" / "fonts" / "MaterialSymbolsOutlined-subset.ttf"

# Feste Achsenwerte: umriss, normale Strichstaerke, wie die App die Icons zeichnet
AXES = {"FILL": 0, "GRAD": 0, "opsz": 24, "wght": 400}

# Bei neuen Icons hier ergaenzen; tests/test_icon_font.py meldet fehlende
CODEPOINTS = [
    0xE002,  # warning
    0xE01F,  # fast_forward
    0xE020,  # fast_rewind
    0xE030,  # library_music
    0xE034,  # pause
    0xE037,  # play_arrow
    0xE04D,  # volume_down
    0xE04F,  # volume_off
    0xE050,  # volume_up
    0xE145,  # add
    0xE150,  # edit
    0xE1BB,  # nfc
    0xE1E0,  # usb
    0xE251,  # image
    0xE254,  # edit
    0xE2C7,  # folder
    0xE3A1,  # music_note
    0xE3C4,  # image
    0xE3C9,  # edit
    0xE3F4,  # image
    0xE405,  # music_note
    0xE5CA,  # check
    0xE5D5,  # refresh
    0xE5D8,  # arrow_upward
    0xE5DB,  # arrow_downward
    0xE668,  # check
    0xE86C,  # check_circle
    0xE872,  # delete
    0xE877,  # done_all
    0xE8A1,  # credit_card
    0xE8B2,  # warning
    0xE8B8,  # settings
    0xE92E,  # delete
    0xF035,  # edit
    0xF083,  # warning
    0xF097,  # edit
    0xFFEDF,  # settings_screen
]


def build(source: Path, output: Path = OUTPUT) -> None:
    """Friert die Achsen ein und schreibt nur die Icons aus CODEPOINTS"""
    font = instancer.instantiateVariableFont(TTFont(source), AXES)
    options = subset.Options()
    options.layout_features = []
    options.name_IDs = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=CODEPOINTS)
    subsetter.subset(font)
    font.save(output)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(Path(sys.argv[1]))
    print(f"{OUTPUT.name}: {OUTPUT.stat().st_size} Bytes, {len(CODEPOINTS)} Icons")
