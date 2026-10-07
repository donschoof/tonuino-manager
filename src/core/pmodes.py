"""
Wiedergabemodi (pmode_t) der TonUINO-Firmware - einzige Quelle fuer die
Kartenformate beider Programmierwege (ACR122U in rfid.py, seriell in
tonuino_serial.py). Siehe TonUINO-TNG/src/chip_card.hpp.
"""

PMODE_HOERSPIEL = 1
PMODE_ALBUM = 2
PMODE_PARTY = 3
PMODE_EINZEL = 4
PMODE_HOERBUCH = 5
# "Admin" (6) ist nur ein Menue-Auswahlwert der Firmware; auf einer Karte steht
# fuer Admin-Karten PMODE_ADMIN_CARD (die Firmware ersetzt 6 nur im
# Menuepfad, nicht beim WRITECARD-Serial-Befehl).
PMODE_ADMIN = 6
PMODE_ADMIN_CARD = 0xFF
PMODE_HOERSPIEL_VB = 7
PMODE_ALBUM_VB = 8
PMODE_PARTY_VB = 9
PMODE_HOERBUCH_1 = 10
PMODE_REPEAT_LAST = 11
PMODE_QUIZ_GAME = 12
PMODE_MEMORY_GAME = 13
PMODE_SWITCH_BT = 14
PMODE_TEAPOT_GAME = 15
PMODE_HOERBUCH_VB = 16
