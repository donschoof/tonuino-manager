"""
Hauptfenster des Tonuino-Managers
"""

import os
import sys
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidgetItem, QListWidget,
    QStackedWidget, QFrame, QFileDialog, QMessageBox,
    QStatusBar, QSplitter,
    QAbstractItemView, QProgressDialog,
    QMenuBar, QStyle, QStyleOptionViewItem
)
from PyQt6.QtCore import Qt, QTimer, QSize, QSettings, QEvent, QPoint, QRect
from PyQt6.QtGui import QCursor, QPixmap, QIcon, QActionGroup

from core import __version__
from core.sd_card import SDCard, Folder, Track, PurgePreview, MAX_TRACKS_PER_FOLDER
from core.drive_check import get_total_size, is_removable_drive, MAX_SD_CARD_BYTES
from core.audio_converter import AudioConverter
from core.metadata import MetadataManager
from gui.common import resource_path, heading_font, confirm_action, icon_from_glyph
from gui.track_list import HoverListWidget, reorder_with_selection
from gui.workers import (
    SDCardScanner, TrackAddWorker, FolderNameWorker, TrackMetaWorker, PurgeWorker,
)
from gui.audio_player import AudioPlayerBar, ElidedLabel, TrackInfo
from gui.cover_edit import CoverEditWidget
from gui.rfid_panel import RfidPanel
from gui.update_controller import UpdateController
from gui.title_bar import TitleBar


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
        self.scanner: SDCardScanner = None
        self._add_tracks_worker: TrackAddWorker = None
        self._purge_worker: PurgeWorker = None
        self.current_folder: Folder = None
        self._folder_name_cache = {}  # folder_index -> aus Album-Tag ermittelter Name
        self._folder_name_labels = {}  # folder_index -> Namens-Label in der Ordnerliste
        self._folder_name_worker: FolderNameWorker = None
        self._track_meta_worker: TrackMetaWorker = None
        self._track_meta_generation = 0
        self._track_meta_total = 0.0

        self.update_controller = UpdateController(self)

        self._setup_ui()
        self._setup_statusbar()
        self._check_dependencies()
        
        # SD-Karten-Timer: erkennt, wenn die geoeffnete SD-Karte (z.B. per
        # USB/Kartenleser) waehrend der Nutzung entfernt wird, und setzt die
        # UI dann sauber zurueck statt bei jedem weiteren Zugriff auf die
        # verschwundenen Pfade Dateisystem-Fehler ins Log zu schreiben.
        self.sd_card_timer = QTimer()
        self.sd_card_timer.timeout.connect(self._check_sd_card_presence)
        self.sd_card_timer.start(1000)

        # Update-Pruefung beim Start (versetzt, damit sie nicht mit der
        # RFID-Verbindung um Systemressourcen konkurriert)
        QTimer.singleShot(1500, self.update_controller.check_on_startup)

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
        action_check_now.triggered.connect(self.update_controller.check_manual)

        menu.addSeparator()

        auto_check_enabled = QSettings().value("updater/auto_check_enabled", True, type=bool)
        action_auto_check = menu.addAction("Automatisch nach Updates suchen")
        action_auto_check.setCheckable(True)
        action_auto_check.setChecked(auto_check_enabled)
        action_auto_check.toggled.connect(self.update_controller.on_auto_check_toggled)

        menu.addSeparator()

        reader_menu = menu.addMenu("RFID-Leser")
        reader_group = QActionGroup(self)
        reader_group.setExclusive(True)

        action_reader_acr122u = reader_menu.addAction("ACR122U")
        action_reader_acr122u.setCheckable(True)
        action_reader_acr122u.setChecked(True)  # Default
        action_reader_acr122u.triggered.connect(
            lambda: self.rfid_panel.set_reader_mode(RfidPanel.READER_MODE_ACR122U)
        )
        reader_group.addAction(action_reader_acr122u)

        action_reader_tonuino = reader_menu.addAction("TonUINO (seriell)")
        action_reader_tonuino.setCheckable(True)
        action_reader_tonuino.triggered.connect(
            lambda: self.rfid_panel.set_reader_mode(RfidPanel.READER_MODE_TONUINO)
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
        
        self.rfid_panel = RfidPanel(
            get_folder=lambda: self.current_folder,
            folder_name=self._resolve_folder_name,
            show_status=lambda message: self.status_bar.showMessage(message),
        )
        layout.addWidget(self.rfid_panel)

        return sidebar

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
        btn_add_tracks.setIcon(icon_from_glyph("\ue145", color="#1e1e2e"))  # Add
        btn_add_tracks.setFixedHeight(38)
        btn_add_tracks.setMinimumWidth(170)
        btn_add_tracks.clicked.connect(self._add_tracks)
        self.btn_add_tracks = btn_add_tracks
        actions.addWidget(btn_add_tracks)

        btn_delete_folder = QPushButton(" Ordner löschen")
        btn_delete_folder.setObjectName("dangerButton")
        btn_delete_folder.setIcon(icon_from_glyph("\ue872", color="#1e1e2e"))  # Delete
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
        self.btn_multi_select.setIcon(icon_from_glyph("\ue877", color="#cdd6f4"))  # Done all
        self.btn_multi_select.setCheckable(True)
        self.btn_multi_select.setToolTip("Mehrfachauswahl ein-/ausschalten")
        self.btn_multi_select.setEnabled(False)
        self.btn_multi_select.toggled.connect(self._set_multi_select_mode)
        track_header_layout.addWidget(self.btn_multi_select)

        self.btn_move_track_up = QPushButton()
        self.btn_move_track_up.setIcon(icon_from_glyph("", color="#cdd6f4"))  # Up
        self.btn_move_track_up.setToolTip("Track nach oben verschieben")
        self.btn_move_track_up.setEnabled(False)
        self.btn_move_track_up.clicked.connect(lambda: self._move_selected_tracks(-1))
        track_header_layout.addWidget(self.btn_move_track_up)

        self.btn_move_track_down = QPushButton()
        self.btn_move_track_down.setIcon(icon_from_glyph("", color="#cdd6f4"))  # Down
        self.btn_move_track_down.setToolTip("Track nach unten verschieben")
        self.btn_move_track_down.setEnabled(False)
        self.btn_move_track_down.clicked.connect(lambda: self._move_selected_tracks(1))
        track_header_layout.addWidget(self.btn_move_track_down)

        self.btn_delete_tracks = QPushButton(" Track löschen")
        self.btn_delete_tracks.setObjectName("dangerButton")
        self.btn_delete_tracks.setIcon(icon_from_glyph("", color="#1e1e2e"))  # Delete
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
        if not self.rfid_panel.rfid_reader.scard_available:
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

        self._stop_folder_name_worker()
        self._stop_track_meta_worker()

        self.sd_card = None
        self.current_folder = None
        self._folder_name_cache.clear()

        self.folder_list.clear()
        self._update_welcome_text()
        self.player_bar.stop_and_clear()
        self.stack.setCurrentWidget(self.welcome_widget)
        self.btn_new_folder.setEnabled(False)
        self.btn_purge_card.setEnabled(False)
        self.rfid_panel.refresh()
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
        self._stop_folder_name_worker()
        self.folder_list.clear()
        self._folder_name_labels.clear()
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
            widget = self._create_folder_item_widget(folder, name)
            self._folder_name_labels[idx] = widget.name_label
            self.folder_list.setItemWidget(item, widget)

        for special_name in SDCard.SPECIAL_FOLDER_NAMES:
            folder = self.sd_card.special_folders.get(special_name)
            if not folder:
                continue

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, special_name)
            item.setSizeHint(QSize(0, 36))
            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, self._create_folder_item_widget(folder, folder.name))

        # Namen der noch unbekannten Ordner im Hintergrund nachladen
        pending = [f for i, f in self.sd_card.folders.items() if i not in self._folder_name_cache]
        if pending:
            self._folder_name_worker = FolderNameWorker(pending, self.metadata_manager)
            self._folder_name_worker.name_found.connect(self._set_folder_name)
            self._folder_name_worker.start()

    def _stop_folder_name_worker(self):
        worker = self._folder_name_worker
        if worker is not None:
            worker.cancel()
            worker.wait()
            self._folder_name_worker = None

    def _set_folder_name(self, folder_index: int, name: str):
        """Uebernimmt einen im Hintergrund ermittelten Ordnernamen in Cache,
        Ordnerliste und (falls gerade offen) Kopfbereich."""
        if self.sd_card is None or folder_index not in self.sd_card.folders:
            return
        self._folder_name_cache[folder_index] = name
        label = self._folder_name_labels.get(folder_index)
        if label is not None:
            label.setText(name)
        if self.current_folder is not None and not self.current_folder.is_special \
                and self.current_folder.index == folder_index:
            self._update_folder_title(self.current_folder)

    def _is_special_folder(self, folder: Optional[Folder]) -> bool:
        """True, wenn folder einer der nicht editierbaren Tonuio-Systemordner
        (mp3/advert) ist"""
        return folder is not None and folder.is_special

    def _resolve_folder_name(self, folder: Folder) -> str:
        """Anzeigename eines Ordners: der im Hintergrund aus dem Album-Tag
        ermittelte Name (siehe FolderNameWorker), bis dahin 'Ordner NN'."""
        if folder.index in self._folder_name_cache:
            return self._folder_name_cache[folder.index]

        return self._folder_name_cache.get(folder.index, f"Ordner {folder.index:02d}")

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
        widget.name_label = name_label

        return widget

    def _on_folder_selected(self, item: QListWidgetItem):
        """Wird aufgerufen wenn ein Ordner ausgewaehlt wird"""
        identity = item.data(Qt.ItemDataRole.UserRole)
        self.current_folder = self.sd_card.get_any_folder(identity)

        # Ein anderer Ordner startet immer wieder im Einzelauswahl-Modus
        self._set_multi_select_mode(False)
        if self.current_folder:
            self._show_folder(self.current_folder)

        self.rfid_panel.refresh()

    def _select_folder_in_list(self, folder_index: int):
        """Waehlt einen Ordner in der Sidebar-Liste aus und zeigt ihn im Hauptbereich an
        (z.B. direkt nach dem Anlegen eines neuen Ordners)"""
        for row in range(self.folder_list.count()):
            item = self.folder_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == folder_index:
                self.folder_list.setCurrentItem(item)
                self._on_folder_selected(item)
                return

    @staticmethod
    def _folder_cover_file_pixmap(folder: Folder) -> Optional[QPixmap]:
        """Fallback-Cover aus einer Cover-Datei im Ordner (Altbestand, z.B.
        cover.jpg von frueheren Versionen). Das eingebettete Cover des ersten
        Tracks liefert TrackMetaWorker und ersetzt dieses, sobald es gelesen ist."""
        if folder.cover_path:
            pixmap = QPixmap(folder.cover_path)
            if not pixmap.isNull():
                return pixmap
        return None

    def _show_folder(self, folder: Folder):
        """Zeigt einen Ordner an"""
        self.stack.setCurrentWidget(self.folder_widget)

        self._update_folder_title(folder)
        # Der Pfad steht nicht mehr als Zeile da, bleibt aber als Tooltip erreichbar
        for widget in (self.folder_title, self.folder_subtitle, self.folder_meta):
            widget.setToolTip(f"Pfad: {folder.path}")

        self.cover_label.set_cover(self._folder_cover_file_pixmap(folder))

        self._populate_track_list(folder)
        self._update_folder_action_buttons()

    def _update_folder_title(self, folder: Folder):
        """Titel und Untertitel im Kopfbereich"""
        self.folder_title.setText(folder.name if folder.is_special else self._resolve_folder_name(folder))
        subtitle = "Tonuino-Systemordner" if folder.is_special else f"Ordner {folder.index:02d}"
        self.folder_subtitle.setText(subtitle)
        # Hat der Ordner keinen eigenen Namen (aus den Tags), waere der Untertitel
        # nur eine Wiederholung des Titels
        self.folder_subtitle.setVisible(self.folder_title.text() != subtitle)

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
        self._stop_track_meta_worker()

        self.track_list.blockSignals(True)
        self.track_list.clear()
        for track in folder.tracks:
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

        self._track_meta_total = 0.0
        self._update_folder_meta(folder)
        self._refresh_track_row_icons()
        self._update_track_action_buttons()

        # Tags, Dauer und Cover im Hintergrund lesen (je Datei einmal)
        self._track_meta_worker = TrackMetaWorker(
            self._track_meta_generation, list(folder.tracks), self.metadata_manager
        )
        self._track_meta_worker.track_loaded.connect(self._on_track_meta_loaded)
        self._track_meta_worker.completed.connect(self._on_track_meta_completed)
        self._track_meta_worker.start()

    def _stop_track_meta_worker(self):
        """Bricht das Metadaten-Lesen ab. Die Generation verwirft bereits
        eingereihte Signale des alten Workers."""
        self._track_meta_generation += 1
        worker = self._track_meta_worker
        if worker is not None:
            worker.cancel()
            worker.wait()
            self._track_meta_worker = None

    def _release_files(self):
        """Gibt alle Dateien frei, bevor sie umbenannt/geloescht/ueberschrieben
        werden: Player entladen und Hintergrund-Leser stoppen (unter Windows
        halten beide die Dateien sonst gesperrt)."""
        self._stop_folder_name_worker()
        self._stop_track_meta_worker()
        self.player_bar.release_file()

    def _on_track_meta_loaded(self, generation: int, row: int, metadata, cover_bytes):
        if generation != self._track_meta_generation or row >= self.track_list.count():
            return
        item = self.track_list.item(row)
        track = item.data(Qt.ItemDataRole.UserRole)
        track.title = metadata.title
        track.artist = metadata.artist
        track.album = metadata.album
        item.setText(track.display_name)
        self._track_meta_total += metadata.duration or 0.0

        folder = self.current_folder
        if folder is None or folder.is_special:
            return
        # Tracks treffen der Reihe nach ein: der erste mit Album-Tag benennt den Ordner
        if metadata.album and folder.index not in self._folder_name_cache:
            self._set_folder_name(folder.index, metadata.album)
        if cover_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(cover_bytes):
                self.cover_label.set_cover(pixmap)

    def _on_track_meta_completed(self, generation: int):
        if generation == self._track_meta_generation and self.current_folder is not None:
            self._update_folder_meta(self.current_folder)

    def _update_folder_meta(self, folder: Folder):
        """Infozeile unter dem Ordnernamen: Anzahl der Tracks und Gesamtdauer
        (die Dauer kommt, sobald die Metadaten gelesen sind)"""
        count = len(folder.tracks)
        total = self._track_meta_total
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
                    self.sd_card.create_folder(i)
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

        self._release_files()
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
        self.rfid_panel.refresh()
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

        self._release_files()
        try:
            self.sd_card.delete_folder(folder.index)
            self._folder_name_cache.pop(folder.index, None)
            self.current_folder = None
            self.stack.setCurrentWidget(self.welcome_widget)
            self._populate_folder_list()
            self.rfid_panel.refresh()
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

        self._release_files()

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
            self._release_files()

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
            icon_from_glyph("", color="#1e1e2e" if enabled else "#cdd6f4")  # Done all
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
                self._row_icons[kind] = icon_from_glyph(glyphs[kind], color="#89b4fa", size=18)
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

        self._release_files()
        try:
            self.sd_card.delete_tracks(self.current_folder, tracks)
            self._folder_name_cache.pop(self.current_folder.index, None)
            self._show_folder(self.current_folder)
            self._populate_folder_list()
            self.status_bar.showMessage(f"{len(tracks)} Track(s) gelöscht")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Löschen: {e}")

    def _move_selected_tracks(self, delta: int):
        """Verschiebt die ausgewaehlten Tracks um eine Position nach oben
        (delta=-1) oder unten (delta=1) und benennt die Dateien auf der
        SD-Karte entsprechend fortlaufend um (siehe reorder_with_selection)."""
        if not self.current_folder or self._is_special_folder(self.current_folder):
            return

        selected = self._get_selected_tracks()
        if not selected:
            return

        new_order, moved_rows = reorder_with_selection(
            list(self.current_folder.tracks), {id(t) for t in selected}, delta
        )
        if new_order == list(self.current_folder.tracks):
            return  # nichts verschiebbar (alles schon am Rand)

        self._release_files()
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

    def closeEvent(self, event):
        """Wird beim Schliessen aufgerufen"""
        self.player_bar.stop()
        self.rfid_panel.shutdown()
        self.update_controller.shutdown()
        self._stop_background_threads()
        event.accept()

    def _stop_background_threads(self):
        """Beendet laufende Hintergrund-Threads, bevor das Fenster verschwindet -
        sonst endet der Prozess mit 'QThread: Destroyed while thread is still running'."""
        if self._add_tracks_worker is not None and self._add_tracks_worker.isRunning():
            self._add_tracks_worker.cancel()
            self._add_tracks_worker.wait(3000)

        self._stop_folder_name_worker()
        self._stop_track_meta_worker()

        # Scan und Bereinigung sind nicht abbrechbar - kurz auslaufen lassen
        for worker in (self.scanner, self._purge_worker):
            if worker is not None and worker.isRunning():
                worker.wait(3000)
