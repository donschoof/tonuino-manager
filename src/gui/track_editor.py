"""
Track-Editor Dialog fuer Tonuino-Manager
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QPushButton, QLabel,
    QFileDialog, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from core.metadata import TrackMetadata, MetadataManager


class TrackEditorDialog(QDialog):
    """Dialog zum Bearbeiten von Track-Metadaten"""
    
    def __init__(self, metadata: TrackMetadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Track bearbeiten")
        self.setMinimumWidth(400)
        
        self.metadata = metadata
        self.cover_path = ""
        
        self._setup_ui()
        self._load_metadata()
    
    def _setup_ui(self):
        """Erstellt die UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Cover-Vorschau
        cover_frame = QFrame()
        cover_frame.setObjectName("cardFrame")
        cover_layout = QVBoxLayout(cover_frame)
        
        self.cover_label = QLabel("Kein Cover")
        self.cover_label.setFixedSize(150, 150)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setObjectName("coverLabel")
        cover_layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        btn_load_cover = QPushButton("Cover laden")
        btn_load_cover.clicked.connect(self._load_cover)
        cover_layout.addWidget(btn_load_cover)
        
        layout.addWidget(cover_frame)
        
        # Formular
        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Track-Titel")
        form_layout.addRow("Titel:", self.title_edit)
        
        self.artist_edit = QLineEdit()
        self.artist_edit.setPlaceholderText("Kuenstler")
        form_layout.addRow("Kuenstler:", self.artist_edit)
        
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
        
        if self.metadata.has_cover:
            self.cover_label.setText("Cover vorhanden")
    
    def _load_cover(self):
        """Laedt ein Cover-Bild"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Cover-Bild auswaehlen",
            "",
            "Bilder (*.jpg *.png *.jpeg);;Alle Dateien (*)"
        )
        
        if filepath:
            self.cover_path = filepath
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    150, 150,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.cover_label.setPixmap(scaled)
    
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
