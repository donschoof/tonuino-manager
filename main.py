"""
Tonuino-Manager
Ein hübsches Tool zum Verwalten von Tonuino SD-Karten und RFID-Karten.
"""

import sys
import os

# PyInstaller-Kompatibilitaet
if getattr(sys, 'frozen', False):
    # Lauft als kompilierte EXE (onefile-Build, siehe Tonuino-Manager.spec).
    # Gebuendelte Daten (datas=[('src', 'src')]) werden zur Laufzeit nach
    # sys._MEIPASS entpackt - NICHT neben die EXE-Datei selbst.
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    src_dir = os.path.join(base_dir, 'src')
else:
    # Lauft als Python-Skript
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(script_dir, 'src')

# Fuege src zum Python-Pfad hinzu
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFontDatabase
from core import __version__
from gui.main_window import MainWindow


def main():
    # High DPI Skalierung aktivieren
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("Tonuino-Manager")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("TonuinoManager")

    icon_path = os.path.join(src_dir, "resources", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Icon-Schriftart bundlen (Material Icons, Apache-2.0) statt der
    # Windows-exklusiven Segoe Fluent Icons/Segoe MDL2 Assets zu verwenden -
    # macht die Button-/Status-Icons auf allen Plattformen (Windows/macOS/
    # Linux) gleichermassen sichtbar, siehe gui/main_window.py.
    icon_font_path = os.path.join(src_dir, "resources", "fonts", "MaterialIcons-Regular.ttf")
    if os.path.exists(icon_font_path):
        QFontDatabase.addApplicationFont(icon_font_path)

    # Stylesheet laden
    from gui.styles import MAIN_STYLESHEET
    app.setStyleSheet(MAIN_STYLESHEET)

    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

