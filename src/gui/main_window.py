"""
Hauptfenster des Tonuino-Managers
"""

import os
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QStackedWidget, QFrame, QFileDialog, QMessageBox,
    QStatusBar, QProgressBar, QSplitter, QInputDialog,
    QAbstractItemView, QProgressDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QFont, QPixmap, QIcon, QPainter, QColor

from core.sd_card import SDCard, Folder, Track
from core.audio_converter import AudioConverter
from core.metadata import MetadataManager
from core.rfid import RFIDReader
from core.tonuino_config import TonuinoConfigManager


def resource_path(*parts) -> str:
    """Ermittelt einen Pfad relativ zum src-Verzeichnis - funktioniert sowohl im
    Skript- als auch im PyInstaller-EXE-Modus (siehe auch main.py)."""
    if getattr(sys, 'frozen', False):
        src_dir = os.path.join(os.path.dirname(sys.executable), 'src')
    else:
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(src_dir, *parts)


class ClickableLabel(QLabel):
    """QLabel, das per Klick ein Signal auslöst (fuer das Cover-Bild als In-Place-Button)"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SDCardScanner(QThread):
    """Thread fuer das Scannen der SD-Karte"""
    finished = pyqtSignal(bool)
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
            self.finished.emit(success)
        except Exception as e:
            print(f"Scan-Fehler: {e}")
            import traceback
            traceback.print_exc()
            self.finished.emit(False)


class TrackAddWorker(QThread):
    """Thread zum Hinzufuegen (Kopieren/Konvertieren) von Tracks, damit die
    UI waehrend FFmpeg-Konvertierung/Datei-I/O nicht einfriert."""
    progress = pyqtSignal(int, int, str)  # aktueller Index, Gesamtzahl, Dateiname
    track_added = pyqtSignal(object)  # neuer Track
    error = pyqtSignal(str, str)  # Dateiname, Fehlermeldung
    finished = pyqtSignal(int)  # Anzahl erfolgreich hinzugefuegter Tracks

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
            if next_number > 999:
                break

            dest_filename = f"{next_number:03d}.mp3"
            dest_path = Path(self.folder.path) / dest_filename

            try:
                if self.audio_converter.needs_conversion(filepath):
                    if not self.audio_converter.is_available:
                        self.error.emit(os.path.basename(filepath), "FFmpeg ist nicht verfuegbar.")
                        continue
                    self.audio_converter.convert_to_mp3(filepath, str(dest_path))
                else:
                    import shutil
                    shutil.copy2(filepath, dest_path)

                source_metadata = self.metadata_manager.read_metadata(filepath)
                if source_metadata.title:
                    self.metadata_manager.write_metadata(
                        str(dest_path),
                        title=source_metadata.title,
                        artist=source_metadata.artist,
                        album=source_metadata.album,
                        track_number=next_number
                    )

                new_track = Track(
                    index=next_number,
                    filename=dest_filename,
                    filepath=str(dest_path),
                    title=source_metadata.title
                )
                self._used_numbers.add(next_number)
                self.track_added.emit(new_track)
                added += 1

            except Exception as e:
                self.error.emit(os.path.basename(filepath), str(e))

        self.finished.emit(added)


class MainWindow(QMainWindow):
    """Hauptfenster des Tonuino-Managers"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tonuino-Manager")
        icon_path = resource_path("resources", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(1200, 800)
        
        self.sd_card: SDCard = None
        self.audio_converter = AudioConverter()
        self.metadata_manager = MetadataManager()
        self.rfid_reader = RFIDReader()
        self.config_manager: TonuinoConfigManager = None
        self.current_folder: Folder = None
        self._folder_name_cache = {}  # folder_index -> aus Album-Tag ermittelter Name

        self._setup_ui()
        self._setup_statusbar()
        self._check_dependencies()
        
        # RFID-Timer fuer regelmaessige Kartenpruefung
        self.rfid_timer = QTimer()
        self.rfid_timer.timeout.connect(self._check_rfid_card)
        self.rfid_timer.start(500)
        
        # Automatische RFID-Reader-Verbindung beim Start
        QTimer.singleShot(500, self._auto_connect_rfid)
    
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
            self.btn_program_card.setEnabled(False)
            self._update_card_status(present=False)
        else:
            self._set_status_icon(self.reader_icon, "error")
    
    def _setup_ui(self):
        """Erstellt die Benutzeroberflaeche"""
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
        title_row.addWidget(logo_label)

        title = QLabel("Tonuino-Manager")
        title.setObjectName("sidebarTitle")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title_row.addWidget(title, 1)

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
        
        layout.addWidget(QLabel("Ordner:"))
        self.folder_list = QListWidget()
        self.folder_list.setObjectName("folderList")
        self.folder_list.itemClicked.connect(self._on_folder_selected)
        layout.addWidget(self.folder_list)
        
        rfid_frame = QFrame()
        rfid_frame.setObjectName("cardFrame")
        rfid_layout = QVBoxLayout(rfid_frame)
        rfid_layout.setSpacing(10)

        rfid_title = QLabel("RFID-Karte")
        rfid_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        rfid_layout.addWidget(rfid_title)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        # Einheitliche Icons aus Segoe Fluent Icons / Segoe MDL2 Assets (Windows-Icon-Font):
        # U+E88E = USB, U+E963 = SmartCard, U+E8B7 = Folder
        reader_tile, self.reader_icon = self._create_status_tile("", "Reader")
        status_row.addWidget(reader_tile)

        card_tile, self.card_icon = self._create_status_tile("", "Karte")
        status_row.addWidget(card_tile)

        programmed_tile, self.programmed_icon = self._create_status_tile("", "Ordner")
        status_row.addWidget(programmed_tile)

        rfid_layout.addLayout(status_row)

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
        """Rendert ein Glyph aus Segoe Fluent Icons/Segoe MDL2 Assets als QIcon,
        damit es (anders als reiner Text) mit setIcon() auf Buttons benutzt
        werden kann, ohne die restliche Button-Schrift zu beeinflussen."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        font = QFont("Segoe Fluent Icons")
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        self.welcome_widget = QWidget()
        welcome_layout = QVBoxLayout(self.welcome_widget)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        welcome_label = QLabel("Willkommen beim Tonuino-Manager!")
        welcome_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_label)
        
        info_label = QLabel(
            "Oeffne eine SD-Karte um zu beginnen.\n\n"
            "- Verwalte deine Tonuio-Ordner\n"
            "- Fuege Musik hinzu mit automatischer Konvertierung\n"
            "- Bearbeite Metadaten und Cover\n"
            "- Programmiere RFID-Karten direkt"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        welcome_layout.addWidget(info_label)
        
        self.folder_widget = QWidget()
        folder_layout = QVBoxLayout(self.folder_widget)
        
        header_layout = QHBoxLayout()
        self.folder_title = QLabel("Ordner")
        self.folder_title.setObjectName("titleLabel")
        header_layout.addWidget(self.folder_title)
        
        header_layout.addStretch()
        
        btn_add_tracks = QPushButton(" Tracks hinzufuegen")
        btn_add_tracks.setObjectName("primaryButton")
        btn_add_tracks.setIcon(self._icon_from_glyph("", color="#1e1e2e"))  # Add
        btn_add_tracks.clicked.connect(self._add_tracks)
        header_layout.addWidget(btn_add_tracks)

        btn_delete_folder = QPushButton(" Ordner loeschen")
        btn_delete_folder.setObjectName("dangerButton")
        btn_delete_folder.setIcon(self._icon_from_glyph("", color="#1e1e2e"))  # Delete
        btn_delete_folder.clicked.connect(self._delete_folder)
        header_layout.addWidget(btn_delete_folder)

        folder_layout.addLayout(header_layout)
        
        info_layout = QHBoxLayout()
        
        self.cover_label = ClickableLabel()
        self.cover_label.setObjectName("coverLabel")
        self.cover_label.setFixedSize(150, 150)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setText("Kein Cover\n(klicken zum Aendern)")
        self.cover_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover_label.setToolTip("Klicken um das Cover zu aendern")
        self.cover_label.clicked.connect(self._set_folder_cover)
        info_layout.addWidget(self.cover_label)
        
        self.folder_info = QLabel()
        self.folder_info.setObjectName("subtitleLabel")
        info_layout.addWidget(self.folder_info, 1)
        
        folder_layout.addLayout(info_layout)

        track_header_layout = QHBoxLayout()
        track_header_layout.addWidget(QLabel("Tracks:"))
        track_header_layout.addStretch()

        self.btn_move_track_up = QPushButton()
        self.btn_move_track_up.setIcon(self._icon_from_glyph("", color="#cdd6f4"))  # Up
        self.btn_move_track_up.setToolTip("Ausgewaehlten Track nach oben verschieben")
        self.btn_move_track_up.setEnabled(False)
        self.btn_move_track_up.clicked.connect(lambda: self._move_current_track(-1))
        track_header_layout.addWidget(self.btn_move_track_up)

        self.btn_move_track_down = QPushButton()
        self.btn_move_track_down.setIcon(self._icon_from_glyph("", color="#cdd6f4"))  # Down
        self.btn_move_track_down.setToolTip("Ausgewaehlten Track nach unten verschieben")
        self.btn_move_track_down.setEnabled(False)
        self.btn_move_track_down.clicked.connect(lambda: self._move_current_track(1))
        track_header_layout.addWidget(self.btn_move_track_down)

        self.btn_delete_tracks = QPushButton(" Auswahl loeschen")
        self.btn_delete_tracks.setObjectName("dangerButton")
        self.btn_delete_tracks.setIcon(self._icon_from_glyph("", color="#1e1e2e"))  # Delete
        self.btn_delete_tracks.setEnabled(False)
        self.btn_delete_tracks.clicked.connect(self._delete_selected_tracks)
        track_header_layout.addWidget(self.btn_delete_tracks)

        folder_layout.addLayout(track_header_layout)

        self.track_list = QListWidget()
        self.track_list.itemDoubleClicked.connect(self._on_track_double_clicked)
        self.track_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.track_list.currentItemChanged.connect(self._on_track_current_changed)
        self.track_list.itemChanged.connect(self._on_track_check_changed)
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
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.status_bar.showMessage("Bereit")
    
    def _check_dependencies(self):
        """Prueft verfuegbare Abhaengigkeiten"""
        if not self.audio_converter.is_available:
            self.status_bar.showMessage("FFmpeg nicht gefunden - Konvertierung nicht moeglich")
        
        if not self.rfid_reader.scard_available:
            self.status_bar.showMessage("pyscard nicht installiert - RFID nicht verfuegbar")

    def _open_sd_card(self):
        """Oeffnet eine SD-Karte"""
        path = QFileDialog.getExistingDirectory(
            self,
            "SD-Karte auswaehlen",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not path:
            return
        
        self.sd_card = SDCard(path)
        self.config_manager = TonuinoConfigManager(path)
        self._folder_name_cache.clear()

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("Scanne SD-Karte...")
        
        self.scanner = SDCardScanner(self.sd_card)
        self.scanner.progress.connect(self.progress_bar.setValue)
        self.scanner.finished.connect(self._on_scan_finished)
        self.scanner.start()
    
    def _on_scan_finished(self, success: bool):
        """Wird aufgerufen wenn der Scan abgeschlossen ist"""
        self.progress_bar.setVisible(False)
        
        if success:
            self.status_bar.showMessage(
                f"SD-Karte geladen: {self.sd_card.folder_count} Ordner, "
                f"{self.sd_card.total_tracks} Tracks"
            )
            self.btn_new_folder.setEnabled(True)
            self._populate_folder_list()
            
            if self.config_manager:
                self.config_manager.load()
        else:
            self.status_bar.showMessage("Fehler beim Scannen der SD-Karte")
            QMessageBox.warning(
                self,
                "Fehler",
                "Die SD-Karte konnte nicht gelesen werden."
            )
    
    def _populate_folder_list(self):
        """Fuellt die Ordner-Liste mit Ordnernummer-Badge und ermitteltem Namen"""
        self.folder_list.clear()

        if not self.sd_card:
            return

        for idx in sorted(self.sd_card.folders.keys()):
            folder = self.sd_card.folders[idx]
            name = self._resolve_folder_name(folder)

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setSizeHint(QSize(0, 36))
            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, self._create_folder_item_widget(folder.index, name))

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

    def _create_folder_item_widget(self, folder_index: int, name: str) -> QWidget:
        """Erstellt das Zeilen-Widget fuer die Ordnerliste: Nummer-Badge + Name"""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(10)

        badge = QLabel(f"{folder_index:02d}")
        badge.setObjectName("folderBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumSize(34, 24)
        row.addWidget(badge)

        name_label = QLabel(name)
        name_label.setObjectName("folderNameLabel")
        row.addWidget(name_label, 1)

        return widget
    
    def _on_folder_selected(self, item: QListWidgetItem):
        """Wird aufgerufen wenn ein Ordner ausgewaehlt wird"""
        folder_idx = item.data(Qt.ItemDataRole.UserRole)
        self.current_folder = self.sd_card.get_folder(folder_idx)

        if self.current_folder:
            self._show_folder(self.current_folder)

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
        
        self.folder_title.setText(self._resolve_folder_name(folder))
        
        pixmap = self._get_folder_cover_pixmap(folder)
        if pixmap:
            scaled = pixmap.scaled(
                150, 150,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.cover_label.setPixmap(scaled)
        else:
            self.cover_label.setText("Kein Cover\n(klicken zum Aendern)")
        
        info_text = (
            f"Ordner-Nummer: {folder.index:02d}\n"
            f"Anzahl Tracks: {folder.track_count}\n"
            f"Pfad: {folder.path}"
        )
        
        if self.config_manager:
            mode = self.config_manager.get_folder_mode(folder.index)
            if mode:
                info_text += f"\nWiedergabemodus: {mode}"
        
        self.folder_info.setText(info_text)

        self._populate_track_list(folder)

    def _populate_track_list(self, folder: Folder):
        """Baut die Track-Liste eines Ordners neu auf (liest Metadaten je Track).
        Jeder Track hat eine Checkbox zum Auswaehlen fuer das Loeschen mehrerer
        Tracks - unabhaengig von der normalen (Einzel-)Auswahl, die fuer die
        Nach-oben/unten-Buttons benutzt wird."""
        self.track_list.blockSignals(True)
        self.track_list.clear()
        for track in folder.tracks:
            metadata = self.metadata_manager.read_metadata(track.filepath)
            track.title = metadata.title
            track.artist = metadata.artist
            track.album = metadata.album

            item = QListWidgetItem(track.display_name)
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.track_list.addItem(item)
        self.track_list.blockSignals(False)

        self.btn_delete_tracks.setEnabled(False)
        self.btn_move_track_up.setEnabled(False)
        self.btn_move_track_down.setEnabled(False)
    
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

    def _delete_folder(self):
        """Loescht den aktuellen Ordner samt Inhalt unwiderruflich von der SD-Karte"""
        if not self.current_folder:
            return

        folder = self.current_folder
        name = self._resolve_folder_name(folder)

        reply = QMessageBox.question(
            self,
            "Ordner löschen",
            f"Soll der Ordner '{name}' (Ordner {folder.index:02d}) mit allen "
            f"{folder.track_count} Track(s) unwiderruflich von der SD-Karte "
            f"gelöscht werden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.sd_card.delete_folder(folder.index)
            self._folder_name_cache.pop(folder.index, None)
            self.current_folder = None
            self.stack.setCurrentWidget(self.welcome_widget)
            self._populate_folder_list()
            self.status_bar.showMessage(f"Ordner {folder.index:02d} gelöscht")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Löschen: {e}")

    def _add_tracks(self):
        """Fuegt Tracks zum aktuellen Ordner hinzu (im Hintergrund, mit Fortschrittsanzeige)"""
        if not self.current_folder:
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Audio-Dateien auswaehlen",
            "",
            "Audio (*.mp3 *.wav *.flac *.ogg *.aac *.wma *.m4a *.opus);;Alle (*)"
        )

        if not files:
            return

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
        self._add_tracks_worker.finished.connect(self._on_add_tracks_finished)
        self._add_tracks_dialog.canceled.connect(self._add_tracks_worker.cancel)

        self._add_tracks_worker.start()

    def _on_add_tracks_progress(self, current: int, total: int, filename: str):
        self._add_tracks_dialog.setLabelText(f"({current}/{total}) {filename}")
        self._add_tracks_dialog.setValue(current)

    def _on_track_added(self, track: Track):
        self.current_folder.tracks.append(track)
        self.current_folder.tracks.sort(key=lambda t: t.index)

    def _on_add_tracks_error(self, filename: str, message: str):
        self._add_tracks_errors.append(f"{filename}: {message}")

    def _on_add_tracks_finished(self, added_count: int):
        self._add_tracks_dialog.close()

        self._folder_name_cache.pop(self.current_folder.index, None)
        self._show_folder(self.current_folder)
        self._populate_folder_list()
        self.status_bar.showMessage(f"{added_count} Track(s) hinzugefuegt")

        if self._add_tracks_errors:
            QMessageBox.warning(
                self,
                "Einige Tracks konnten nicht hinzugefuegt werden",
                "\n".join(self._add_tracks_errors)
            )

    def _set_folder_cover(self):
        """Setzt das Cover fuer den aktuellen Ordner - wird in die ID3-Metadaten
        aller Tracks des Ordners uebernommen (das Cover wird von dort geladen)."""
        if not self.current_folder:
            return

        if not self.current_folder.tracks:
            QMessageBox.information(
                self,
                "Keine Tracks",
                "Dieser Ordner hat noch keine Tracks - bitte zuerst Tracks hinzufuegen."
            )
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Cover-Bild auswaehlen",
            "",
            "Bilder (*.jpg *.png *.jpeg);;Alle (*)"
        )

        if not filepath:
            return

        import tempfile

        try:
            from PIL import Image
            img = Image.open(filepath).convert("RGB")
            img = img.resize((300, 300), Image.Resampling.LANCZOS)

            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(tmp_fd)
            img.save(tmp_path, "JPEG", quality=90)

            try:
                updated = sum(
                    1 for track in self.current_folder.tracks
                    if self.metadata_manager.set_cover(track.filepath, tmp_path)
                )
            finally:
                os.remove(tmp_path)

            self._show_folder(self.current_folder)
            self.status_bar.showMessage(f"Cover fuer {updated} Track(s) aktualisiert")

        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler: {e}")
    
    def _on_track_double_clicked(self, item: QListWidgetItem):
        """Wird aufgerufen wenn ein Track doppelt geklickt wird"""
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self._show_track_editor(track)
    
    def _show_track_editor(self, track):
        """Zeigt den Track-Editor"""
        from gui.track_editor import TrackEditorDialog
        
        metadata = self.metadata_manager.read_metadata(track.filepath)
        dialog = TrackEditorDialog(metadata, self)
        
        if dialog.exec() == TrackEditorDialog.DialogCode.Accepted:
            new_metadata = dialog.get_metadata()
            self.metadata_manager.write_metadata(
                track.filepath,
                title=new_metadata.title,
                artist=new_metadata.artist,
                album=new_metadata.album,
                track_number=new_metadata.track_number
            )
            self._show_folder(self.current_folder)

    def _on_track_current_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Aktiviert/deaktiviert die Nach-oben/unten-Buttons je nachdem, ob ein
        Track (einzeln) ausgewaehlt ist"""
        has_current = current is not None
        self.btn_move_track_up.setEnabled(has_current)
        self.btn_move_track_down.setEnabled(has_current)

    def _on_track_check_changed(self, item: QListWidgetItem):
        """Aktiviert/deaktiviert den 'Auswahl loeschen'-Button je nachdem, ob
        mindestens ein Track per Checkbox ausgewaehlt ist"""
        any_checked = any(
            self.track_list.item(row).checkState() == Qt.CheckState.Checked
            for row in range(self.track_list.count())
        )
        self.btn_delete_tracks.setEnabled(any_checked)

    def _get_checked_tracks(self) -> list:
        return [
            self.track_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.track_list.count())
            if self.track_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def _delete_selected_tracks(self):
        """Loescht die per Checkbox ausgewaehlten Tracks von der SD-Karte und
        nummeriert die verbleibenden Tracks fortlaufend um (keine Luecken, wie
        von Tonuino benoetigt)"""
        if not self.current_folder:
            return

        tracks = self._get_checked_tracks()
        if not tracks:
            return

        if len(tracks) == 1:
            message = f"Soll der Track '{tracks[0].display_name}' unwiderruflich gelöscht werden?"
        else:
            message = f"Sollen die {len(tracks)} ausgewählten Tracks unwiderruflich gelöscht werden?"

        reply = QMessageBox.question(
            self,
            "Tracks löschen",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.sd_card.delete_tracks(self.current_folder, tracks)
            self._folder_name_cache.pop(self.current_folder.index, None)
            self._show_folder(self.current_folder)
            self._populate_folder_list()
            self.status_bar.showMessage(f"{len(tracks)} Track(s) gelöscht")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Löschen: {e}")

    def _move_current_track(self, delta: int):
        """Verschiebt den aktuell (einzeln) ausgewaehlten Track um eine Position
        nach oben (delta=-1) oder unten (delta=1) und benennt die Dateien auf
        der SD-Karte entsprechend fortlaufend um."""
        if not self.current_folder:
            return

        current_item = self.track_list.currentItem()
        if not current_item:
            return

        row = self.track_list.row(current_item)
        target_row = row + delta
        if target_row < 0 or target_row >= len(self.current_folder.tracks):
            return

        new_order = list(self.current_folder.tracks)
        new_order[row], new_order[target_row] = new_order[target_row], new_order[row]

        try:
            self.sd_card.reorder_tracks(self.current_folder, new_order)
            self._folder_name_cache.pop(self.current_folder.index, None)
            self._populate_track_list(self.current_folder)
            self.track_list.setCurrentRow(target_row)
            self.status_bar.showMessage("Reihenfolge aktualisiert")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Umsortieren: {e}")

    def _update_card_status(self, present: bool):
        """Setzt Karten- und Programmiert-Icon auf den 'keine Karte'-Zustand zurueck"""
        if not present:
            self._set_status_icon(self.card_icon, "neutral")
            self._set_status_icon(self.programmed_icon, "neutral")
            self.btn_program_card.setEnabled(False)
            self.btn_program_admin.setEnabled(False)

    def _check_rfid_card(self):
        """Prueft periodisch Reader- und Kartenstatus und aktualisiert die Anzeige automatisch"""
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

        # Reader verbunden - Karte pruefen
        try:
            if not self.rfid_reader.is_card_present():
                self._update_card_status(present=False)
                return

            uid = self.rfid_reader.get_card_uid()
            if not uid:
                self._set_status_icon(self.card_icon, "warning")
                self._set_status_icon(self.programmed_icon, "neutral")
                self.btn_program_card.setEnabled(False)
                self.btn_program_admin.setEnabled(False)
                return

            self._set_status_icon(self.card_icon, "ok")
            self.btn_program_card.setEnabled(True)
            self.btn_program_admin.setEnabled(True)

            card_data = self.rfid_reader.read_tonuino_card()
            if card_data:
                self._set_status_icon(self.programmed_icon, "ok")
            else:
                self._set_status_icon(self.programmed_icon, "warning")

        except Exception as e:
            # Fehler nur in der Statusleiste anzeigen, nicht als Popup
            self.status_bar.showMessage(f"RFID-Fehler: {e}")
            self._update_card_status(present=False)
    
    # Wiedergabemodi wie vom original TonUINO-Firmware erwartet (chip_card.hpp: pmode_t)
    RFID_MODES = [
        ("Hörspiel (zufällige Wiedergabe, kein Fortschritt)", 1),
        ("Album (alle Tracks der Reihe nach)", 2),
        ("Party (alle Tracks in zufälliger Reihenfolge)", 3),
        ("Einzelner Track", 4),
        ("Hörbuch (Fortschritt wird gespeichert)", 5),
    ]

    def _program_rfid_card(self):
        """Programmiert eine RFID-Karte"""
        if not self.current_folder:
            QMessageBox.warning(
                self,
                "Kein Ordner",
                "Bitte waehle zuerst einen Ordner aus."
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
            f"Modus fuer Ordner '{self._resolve_folder_name(self.current_folder)}':",
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
                "Track auswaehlen",
                "Welcher Track soll gespielt werden?",
                1, 1, track_count
            )
            if not ok:
                return

        reply = QMessageBox.question(
            self,
            "Karte programmieren",
            f"Soll die Karte fuer Ordner \'{self._resolve_folder_name(self.current_folder)}\' "
            f"programmiert werden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
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
        if not self.rfid_reader.is_card_present():
            QMessageBox.information(
                self,
                "Karte legen",
                "Bitte lege eine Karte auf den Reader."
            )
            return

        reply = QMessageBox.question(
            self,
            "Admin-Karte programmieren",
            "Soll diese Karte als Admin-Karte programmiert werden?\n\n"
            "Eine Admin-Karte ist keinem Ordner zugeordnet und oeffnet am "
            "TonUINO das Admin-Menue.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
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

    def closeEvent(self, event):
        """Wird beim Schliessen aufgerufen"""
        if self.rfid_reader:
            self.rfid_reader.disconnect()
        event.accept()
