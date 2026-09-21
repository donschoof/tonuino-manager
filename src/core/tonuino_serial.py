"""
Kartenprogrammierung ueber den TonUINO selbst (statt ueber einen externen
RFID-Leser wie den ACR122U).

Voraussetzung: Die TonUINO-Firmware wurde mit aktiviertem
"#define SerialInputAsCommand" gebaut (siehe TonUINO-TNG/src/constants.hpp,
standardmaessig auskommentiert).

Protokoll (siehe TonUINO-TNG/src/serial_input.cpp, state_machine.cpp):
  WRITECARD <mode>[,<folder>[,<special>[,<special2>]]]
schreibt eine auf dem TonUINO-eigenen Leser aufliegende Karte direkt, ohne
Menuefuehrung. Welche der optionalen Parameter mitgesendet werden muessen,
haengt vom Modus ab (siehe WRITECARD_MODES/_GROUP_PARAMS unten) - die
Firmware ruft pro erwartetem Parameter erneut Serial.parseInt() auf; fehlt
ein Parameter am Zeilenende, blockiert das bis zum ~1s-Serial-Timeout des
Arduino, bevor 0 zurueckgegeben wird. Deshalb werden hier immer alle von der
Modus-Gruppe geforderten Parameter explizit mitgesendet.

Die Firmware startet den Schreibvorgang nur, wenn zum Zeitpunkt des Befehls
KEINE Karte auf dem Leser liegt (chip_card.isCardRemoved()) - liegt schon
eine auf, wird der Befehl kommentarlos ignoriert. Bei ungueltigen Parametern
antwortet die Firmware sofort mit einer Zeile "WRITECARD: <Fehlertext>". Bei
gueltigen Parametern wartet sie (ohne eigenes Timeout) darauf, dass eine
Karte aufgelegt wird, schreibt sie und meldet den Abschluss dann zusaetzlich
ueber zwei weitere Zeilen: "WRITECARD: OK" + "WRITECARD: Karte erfolgreich
beschrieben" bei Erfolg, bzw. "WRITECARD: ERROR" + "WRITECARD: Schreiben
fehlgeschlagen" bei Fehler/Abbruch. Ein laufender Schreibvorgang kann per
"WRITECARD CANCEL" abgebrochen werden, was ueber denselben ERROR-Abschluss
gemeldet wird; laeuft kein Schreibvorgang, antwortet die Firmware sofort mit
"WRITECARD: kein Schreibvorgang aktiv, nichts abzubrechen".
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional


class TonuinoSerialError(Exception):
    """Fehler bei der seriellen Kommunikation mit dem TonUINO"""
    pass


@dataclass
class SerialPortInfo:
    device: str
    description: str


# Parameter-Gruppen einer WRITECARD-Modus-Zeile (siehe Modultext oben)
GROUP_MODE_ONLY = "mode"
GROUP_MODE_FOLDER = "mode_folder"
GROUP_MODE_FOLDER_SPECIAL = "mode_folder_special"
GROUP_MODE_FOLDER_SPECIAL_SPECIAL2 = "mode_folder_special_special2"


@dataclass(frozen=True)
class WriteCardMode:
    value: int
    label: str
    group: str


class TonuinoSerial:
    """Steuert einen per USB angeschlossenen TonUINO (SerialInputAsCommand) fern"""

    BAUDRATE = 115200

    # Als Klassenattribute verfuegbar machen, damit Aufrufer (main_window.py)
    # sie ueber TonuinoSerial.GROUP_MODE_* referenzieren koennen.
    GROUP_MODE_ONLY = GROUP_MODE_ONLY
    GROUP_MODE_FOLDER = GROUP_MODE_FOLDER
    GROUP_MODE_FOLDER_SPECIAL = GROUP_MODE_FOLDER_SPECIAL
    GROUP_MODE_FOLDER_SPECIAL_SPECIAL2 = GROUP_MODE_FOLDER_SPECIAL_SPECIAL2

    # pmode_t-Werte aus TonUINO-TNG/src/chip_card.hpp
    PMODE_HOERSPIEL = 1
    PMODE_ALBUM = 2
    PMODE_PARTY = 3
    PMODE_EINZEL = 4
    PMODE_HOERBUCH = 5
    # "Admin" (6) ist nur ein Menue-Auswahlwert: waehlt man ihn im normalen
    # Menuepfad "Neue Karte anlegen" -> Modus, ersetzt die Firmware ihn dort
    # sofort durch PMODE_ADMIN_CARD und setzt folder=0 (state_machine.cpp,
    # ChMode::react()). Der WRITECARD-Serial-Befehl durchlaeuft dieses Menue
    # nicht und macht diese Ersetzung NICHT - fuer echte Admin-Karten muss
    # daher direkt PMODE_ADMIN_CARD gesendet werden, sonst landet der rohe
    # Wert 6 auf der Karte und sie wird nicht als Admin-Karte erkannt.
    PMODE_ADMIN = 6
    PMODE_ADMIN_CARD = 0xFF  # pmode_t::admin_card aus chip_card.hpp
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

    # Single Source of Truth fuer alle 16 WRITECARD-Modi (Label + benoetigte
    # Parameter), siehe TonUINO-TNG/src/constants.hpp fuer die Modustabelle.
    WRITECARD_MODES: Dict[int, WriteCardMode] = {
        PMODE_HOERSPIEL: WriteCardMode(PMODE_HOERSPIEL, "Hörspiel", GROUP_MODE_FOLDER),
        PMODE_ALBUM: WriteCardMode(PMODE_ALBUM, "Album", GROUP_MODE_FOLDER),
        PMODE_PARTY: WriteCardMode(PMODE_PARTY, "Party", GROUP_MODE_FOLDER),
        PMODE_EINZEL: WriteCardMode(PMODE_EINZEL, "Einzel", GROUP_MODE_FOLDER_SPECIAL),
        PMODE_HOERBUCH: WriteCardMode(PMODE_HOERBUCH, "Hörbuch", GROUP_MODE_FOLDER),
        PMODE_ADMIN_CARD: WriteCardMode(PMODE_ADMIN_CARD, "Admin", GROUP_MODE_FOLDER),
        PMODE_HOERSPIEL_VB: WriteCardMode(PMODE_HOERSPIEL_VB, "Hörspiel von-bis", GROUP_MODE_FOLDER_SPECIAL_SPECIAL2),
        PMODE_ALBUM_VB: WriteCardMode(PMODE_ALBUM_VB, "Album von-bis", GROUP_MODE_FOLDER_SPECIAL_SPECIAL2),
        PMODE_PARTY_VB: WriteCardMode(PMODE_PARTY_VB, "Party von-bis", GROUP_MODE_FOLDER_SPECIAL_SPECIAL2),
        PMODE_HOERBUCH_1: WriteCardMode(PMODE_HOERBUCH_1, "Hörbuch einzel", GROUP_MODE_FOLDER_SPECIAL),
        PMODE_REPEAT_LAST: WriteCardMode(PMODE_REPEAT_LAST, "Wiederhole", GROUP_MODE_ONLY),
        PMODE_QUIZ_GAME: WriteCardMode(PMODE_QUIZ_GAME, "Quiz Spiel", GROUP_MODE_FOLDER_SPECIAL_SPECIAL2),
        PMODE_MEMORY_GAME: WriteCardMode(PMODE_MEMORY_GAME, "Memory Spiel", GROUP_MODE_FOLDER),
        PMODE_SWITCH_BT: WriteCardMode(PMODE_SWITCH_BT, "Bluetooth an/aus", GROUP_MODE_ONLY),
        PMODE_TEAPOT_GAME: WriteCardMode(PMODE_TEAPOT_GAME, "Teekesselchen Spiel", GROUP_MODE_FOLDER),
        PMODE_HOERBUCH_VB: WriteCardMode(PMODE_HOERBUCH_VB, "Hörbuch von-bis", GROUP_MODE_FOLDER_SPECIAL_SPECIAL2),
    }

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

    def _read_line(self, deadline: float) -> Optional[str]:
        """Liest Zeilen, bis eine nicht-leere Zeile ankommt oder 'deadline'
        (time.monotonic()) erreicht ist. Der Port-Timeout wird waehrenddessen
        klein gehalten, damit die Deadline zeitnah geprueft werden kann."""
        original_timeout = self._serial.timeout
        self._serial.timeout = 0.3
        try:
            while time.monotonic() < deadline:
                raw = self._serial.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        return line
            return None
        finally:
            self._serial.timeout = original_timeout

    def write_card(
        self,
        mode: int,
        folder: Optional[int] = None,
        special: Optional[int] = None,
        special2: Optional[int] = None,
        timeout: float = 300.0,
    ) -> str:
        """
        Schreibt eine auf dem TonUINO-eigenen Leser aufliegende (bzw. noch
        aufzulegende) Karte per WRITECARD-Befehl.

        mode: einer der PMODE_*-Werte
        folder/special/special2: je nach Modus-Gruppe erforderlich (siehe
            WRITECARD_MODES) - fuer Modi ohne Ordnerbezug ('mode_folder'-
            Gruppe) darf folder=None gelassen werden und wird auf 0
            defaultet (z.B. Admin-Karte). special/special2 werden dagegen
            NIE stillschweigend defaultet, da sie inhaltlich relevant sind
            (z.B. der Track bei 'Einzel').
        timeout: maximale Wartezeit in Sekunden auf die abschliessende
            OK/ERROR-Rueckmeldung (die Firmware selbst hat dabei kein
            eigenes Timeout - sie wartet unbegrenzt, bis eine Karte aufgelegt
            wird; siehe cancel_write() fuer einen aktiven Abbruch).

        Gibt die Erfolgsmeldung der Firmware zurueck, oder wirft
        TonuinoSerialError bei Validierungs-/Schreibfehler bzw. Timeout.
        """
        if not self.is_connected:
            raise TonuinoSerialError("Nicht mit dem TonUINO verbunden")

        info = self.WRITECARD_MODES.get(mode)
        if info is None:
            raise ValueError(f"Unbekannter WRITECARD-Modus: {mode}")

        needs_folder = info.group != GROUP_MODE_ONLY
        needs_special = info.group in (
            GROUP_MODE_FOLDER_SPECIAL,
            GROUP_MODE_FOLDER_SPECIAL_SPECIAL2,
        )
        needs_special2 = info.group == GROUP_MODE_FOLDER_SPECIAL_SPECIAL2

        if needs_folder:
            if folder is None:
                folder = 0
            elif mode != self.PMODE_ADMIN_CARD and not (1 <= folder <= 99):
                raise ValueError("folder muss zwischen 1 und 99 liegen")

        if needs_special and special is None:
            raise ValueError(f"Modus '{info.label}' benoetigt 'special'")
        if needs_special2 and special2 is None:
            raise ValueError(f"Modus '{info.label}' benoetigt 'special2'")

        if mode == self.PMODE_EINZEL and special < 1:
            raise ValueError("Fuer 'Einzel' muss 'special' (Track) mindestens 1 sein")
        elif mode == self.PMODE_HOERBUCH_1 and not (special < 30):
            raise ValueError("Fuer 'Hörbuch einzel' muss 'special' kleiner als 30 sein")
        elif mode in (self.PMODE_HOERSPIEL_VB, self.PMODE_ALBUM_VB,
                      self.PMODE_PARTY_VB, self.PMODE_HOERBUCH_VB):
            if not (1 <= special <= special2):
                raise ValueError("Fuer 'von-bis'-Modi muss 1 <= special <= special2 gelten")
        elif mode == self.PMODE_QUIZ_GAME:
            if special not in (0, 2, 4) or special2 not in (0, 1):
                raise ValueError("Fuer 'Quiz Spiel' muss special in {0,2,4} und special2 in {0,1} liegen")

        parts = [str(mode)]
        if needs_folder:
            parts.append(str(folder))
        if needs_special:
            parts.append(str(special))
        if needs_special2:
            parts.append(str(special2))
        command = "WRITECARD " + ",".join(parts) + "\n"

        try:
            self._serial.write(command.encode("ascii"))
            self._serial.flush()
        except Exception as e:
            raise TonuinoSerialError(f"Senden an TonUINO fehlgeschlagen: {e}") from e

        deadline = time.monotonic() + timeout
        while True:
            line = self._read_line(deadline)
            if line is None:
                raise TonuinoSerialError(
                    "Zeitüberschreitung: keine Rückmeldung vom TonUINO. "
                    "Liegt eventuell schon eine Karte auf dem Leser?"
                )
            if line == "WRITECARD: OK":
                detail = self._read_line(min(deadline, time.monotonic() + 2.0))
                return detail or "Karte erfolgreich beschrieben"
            if line == "WRITECARD: ERROR":
                detail = self._read_line(min(deadline, time.monotonic() + 2.0))
                raise TonuinoSerialError(detail or "Schreiben fehlgeschlagen")
            if line.startswith("WRITECARD: "):
                raise TonuinoSerialError(line[len("WRITECARD: "):])
            # Sonstige Boot-/Debug-Ausgaben der Firmware ignorieren und weiterlesen.

    def cancel_write(self):
        """Bricht einen per write_card() laufenden Schreibvorgang ab. Die
        Rueckmeldung (ERROR-Abschluss bzw. 'kein Schreibvorgang aktiv') wird
        von der Leseschleife des laufenden write_card()-Aufrufs verarbeitet -
        diese Methode liest selbst keine Antwort."""
        if not self.is_connected:
            raise TonuinoSerialError("Nicht mit dem TonUINO verbunden")

        try:
            self._serial.write(b"WRITECARD CANCEL\n")
            self._serial.flush()
        except Exception as e:
            raise TonuinoSerialError(f"Senden an TonUINO fehlgeschlagen: {e}") from e
