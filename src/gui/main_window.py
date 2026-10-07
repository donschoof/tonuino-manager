"""
Hauptfenster des Tonuino-Managers
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QStackedWidget, QFrame, QFileDialog, QMessageBox,
    QStatusBar, QSplitter, QInputDialog,
    QAbstractItemView, QProgressDialog, QApplication,
    QComboBox, QMenuBar, QStyle, QStyleOptionViewItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize, QSettings, QEvent, QPoint, QRect
from PyQt6.QtGui import QCursor, QFont, QPixmap, QIcon, QPainter, QColor, QActionGroup

from core import __version__
from core.sd_card import SDCard, Folder, Track, PurgePreview, MAX_TRACKS_PER_FOLDER
from core.drive_check import get_total_size, is_removable_drive, MAX_SD_CARD_BYTES
from core.audio_converter import AudioConverter
from core.metadata import MetadataManager
from core.rfid import RFIDReader, PLAYBACK_MODES
from core.tonuino_serial import TonuinoSerial, TonuinoSerialError, TonuinoWriteCancelled
from core.updater import UpdateChecker, UpdateDownloader, UpdateInfo, GITHUB_RELEASES_PAGE
from gui.audio_player import AudioPlayerBar, ElidedLabel, TrackInfo
from gui.cover_edit import CoverEditWidget
from gui.update_dialog import UpdateDialog
from gui.title_bar import TitleBar


def resource_path(*parts) -> str:
    """Ermittelt einen Pfad relativ zum src-Verzeichnis - funktioniert sowohl im
    Skript- als auch im PyInstaller-EXE-Modus (siehe auch main.py).
    Im (onefile-)EXE-Modus liegen gebuendelte Daten unter sys._MEIPASS, nicht
    neben der EXE-Datei."""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        src_dir = os.path.join(base_dir, 'src')
    else:
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(src_dir, *parts)


def heading_font(point_size: int) -> QFont:
    """Fette Ueberschriften-Schriftart. 'Segoe UI' wird nur unter Windows
    explizit gesetzt (dort das native Default) - unter macOS/Linux existiert
    diese Schriftart nicht, ein fest codierter Name fuehrt dort zu einer
    Qt-Log-Warnung ("Populating font family aliases... Replace uses of
    missing font family") und einem uneinheitlichen Fallback-Rendering.
    Ohne explizite Familie verwendet Qt dort automatisch die native
    System-Schriftart (San Francisco bzw. die Desktop-Standardschrift)."""
    font = QFont("Segoe UI") if sys.platform == "win32" else QFont()
    font.setPointSize(point_size)
    font.setWeight(QFont.Weight.Bold)
    return font


def confirm_action(parent, title: str, text: str, default_no: bool = True) -> bool:
    """Zeigt einen Ja/Nein-Bestaetigungsdialog mit deutschen Buttons.
    Qt uebersetzt die Standard-Yes/No-Buttons von QMessageBox.question() nicht
    automatisch ins Deutsche (haengt von geladenen Qt-Uebersetzungsdateien ab),
    daher werden hier explizit deutsch beschriftete Buttons verwendet."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    btn_yes = box.addButton("Ja", QMessageBox.ButtonRole.YesRole)
    btn_no = box.addButton("Nein", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(btn_no if default_no else btn_yes)
    box.exec()
    return box.clickedButton() == btn_yes


class ClickableLabel(QLabel):
    """QLabel, das per Klick ein Signal auslöst (fuer das Cover-Bild als In-Place-Button)"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class HoverListWidget(QListWidget):
    """QListWidget, das meldet, ueber welcher Zeile die Maus steht (-1 = keine).
    Dient den Abspielen-Symbolen der Track-Liste, die beim Ueberfahren erscheinen."""
    hovered_row_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._hover_row = -1
        # Position des letzten Mausklicks (Viewport-Koordinaten): itemClicked
        # liefert sie nicht mit, wird aber fuer die Klick-Zone der Symbole gebraucht
        self.last_press_pos = QPoint()

    def _set_hover_row(self, row: int):
        if row != self._hover_row:
            self._hover_row = row
            self.hovered_row_changed.emit(row)

    def mouseMoveEvent(self, event):
        self._set_hover_row(self.indexAt(event.position().toPoint()).row())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self.last_press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self._set_hover_row(-1)
        super().leaveEvent(event)


class SDCardScanner(QThread):
    """Thread fuer das Scannen der SD-Karte"""
    completed = pyqtSignal(bool)
    progress = pyqtSignal(int)
    
    def __init__(self, sd_card: SDCard):
        super().__init__()
        self.sd_card = sd_card
    
    def run(self):
        try:
            self.progress.emit(10)
            # Kurze Pause um Signal zu verarbeiten
            self.msleep(50)
            success = self.sd_card.scan()
            self.progress.emit(100)
            self.completed.emit(success)
        except Exception as e:
            print(f"Scan-Fehler: {e}")
            import traceback
            traceback.print_exc()
            self.completed.emit(False)


class TrackAddWorker(QThread):
    """Thread zum Hinzufuegen (Kopieren/Konvertieren) von Tracks, damit die
    UI waehrend FFmpeg-Konvertierung/Datei-I/O nicht einfriert."""
    progress = pyqtSignal(int, int, str)  # aktueller Index, Gesamtzahl, Dateiname
    track_added = pyqtSignal(object)  # neuer Track
    error = pyqtSignal(str, str)  # Dateiname, Fehlermeldung
    completed = pyqtSignal(int)  # Anzahl erfolgreich hinzugefuegter Tracks

    def __init__(self, folder: Folder, filepaths: list,
                 audio_converter: AudioConverter, metadata_manager: MetadataManager):
        super().__init__()
        self.folder = folder
        self.filepaths = filepaths
        self.audio_converter = audio_converter
        self.metadata_manager = metadata_manager
        self._cancelled = False
        # Bereits belegte Tracknummern werden hier fortlaufend gefuehrt, da die
        # eigentliche Ordnerliste (folder.tracks) erst im GUI-Thread aktualisiert wird
        self._used_numbers = {t.index for t in folder.tracks}

    def cancel(self):
        self._cancelled = True

    def run(self):
        added = 0
        for i, filepath in enumerate(self.filepaths, start=1):
            if self._cancelled:
                break

            self.progress.emit(i, len(self.filepaths), os.path.basename(filepath))

            next_number = 1
            while next_number in self._used_numbers:
                next_number += 1
            if next_number > MAX_TRACKS_PER_FOLDER:
                break

            dest_filename = f"{next_number:03d}.mp3"
            dest_path = Path(self.folder.path) / dest_filename

            try:
                if self.audio_converter.needs_conversion(filepath):
                    if not self.audio_converter.is_available:
                        self.error.emit(os.path.basename(filepath), "FFmpeg ist nicht verfügbar.")
                        continue
                    self.audio_converter.convert_to_mp3(filepath, str(dest_path))
                else:
                    shutil.copy2(filepath, dest_path)

                # Tags stehen jetzt in der Zieldatei (bei Konvertierung von FFmpeg
                # uebernommen, bei MP3 mitkopiert) - dort lesen statt in der Quelle,
                # die ggf. kein MP3 ist und von mutagen.mp3 nicht gelesen werden kann.
                metadata = self.metadata_manager.read_metadata(str(dest_path))
                if metadata.title:
                    self.metadata_manager.write_metadata(str(dest_path), track_number=next_number)

                new_track = Track(
                    index=next_number,
                    filename=dest_filename,
                    filepath=str(dest_path),
                    title=metadata.title
                )
                self._used_numbers.add(next_number)
                self.track_added.emit(new_track)
                added += 1

            except Exception as e:
                self.error.emit(os.path.basename(filepath), str(e))

        self.completed.emit(added)


class PurgeWorker(QThread):
    """Thread fuer das Bereinigen der SD-Karte (Whitelist-Purge), damit die
    UI waehrend der Dateisystem-Operationen nicht einfriert."""
    completed = pyqtSignal(bool, str)  # Erfolg, Fehlermeldung (leer bei Erfolg)

    def __init__(self, sd_card: SDCard):
        super().__init__()
        self.sd_card = sd_card

    def run(self):
        try:
            self.sd_card.purge()
            self.completed.emit(True, "")
        except Exception as e:
            self.completed.emit(False, str(e))


TONUINO_IDLE_HINT = (
    "\n\nHinweis: Der TonUINO muss dafür im Leerlauf (IDLE) oder in Pause sein "
    "- nicht während der Wiedergabe."
)


class TonuinoCardWorker(QThread):
    """Fuehrt eine Karten-Programmierung ueber den seriell verbundenen TonUINO aus
    (WRITECARD-Befehl), damit die UI waehrend der - potenziell langen, da die
    Firmware ohne eigenes Timeout auf das Auflegen der Karte wartet - Antwort
    nicht einfriert."""
    completed = pyqtSignal(bool, str)  # Erfolg, Meldungstext (Firmware-Text bzw. Fehler)

    def __init__(self, tonuino: TonuinoSerial, mode: int,
                 folder: Optional[int] = None, special: Optional[int] = None,
                 special2: Optional[int] = None):
        super().__init__()
        self.tonuino = tonuino
        self.mode = mode
        self.folder = folder
        self.special = special
        self.special2 = special2

    def run(self):
        try:
            message = self.tonuino.write_card(
                self.mode, folder=self.folder, special=self.special, special2=self.special2
            )
            self.completed.emit(True, message)
        except TonuinoWriteCancelled as e:
            self.completed.emit(False, str(e))
        except (TonuinoSerialError, ValueError) as e:
            self.completed.emit(False, str(e))
        except Exception as e:
            self.completed.emit(False, f"Unerwarteter Fehler: {e}")


class MainWindow(QMainWindow):
    """Hauptfenster des Tonuino-Managers"""

    # Zwei alternative Wege, eine RFID-Karte zu programmieren - siehe
    # _set_reader_mode(): teilen sich denselben Bereich in der Sidebar,
    # umgeschaltet ueber das Menue Einstellungen (RFID-Leser).
    READER_MODE_ACR122U = "acr122u"
    READER_MODE_TONUINO = "tonuino"

    # Kantenlaenge (px) des Ordner-Covers im Kopfbereich
    FOLDER_COVER_SIZE = 170

    # Breite des Fensterrands (px), an dem unter Windows die Groesse geaendert wird
    RESIZE_BORDER = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tonuino-Manager")
        icon_path = resource_path("resources", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        # Unter Windows ersetzt eine eigene Titelleiste (mit Menue) die native
        # - siehe gui/title_bar.py. Auf macOS/Linux bleibt die normale Menueleiste.
        self._title_bar = None
        self._multi_select_mode = False
        self._hover_row = -1
        self._row_icons = {}
        if sys.platform == "win32":
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(1200, 800)

        self.sd_card: SDCard = None
        self.audio_converter = AudioConverter()
        self.metadata_manager = MetadataManager()
        self.rfid_reader = RFIDReader()
        self.tonuino_serial = TonuinoSerial()
        self._reader_mode = self.READER_MODE_ACR122U
        self._tonuino_worker: TonuinoCardWorker = None
        self.scanner: SDCardScanner = None
        self._add_tracks_worker: TrackAddWorker = None
        self._purge_worker: PurgeWorker = None
        self._update_checker: UpdateChecker = None
        self._update_downloader: UpdateDownloader = None
        self.current_folder: Folder = None
        self._folder_name_cache = {}  # folder_index -> aus Album-Tag ermittelter Name
        self._rfid_card_present = False  # fuer die Freischaltung von "Karte programmieren"
        self._rfid_card_programmed = False  # fuer die Freischaltung des Loeschen-Icons

        self._setup_ui()
        self._setup_statusbar()
        self._check_dependencies()
        
        # RFID-Timer fuer regelmaessige Kartenpruefung
        self.rfid_timer = QTimer()
        self.rfid_timer.timeout.connect(self._check_rfid_card)
        self.rfid_timer.start(500)

        # SD-Karten-Timer: erkennt, wenn die geoeffnete SD-Karte (z.B. per
        # USB/Kartenleser) waehrend der Nutzung entfernt wird, und setzt die
        # UI dann sauber zurueck statt bei jedem weiteren Zugriff auf die
        # verschwundenen Pfade Dateisystem-Fehler ins Log zu schreiben.
        self.sd_card_timer = QTimer()
        self.sd_card_timer.timeout.connect(self._check_sd_card_presence)
        self.sd_card_timer.start(1000)

        # Automatische RFID-Reader-Verbindung beim Start
        QTimer.singleShot(500, self._auto_connect_rfid)

        # Update-Pruefung beim Start (versetzt, damit sie nicht mit der
        # RFID-Verbindung um Systemressourcen konkurriert)
        QTimer.singleShot(1500, self._check_for_updates)

    def _auto_connect_rfid(self):
        """Verbindet automatisch mit dem ersten verfuegbaren RFID-Reader"""
        if not self.rfid_reader.scard_available:
            self._set_status_icon(self.reader_icon, "error")
            return

        readers = self.rfid_reader.get_readers()
        if not readers:
            self._set_status_icon(self.reader_icon, "neutral")
            return

        # Ersten Reader automatisch verbinden
        if self.rfid_reader.connect(0):
            self._set_status_icon(self.reader_icon, "ok")
            self._update_card_status(present=False)
        else:
            self._set_status_icon(self.reader_icon, "error")
    
    def _setup_ui(self):
        """Erstellt die Benutzeroberflaeche"""
        if sys.platform == "win32":
            self._title_bar = TitleBar(self, resource_path("resources", "icon.png"))
            self.setMenuWidget(self._title_bar)
            menu_bar = self._title_bar.menu_bar
        else:
            menu_bar = self.menuBar()
        self._create_menu_bar(menu_bar)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = self._create_sidebar()
        splitter.addWidget(sidebar)
        
        main_content = self._create_main_content()
        splitter.addWidget(main_content)
        
        splitter.setSizes([300, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)

    def nativeEvent(self, event_type, message):
        """Unter Windows: Hit-Test fuer das rahmenlose Fenster. Windows
        uebernimmt damit Verschieben, Groesse aendern und Einrasten selbst."""
        if sys.platform == "win32" and self._title_bar is not None and bytes(event_type) == b"windows_generic_MSG":
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                pos = self.mapFromGlobal(QCursor.pos())
                result = self._hit_test(pos)
                if result is not None:
                    return True, result
        # Bewusst kein super().nativeEvent(): der Aufruf stuerzt mit PyQt6 ab
        return False, 0

    def _hit_test(self, pos: QPoint):
        """Liefert den WM_NCHITTEST-Rueckgabewert fuer pos (Fensterkoordinaten)
        oder None, wenn das Fenster normal (HTCLIENT) reagieren soll."""
        HTCAPTION = 2
        HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
        HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

        if not self.isMaximized():
            b = self.RESIZE_BORDER
            left, right = pos.x() < b, pos.x() >= self.width() - b
            top, bottom = pos.y() < b, pos.y() >= self.height() - b
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM

        if self._title_bar.is_draggable_at(pos):
            return HTCAPTION
        return None

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self._title_bar is not None:
            self._title_bar.update_maximize_button()
        super().changeEvent(event)

    def _create_menu_bar(self, menu_bar: QMenuBar):
        """Erstellt das Menue Einstellungen in der Menueleiste des Fensters
        (Updates, RFID-Leser)."""
        menu = menu_bar.addMenu("Einstellungen")

        action_check_now = menu.addAction("Nach Updates suchen")
        action_check_now.triggered.connect(self._check_for_updates_manual)

        menu.addSeparator()

        auto_check_enabled = QSettings().value("updater/auto_check_enabled", True, type=bool)
        action_auto_check = menu.addAction("Automatisch nach Updates suchen")
        action_auto_check.setCheckable(True)
        action_auto_check.setChecked(auto_check_enabled)
        action_auto_check.toggled.connect(self._on_auto_check_toggled)

        menu.addSeparator()

        reader_menu = menu.addMenu("RFID-Leser")
        reader_group = QActionGroup(self)
        reader_group.setExclusive(True)

        action_reader_acr122u = reader_menu.addAction("ACR122U")
        action_reader_acr122u.setCheckable(True)
        action_reader_acr122u.setChecked(True)  # Default
        action_reader_acr122u.triggered.connect(
            lambda: self._set_reader_mode(self.READER_MODE_ACR122U)
        )
        reader_group.addAction(action_reader_acr122u)

        action_reader_tonuino = reader_menu.addAction("TonUINO (seriell)")
        action_reader_tonuino.setCheckable(True)
        action_reader_tonuino.triggered.connect(
            lambda: self._set_reader_mode(self.READER_MODE_TONUINO)
        )
        reader_group.addAction(action_reader_tonuino)

    def _create_sidebar(self) -> QFrame:
        """Erstellt die Sidebar"""
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        logo_path = resource_path("resources", "icon.png")
        logo_label = QLabel()
        logo_pixmap = QPixmap(logo_path)
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
        logo_label.setMinimumHeight(60)
        title_row.addWidget(logo_label)

        title = QLabel("Tonuino-Manager")
        title.setObjectName("sidebarTitle")
        title.setFont(heading_font(14))

        version_label = QLabel(f"Version {__version__}")
        # padding-left entspricht dem Padding von #sidebarTitle, damit beide bündig sind
        version_label.setStyleSheet("color: #6c7086; font-size: 10px; padding-left: 15px;")

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        # Block wird neben dem Logo zentriert, sonst verteilt das Layout
        # die ueberschuessige Hoehe zwischen Titel und Version
        title.setStyleSheet("padding-top: 0px; padding-bottom: 0px;")
        title.setFixedHeight(title.sizeHint().height() - 2)
        version_label.setStyleSheet(
            "color: #6c7086; font-size: 10px; padding-left: 15px; padding-top: 0px;"
        )
        title_col.addWidget(title)
        title_col.addWidget(version_label)
        title_row.addLayout(title_col, 1)
        title_row.setAlignment(title_col, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(title_row)
        
        btn_open_sd = QPushButton("SD-Karte öffnen")
        btn_open_sd.setObjectName("primaryButton")
        btn_open_sd.clicked.connect(self._open_sd_card)
        layout.addWidget(btn_open_sd)
        
        btn_new_folder = QPushButton("Neuer Ordner")
        btn_new_folder.clicked.connect(self._create_new_folder)
        btn_new_folder.setEnabled(False)
        self.btn_new_folder = btn_new_folder
        layout.addWidget(btn_new_folder)

        btn_purge_card = QPushButton("SD-Karte bereinigen")
        btn_purge_card.setObjectName("dangerButton")
        btn_purge_card.clicked.connect(self._purge_sd_card)
        btn_purge_card.setEnabled(False)
        self.btn_purge_card = btn_purge_card
        layout.addWidget(btn_purge_card)

        layout.addWidget(QLabel("Ordner:"))
        self.folder_list = QListWidget()
        self.folder_list.setObjectName("folderList")
        self.folder_list.itemClicked.connect(self._on_folder_selected)
        layout.addWidget(self.folder_list)
        
        rfid_frame = QFrame()
        rfid_frame.setObjectName("cardFrame")
        rfid_layout = QVBoxLayout(rfid_frame)
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

        layout.addWidget(rfid_frame)

        return sidebar

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

    def _icon_from_glyph(self, glyph: str, color: str = "#1e1e2e", size: int = 16) -> QIcon:
        """Rendert ein Glyph aus der gebuendelten Material-Icons-Schriftart als
        QIcon, damit es (anders als reiner Text) mit setIcon() auf Buttons
        benutzt werden kann, ohne die restliche Button-Schrift zu beeinflussen.
        Material Icons (Apache-2.0) statt der Windows-exklusiven Segoe Fluent
        Icons, damit die App auch unter macOS/Linux funktioniert."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        font = QFont("Material Icons")
        font.setPointSize(int(size * 0.65))
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        painter.end()

        return QIcon(pixmap)

    def _create_main_content(self) -> QWidget:
        """Erstellt den Hauptbereich"""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(16)

        self.welcome_widget = QWidget()
        welcome_layout = QVBoxLayout(self.welcome_widget)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        welcome_label = QLabel("Willkommen beim Tonuino-Manager!")
        welcome_label.setFont(heading_font(18))
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_label)
        
        self.welcome_info_label = QLabel()
        self.welcome_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_info_label.setWordWrap(True)
        welcome_layout.addWidget(self.welcome_info_label)
        self._update_welcome_text()
        
        self.folder_widget = QWidget()
        folder_layout = QVBoxLayout(self.folder_widget)
        folder_layout.setContentsMargins(9, 0, 9, 9)  # oben kein zusaetzlicher Abstand

        # Player ganz oben: Karte in voller Breite, Inhalt zentriert (siehe AudioPlayerBar)
        self.player_bar = AudioPlayerBar()
        self.player_bar.track_info_provider = self._player_track_info
        self.player_bar.prev_clicked.connect(self._play_previous_track)
        self.player_bar.next_clicked.connect(self._play_next_track)
        self.player_bar.playback_changed.connect(self._refresh_track_row_icons)
        self.player_bar.playback_changed.connect(self._update_player_navigation)
        self.player_bar.play_requested.connect(self._play_selected_track)

        folder_layout.addWidget(self.player_bar)

        # Kopfbereich wie in Apple Music: grosses Cover links, rechts Name, Ordner-
        # nummer und Infozeile, darunter (unten buendig mit dem Cover) die Aktionen.
        # Feste Hoehe (= Cover), damit die Stretches im Textblock das Layout nicht
        # vertikal aufblaehen.
        folder_header = QWidget()
        folder_header.setFixedHeight(self.FOLDER_COVER_SIZE)
        header_layout = QHBoxLayout(folder_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(24)

        self.cover_label = CoverEditWidget(self.FOLDER_COVER_SIZE)
        self.cover_label.clicked.connect(self._set_folder_cover)
        header_layout.addWidget(self.cover_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.addStretch(1)

        self.folder_title = ElidedLabel("Ordner")
        self.folder_title.setObjectName("folderTitle")
        self.folder_title.setFixedHeight(40)
        info_col.addWidget(self.folder_title)

        self.folder_subtitle = QLabel()
        self.folder_subtitle.setObjectName("folderSubtitle")
        info_col.addWidget(self.folder_subtitle)

        self.folder_meta = QLabel()
        self.folder_meta.setObjectName("folderMeta")
        info_col.addWidget(self.folder_meta)

        info_col.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        btn_add_tracks = QPushButton(" Tracks hinzufügen")
        btn_add_tracks.setObjectName("primaryButton")
        btn_add_tracks.setIcon(self._icon_from_glyph("\ue145", color="#1e1e2e"))  # Add
        btn_add_tracks.setFixedHeight(38)
        btn_add_tracks.setMinimumWidth(170)
        btn_add_tracks.clicked.connect(self._add_tracks)
        self.btn_add_tracks = btn_add_tracks
        actions.addWidget(btn_add_tracks)

        btn_delete_folder = QPushButton(" Ordner löschen")
        btn_delete_folder.setObjectName("dangerButton")
        btn_delete_folder.setIcon(self._icon_from_glyph("\ue872", color="#1e1e2e"))  # Delete
        btn_delete_folder.setFixedHeight(38)
        btn_delete_folder.setMinimumWidth(170)
        btn_delete_folder.clicked.connect(self._delete_folder)
        self.btn_delete_folder = btn_delete_folder
        actions.addWidget(btn_delete_folder)

        actions.addStretch(1)
        info_col.addLayout(actions)

        header_layout.addLayout(info_col, 1)
        folder_layout.addWidget(folder_header)

        track_header_layout = QHBoxLayout()
        track_header_layout.addWidget(QLabel("Tracks:"))
        track_header_layout.addStretch()

        self.btn_multi_select = QPushButton(" Auswählen")
        self.btn_multi_select.setIcon(self._icon_from_glyph("\ue877", color="#cdd6f4"))  # Done all
        self.btn_multi_select.setCheckable(True)
        self.btn_multi_select.setToolTip("Mehrfachauswahl ein-/ausschalten")
        self.btn_multi_select.setEnabled(False)
        self.btn_multi_select.toggled.connect(self._set_multi_select_mode)
        track_header_layout.addWidget(self.btn_multi_select)

        self.btn_move_track_up = QPushButton()
        self.btn_move_track_up.setIcon(self._icon_from_glyph("", color="#cdd6f4"))  # Up
        self.btn_move_track_up.setToolTip("Track nach oben verschieben")
        self.btn_move_track_up.setEnabled(False)
        self.btn_move_track_up.clicked.connect(lambda: self._move_selected_tracks(-1))
        track_header_layout.addWidget(self.btn_move_track_up)

        self.btn_move_track_down = QPushButton()
        self.btn_move_track_down.setIcon(self._icon_from_glyph("", color="#cdd6f4"))  # Down
        self.btn_move_track_down.setToolTip("Track nach unten verschieben")
        self.btn_move_track_down.setEnabled(False)
        self.btn_move_track_down.clicked.connect(lambda: self._move_selected_tracks(1))
        track_header_layout.addWidget(self.btn_move_track_down)

        self.btn_delete_tracks = QPushButton(" Track löschen")
        self.btn_delete_tracks.setObjectName("dangerButton")
        self.btn_delete_tracks.setIcon(self._icon_from_glyph("", color="#1e1e2e"))  # Delete
        self.btn_delete_tracks.setEnabled(False)
        self.btn_delete_tracks.clicked.connect(self._delete_selected_tracks)
        track_header_layout.addWidget(self.btn_delete_tracks)

        folder_layout.addLayout(track_header_layout)

        self.track_list = HoverListWidget()
        self.track_list.setIconSize(QSize(18, 18))
        self.track_list.hovered_row_changed.connect(self._on_track_hover_changed)
        self.track_list.itemDoubleClicked.connect(self._on_track_double_clicked)
        self.track_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.track_list.currentItemChanged.connect(self._on_track_current_changed)
        self.track_list.itemClicked.connect(self._on_track_clicked)
        folder_layout.addWidget(self.track_list)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.welcome_widget)
        self.stack.addWidget(self.folder_widget)
        
        layout.addWidget(self.stack)
        
        return content
    
    def _setup_statusbar(self):
        """Erstellt die Statusleiste"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Bereit")
    
    def _check_dependencies(self):
        """Prueft verfuegbare Abhaengigkeiten"""
        missing = []
        if not self.audio_converter.is_available:
            missing.append("FFmpeg nicht gefunden - Konvertierung nicht möglich")
        if not self.rfid_reader.scard_available:
            missing.append("pyscard nicht installiert - RFID nicht verfügbar")
        if missing:
            self.status_bar.showMessage(" | ".join(missing))

    def _open_sd_card(self):
        """Oeffnet eine SD-Karte"""
        path = QFileDialog.getExistingDirectory(
            self,
            "SD-Karte auswählen",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not path:
            return
        
        self.sd_card = SDCard(path)
        self._folder_name_cache.clear()

        self.status_bar.showMessage("Scanne SD-Karte...")

        self._open_sd_dialog = QProgressDialog(
            "SD-Karte wird gescannt...", "", 0, 100, self
        )
        self._open_sd_dialog.setWindowTitle("SD-Karte öffnen")
        self._open_sd_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._open_sd_dialog.setMinimumDuration(0)
        self._open_sd_dialog.setCancelButton(None)
        self._open_sd_dialog.setValue(0)

        self.scanner = SDCardScanner(self.sd_card)
        self.scanner.progress.connect(self._open_sd_dialog.setValue)
        self.scanner.completed.connect(self._on_scan_finished)
        self.scanner.start()

    def _on_scan_finished(self, success: bool):
        """Wird aufgerufen wenn der Scan abgeschlossen ist"""
        self._open_sd_dialog.close()

        if success:
            self.status_bar.showMessage(
                f"SD-Karte geladen: {self.sd_card.folder_count} Ordner, "
                f"{self.sd_card.total_tracks} Tracks"
            )
            self.btn_new_folder.setEnabled(True)
            self.btn_purge_card.setEnabled(True)
            self._populate_folder_list()
        else:
            self.status_bar.showMessage("Fehler beim Scannen der SD-Karte")
            QMessageBox.warning(
                self,
                "Fehler",
                "Die SD-Karte konnte nicht gelesen werden."
            )

    def _check_sd_card_presence(self):
        """Prueft periodisch, ob die geoeffnete SD-Karte noch vorhanden ist
        (z.B. per USB/Kartenleser entfernt wurde)"""
        if not self.sd_card:
            return

        try:
            still_present = self.sd_card.path.exists()
        except OSError:
            still_present = False

        if not still_present:
            self._handle_sd_card_removed()

    def _handle_sd_card_removed(self):
        """Setzt die UI zurueck, nachdem die geoeffnete SD-Karte verschwunden
        ist - verhindert, dass weitere Aktionen auf die nicht mehr
        vorhandenen Pfade zugreifen und dabei Dateisystem-Fehler ins Log
        schreiben."""
        if self._add_tracks_worker is not None and self._add_tracks_worker.isRunning():
            self._add_tracks_worker.cancel()

        self.sd_card = None
        self.current_folder = None
        self._folder_name_cache.clear()

        self.folder_list.clear()
        self._update_welcome_text()
        self.player_bar.stop_and_clear()
        self.stack.setCurrentWidget(self.welcome_widget)
        self.btn_new_folder.setEnabled(False)
        self.btn_purge_card.setEnabled(False)
        self._update_program_buttons()
        self._update_folder_action_buttons()

        self.status_bar.showMessage("SD-Karte wurde entfernt")
        QMessageBox.warning(
            self,
            "SD-Karte entfernt",
            "Die SD-Karte ist nicht mehr verfügbar - wurde sie entfernt?\n\n"
            "Bitte öffne sie erneut, sobald sie wieder verbunden ist."
        )

    def _update_welcome_text(self):
        """Zeigt die Aufforderung zum Oeffnen nur, solange keine SD-Karte
        geoeffnet ist; danach den Hinweis, einen Ordner zu waehlen"""
        if getattr(self, "sd_card", None):
            self.welcome_info_label.setText("Wähle links einen Ordner aus.")
            return
        self.welcome_info_label.setText(
            "Öffne eine SD-Karte, um zu beginnen.\n\n"
            "- Verwalte deine Tonuino-Ordner\n"
            "- Füge Musik hinzu mit automatischer Konvertierung\n"
            "- Bearbeite Metadaten und Cover\n"
            "- Programmiere RFID-Karten direkt"
        )

    def _populate_folder_list(self):
        """Fuellt die Ordner-Liste mit Ordnernummer-Badge und ermitteltem Namen,
        gefolgt von den (nicht editierbaren) Tonuio-Systemordnern mp3/advert"""
        self.folder_list.clear()
        self._update_welcome_text()

        if not self.sd_card:
            return

        for idx in sorted(self.sd_card.folders.keys()):
            folder = self.sd_card.folders[idx]
            name = self._resolve_folder_name(folder)

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setSizeHint(QSize(0, 36))
            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, self._create_folder_item_widget(folder, name))

        for special_name in SDCard.SPECIAL_FOLDER_NAMES:
            folder = self.sd_card.special_folders.get(special_name)
            if not folder:
                continue

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, special_name)
            item.setSizeHint(QSize(0, 36))
            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, self._create_folder_item_widget(folder, folder.name))

    def _is_special_folder(self, folder: Optional[Folder]) -> bool:
        """True, wenn folder einer der nicht editierbaren Tonuio-Systemordner
        (mp3/advert) ist"""
        return folder is not None and folder.is_special

    def _resolve_folder_name(self, folder: Folder) -> str:
        """Ermittelt den Anzeigenamen eines Ordners aus dem Album-Tag der ersten
        Track-Datei (der Reihe nach), die einen hat. Fallback: 'Ordner NN'."""
        if folder.index in self._folder_name_cache:
            return self._folder_name_cache[folder.index]

        name = f"Ordner {folder.index:02d}"
        for track in sorted(folder.tracks, key=lambda t: t.index):
            metadata = self.metadata_manager.read_metadata(track.filepath)
            if metadata.album:
                name = metadata.album
                break

        self._folder_name_cache[folder.index] = name
        return name

    def _create_folder_item_widget(self, folder: Folder, name: str) -> QWidget:
        """Erstellt das Zeilen-Widget fuer die Ordnerliste: Nummer-/Namens-Badge + Name.
        Systemordner (mp3/advert) werden in einem gedimmten, nicht editierbaren Stil dargestellt."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(10)

        badge = QLabel(folder.name if folder.is_special else f"{folder.index:02d}")
        badge.setObjectName("folderBadgeSpecial" if folder.is_special else "folderBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumSize(34, 24)
        row.addWidget(badge)

        name_label = QLabel(name)
        name_label.setObjectName("folderNameLabelSpecial" if folder.is_special else "folderNameLabel")
        row.addWidget(name_label, 1)

        return widget

    def _on_folder_selected(self, item: QListWidgetItem):
        """Wird aufgerufen wenn ein Ordner ausgewaehlt wird"""
        identity = item.data(Qt.ItemDataRole.UserRole)
        self.current_folder = self.sd_card.get_any_folder(identity)

        # Ein anderer Ordner startet immer wieder im Einzelauswahl-Modus
        self._set_multi_select_mode(False)
        if self.current_folder:
            self._show_folder(self.current_folder)

        self._update_program_buttons()

    def _select_folder_in_list(self, folder_index: int):
        """Waehlt einen Ordner in der Sidebar-Liste aus und zeigt ihn im Hauptbereich an
        (z.B. direkt nach dem Anlegen eines neuen Ordners)"""
        for row in range(self.folder_list.count()):
            item = self.folder_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == folder_index:
                self.folder_list.setCurrentItem(item)
                self._on_folder_selected(item)
                return

    def _get_folder_cover_pixmap(self, folder: Folder) -> Optional[QPixmap]:
        """Ermittelt das Cover eines Ordners: zuerst aus den ID3-Metadaten des ersten
        Tracks (der Reihe nach) mit eingebettetem Cover, sonst Fallback auf eine
        Cover-Datei im Ordner (Altbestand, z.B. cover.jpg von frueheren Versionen)."""
        for track in sorted(folder.tracks, key=lambda t: t.index):
            cover_bytes = self.metadata_manager.get_cover_bytes(track.filepath)
            if cover_bytes:
                pixmap = QPixmap()
                if pixmap.loadFromData(cover_bytes):
                    return pixmap

        if folder.cover_path:
            pixmap = QPixmap(folder.cover_path)
            if not pixmap.isNull():
                return pixmap

        return None

    def _show_folder(self, folder: Folder):
        """Zeigt einen Ordner an"""
        self.stack.setCurrentWidget(self.folder_widget)

        self.folder_title.setText(folder.name if folder.is_special else self._resolve_folder_name(folder))
        subtitle = "Tonuino-Systemordner" if folder.is_special else f"Ordner {folder.index:02d}"
        self.folder_subtitle.setText(subtitle)
        # Hat der Ordner keinen eigenen Namen (aus den Tags), waere der Untertitel
        # nur eine Wiederholung des Titels
        self.folder_subtitle.setVisible(self.folder_title.text() != subtitle)
        # Der Pfad steht nicht mehr als Zeile da, bleibt aber als Tooltip erreichbar
        for widget in (self.folder_title, self.folder_subtitle, self.folder_meta):
            widget.setToolTip(f"Pfad: {folder.path}")

        self.cover_label.set_cover(self._get_folder_cover_pixmap(folder))

        self._populate_track_list(folder)
        self._update_folder_action_buttons()

    def _update_folder_action_buttons(self):
        """Schaltet die ordnerbezogenen Bearbeiten-Aktionen frei/aus - Tonuio-
        Systemordner (mp3/advert) sind nur einseh- und abspielbar, aber nicht editierbar."""
        editable = self.current_folder is not None and not self._is_special_folder(self.current_folder)
        self.btn_add_tracks.setEnabled(editable)
        self.btn_delete_folder.setEnabled(editable)
        self.cover_label.setEnabled(editable)

    def _populate_track_list(self, folder: Folder):
        """Baut die Track-Liste eines Ordners neu auf (liest Metadaten je Track).
        Im Mehrfachauswahl-Modus zeigt jeder Track einen Auswahlkreis (Haken);
        sonst gilt die normale Einzelauswahl der Liste."""
        # Player stoppen: die zugrunde liegenden Dateipfade koennen sich durch
        # Hinzufuegen/Loeschen/Umsortieren aendern (Umbenennung auf fortlaufende
        # Nummern), der aktuell geladene Pfad waere dann ungueltig
        self.player_bar.stop_and_clear()

        self.track_list.blockSignals(True)
        self.track_list.clear()
        for track in folder.tracks:
            metadata = self.metadata_manager.read_metadata(track.filepath)
            track.title = metadata.title
            track.artist = metadata.artist
            track.album = metadata.album

            item = QListWidgetItem(track.display_name)
            item.setData(Qt.ItemDataRole.UserRole, track)
            # ItemIsUserCheckable ist standardmaessig gesetzt und wuerde den Kreis
            # selbst umschalten - dann wuerde _on_track_clicked ihn gleich wieder
            # zuruecksetzen. Das Umschalten uebernimmt deshalb allein
            # _on_track_clicked, fuer die ganze Zeile inklusive Kreis.
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            if self._multi_select_mode:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.track_list.addItem(item)
        self.track_list.blockSignals(False)

        self._update_folder_meta(folder)
        self._refresh_track_row_icons()
        self._update_track_action_buttons()

    def _update_folder_meta(self, folder: Folder):
        """Infozeile unter dem Ordnernamen: Anzahl der Tracks und Gesamtdauer"""
        count = len(folder.tracks)
        total = sum(
            self.metadata_manager.read_metadata(t.filepath).duration or 0.0 for t in folder.tracks
        )
        parts = [f"{count} Track" if count == 1 else f"{count} Tracks"]
        if total >= 1:
            if total < 60:
                parts.append(f"{int(total)} Sek.")
            else:
                minutes = round(total / 60)
                parts.append(f"{minutes // 60} Std. {minutes % 60} Min." if minutes >= 60 else f"{minutes} Min.")
        self.folder_meta.setText(" · ".join(parts))

    def _create_new_folder(self):
        """Erstellt einen neuen Ordner"""
        if not self.sd_card:
            return
        
        for i in range(1, 100):
            if i not in self.sd_card.folders:
                try:
                    folder = self.sd_card.create_folder(i)
                    self._populate_folder_list()
                    self._select_folder_in_list(i)
                    self.status_bar.showMessage(f"Ordner {i:02d} erstellt")
                    return
                except Exception as e:
                    QMessageBox.warning(self, "Fehler", str(e))
                    return
        
        QMessageBox.warning(
            self,
            "Fehler",
            "Maximale Anzahl von 99 Ordnern erreicht!"
        )

    def _confirm_purge_target_is_sd_card(self) -> bool:
        """Warnt, bevor unwiderruflich geloescht wird, wenn das gewaehlte
        Verzeichnis nicht zu einer typischen Tonuino-SD-Karte passt: kein
        Wechseldatentraeger und/oder groesser als eine handelsuebliche 32GB-
        Karte. Laesst sich das auf der Plattform nicht ermitteln, wird nicht
        blockiert. Gibt True zurueck, wenn bereinigt werden darf."""
        total_size = get_total_size(self.sd_card.path)
        removable = is_removable_drive(self.sd_card.path)

        too_large = total_size is not None and total_size > MAX_SD_CARD_BYTES
        not_removable = removable is False

        if not too_large and not not_removable:
            return True

        reasons = []
        if not_removable:
            reasons.append(
                "Laut Betriebssystem handelt es sich nicht um einen "
                "Wechseldatenträger (SD-Kartenleser/USB), sondern vermutlich "
                "um ein fest eingebautes Laufwerk."
            )
        if too_large:
            size_gb = total_size / (1024 ** 3)
            reasons.append(
                f"Das Laufwerk ist mit {size_gb:.1f} GB deutlich größer als "
                "eine übliche 32GB-Tonuino-SD-Karte."
            )

        return confirm_action(
            self,
            "Ungewöhnliches Laufwerk",
            f"Das gewählte Laufwerk ({self.sd_card.path}) sieht nicht wie eine "
            "typische Tonuino-SD-Karte aus:\n\n- " + "\n- ".join(reasons) +
            "\n\nWird hier fortgefahren, können unwiderruflich Daten auf dem "
            "falschen Laufwerk gelöscht werden!\n\nTrotzdem fortfahren?"
        )

    @staticmethod
    def _format_name_list(names: list, limit: int = 5) -> str:
        shown = ", ".join(names[:limit])
        if len(names) > limit:
            shown += f", … (+{len(names) - limit} weitere)"
        return shown

    def _purge_confirmation_text(self, preview: PurgePreview) -> str:
        """Baut die Bestaetigungsabfrage-Nachricht aus einer PurgePreview,
        damit vor dem unwiderruflichen Loeschen konkret sichtbar ist, was
        betroffen sein wird."""
        lines = ["Folgendes wird unwiderruflich von der SD-Karte entfernt:", ""]

        if preview.root_files:
            lines.append(
                f"• {len(preview.root_files)} Datei(en) im Wurzelverzeichnis: "
                f"{self._format_name_list(preview.root_files)}"
            )
        if preview.root_dirs:
            lines.append(
                f"• {len(preview.root_dirs)} fremde(r) Ordner im Wurzelverzeichnis: "
                f"{self._format_name_list(preview.root_dirs)}"
            )
        if preview.foreign_items_in_folders:
            lines.append(
                f"• {preview.foreign_items_in_folders} Fremddatei(en)/-ordner "
                "innerhalb von 01-99/mp3/advert"
            )
        if preview.is_empty:
            lines.append("• Keine Fremddateien oder -ordner gefunden.")

        lines.append("")
        lines.append(
            "Außerdem werden leere Ordner gelöscht und alle Ordner- und "
            "Track-Nummern lückenlos neu vergeben."
        )
        lines.append("")
        lines.append("Fortfahren?")
        return "\n".join(lines)

    def _purge_sd_card(self):
        """Bereinigt die SD-Karte: entfernt alles, was nicht zur Tonuio-Struktur
        gehoert (Whitelist: Ordner 01-99, mp3, advert), raeumt Fremddateien auch
        innerhalb dieser Ordner auf und nummeriert Ordner/Tracks anschliessend
        luecken- und kollisionsfrei durch."""
        if not self.sd_card:
            return

        if not self._confirm_purge_target_is_sd_card():
            return

        preview = self.sd_card.preview_purge()
        confirmed = confirm_action(
            self,
            "SD-Karte bereinigen",
            self._purge_confirmation_text(preview)
        )
        if not confirmed:
            return

        self.player_bar.release_file()
        self.btn_purge_card.setEnabled(False)
        self.status_bar.showMessage("SD-Karte wird bereinigt...")

        # Modaler, unbestimmter Fortschrittsdialog ohne Abbrechen-Button: die
        # Dateisystem-Operationen laufen nicht schrittweise/abbrechbar ab, aber
        # die UI-Interaktion muss waehrend des Bereinigens gesperrt sein, damit
        # niemand parallel auf der noch veraenderten SD-Karte agiert.
        self._purge_dialog = QProgressDialog(
            "SD-Karte wird bereinigt, bitte warten...", None, 0, 0, self
        )
        self._purge_dialog.setWindowTitle("SD-Karte bereinigen")
        self._purge_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._purge_dialog.setCancelButton(None)
        self._purge_dialog.setMinimumDuration(0)
        self._purge_dialog.show()

        self._purge_worker = PurgeWorker(self.sd_card)
        self._purge_worker.completed.connect(self._on_purge_finished)
        self._purge_worker.start()

    def _on_purge_finished(self, success: bool, error_message: str):
        """Wird aufgerufen, wenn der Bereinigungs-Thread fertig ist"""
        self._purge_dialog.close()

        if self.sd_card is None:
            return  # Karte wurde waehrend des Bereinigens entfernt (UI ist schon zurueckgesetzt)

        if not success:
            self.btn_purge_card.setEnabled(True)
            QMessageBox.warning(self, "Fehler", f"Fehler beim Bereinigen: {error_message}")
            return

        self.current_folder = None
        self._folder_name_cache.clear()
        self.stack.setCurrentWidget(self.welcome_widget)
        self._populate_folder_list()
        self._update_program_buttons()
        self._update_folder_action_buttons()
        self.btn_purge_card.setEnabled(True)
        self.status_bar.showMessage(
            f"SD-Karte bereinigt: {self.sd_card.folder_count} Ordner, "
            f"{self.sd_card.total_tracks} Tracks"
        )

    def _delete_folder(self):
        """Loescht den aktuellen Ordner samt Inhalt unwiderruflich von der SD-Karte"""
        if not self.current_folder or self._is_special_folder(self.current_folder):
            return

        folder = self.current_folder
        name = self._resolve_folder_name(folder)

        confirmed = confirm_action(
            self,
            "Ordner löschen",
            f"Soll der Ordner '{name}' (Ordner {folder.index:02d}) mit allen "
            f"{folder.track_count} Track(s) unwiderruflich von der SD-Karte "
            f"gelöscht werden?"
        )
        if not confirmed:
            return

        self.player_bar.release_file()
        try:
            self.sd_card.delete_folder(folder.index)
            self._folder_name_cache.pop(folder.index, None)
            self.current_folder = None
            self.stack.setCurrentWidget(self.welcome_widget)
            self._populate_folder_list()
            self._update_program_buttons()
            self._update_folder_action_buttons()
            self.status_bar.showMessage(f"Ordner {folder.index:02d} gelöscht")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Löschen: {e}")

    def _add_tracks(self):
        """Fuegt Tracks zum aktuellen Ordner hinzu (im Hintergrund, mit Fortschrittsanzeige)"""
        if not self.current_folder or self._is_special_folder(self.current_folder):
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Audio-Dateien auswählen",
            "",
            "Audio (*.mp3 *.wav *.flac *.ogg *.aac *.wma *.m4a *.opus);;Alle (*)"
        )

        if not files:
            return

        free_slots = MAX_TRACKS_PER_FOLDER - self.current_folder.track_count
        if len(files) > free_slots:
            skipped = len(files) - max(free_slots, 0)
            if free_slots <= 0:
                QMessageBox.warning(
                    self,
                    "Ordner voll",
                    f"Der Ordner enthält bereits {MAX_TRACKS_PER_FOLDER} Tracks - "
                    "mehr erlaubt TonUINO nicht."
                )
                return
            QMessageBox.warning(
                self,
                "Zu viele Tracks",
                f"Ein TonUINO-Ordner kann maximal {MAX_TRACKS_PER_FOLDER} Tracks enthalten. "
                f"Es werden nur die ersten {free_slots} der {len(files)} gewählten "
                f"Dateien hinzugefügt, {skipped} werden übersprungen."
            )
            files = files[:free_slots]

        self._add_tracks_errors = []

        self._add_tracks_dialog = QProgressDialog(
            "Tracks werden hinzugefügt...", "Abbrechen", 0, len(files), self
        )
        self._add_tracks_dialog.setWindowTitle("Tracks hinzufügen")
        self._add_tracks_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._add_tracks_dialog.setMinimumDuration(0)
        self._add_tracks_dialog.setValue(0)

        self._add_tracks_worker = TrackAddWorker(
            self.current_folder, files, self.audio_converter, self.metadata_manager
        )
        self._add_tracks_worker.progress.connect(self._on_add_tracks_progress)
        self._add_tracks_worker.track_added.connect(self._on_track_added)
        self._add_tracks_worker.error.connect(self._on_add_tracks_error)
        self._add_tracks_worker.completed.connect(self._on_add_tracks_finished)
        self._add_tracks_dialog.canceled.connect(self._add_tracks_worker.cancel)

        self._add_tracks_worker.start()

    def _on_add_tracks_progress(self, current: int, total: int, filename: str):
        self._add_tracks_dialog.setLabelText(f"({current}/{total}) {filename}")
        self._add_tracks_dialog.setValue(current)

    def _on_track_added(self, track: Track):
        if self.current_folder is None:
            return
        self.current_folder.tracks.append(track)
        self.current_folder.tracks.sort(key=lambda t: t.index)

    def _on_add_tracks_error(self, filename: str, message: str):
        self._add_tracks_errors.append(f"{filename}: {message}")

    def _on_add_tracks_finished(self, added_count: int):
        self._add_tracks_dialog.close()

        if self.current_folder is None:
            return  # Karte wurde waehrend des Hinzufuegens entfernt (UI ist schon zurueckgesetzt)

        self._folder_name_cache.pop(self.current_folder.index, None)
        self._show_folder(self.current_folder)
        self._populate_folder_list()
        self.status_bar.showMessage(f"{added_count} Track(s) hinzugefügt")

        if self._add_tracks_errors:
            QMessageBox.warning(
                self,
                "Einige Tracks konnten nicht hinzugefügt werden",
                "\n".join(self._add_tracks_errors)
            )

    def _set_folder_cover(self):
        """Setzt das Cover fuer den aktuellen Ordner - wird in die ID3-Metadaten
        aller Tracks des Ordners uebernommen (das Cover wird von dort geladen)."""
        if not self.current_folder or self._is_special_folder(self.current_folder):
            return

        if not self.current_folder.tracks:
            QMessageBox.information(
                self,
                "Keine Tracks",
                "Dieser Ordner hat noch keine Tracks - bitte zuerst Tracks hinzufügen."
            )
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Cover-Bild auswählen",
            "",
            "Bilder (*.jpg *.png *.jpeg);;Alle (*)"
        )

        if not filepath:
            return

        self.player_bar.release_file()

        try:
            updated = self._apply_cover(self.current_folder.tracks, filepath)
            self._show_folder(self.current_folder)
            self.status_bar.showMessage(f"Cover für {updated} Track(s) aktualisiert")

        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler: {e}")

    def _apply_cover(self, tracks: list, image_path: str) -> int:
        """Schreibt das Bild (auf 300x300 JPEG verkleinert) als Cover in die ID3-
        Metadaten der Tracks. Gibt die Anzahl erfolgreich aktualisierter Tracks zurueck."""
        import tempfile
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img = img.resize((300, 300), Image.Resampling.LANCZOS)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(tmp_fd)
        img.save(tmp_path, "JPEG", quality=90)

        try:
            return sum(1 for track in tracks if self.metadata_manager.set_cover(track.filepath, tmp_path))
        finally:
            os.remove(tmp_path)

    def _on_track_double_clicked(self, item: QListWidgetItem):
        """Wird aufgerufen wenn ein Track doppelt geklickt wird"""
        if self._is_special_folder(self.current_folder):
            return

        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self._show_track_editor(track)
    
    def _show_track_editor(self, track):
        """Zeigt den Track-Editor"""
        from gui.track_editor import TrackEditorDialog
        
        if self.player_bar.is_current(track.filepath):
            self.player_bar.release_file()

        metadata = self.metadata_manager.read_metadata(track.filepath)
        cover_pixmap = None
        cover_bytes = self.metadata_manager.get_cover_bytes(track.filepath)
        if cover_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(cover_bytes):
                cover_pixmap = pixmap
        dialog = TrackEditorDialog(metadata, self, cover_pixmap=cover_pixmap)
        
        if dialog.exec() == TrackEditorDialog.DialogCode.Accepted:
            new_metadata = dialog.get_metadata()
            self.metadata_manager.write_metadata(
                track.filepath,
                title=new_metadata.title,
                artist=new_metadata.artist,
                album=new_metadata.album,
                track_number=new_metadata.track_number,
                total_tracks=metadata.total_tracks,
                genre=new_metadata.genre,
                year=new_metadata.year
            )
            if dialog.cover_path:
                try:
                    self._apply_cover([track], dialog.cover_path)
                except Exception as e:
                    QMessageBox.warning(self, "Fehler", f"Cover konnte nicht gesetzt werden: {e}")
            self._show_folder(self.current_folder)

    def _on_track_current_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Aktualisiert die Aktions-Buttons passend zur (Einzel-)Auswahl"""
        self._update_track_action_buttons()

    def _checked_rows(self) -> list:
        return [
            row for row in range(self.track_list.count())
            if self.track_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def _update_track_action_buttons(self):
        """Setzt Aktivierung und Beschriftung der Track-Aktionen. Im
        Mehrfachauswahl-Modus wirken Loeschen und Nach oben/unten auf alle
        markierten Tracks, sonst auf den aktuell ausgewaehlten Track.
        In Systemordnern (mp3/advert) ist Bearbeiten (Umsortieren, Loeschen,
        Mehrfachauswahl) nicht erlaubt, Abspielen schon (Symbole in der Liste)."""
        editable = bool(self.current_folder) and not self._is_special_folder(self.current_folder)
        has_current = self.track_list.currentItem() is not None
        if self._multi_select_mode:
            has_target = bool(self._checked_rows())
            self.btn_delete_tracks.setText(" Auswahl löschen")
            self.btn_move_track_up.setToolTip("Ausgewählte Tracks nach oben verschieben")
            self.btn_move_track_down.setToolTip("Ausgewählte Tracks nach unten verschieben")
        else:
            has_target = has_current
            self.btn_delete_tracks.setText(" Track löschen")
            self.btn_move_track_up.setToolTip("Track nach oben verschieben")
            self.btn_move_track_down.setToolTip("Track nach unten verschieben")

        self.btn_multi_select.setEnabled(editable)
        self.btn_move_track_up.setEnabled(has_target and editable)
        self.btn_move_track_down.setEnabled(has_target and editable)
        self.btn_delete_tracks.setEnabled(has_target and editable)
        # Ist noch nichts geladen, kann Play den ausgewaehlten Track starten
        self.player_bar.set_idle_playable(bool(self._get_selected_tracks()))

    def _set_multi_select_mode(self, enabled: bool):
        """Schaltet die Mehrfachauswahl ein/aus (wie in Apple Mail): Eingeschaltet
        zeigt jeder Track einen Auswahlkreis, ein Klick auf die Zeile markiert
        ihn. Ausgeschaltet wird die Auswahl verworfen und es gilt wieder die
        Einzelauswahl."""
        self._multi_select_mode = enabled

        if self.btn_multi_select.isChecked() != enabled:
            self.btn_multi_select.blockSignals(True)
            self.btn_multi_select.setChecked(enabled)
            self.btn_multi_select.blockSignals(False)
        self.btn_multi_select.setText(" Fertig" if enabled else " Auswählen")
        # dunkles Icon auf dem blauen (eingeschalteten) Button, sonst hell
        self.btn_multi_select.setIcon(
            self._icon_from_glyph("", color="#1e1e2e" if enabled else "#cdd6f4")  # Done all
        )

        self.track_list.blockSignals(True)
        for row in range(self.track_list.count()):
            item = self.track_list.item(row)
            if enabled:
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setData(Qt.ItemDataRole.CheckStateRole, None)
        self.track_list.blockSignals(False)

        self._refresh_track_row_icons()
        self._update_track_action_buttons()

    def _play_icon_rect(self, item: QListWidgetItem) -> QRect:
        """Bereich des Wiedergabe-Symbols in der Zeile (Viewport-Koordinaten).
        Im Einzelmodus ist das der Symbolbereich links, im Mehrfachauswahl-Modus
        der Streifen zwischen Auswahlkreis und Textanfang. Die Positionen
        kommen vom Style (nicht fest verdrahtet); der Streifen ist bewusst
        grosszuegig, weil der Style die Elemente rechts vom Kreis etwas
        weiter links meldet, als sie tatsaechlich gezeichnet werden."""
        opt = QStyleOptionViewItem()
        opt.initFrom(self.track_list)
        row_rect = self.track_list.visualItemRect(item)
        opt.rect = row_rect
        opt.decorationSize = QSize(18, 18)
        opt.font = self.track_list.font()
        opt.text = item.text()
        opt.features = (
            QStyleOptionViewItem.ViewItemFeature.HasDecoration
            | QStyleOptionViewItem.ViewItemFeature.HasDisplay
        )
        style = self.track_list.style()

        if not self._multi_select_mode:
            icon = style.subElementRect(QStyle.SubElement.SE_ItemViewItemDecoration, opt, self.track_list)
            return icon.adjusted(-8, -8, 8, 8)

        opt.features |= QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        opt.checkState = item.checkState()
        indicator = style.subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, self.track_list)
        text = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, self.track_list)
        return QRect(indicator.right() + 1, row_rect.top(), text.left() + 8 - indicator.right() - 1, row_rect.height())

    def _on_track_clicked(self, item: QListWidgetItem):
        """Ein Klick auf das Wiedergabe-Symbol startet/pausiert den Track. Sonst
        markiert/entmarkiert ein Klick den Track im Mehrfachauswahl-Modus
        (Kreis und restliche Zeile), im Einzelmodus waehlt er ihn nur aus."""
        track = item.data(Qt.ItemDataRole.UserRole)
        if track and self._play_icon_rect(item).contains(self.track_list.last_press_pos):
            self.player_bar.toggle_track(track.filepath, track.display_name)
            return
        if not self._multi_select_mode:
            return
        checked = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
        self._update_track_action_buttons()

    def _player_track_info(self, filepath: str) -> TrackInfo:
        """Anzeigedaten fuer den Player: Titel, Interpret, Album und eingebettetes
        Cover aus den ID3-Tags des Tracks"""
        metadata = self.metadata_manager.read_metadata(filepath)
        cover = None
        cover_bytes = self.metadata_manager.get_cover_bytes(filepath)
        if cover_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(cover_bytes):
                cover = pixmap
        return TrackInfo(title=metadata.title, artist=metadata.artist, album=metadata.album, cover=cover)

    def _update_player_navigation(self):
        """Zurueck/Weiter im Player nur aktivieren, wenn es relativ zum geladenen
        Track in dieser Richtung noch einen Track im Ordner gibt (kein Wrap-around)"""
        tracks = self.current_folder.tracks if self.current_folder else []
        current_path = self.player_bar.current_path
        index = next((i for i, t in enumerate(tracks) if t.filepath == current_path), None)
        if index is None:
            self.player_bar.set_navigation_enabled(False, False)
        else:
            self.player_bar.set_navigation_enabled(index > 0, index < len(tracks) - 1)

    def _play_selected_track(self):
        """Play im Player ohne geladenen Track: spielt den in der Liste
        ausgewaehlten Track (im Mehrfachauswahl-Modus den ersten markierten)"""
        tracks = self._get_selected_tracks()
        if tracks:
            self.player_bar.load_track(tracks[0].filepath, tracks[0].display_name, autoplay=True)

    def _on_track_hover_changed(self, row: int):
        self._hover_row = row
        self._refresh_track_row_icons()

    def _row_icon(self, kind: str) -> QIcon:
        """Symbole der Track-Zeilen (gecacht): play/pause beim Ueberfahren,
        speaker beim geladenen Track, blank haelt den Platz frei"""
        if kind not in self._row_icons:
            glyphs = {"play": "\ue037", "pause": "\ue034", "speaker": "\ue050"}
            if kind == "blank":
                pixmap = QPixmap(18, 18)
                pixmap.fill(Qt.GlobalColor.transparent)
                self._row_icons[kind] = QIcon(pixmap)
            else:
                self._row_icons[kind] = self._icon_from_glyph(glyphs[kind], color="#89b4fa", size=18)
        return self._row_icons[kind]

    def _refresh_track_row_icons(self):
        """Setzt je Zeile das Symbol wie in Apple Music: ueberfahrene Zeile zeigt
        Play (beim gerade spielenden Track Pause), der geladene Track sonst einen
        Lautsprecher. Funktioniert auch im Mehrfachauswahl-Modus (Symbol neben dem
        Auswahlkreis)."""
        playing = self.player_bar.is_playing()
        for row in range(self.track_list.count()):
            item = self.track_list.item(row)
            track = item.data(Qt.ItemDataRole.UserRole)
            is_current = bool(track) and self.player_bar.is_current(track.filepath)
            hovered = row == self._hover_row

            if hovered:
                kind = "pause" if is_current and playing else "play"
            elif is_current:
                kind = "speaker"
            else:
                kind = "blank"
            item.setIcon(self._row_icon(kind))

    def _play_previous_track(self):
        self._play_relative_track(-1)

    def _play_next_track(self):
        self._play_relative_track(1)

    def _play_relative_track(self, delta: int):
        """Spielt den vorherigen/naechsten Track relativ zum aktuell im Player
        geladenen Track (kein Wrap-around am Anfang/Ende der Liste)"""
        if not self.current_folder or not self.current_folder.tracks:
            return

        tracks = self.current_folder.tracks
        current_path = self.player_bar.current_path
        current_index = next(
            (i for i, t in enumerate(tracks) if t.filepath == current_path), None
        )
        if current_index is None:
            return

        target_index = current_index + delta
        if target_index < 0 or target_index >= len(tracks):
            return

        track = tracks[target_index]
        self.player_bar.load_track(track.filepath, track.display_name, autoplay=True)
        self.track_list.setCurrentRow(target_index)

    def _get_selected_tracks(self) -> list:
        """Die Tracks, auf die Aktionen wirken: im Mehrfachauswahl-Modus alle
        markierten, sonst der aktuell ausgewaehlte"""
        if self._multi_select_mode:
            return [self.track_list.item(row).data(Qt.ItemDataRole.UserRole) for row in self._checked_rows()]
        current_item = self.track_list.currentItem()
        return [current_item.data(Qt.ItemDataRole.UserRole)] if current_item else []

    def _delete_selected_tracks(self):
        """Loescht die ausgewaehlten Tracks von der SD-Karte und
        nummeriert die verbleibenden Tracks fortlaufend um (keine Luecken, wie
        von Tonuino benoetigt)"""
        if not self.current_folder or self._is_special_folder(self.current_folder):
            return

        tracks = self._get_selected_tracks()
        if not tracks:
            return

        if len(tracks) == 1:
            message = f"Soll der Track '{tracks[0].display_name}' unwiderruflich gelöscht werden?"
        else:
            message = f"Sollen die {len(tracks)} ausgewählten Tracks unwiderruflich gelöscht werden?"

        if not confirm_action(self, "Tracks löschen", message):
            return

        self.player_bar.release_file()
        try:
            self.sd_card.delete_tracks(self.current_folder, tracks)
            self._folder_name_cache.pop(self.current_folder.index, None)
            self._show_folder(self.current_folder)
            self._populate_folder_list()
            self.status_bar.showMessage(f"{len(tracks)} Track(s) gelöscht")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Löschen: {e}")

    @staticmethod
    def _reorder_with_selection(tracks: list, selected_ids: set, delta: int):
        """Berechnet die neue Reihenfolge, wenn die markierten Tracks um eine
        Position nach oben (delta=-1) oder unten (delta=1) verschoben werden.
        Verstreute Markierungen werden dabei unter Beibehaltung ihrer
        Reihenfolge zu einem Block zusammengezogen, der am obersten (bzw. beim
        Verschieben nach unten untersten) markierten Track ansetzt und ueber den
        naechsten nicht markierten Track springt. Gibt (neue_reihenfolge,
        zeilen_der_markierten) zurueck."""
        marked = [i for i, t in enumerate(tracks) if id(t) in selected_ids]
        block = [tracks[i] for i in marked]
        rest = [t for t in tracks if id(t) not in selected_ids]

        if delta < 0:
            anchor = marked[0]  # so viele nicht markierte Tracks stehen davor
            insert_at = max(anchor - 1, 0)
        else:
            anchor = marked[-1] - (len(marked) - 1)
            insert_at = min(anchor + 1, len(rest))

        new_order = rest[:insert_at] + block + rest[insert_at:]
        return new_order, list(range(insert_at, insert_at + len(block)))

    def _move_selected_tracks(self, delta: int):
        """Verschiebt die ausgewaehlten Tracks um eine Position nach oben
        (delta=-1) oder unten (delta=1) und benennt die Dateien auf der
        SD-Karte entsprechend fortlaufend um (siehe _reorder_with_selection)."""
        if not self.current_folder or self._is_special_folder(self.current_folder):
            return

        selected = self._get_selected_tracks()
        if not selected:
            return

        new_order, moved_rows = self._reorder_with_selection(
            list(self.current_folder.tracks), {id(t) for t in selected}, delta
        )
        if new_order == list(self.current_folder.tracks):
            return  # nichts verschiebbar (alles schon am Rand)

        self.player_bar.release_file()
        try:
            self.sd_card.reorder_tracks(self.current_folder, new_order)
            self._folder_name_cache.pop(self.current_folder.index, None)
            self._populate_track_list(self.current_folder)
            if self._multi_select_mode:
                for row in moved_rows:
                    self.track_list.item(row).setCheckState(Qt.CheckState.Checked)
                self._update_track_action_buttons()
            else:
                self.track_list.setCurrentRow(moved_rows[0])
            self.status_bar.showMessage("Reihenfolge aktualisiert")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Umsortieren: {e}")

    def _set_reader_mode(self, mode: str):
        """Schaltet zwischen den beiden Programmierwegen um (ACR122U-Leser vs.
        seriell ueber den TonUINO selbst) - ausgewaehlt ueber das Menue Einstellungen
        (RFID-Leser), beide teilen sich denselben Bereich in der Sidebar."""
        self._reader_mode = mode
        is_tonuino = mode == self.READER_MODE_TONUINO
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
        self.setEnabled(False)
        QApplication.processEvents()
        try:
            self.tonuino_serial.connect(port)
        except TonuinoSerialError as e:
            self.setEnabled(True)
            self.tonuino_status_label.setText(f"Verbindung fehlgeschlagen: {e}")
            QMessageBox.warning(self, "Fehler", str(e))
            return

        self.setEnabled(True)
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

    def _check_rfid_card(self):
        """Prueft periodisch Reader- und Kartenstatus und aktualisiert die Anzeige automatisch"""
        if self._reader_mode != self.READER_MODE_ACR122U:
            return
        if not self.rfid_reader.scard_available:
            return

        # Reader nicht verbunden - automatisch (wieder) verbinden
        if not self.rfid_reader._reader_available:
            readers = self.rfid_reader.get_readers()
            if not readers:
                self._set_status_icon(self.reader_icon, "neutral")
                self._update_card_status(present=False)
                return

            try:
                if self.rfid_reader.connect(0):
                    self._set_status_icon(self.reader_icon, "ok")
            except Exception:
                pass
            return

        # Reader war verbunden - pruefen ob er noch physisch angeschlossen ist
        # (z.B. nicht per USB abgezogen wurde). Das ist unabhaengig davon, ob
        # gerade eine Karte aufliegt.
        if not self.rfid_reader.is_reader_present():
            self.rfid_reader.disconnect()
            self._set_status_icon(self.reader_icon, "neutral")
            self._update_card_status(present=False)
            return

        # Reader verbunden - Karte pruefen
        try:
            if not self.rfid_reader.is_card_present():
                self._update_card_status(present=False)
                return

            uid = self.rfid_reader.get_card_uid()
            if not uid:
                self._set_status_icon(self.card_icon, "warning")
                self._set_status_icon(self.programmed_icon, "neutral")
                self._rfid_card_present = False
                self._rfid_card_programmed = False
                self._update_program_buttons()
                return

            self._set_status_icon(self.card_icon, "ok")
            self._rfid_card_present = True

            card_data = self.rfid_reader.read_tonuino_card()
            self._rfid_card_programmed = bool(card_data)
            if card_data:
                self._set_status_icon(self.programmed_icon, "ok")
            else:
                self._set_status_icon(self.programmed_icon, "warning")

            self._update_program_buttons()

        except Exception as e:
            # Fehler nur in der Statusleiste anzeigen, nicht als Popup
            self.status_bar.showMessage(f"RFID-Fehler: {e}")
            self._update_card_status(present=False)
    
    RFID_MODES = PLAYBACK_MODES

    # WRITECARD-Modi fuer den TonUINO-seriell-Weg (siehe core.tonuino_serial) -
    # alle 16 Firmware-Modi ausser Admin, der einen eigenen Button hat.
    TONUINO_MODES = [
        (info.label, info.value)
        for info in TonuinoSerial.WRITECARD_MODES.values()
        if info.value != TonuinoSerial.PMODE_ADMIN_CARD
    ]

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
            try:
                success = self.rfid_reader.write_tonuino_card(
                    self.current_folder.index,
                    mode=mode,
                    special=special
                )
                if success:
                    self.status_bar.showMessage("Karte erfolgreich programmiert!")
                    QMessageBox.information(
                        self,
                        "Erfolg",
                        "Die Karte wurde erfolgreich programmiert!"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Fehler",
                        "Die Karte konnte nicht programmiert werden."
                    )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Fehler",
                    f"Fehler beim Programmieren: {e}"
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
            try:
                success = self.rfid_reader.write_admin_card()
                if success:
                    self.status_bar.showMessage("Admin-Karte erfolgreich programmiert!")
                    QMessageBox.information(
                        self,
                        "Erfolg",
                        "Die Admin-Karte wurde erfolgreich programmiert!"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Fehler",
                        "Die Admin-Karte konnte nicht programmiert werden."
                    )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Fehler",
                    f"Fehler beim Programmieren: {e}"
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
            self.status_bar.showMessage(message)
            QMessageBox.information(self, "Erfolg", message)
        else:
            self.tonuino_status_label.setText(f"Fehler: {message}")
            QMessageBox.warning(self, "Fehler", f"Die Karte konnte nicht programmiert werden:\n{message}")

    def _set_erase_icon_state(self, enabled: bool):
        """Faerbt das Loeschen-Icon rot (Karte enthaelt Daten) oder grau
        (nichts zu loeschen) und blockt Klicks im deaktivierten Zustand -
        wie bei einem echten (aber unsichtbaren) Button."""
        color = "#f38ba8" if enabled else "#585b70"
        self.erase_card_icon.setPixmap(self._icon_from_glyph("", color=color, size=20).pixmap(20, 20))
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
            try:
                success = self.rfid_reader.erase_tonuino_card()
                if success:
                    self.status_bar.showMessage("Karten-Daten erfolgreich gelöscht!")
                    QMessageBox.information(
                        self,
                        "Erfolg",
                        "Die Karten-Daten wurden erfolgreich gelöscht!"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Fehler",
                        "Die Karten-Daten konnten nicht gelöscht werden."
                    )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Fehler",
                    f"Fehler beim Löschen: {e}"
                )

    def _check_for_updates(self):
        """Automatische Update-Pruefung beim Programmstart - nur, wenn im
        Hilfe-Menue nicht deaktiviert. Ohne Drosselung, da ein GitHub-API-
        Request beim Start keinen nennenswerten Traffic verursacht. Schlaegt
        die Pruefung fehl, bleibt das hier bewusst unbemerkt (siehe
        UpdateChecker) - anders als bei der manuellen Pruefung ueber das
        Menue soll ein Start nie mit einer Fehlermeldung unterbrochen werden."""
        if not QSettings().value("updater/auto_check_enabled", True, type=bool):
            return
        self._run_update_check(manual=False)

    def _check_for_updates_manual(self):
        """Manuelle Update-Pruefung ueber Hilfe > Nach Updates suchen - meldet
        im Gegensatz zum automatischen Start-Check explizit, ob ein Update
        gefunden wurde, keins vorhanden ist, oder die Pruefung fehlgeschlagen ist."""
        if self._update_checker is not None and self._update_checker.isRunning():
            return
        self._run_update_check(manual=True)

    def _run_update_check(self, manual: bool):
        self._update_checker = UpdateChecker(__version__)
        self._update_checker.update_available.connect(self._on_update_available)
        if manual:
            self._update_checker.no_update.connect(self._on_manual_check_no_update)
            self._update_checker.check_failed.connect(self._on_manual_check_failed)
        self._update_checker.start()

    def _on_manual_check_no_update(self):
        QMessageBox.information(
            self,
            "Kein Update verfügbar",
            f"Sie verwenden bereits die neueste Version ({__version__})."
        )

    def _on_manual_check_failed(self, message: str):
        QMessageBox.warning(
            self,
            "Update-Prüfung fehlgeschlagen",
            f"Die Prüfung auf Updates ist fehlgeschlagen:\n{message}"
        )

    def _on_auto_check_toggled(self, checked: bool):
        QSettings().setValue("updater/auto_check_enabled", checked)

    def _on_update_available(self, info: UpdateInfo):
        settings = QSettings()

        if settings.value("updater/ignored_version", "", type=str) == info.version:
            return

        dialog = UpdateDialog(info, __version__, self)
        dialog.exec()

        if dialog.result_choice == UpdateDialog.UPDATE_NOW:
            self._start_update_download(info)
        elif dialog.result_choice == UpdateDialog.IGNORE:
            settings.setValue("updater/ignored_version", info.version)

    def _start_update_download(self, info: UpdateInfo):
        """Laedt den passenden Installer herunter, mit Fortschrittsanzeige"""
        self._update_download_dialog = QProgressDialog(
            f"Lade Update {info.version} herunter...", "Abbrechen", 0, 100, self
        )
        self._update_download_dialog.setWindowTitle("Update herunterladen")
        self._update_download_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._update_download_dialog.setMinimumDuration(0)
        self._update_download_dialog.setValue(0)

        self._update_downloader = UpdateDownloader(info)
        self._update_downloader.progress.connect(self._on_update_download_progress)
        self._update_downloader.completed.connect(self._on_update_download_finished)
        self._update_downloader.error.connect(self._on_update_download_error)
        self._update_download_dialog.canceled.connect(self._update_downloader.cancel)

        self._update_downloader.start()

    def _on_update_download_progress(self, read: int, total: int):
        if total > 0:
            self._update_download_dialog.setMaximum(total)
            self._update_download_dialog.setValue(read)
        else:
            self._update_download_dialog.setMaximum(0)

    def _on_update_download_finished(self, filepath: str):
        self._update_download_dialog.close()
        self._launch_installer(filepath)

    def _on_update_download_error(self, message: str):
        self._update_download_dialog.close()
        QMessageBox.warning(
            self,
            "Download fehlgeschlagen",
            f"Das Update konnte nicht heruntergeladen werden:\n{message}\n\n"
            f"Sie können es manuell herunterladen:\n{GITHUB_RELEASES_PAGE}"
        )

    def _launch_installer(self, filepath: str):
        """Uebergibt den heruntergeladenen Installer an das Betriebssystem.
        Unter Windows wird die App danach beendet, da installer.iss keine
        CloseApplications-Direktive hat und der Installer die laufende, aus
        Program Files gestartete EXE sonst nicht ueberschreiben kann. Unter
        Linux/macOS bleibt die App offen - dort besteht kein Datei-Konflikt,
        da .deb-Paketinstallation bzw. .dmg-Mounten die laufende Instanz nicht
        beruehren."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(filepath)
                QApplication.instance().quit()
            elif sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", filepath])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", filepath])
            else:
                self._show_update_manual_fallback(filepath)
        except Exception:
            self._show_update_manual_fallback(filepath)

    def _show_update_manual_fallback(self, filepath: str):
        QMessageBox.information(
            self,
            "Manuelle Installation erforderlich",
            f"Die Installationsdatei wurde heruntergeladen nach:\n{filepath}\n\n"
            f"Bitte führen Sie die Datei manuell aus, oder laden Sie sie erneut "
            f"herunter unter:\n{GITHUB_RELEASES_PAGE}"
        )

    def closeEvent(self, event):
        """Wird beim Schliessen aufgerufen"""
        self.player_bar.stop()
        self._stop_background_threads()
        if self.rfid_reader:
            self.rfid_reader.disconnect()
        if self.tonuino_serial.is_connected:
            self.tonuino_serial.disconnect()
        event.accept()

    def _stop_background_threads(self):
        """Beendet laufende Hintergrund-Threads, bevor das Fenster verschwindet -
        sonst endet der Prozess mit 'QThread: Destroyed while thread is still
        running' bzw. der Serial-Thread liest von einem schon geschlossenen Port."""
        if self._tonuino_worker is not None and self._tonuino_worker.isRunning():
            try:
                self.tonuino_serial.cancel_write()
            except TonuinoSerialError:
                pass
            self._tonuino_worker.wait(3000)

        for worker in (self._add_tracks_worker, self._update_downloader):
            if worker is not None and worker.isRunning():
                worker.cancel()
                worker.wait(3000)

        # Scan, Bereinigung und Update-Pruefung sind nicht abbrechbar - kurz auslaufen lassen
        for worker in (self.scanner, self._purge_worker, self._update_checker):
            if worker is not None and worker.isRunning():
                worker.wait(3000)
