"""
Tonuino SD-Karten Manager
Ein hübsches Tool zum Verwalten von Tonuino SD-Karten und RFID-Karten.
"""

import sys
import os

# PyInstaller-Kompatibilitaet
if getattr(sys, 'frozen', False):
    # Lauft als kompilierte EXE
    script_dir = os.path.dirname(sys.executable)
    src_dir = os.path.join(script_dir, 'src')
else:
    # Lauft als Python-Skript
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(script_dir, 'src')

# Fuege src zum Python-Pfad hinzu
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.main_window import MainWindow


def main():
    # High DPI Skalierung aktivieren
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication(sys.argv)
    app.setApplicationName("Tonuino SD-Manager")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("TonuinoManager")
    
    # Stylesheet laden
    from gui.styles import MAIN_STYLESHEET
    app.setStyleSheet(MAIN_STYLESHEET)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

