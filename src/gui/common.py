"""
Gemeinsam genutzte GUI-Helfer (Pfade, Schriften, Dialoge, Icons)
"""

import os
import sys

from PyQt6.QtWidgets import QLabel, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from gui import theme


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


def icon_from_glyph(glyph: str, color: str = theme.BASE, size: int = 16) -> QIcon:
    """Rendert ein Glyph aus der gebuendelten Material-Icons-Schriftart (Apache-2.0)
    als QIcon, damit es (anders als reiner Text) mit setIcon() auf Buttons benutzt
    werden kann, ohne die restliche Button-Schrift zu beeinflussen. Plattformneutral
    statt der Windows-exklusiven Segoe Fluent Icons."""
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
