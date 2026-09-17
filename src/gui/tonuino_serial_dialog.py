"""
Dialog zum Programmieren von RFID-Karten direkt ueber den TonUINO
(statt ueber einen externen Leser wie den ACR122U) via USB-Serial.

Setzt eine TonUINO-Firmware voraus, die mit aktiviertem
"#define SerialInputAsCommand" gebaut wurde (siehe TonUINO-TNG/src/constants.hpp).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QMessageBox, QApplication
)
from PyQt6.QtCore import QThread, pyqtSignal

from core.rfid import PLAYBACK_MODES
from core.tonuino_serial import TonuinoSerial, TonuinoSerialError


# Dieselben Modus-Optionen wie beim ACR122U-Programmierweg (core.rfid.PLAYBACK_MODES) -
# die Modus-Zahlen entsprechen pmode_t und sind identisch zu den TonuinoSerial.MODE_*-Konstanten.
SERIAL_RFID_MODES = PLAYBACK_MODES


class TonuinoWriteWorker(QThread):
    """Fuehrt die Serien serieller Kommandos aus, ohne die UI zu blockieren
    (die Firmware-Menuefuehrung braucht wegen Sprachansagen mehrere Sekunden)."""
    finished = pyqtSignal(bool, str)  # Erfolg, Fehlermeldung (leer bei Erfolg)

    def __init__(self, tonuino: TonuinoSerial, folder: int, mode: int, special: int, admin: bool):
        super().__init__()
        self.tonuino = tonuino
        self.folder = folder
        self.mode = mode
        self.special = special
        self.admin = admin

    def run(self):
        try:
            if self.admin:
                self.tonuino.write_admin_card()
            else:
                self.tonuino.write_folder_card(self.folder, self.mode, self.special)
            self.finished.emit(True, "")
        except (TonuinoSerialError, ValueError) as e:
            self.finished.emit(False, str(e))
        except Exception as e:
            self.finished.emit(False, f"Unerwarteter Fehler: {e}")


class TonuinoSerialDialog(QDialog):
    """Verbindet sich mit einem per USB angeschlossenen TonUINO und
    programmiert die dort aufliegende Karte ferngesteuert ueber das
    Admin-Menue der Firmware."""

    def __init__(self, folder_index: int = None, folder_name: str = "", track_count: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Karte über TonUINO programmieren")
        self.setMinimumWidth(420)

        self.tonuino = TonuinoSerial()
        self.folder_index = folder_index
        self.track_count = max(track_count, 1)
        self._worker: TonuinoWriteWorker = None

        self._setup_ui(folder_name)
        self._refresh_ports()

    def _setup_ui(self, folder_name: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info = QLabel(
            "Verbinde den TonUINO per USB. Voraussetzung: Die Firmware wurde mit "
            "aktiviertem <b>#define SerialInputAsCommand</b> gebaut."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("COM-Port:"))
        self.port_combo = QComboBox()
        port_row.addWidget(self.port_combo, 1)
        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.clicked.connect(self._refresh_ports)
        port_row.addWidget(btn_refresh)
        layout.addLayout(port_row)

        self.btn_connect = QPushButton("Verbinden")
        self.btn_connect.setObjectName("primaryButton")
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.btn_connect)

        self.status_label = QLabel("Nicht verbunden.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Ordner:"))
        self.folder_label = QLabel(
            f"{self.folder_index} ({folder_name})" if self.folder_index else "-"
        )
        folder_row.addWidget(self.folder_label, 1)
        layout.addLayout(folder_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Modus:"))
        self.mode_combo = QComboBox()
        for label, _ in SERIAL_RFID_MODES:
            self.mode_combo.addItem(label)
        self.mode_combo.currentIndexChanged.connect(self._update_track_visibility)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        self.track_row = QHBoxLayout()
        self.track_label = QLabel("Track:")
        self.track_row.addWidget(self.track_label)
        self.track_spin = QSpinBox()
        self.track_spin.setMinimum(1)
        self.track_spin.setMaximum(self.track_count)
        self.track_row.addWidget(self.track_spin, 1)
        layout.addLayout(self.track_row)
        self._update_track_visibility()

        button_row = QHBoxLayout()

        self.btn_write_admin = QPushButton("Admin-Karte programmieren")
        self.btn_write_admin.setEnabled(False)
        self.btn_write_admin.clicked.connect(lambda: self._start_write(admin=True))
        button_row.addWidget(self.btn_write_admin)

        button_row.addStretch()

        self.btn_write = QPushButton("Karte programmieren")
        self.btn_write.setObjectName("successButton")
        self.btn_write.setEnabled(False)
        self.btn_write.clicked.connect(lambda: self._start_write(admin=False))
        button_row.addWidget(self.btn_write)

        layout.addLayout(button_row)

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.reject)
        layout.addWidget(btn_close)

    def _update_track_visibility(self):
        is_einzel = SERIAL_RFID_MODES[self.mode_combo.currentIndex()][1] == TonuinoSerial.MODE_EINZEL
        self.track_label.setVisible(is_einzel)
        self.track_spin.setVisible(is_einzel)

    def _refresh_ports(self):
        self.port_combo.clear()
        ports = TonuinoSerial.list_ports()
        if not ports:
            self.port_combo.addItem("Kein COM-Port gefunden", None)
            self.port_combo.setEnabled(False)
            return
        self.port_combo.setEnabled(True)
        for p in ports:
            self.port_combo.addItem(f"{p.device} - {p.description}", p.device)

    def _on_connect_clicked(self):
        if self.tonuino.is_connected:
            self.tonuino.disconnect()
            self.btn_connect.setText("Verbinden")
            self.btn_write.setEnabled(False)
            self.btn_write_admin.setEnabled(False)
            self.status_label.setText("Nicht verbunden.")
            return

        if not TonuinoSerial.serial_available():
            QMessageBox.warning(
                self, "Fehler",
                "Das Paket 'pyserial' ist nicht installiert."
            )
            return

        port = self.port_combo.currentData()
        if not port:
            QMessageBox.information(self, "COM-Port wählen", "Bitte wähle einen COM-Port.")
            return

        self.status_label.setText("Verbinde...")
        self.setEnabled(False)
        QApplication.processEvents()
        try:
            self.tonuino.connect(port)
        except TonuinoSerialError as e:
            self.setEnabled(True)
            self.status_label.setText(f"Verbindung fehlgeschlagen: {e}")
            QMessageBox.warning(self, "Fehler", str(e))
            return

        self.setEnabled(True)
        self.btn_connect.setText("Trennen")
        self.status_label.setText(f"Verbunden mit {port}.")
        self.btn_write.setEnabled(self.folder_index is not None)
        self.btn_write_admin.setEnabled(True)

    def _start_write(self, admin: bool):
        if not self.tonuino.is_connected:
            return

        mode = SERIAL_RFID_MODES[self.mode_combo.currentIndex()][1]
        special = self.track_spin.value() if mode == TonuinoSerial.MODE_EINZEL else 0

        self._set_busy(True, "Programmiere Karte über TonUINO - bitte warten...")

        self._worker = TonuinoWriteWorker(self.tonuino, self.folder_index or 0, mode, special, admin)
        self._worker.finished.connect(self._on_write_finished)
        self._worker.start()

    def _on_write_finished(self, success: bool, error: str):
        self._set_busy(False)
        if success:
            self.status_label.setText("Karte erfolgreich programmiert!")
            QMessageBox.information(self, "Erfolg", "Die Karte wurde erfolgreich programmiert!")
        else:
            self.status_label.setText(f"Fehler: {error}")
            QMessageBox.warning(self, "Fehler", f"Die Karte konnte nicht programmiert werden:\n{error}")

    def _set_busy(self, busy: bool, message: str = ""):
        if message:
            self.status_label.setText(message)
        self.btn_write.setEnabled(not busy and self.tonuino.is_connected and self.folder_index is not None)
        self.btn_write_admin.setEnabled(not busy and self.tonuino.is_connected)
        self.btn_connect.setEnabled(not busy)
        self.mode_combo.setEnabled(not busy)
        self.track_spin.setEnabled(not busy)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        self.tonuino.disconnect()
        super().closeEvent(event)

    def reject(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self.tonuino.disconnect()
        super().reject()
