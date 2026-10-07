"""
RFID-Bereich der Sidebar: Reader-Status, Karten programmieren/loeschen -
entweder ueber einen ACR122U-Leser oder seriell ueber den TonUINO selbst.
"""

from typing import Callable, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QMessageBox, QInputDialog, QComboBox
)
from PyQt6.QtCore import Qt

from core.sd_card import Folder
from core.rfid import RFIDReader, RfidStatus, PLAYBACK_MODES
from core.tonuino_serial import TonuinoSerial, TonuinoSerialError
from gui.common import heading_font, confirm_action, icon_from_glyph, ClickableLabel
from gui.workers import RfidPoller, TonuinoConnectWorker, TonuinoCardWorker

TONUINO_IDLE_HINT = (
    "\n\nHinweis: Der TonUINO muss dafür im Leerlauf (IDLE) oder in Pause sein "
    "- nicht während der Wiedergabe."
)


class RfidPanel(QFrame):
    """Sidebar-Bereich 'RFID-Karte'. Kennt das Hauptfenster nur ueber drei
    Rueckrufe: den ausgewaehlten Ordner, dessen Anzeigenamen und die Statusleiste."""

    # Zwei alternative Wege, eine RFID-Karte zu programmieren - siehe
    # set_reader_mode(): teilen sich denselben Bereich in der Sidebar,
    # umgeschaltet ueber das Menue Einstellungen (RFID-Leser).
    READER_MODE_ACR122U = "acr122u"
    READER_MODE_TONUINO = "tonuino"

    def __init__(
        self,
        get_folder: Callable[[], Optional[Folder]],
        folder_name: Callable[[Folder], str],
        show_status: Callable[[str], None],
        parent=None,
    ):
        super().__init__(parent)
        self._get_folder = get_folder
        self._folder_name = folder_name
        self._show_status = show_status

        self.rfid_reader = RFIDReader()
        self.tonuino_serial = TonuinoSerial()
        self._reader_mode = self.READER_MODE_ACR122U
        self._tonuino_worker: Optional[TonuinoCardWorker] = None
        self._tonuino_connect_worker: Optional[TonuinoConnectWorker] = None
        self._last_rfid_status: Optional[RfidStatus] = None
        self._rfid_card_present = False  # fuer die Freischaltung von "Karte programmieren"
        self._rfid_card_programmed = False  # fuer die Freischaltung des Loeschen-Icons

        self._setup_ui()

        # Regelmaessige Reader-/Kartenpruefung im Hintergrund-Thread
        self._rfid_poller = RfidPoller(self.rfid_reader)
        self._rfid_poller.status_changed.connect(self._apply_rfid_status)
        self._rfid_poller.start()

    # ---------------------------------------------------------------- Zugriff
    @property
    def current_folder(self) -> Optional[Folder]:
        return self._get_folder()

    def _resolve_folder_name(self, folder: Folder) -> str:
        return self._folder_name(folder)

    @staticmethod
    def _is_special_folder(folder: Optional[Folder]) -> bool:
        return folder is not None and folder.is_special

    @property
    def reader_mode(self) -> str:
        return self._reader_mode

    def refresh(self):
        """Aktiviert/deaktiviert die Programmier-Buttons passend zu Karte,
        Verbindung und aktuell ausgewaehltem Ordner (vom Hauptfenster nach
        jedem Ordnerwechsel aufgerufen)"""
        self._update_program_buttons()

    def shutdown(self):
        """Beendet Poller und laufende Programmierung und trennt Reader/TonUINO"""
        self._rfid_poller.stop()
        self._rfid_poller.wait(3000)

        if self._tonuino_worker is not None and self._tonuino_worker.isRunning():
            try:
                self.tonuino_serial.cancel_write()
            except TonuinoSerialError:
                pass
            self._tonuino_worker.wait(3000)
        if self._tonuino_connect_worker is not None and self._tonuino_connect_worker.isRunning():
            self._tonuino_connect_worker.wait(3000)

        self.rfid_reader.disconnect()
        if self.tonuino_serial.is_connected:
            self.tonuino_serial.disconnect()

    # --------------------------------------------------------------------- UI
    def _setup_ui(self):
        self.setObjectName("cardFrame")
        rfid_layout = QVBoxLayout(self)
        rfid_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        rfid_title = QLabel("RFID-Karte")
        rfid_title.setFont(heading_font(10))
        title_row.addWidget(rfid_title)

        title_row.addStretch()

        self.erase_card_icon = ClickableLabel()
        self.erase_card_icon.setFixedSize(24, 24)
        self.erase_card_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.erase_card_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.erase_card_icon.setToolTip("Karten-Daten löschen")
        self.erase_card_icon.clicked.connect(self._erase_rfid_card)
        self._set_erase_icon_state(False)
        title_row.addWidget(self.erase_card_icon)

        rfid_layout.addLayout(title_row)

        self.acr122u_status_widget = QWidget()
        status_row = QHBoxLayout(self.acr122u_status_widget)
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)

        # Einheitliche Icons aus Material Icons (Apache-2.0, gebuendelt) statt
        # der Windows-exklusiven Segoe Fluent Icons - funktioniert plattformneutral
        reader_tile, self.reader_icon = self._create_status_tile("", "Reader")
        status_row.addWidget(reader_tile)

        card_tile, self.card_icon = self._create_status_tile("", "Karte")
        status_row.addWidget(card_tile)

        programmed_tile, self.programmed_icon = self._create_status_tile("", "Ordner")
        status_row.addWidget(programmed_tile)

        rfid_layout.addWidget(self.acr122u_status_widget)

        self.tonuino_status_widget = QWidget()
        tonuino_layout = QVBoxLayout(self.tonuino_status_widget)
        tonuino_layout.setContentsMargins(0, 0, 0, 0)
        tonuino_layout.setSpacing(6)

        tonuino_port_row = QHBoxLayout()
        tonuino_port_row.setSpacing(6)
        self.tonuino_port_combo = QComboBox()
        tonuino_port_row.addWidget(self.tonuino_port_combo, 1)
        btn_tonuino_refresh = QPushButton("Aktualisieren")
        btn_tonuino_refresh.setToolTip("COM-Ports aktualisieren")
        btn_tonuino_refresh.clicked.connect(self._refresh_tonuino_ports)
        tonuino_port_row.addWidget(btn_tonuino_refresh)
        tonuino_layout.addLayout(tonuino_port_row)

        self.btn_tonuino_connect = QPushButton("Verbinden")
        self.btn_tonuino_connect.clicked.connect(self._on_tonuino_connect_clicked)
        tonuino_layout.addWidget(self.btn_tonuino_connect)

        self.tonuino_status_label = QLabel("Nicht verbunden.")
        self.tonuino_status_label.setWordWrap(True)
        tonuino_layout.addWidget(self.tonuino_status_label)

        rfid_layout.addWidget(self.tonuino_status_widget)
        self.tonuino_status_widget.setVisible(False)

        btn_program_card = QPushButton("Karte programmieren")
        btn_program_card.setObjectName("successButton")
        btn_program_card.clicked.connect(self._program_rfid_card)
        btn_program_card.setEnabled(False)
        self.btn_program_card = btn_program_card
        rfid_layout.addWidget(btn_program_card)

        btn_program_admin = QPushButton("Admin-Karte programmieren")
        btn_program_admin.clicked.connect(self._program_admin_card)
        btn_program_admin.setEnabled(False)
        self.btn_program_admin = btn_program_admin
        rfid_layout.addWidget(btn_program_admin)

        btn_tonuino_cancel_write = QPushButton("Programmierung abbrechen")
        btn_tonuino_cancel_write.clicked.connect(self._on_tonuino_cancel_write_clicked)
        btn_tonuino_cancel_write.setVisible(False)
        self.btn_tonuino_cancel_write = btn_tonuino_cancel_write
        rfid_layout.addWidget(btn_tonuino_cancel_write)


    def _create_status_tile(self, icon: str, caption: str) -> tuple:
        """Erstellt eine Status-Kachel: grosses Icon (Farbe je nach Status) + feste Beschriftung.
        Alle Kacheln erhalten dieselbe feste Icon-Boxgroesse, damit sie unabhaengig
        vom jeweiligen Glyph exakt gleich gross und ausgerichtet erscheinen.
        Gibt (Container-Widget, Icon-Label) zurueck."""
        container = QWidget()
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        icon_label = QLabel(icon)
        icon_label.setObjectName("statusIcon")
        icon_label.setProperty("state", "neutral")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(44, 44)
        col.addWidget(icon_label)

        caption_label = QLabel(caption)
        caption_label.setObjectName("statusCaption")
        caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(caption_label)

        return container, icon_label

    def _set_status_icon(self, icon_label: QLabel, state: str):
        """Setzt die Farbe eines Status-Icons (ok/warning/error/neutral)"""
        icon_label.setProperty("state", state)
        icon_label.style().unpolish(icon_label)
        icon_label.style().polish(icon_label)

    def set_reader_mode(self, mode: str):
        """Schaltet zwischen den beiden Programmierwegen um (ACR122U-Leser vs.
        seriell ueber den TonUINO selbst) - ausgewaehlt ueber das Menue Einstellungen
        (RFID-Leser), beide teilen sich denselben Bereich in der Sidebar."""
        self._reader_mode = mode
        is_tonuino = mode == self.READER_MODE_TONUINO
        self._rfid_poller.paused = is_tonuino
        self._last_rfid_status = None  # beim Zurueckwechseln neu anzeigen
        self.acr122u_status_widget.setVisible(not is_tonuino)
        self.tonuino_status_widget.setVisible(is_tonuino)
        if is_tonuino and self.tonuino_port_combo.count() == 0:
            self._refresh_tonuino_ports()
        self._update_program_buttons()

    def _refresh_tonuino_ports(self):
        """Aktualisiert die Liste der verfuegbaren COM-Ports fuer den TonUINO"""
        self.tonuino_port_combo.clear()
        ports = TonuinoSerial.list_ports()
        if not ports:
            self.tonuino_port_combo.addItem("Kein COM-Port gefunden", None)
            self.tonuino_port_combo.setEnabled(False)
            return
        self.tonuino_port_combo.setEnabled(True)
        for p in ports:
            self.tonuino_port_combo.addItem(f"{p.device} - {p.description}", p.device)

    def _on_tonuino_connect_clicked(self):
        """Verbindet sich mit dem per USB angeschlossenen TonUINO bzw. trennt
        eine bestehende Verbindung wieder."""
        if self.tonuino_serial.is_connected:
            self.tonuino_serial.disconnect()
            self.btn_tonuino_connect.setText("Verbinden")
            self.tonuino_status_label.setText("Nicht verbunden.")
            self._update_program_buttons()
            return

        if not TonuinoSerial.serial_available():
            QMessageBox.warning(
                self, "Fehler",
                "Das Paket 'pyserial' ist nicht installiert."
            )
            return

        port = self.tonuino_port_combo.currentData()
        if not port:
            QMessageBox.information(self, "COM-Port wählen", "Bitte wähle einen COM-Port.")
            return

        self.tonuino_status_label.setText("Verbinde...")
        self.btn_tonuino_connect.setEnabled(False)
        self._tonuino_connect_worker = TonuinoConnectWorker(self.tonuino_serial, port)
        self._tonuino_connect_worker.completed.connect(
            lambda ok, message, port=port: self._on_tonuino_connected(ok, message, port)
        )
        self._tonuino_connect_worker.start()

    def _on_tonuino_connected(self, success: bool, message: str, port: str):
        self.btn_tonuino_connect.setEnabled(True)
        if not success:
            self.tonuino_status_label.setText(f"Verbindung fehlgeschlagen: {message}")
            QMessageBox.warning(self, "Fehler", message)
            return

        self.btn_tonuino_connect.setText("Trennen")
        self.tonuino_status_label.setText(f"Verbunden mit {port}.")
        self._update_program_buttons()

    def _update_program_buttons(self):
        """Schaltet die Programmier-Buttons je nach Kartenstatus UND (fuer
        'Karte programmieren' zusaetzlich) ausgewaehltem Ordner frei/aus.
        Die Admin-Karte braucht keinen Ordner, die reguläre Karte schon.
        Fuer den TonUINO-seriell-Weg gibt es keine Kartenpraesenz-Erkennung
        (die Firmware meldet das nicht zurueck) - hier zaehlt nur, ob eine
        Verbindung besteht."""
        if self._reader_mode == self.READER_MODE_TONUINO:
            connected = self.tonuino_serial.is_connected
            self.btn_program_admin.setEnabled(connected)
            # Ordnerunabhaengig: manche WRITECARD-Modi (z.B. "Wiederhole",
            # "Bluetooth an/aus") brauchen keinen Ordner - die Pruefung, ob
            # fuer den gewaehlten Modus ein Ordner noetig ist, passiert erst
            # in _program_rfid_card_via_serial() nach der Modusauswahl.
            self.btn_program_card.setEnabled(connected)
            # Das Loeschen einzelner Karten-Bytes ist ueber die TonUINO-Admin-
            # Menuefuehrung nicht vorgesehen (nur ueber den ACR122U moeglich)
            self._set_erase_icon_state(False)
            return

        self.btn_program_admin.setEnabled(self._rfid_card_present)
        self.btn_program_card.setEnabled(
            self._rfid_card_present
            and self.current_folder is not None
            and not self._is_special_folder(self.current_folder)
        )
        self._set_erase_icon_state(self._rfid_card_present and self._rfid_card_programmed)

    def _update_card_status(self, present: bool):
        """Setzt Karten- und Programmiert-Icon auf den 'keine Karte'-Zustand zurueck"""
        if not present:
            self._set_status_icon(self.card_icon, "neutral")
            self._set_status_icon(self.programmed_icon, "neutral")
            self._rfid_card_present = False
            self._rfid_card_programmed = False
            self._update_program_buttons()

    def _apply_rfid_status(self, status: RfidStatus):
        """Uebernimmt das Ergebnis des RFID-Pollers in die Anzeige"""
        if self._reader_mode != self.READER_MODE_ACR122U:
            return
        if status == self._last_rfid_status:
            return
        self._last_rfid_status = status

        self._set_status_icon(self.reader_icon, status.reader)

        if status.error:
            # Fehler nur in der Statusleiste anzeigen, nicht als Popup
            self._show_status(f"RFID-Fehler: {status.error}")

        if status.card == "ok":
            self._set_status_icon(self.card_icon, "ok")
            self._set_status_icon(self.programmed_icon, "ok" if status.programmed else "warning")
            self._rfid_card_present = True
            self._rfid_card_programmed = status.programmed
            self._update_program_buttons()
        elif status.card == "warning":
            self._set_status_icon(self.card_icon, "warning")
            self._set_status_icon(self.programmed_icon, "neutral")
            self._rfid_card_present = False
            self._rfid_card_programmed = False
            self._update_program_buttons()
        else:
            self._update_card_status(present=False)

    RFID_MODES = PLAYBACK_MODES

    # WRITECARD-Modi fuer den TonUINO-seriell-Weg (siehe core.tonuino_serial) -
    # alle 16 Firmware-Modi ausser Admin, der einen eigenen Button hat.
    TONUINO_MODES = [
        (info.label, info.value)
        for info in TonuinoSerial.WRITECARD_MODES.values()
        if info.value != TonuinoSerial.PMODE_ADMIN_CARD
    ]

    def _run_card_action(self, action, success_status: str, success_text: str,
                         failure_text: str, error_prefix: str):
        """Fuehrt eine ACR122U-Kartenaktion (schreiben/loeschen) aus und meldet
        Erfolg, Misserfolg oder Ausnahme per Statusleiste bzw. Meldungsfenster."""
        try:
            success = action()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"{error_prefix}: {e}")
            return

        if success:
            self._show_status(success_status)
            QMessageBox.information(self, "Erfolg", success_text)
        else:
            QMessageBox.warning(self, "Fehler", failure_text)

    def _program_rfid_card(self):
        """Programmiert eine RFID-Karte"""
        if self._reader_mode == self.READER_MODE_TONUINO:
            self._program_rfid_card_via_serial()
            return

        if not self.current_folder or self._is_special_folder(self.current_folder):
            QMessageBox.warning(
                self,
                "Kein Ordner",
                "Bitte wähle zuerst einen Ordner aus."
            )
            return

        if not self.rfid_reader.is_card_present():
            QMessageBox.information(
                self,
                "Karte legen",
                "Bitte lege eine Karte auf den Reader."
            )
            return

        mode_labels = [label for label, _ in self.RFID_MODES]
        mode_label, ok = QInputDialog.getItem(
            self,
            "Wiedergabemodus",
            f"Modus für Ordner '{self._resolve_folder_name(self.current_folder)}':",
            mode_labels,
            1,  # Standard: Album
            False
        )
        if not ok:
            return

        mode = dict(self.RFID_MODES)[mode_label]
        special = 0

        if mode == 4:  # Einzelner Track
            track_count = max(self.current_folder.track_count, 1)
            special, ok = QInputDialog.getInt(
                self,
                "Track auswählen",
                "Welcher Track soll gespielt werden?",
                1, 1, track_count
            )
            if not ok:
                return

        confirmed = confirm_action(
            self,
            "Karte programmieren",
            f"Soll die Karte für Ordner \'{self._resolve_folder_name(self.current_folder)}\' "
            f"programmiert werden?",
            default_no=False
        )

        if confirmed:
            self._run_card_action(
                lambda: self.rfid_reader.write_tonuino_card(
                    self.current_folder.index, mode=mode, special=special
                ),
                success_status="Karte erfolgreich programmiert!",
                success_text="Die Karte wurde erfolgreich programmiert!",
                failure_text="Die Karte konnte nicht programmiert werden.",
                error_prefix="Fehler beim Programmieren",
            )

    def _program_admin_card(self):
        """Programmiert eine TonUINO-Admin-Karte (keinem Ordner zugeordnet)"""
        if self._reader_mode == self.READER_MODE_TONUINO:
            self._program_admin_card_via_serial()
            return

        if not self.rfid_reader.is_card_present():
            QMessageBox.information(
                self,
                "Karte legen",
                "Bitte lege eine Karte auf den Reader."
            )
            return

        confirmed = confirm_action(
            self,
            "Admin-Karte programmieren",
            "Soll diese Karte als Admin-Karte programmiert werden?\n\n"
            "Eine Admin-Karte ist keinem Ordner zugeordnet und öffnet am "
            "TonUINO das Admin-Menü.",
            default_no=False
        )

        if confirmed:
            self._run_card_action(
                self.rfid_reader.write_admin_card,
                success_status="Admin-Karte erfolgreich programmiert!",
                success_text="Die Admin-Karte wurde erfolgreich programmiert!",
                failure_text="Die Admin-Karte konnte nicht programmiert werden.",
                error_prefix="Fehler beim Programmieren",
            )

    def _program_rfid_card_via_serial(self):
        """TonUINO-seriell-Pendant zu _program_rfid_card(): schreibt eine auf dem
        TonUINO-eigenen Leser aufliegende (bzw. noch aufzulegende) Karte per
        WRITECARD-Befehl (siehe core.tonuino_serial). Anders als beim ACR122U-Weg
        kann keine Kartenpraesenz erkannt werden."""
        if not self.tonuino_serial.is_connected:
            QMessageBox.information(
                self,
                "Nicht verbunden",
                "Bitte zuerst mit dem TonUINO verbinden."
            )
            return

        mode_labels = [label for label, _ in self.TONUINO_MODES]
        mode_label, ok = QInputDialog.getItem(
            self,
            "Wiedergabemodus",
            "Modus:",
            mode_labels,
            1,  # Standard: Album
            False
        )
        if not ok:
            return

        mode = dict(self.TONUINO_MODES)[mode_label]
        info = TonuinoSerial.WRITECARD_MODES[mode]

        folder = None
        special = None
        special2 = None

        if info.group != TonuinoSerial.GROUP_MODE_ONLY:
            if not self.current_folder or self._is_special_folder(self.current_folder):
                QMessageBox.warning(
                    self,
                    "Kein Ordner",
                    "Bitte wähle zuerst einen Ordner aus."
                )
                return
            folder = self.current_folder.index

        if info.group == TonuinoSerial.GROUP_MODE_FOLDER_SPECIAL:
            if mode == TonuinoSerial.PMODE_EINZEL:
                track_count = max(self.current_folder.track_count, 1)
                special, ok = QInputDialog.getInt(
                    self, "Track auswählen", "Welcher Track soll gespielt werden?",
                    1, 1, track_count
                )
            else:  # PMODE_HOERBUCH_1 ("Hörbuch einzel")
                special, ok = QInputDialog.getInt(
                    self, "Track auswählen", "Welcher Track soll gespielt werden?",
                    0, 0, 29
                )
            if not ok:
                return

        elif info.group == TonuinoSerial.GROUP_MODE_FOLDER_SPECIAL_SPECIAL2:
            if mode == TonuinoSerial.PMODE_QUIZ_GAME:
                special_label, ok = QInputDialog.getItem(
                    self, "Quiz Spiel", "Anzahl Antwortmöglichkeiten:",
                    ["0", "2", "4"], 1, False
                )
                if not ok:
                    return
                special2_label, ok = QInputDialog.getItem(
                    self, "Quiz Spiel", "Mit Wiederholung bei falscher Antwort:",
                    ["0", "1"], 0, False
                )
                if not ok:
                    return
                special, special2 = int(special_label), int(special2_label)
            else:  # von-bis-Modi (Hörspiel/Album/Party/Hörbuch von-bis)
                track_count = max(self.current_folder.track_count, 1)
                special, ok = QInputDialog.getInt(
                    self, "Track-Bereich", "Von Track:", 1, 1, track_count
                )
                if not ok:
                    return
                special2, ok = QInputDialog.getInt(
                    self, "Track-Bereich", "Bis Track:", special, special, track_count
                )
                if not ok:
                    return

        if folder is not None:
            confirm_text = (
                f"Lege die Karte auf den TonUINO-eigenen Leser. Soll sie dann für "
                f"Ordner \'{self._resolve_folder_name(self.current_folder)}\' "
                f"programmiert werden?"
                f"{TONUINO_IDLE_HINT}"
            )
        else:
            confirm_text = (
                f"Lege die Karte auf den TonUINO-eigenen Leser. Soll sie dann als "
                f"\'{mode_label}\'-Karte programmiert werden?"
                f"{TONUINO_IDLE_HINT}"
            )

        confirmed = confirm_action(self, "Karte programmieren", confirm_text, default_no=False)
        if not confirmed:
            return

        self._start_tonuino_write(mode, folder, special, special2)

    def _program_admin_card_via_serial(self):
        """TonUINO-seriell-Pendant zu _program_admin_card()"""
        if not self.tonuino_serial.is_connected:
            QMessageBox.information(
                self,
                "Nicht verbunden",
                "Bitte zuerst mit dem TonUINO verbinden."
            )
            return

        confirmed = confirm_action(
            self,
            "Admin-Karte programmieren",
            "Lege die Karte auf den TonUINO-eigenen Leser. Soll sie dann als "
            "Admin-Karte programmiert werden?\n\nEine Admin-Karte ist keinem "
            "Ordner zugeordnet und öffnet am TonUINO das Admin-Menü."
            + TONUINO_IDLE_HINT,
            default_no=False
        )
        if not confirmed:
            return

        self._start_tonuino_write(TonuinoSerial.PMODE_ADMIN_CARD, None, None, None)

    def _start_tonuino_write(self, mode: int, folder: Optional[int],
                              special: Optional[int], special2: Optional[int]):
        """Startet die Karten-Programmierung ueber den seriell verbundenen
        TonUINO in einem Hintergrund-Thread (siehe TonuinoCardWorker) - die
        Firmware wartet ohne eigenes Timeout darauf, dass eine Karte aufgelegt
        wird, daher kann das beliebig lange dauern; per btn_tonuino_cancel_write
        kann der Vorgang abgebrochen werden (WRITECARD CANCEL)."""
        self._tonuino_cancel_requested = False
        self.btn_program_card.setEnabled(False)
        self.btn_program_admin.setEnabled(False)
        self.btn_tonuino_connect.setEnabled(False)
        self.btn_tonuino_cancel_write.setVisible(True)
        self.btn_tonuino_cancel_write.setEnabled(True)
        self.tonuino_status_label.setText(
            "Bitte jetzt eine leere Karte auf den TonUINO-Leser legen "
            "(TonUINO muss im Leerlauf oder in Pause sein) - Programmierung läuft..."
        )

        self._tonuino_worker = TonuinoCardWorker(self.tonuino_serial, mode, folder, special, special2)
        self._tonuino_worker.completed.connect(self._on_tonuino_write_finished)
        self._tonuino_worker.start()

    def _on_tonuino_cancel_write_clicked(self):
        """Bricht eine laufende TonUINO-Kartenprogrammierung ab (WRITECARD CANCEL) -
        das Ergebnis (Fehler-Abschluss) kommt ueber den laufenden TonuinoCardWorker
        und _on_tonuino_write_finished() zurueck, nicht hier."""
        self._tonuino_cancel_requested = True
        self.btn_tonuino_cancel_write.setEnabled(False)
        self.tonuino_status_label.setText("Abbruch angefordert...")
        try:
            self.tonuino_serial.cancel_write()
        except TonuinoSerialError as e:
            QMessageBox.warning(self, "Fehler", f"Abbruch fehlgeschlagen: {e}")

    def _on_tonuino_write_finished(self, success: bool, message: str):
        self.btn_tonuino_connect.setEnabled(True)
        self.btn_tonuino_cancel_write.setVisible(False)
        self._update_program_buttons()
        if success:
            port = self.tonuino_port_combo.currentData()
            self.tonuino_status_label.setText(f"Verbunden mit {port}." if port else "Verbunden.")
            self._show_status(message)
            QMessageBox.information(self, "Erfolg", message)
        else:
            self.tonuino_status_label.setText(f"Fehler: {message}")
            QMessageBox.warning(self, "Fehler", f"Die Karte konnte nicht programmiert werden:\n{message}")

    def _set_erase_icon_state(self, enabled: bool):
        """Faerbt das Loeschen-Icon rot (Karte enthaelt Daten) oder grau
        (nichts zu loeschen) und blockt Klicks im deaktivierten Zustand -
        wie bei einem echten (aber unsichtbaren) Button."""
        color = "#f38ba8" if enabled else "#585b70"
        self.erase_card_icon.setPixmap(icon_from_glyph("", color=color, size=20).pixmap(20, 20))
        self.erase_card_icon.setEnabled(enabled)

    def _erase_rfid_card(self):
        """Loescht die Tonuino-Daten der aufliegenden Karte unwiderruflich -
        die Karte gilt danach wieder als unprogrammiert."""
        if not self.rfid_reader.is_card_present():
            QMessageBox.information(
                self,
                "Karte legen",
                "Bitte lege eine Karte auf den Reader."
            )
            return

        confirmed = confirm_action(
            self,
            "Karten-Daten löschen",
            "Sollen alle Tonuino-Daten auf dieser Karte unwiderruflich gelöscht werden?"
        )

        if confirmed:
            self._run_card_action(
                self.rfid_reader.erase_tonuino_card,
                success_status="Karten-Daten erfolgreich gelöscht!",
                success_text="Die Karten-Daten wurden erfolgreich gelöscht!",
                failure_text="Die Karten-Daten konnten nicht gelöscht werden.",
                error_prefix="Fehler beim Löschen",
            )
