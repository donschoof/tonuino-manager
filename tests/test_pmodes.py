from core import pmodes
from core.rfid import PLAYBACK_MODES, RFIDReader, TonuinoCardData, describe_card
from core.tonuino_serial import TonuinoSerial


def test_admin_mode_is_shared_between_both_programming_paths():
    assert RFIDReader.ADMIN_CARD_MODE == pmodes.PMODE_ADMIN_CARD == TonuinoSerial.PMODE_ADMIN_CARD == 0xFF


def test_playback_modes_are_known_writecard_modes():
    for _, value in PLAYBACK_MODES:
        assert value in TonuinoSerial.WRITECARD_MODES


def test_writecard_modes_cover_all_pmodes_except_admin_menu_value():
    names = {n for n in dir(pmodes) if n.startswith("PMODE_")}
    values = {getattr(pmodes, n) for n in names} - {pmodes.PMODE_ADMIN}
    assert values == set(TonuinoSerial.WRITECARD_MODES)


def test_describe_card_empty():
    assert describe_card(None) == ("leer", "Karte ist nicht programmiert")


def test_describe_card_folder_and_mode():
    caption, tooltip = describe_card(TonuinoCardData(folder=3, mode=pmodes.PMODE_ALBUM))
    assert caption == "Ordner 03\nAlbum"
    assert tooltip == "Ordner 03, Modus: Album"


def test_describe_card_admin_and_modes_without_folder():
    assert describe_card(TonuinoCardData(folder=0, mode=pmodes.PMODE_ADMIN_CARD))[0] == "Admin"
    assert describe_card(TonuinoCardData(folder=0, mode=pmodes.PMODE_REPEAT_LAST))[0] == "Wiederhole"


def test_describe_card_shortens_long_mode_names_but_keeps_them_in_tooltip():
    caption, tooltip = describe_card(TonuinoCardData(folder=5, mode=pmodes.PMODE_TEAPOT_GAME))
    assert caption.split("\n")[1].endswith("…") and len(caption.split("\n")[1]) <= 14
    assert "Teekesselchen Spiel" in tooltip


def test_describe_card_unknown_mode():
    assert describe_card(TonuinoCardData(folder=4, mode=99))[0] == "Ordner 04\nModus 99"
