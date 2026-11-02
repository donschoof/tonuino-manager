"""Jedes im Code genutzte Icon muss in der gebuendelten Teilschrift stecken

Ein fehlendes Icon faellt sonst erst in der App als leeres Kaestchen auf.
"""
import re
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "src" / "resources" / "fonts" / "MaterialSymbolsOutlined-subset.ttf"

# Private-Use-Bereiche; Material Symbols nutzt auch den erweiterten ab U+F0000
LITERAL = re.compile("[-\U000f0000-\U0010fffd]")
ESCAPED = re.compile(r"\\u([ef][0-9a-fA-F]{3})|\\U000([ef][0-9a-fA-F]{4})|\\U00(10[0-9a-fA-F]{4})")


def used_icons() -> dict[int, str]:
    """Codepunkt -> erste Fundstelle, als Escape oder woertliches Zeichen"""
    found: dict[int, str] = {}
    for path in [ROOT / "main.py", *sorted((ROOT / "src").rglob("*.py"))]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            codes = [int("".join(m), 16) for m in ESCAPED.findall(line)]
            codes += [ord(m) for m in LITERAL.findall(line)]
            for code in codes:
                found.setdefault(code, f"{path.relative_to(ROOT).as_posix()}:{number}")
    return found


def test_scan_finds_icons():
    assert len(used_icons()) >= 5


def test_all_used_icons_are_in_font():
    available = TTFont(FONT).getBestCmap()
    missing = {f"U+{code:04X}": where for code, where in used_icons().items() if code not in available}
    assert not missing, f"Fehlt in der Icon-Schrift, siehe tools/make_icon_font.py: {missing}"


def test_font_family_matches_code():
    assert TTFont(FONT)["name"].getDebugName(1) == "Material Symbols Outlined"
