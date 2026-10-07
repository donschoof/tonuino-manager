"""
Track-Editor Dialog fuer Tonuino-Manager
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QPushButton, QFileDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from core.metadata import TrackMetadata
from gui.cover_edit import CoverEditWidget


class TrackEditorDialog(QDialog):
    """Dialog zum Bearbeiten von Track-Metadaten"""
    
    def __init__(self, metadata: TrackMetadata, parent=None, cover_pixmap: Optional[QPixmap] = None):
        super().__init__(parent)
        self.setWindowTitle("Track bearbeiten")
        self.setMinimumWidth(400)
        
        self.metadata = metadata
        self.cover_pixmap = cover_pixmap
        # Pfad eines neu gewaehlten Cover-Bildes; leer = Cover unveraendert lassen
        self.cover_path = ""
        
        self._setup_ui()
        self._load_metadata()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Cover: zeigt das echte Cover (oder einen Platzhalter); ein Klick, den ein
        # Hover-Overlay ankuendigt, waehlt ein neues Bild
        self.cover_edit = CoverEditWidget(150)
        self.cover_edit.clicked.connect(self._load_cover)
        layout.addWidget(self.cover_edit, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # Formular
        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Track-Titel")
        form_layout.addRow("Titel:", self.title_edit)
        
        self.artist_edit = QLineEdit()
        self.artist_edit.setPlaceholderText("Künstler")
        form_layout.addRow("Künstler:", self.artist_edit)
        
        self.album_edit = QLineEdit()
        self.album_edit.setPlaceholderText("Album")
        form_layout.addRow("Album:", self.album_edit)
        
        self.track_num_spin = QSpinBox()
        self.track_num_spin.setRange(0, 999)
        self.track_num_spin.setValue(0)
        form_layout.addRow("Track-Nr:", self.track_num_spin)
        
        self.genre_edit = QLineEdit()
        self.genre_edit.setPlaceholderText("Genre")
        form_layout.addRow("Genre:", self.genre_edit)
        
        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("Jahr")
        self.year_edit.setMaxLength(4)
        form_layout.addRow("Jahr:", self.year_edit)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        btn_ok = QPushButton("Speichern")
        btn_ok.setObjectName("primaryButton")
        btn_ok.clicked.connect(self.accept)
        button_layout.addWidget(btn_ok)
        
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
    
    def _load_metadata(self):
        """Laedt die Metadaten in die Felder"""
        self.title_edit.setText(self.metadata.title)
        self.artist_edit.setText(self.metadata.artist)
        self.album_edit.setText(self.metadata.album)
        self.track_num_spin.setValue(self.metadata.track_number)
        self.genre_edit.setText(self.metadata.genre)
        self.year_edit.setText(self.metadata.year)
        
        self.cover_edit.set_cover(self.cover_pixmap)
    
    def _load_cover(self):
        """Laedt ein Cover-Bild"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Cover-Bild auswählen",
            "",
            "Bilder (*.jpg *.png *.jpeg);;Alle Dateien (*)"
        )
        
        if filepath:
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                self.cover_path = filepath
                self.cover_edit.set_cover(pixmap)
    
    def get_metadata(self) -> TrackMetadata:
        """Gibt die bearbeiteten Metadaten zurueck"""
        return TrackMetadata(
            title=self.title_edit.text(),
            artist=self.artist_edit.text(),
            album=self.album_edit.text(),
            track_number=self.track_num_spin.value(),
            genre=self.genre_edit.text(),
            year=self.year_edit.text()
        )
