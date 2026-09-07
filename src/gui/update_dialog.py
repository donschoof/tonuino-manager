"""
Update-Dialog fuer Tonuino-Manager
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
)

from core.updater import UpdateInfo


class UpdateDialog(QDialog):
    """Zeigt ein verfuegbares Update mit Release-Notes und drei Wahlmoeglichkeiten"""

    UPDATE_NOW = "update_now"
    LATER = "later"
    IGNORE = "ignore"

    def __init__(self, info: UpdateInfo, current_version: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update verfügbar")
        self.setMinimumWidth(480)

        self.info = info
        self.result_choice = self.LATER

        self._setup_ui(current_version)

    def _setup_ui(self, current_version: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        headline = QLabel(f"Version {self.info.version} ist verfügbar")
        headline.setObjectName("titleLabel")
        layout.addWidget(headline)

        subtitle = QLabel(f"Installierte Version: {current_version}")
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(subtitle)

        notes = QTextEdit()
        notes.setReadOnly(True)
        notes.setPlainText(self.info.release_notes or "Keine Release-Notes verfügbar.")
        notes.setMaximumHeight(220)
        layout.addWidget(notes)

        button_layout = QHBoxLayout()

        btn_ignore = QPushButton("Diese Version ignorieren")
        btn_ignore.clicked.connect(self._on_ignore)
        button_layout.addWidget(btn_ignore)

        button_layout.addStretch()

        btn_later = QPushButton("Später")
        btn_later.clicked.connect(self._on_later)
        button_layout.addWidget(btn_later)

        btn_update = QPushButton("Jetzt aktualisieren")
        btn_update.setObjectName("primaryButton")
        btn_update.clicked.connect(self._on_update_now)
        button_layout.addWidget(btn_update)

        layout.addLayout(button_layout)

    def _on_ignore(self):
        self.result_choice = self.IGNORE
        self.accept()

    def _on_later(self):
        self.result_choice = self.LATER
        self.reject()

    def _on_update_now(self):
        self.result_choice = self.UPDATE_NOW
        self.accept()
