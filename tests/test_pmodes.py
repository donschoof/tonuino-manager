from core import pmodes
from core.rfid import PLAYBACK_MODES, RFIDReader
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
