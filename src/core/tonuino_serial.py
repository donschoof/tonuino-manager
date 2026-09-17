"""
Kartenprogrammierung ueber den TonUINO selbst (statt ueber einen externen
RFID-Leser wie den ACR122U).

Voraussetzung: Die TonUINO-Firmware wurde mit aktiviertem
"#define SerialInputAsCommand" gebaut (siehe TonUINO-TNG/src/constants.hpp,
standardmaessig auskommentiert).

Protokoll (siehe TonUINO-TNG/src/serial_input.cpp, commands.cpp,
state_machine.cpp): Die Firmware liest ueber die USB-Serielle Verbindung
Ganzzahlen (Serial.parseInt()):
  - negative Werte simulieren einen Tastendruck (commandRaw), z.B. entspricht
    -4 "allLong" (alle Tasten lange gedrueckt), was aus Idle/Play/Pause das
    Admin-Menue oeffnet.
  - positive Werte sind ein "menu_jump": die Firmware springt in der gerade
    aktiven Menue-Ebene direkt auf die angegebene Zahl und bestaetigt sie
    sofort (menu_jump zaehlt intern auch als "select"-Kommando).

Damit laesst sich der Menuepfad "Admin-Menue -> Neue Karte anlegen -> Modus
-> Ordner -> [Track]" fernsteuern, waehrend eine Karte auf dem TonUINO-eigenen
RFID-Leser liegt - die Karte wird danach genauso geschrieben, wie es die
Firmware auch bei Bedienung per Tasten taete.
"""

import time
from dataclasses import dataclass
from typing import List, Optional


class TonuinoSerialError(Exception):
    """Fehler bei der seriellen Kommunikation mit dem TonUINO"""
    pass


@dataclass
class SerialPortInfo:
    device: str
    description: str


class TonuinoSerial:
    """Steuert einen per USB angeschlossenen TonUINO (SerialInputAsCommand) fern"""

    BAUDRATE = 115200

    # commandRaw-Werte aus TonUINO-TNG/src/serial_input.cpp (SerialInputAsCommand)
    CMD_UPDOWN_LONG = -1
    CMD_DOWN        = -2
    CMD_DOWN_LONG   = -3
    CMD_ALL_LONG    = -4   # -> commandRaw::allLong -> command::admin (Admin-Menue oeffnen)
    CMD_PAUSE       = -5
    CMD_PAUSE_LONG  = -6   # -> command::adm_end (Admin-Menue/Eingabe abbrechen)
    CMD_UP          = -8
    CMD_UP_LONG     = -9

    # Wiedergabemodi wie in chip_card.hpp: pmode_t (identisch zu RFIDReader-Werten)
    MODE_HOERSPIEL = 1
    MODE_ALBUM     = 2
    MODE_PARTY     = 3
    MODE_EINZEL    = 4
    MODE_HOERBUCH  = 5
    MODE_ADMIN     = 6

    def __init__(self):
        self._serial = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and getattr(self._serial, "is_open", False)

    @staticmethod
    def serial_available() -> bool:
        try:
            import serial  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def list_ports() -> List[SerialPortInfo]:
        """Gibt alle verfuegbaren seriellen Schnittstellen zurueck"""
        try:
            from serial.tools import list_ports
        except ImportError:
            return []

        try:
            return [
                SerialPortInfo(p.device, p.description or p.device)
                for p in list_ports.comports()
            ]
        except Exception:
            return []

    def connect(self, port: str, timeout: float = 3.0):
        """Oeffnet die serielle Verbindung zum TonUINO"""
        try:
            import serial
        except ImportError as e:
            raise TonuinoSerialError(
                "Das Paket 'pyserial' ist nicht installiert."
            ) from e

        try:
            self._serial = serial.Serial(port, self.BAUDRATE, timeout=timeout)
            # Beim Oeffnen der seriellen Verbindung fuehrt der Arduino i.d.R.
            # einen Reset durch - kurz warten, bis die Firmware wieder bereit ist.
            time.sleep(2.0)
            self._serial.reset_input_buffer()
        except TonuinoSerialError:
            raise
        except Exception as e:
            self._serial = None
            raise TonuinoSerialError(f"Verbindung zu {port} fehlgeschlagen: {e}") from e

    def disconnect(self):
        """Trennt die serielle Verbindung"""
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def send_raw(self, value: int, delay: float = 0.3):
        """Sendet einen einzelnen commandRaw-/menu_jump-Wert an die Firmware"""
        if not self.is_connected:
            raise TonuinoSerialError("Nicht mit dem TonUINO verbunden")

        try:
            self._serial.write(f"{value}\n".encode("ascii"))
            self._serial.flush()
        except Exception as e:
            raise TonuinoSerialError(f"Senden an TonUINO fehlgeschlagen: {e}") from e

        if delay:
            time.sleep(delay)

    def enter_admin_menu(self, delay: float = 1.0):
        """Simuliert 'alle Tasten lange gedrueckt' und oeffnet damit das Admin-Menue"""
        self.send_raw(self.CMD_ALL_LONG, delay=delay)

    def abort(self, delay: float = 0.5):
        """Bricht das aktuelle Admin-Menue/die aktuelle Eingabe ab"""
        self.send_raw(self.CMD_PAUSE_LONG, delay=delay)

    def menu_jump(self, value: int, delay: float = 0.6):
        """Springt in der aktiven Menue-Ebene direkt zu 'value' und bestaetigt sie
        (siehe VoiceMenu::react()/commandRaw::menu_jump in state_machine.cpp)"""
        if value < 1:
            raise ValueError("value muss >= 1 sein")
        self.send_raw(value, delay=delay)

    def write_folder_card(
        self,
        folder: int,
        mode: int,
        special: int = 0,
        last_folder: Optional[int] = None,
    ):
        """
        Programmiert die aktuell auf dem TonUINO-Leser liegende Karte fuer einen
        Ordner, indem das Admin-Menue 'Neue Karte anlegen' ferngesteuert
        durchlaufen wird (state_machine.cpp: Admin_Entry -> Admin_NewCard ->
        ChMode -> ChFolder -> [ChTrack | ChLastFolder]).

        folder: Ordnernummer 1-99
        mode:   Wiedergabemodus (siehe MODE_*-Konstanten, identisch zu
                RFIDReader.write_tonuino_card())
        special: bei mode=MODE_EINZEL der abzuspielende Track
        last_folder: bei mode=MODE_HOERBUCH der letzte Ordner einer
                     fortlaufenden Kette (Standard: nur dieser eine Ordner)

        Die Firmware schreibt die Karte automatisch, sobald die Menuefuehrung
        abgeschlossen ist und die Karte noch aufliegt, und wartet danach, bis
        die Karte wieder entfernt wird.
        """
        if not (1 <= folder <= 99):
            raise ValueError("folder muss zwischen 1 und 99 liegen")
        if mode not in (self.MODE_HOERSPIEL, self.MODE_ALBUM, self.MODE_PARTY,
                         self.MODE_EINZEL, self.MODE_HOERBUCH):
            raise ValueError(f"Nicht unterstuetzter Modus: {mode}")

        self.enter_admin_menu()
        self.menu_jump(1)          # Admin_Entry: Option 1 = "Neue Karte anlegen"
        self.menu_jump(mode)       # ChMode
        self.menu_jump(folder)     # ChFolder

        if mode == self.MODE_EINZEL:
            if special < 1:
                raise ValueError("Fuer Einzeltrack-Modus wird 'special' (Track) benoetigt")
            self.menu_jump(special)                        # ChTrack
        elif mode == self.MODE_HOERBUCH:
            self.menu_jump(last_folder if last_folder is not None else folder)  # ChLastFolder

    def write_admin_card(self):
        """Programmiert die aufliegende Karte als Admin-Karte (keinem Ordner
        zugeordnet, oeffnet spaeter am TonUINO das Admin-Menue)"""
        self.enter_admin_menu()
        self.menu_jump(1)               # Admin_Entry: "Neue Karte anlegen"
        self.menu_jump(self.MODE_ADMIN)  # ChMode: Modus "admin" -> schreibt sofort
