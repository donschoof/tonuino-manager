"""
Update-Pruefung, Download und Start des Installers (GitHub Releases)
"""

import os
import subprocess
import sys
from typing import Optional

from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication, QWidget
from PyQt6.QtCore import QObject, QSettings, Qt

from core import __version__
from core.updater import UpdateChecker, UpdateDownloader, UpdateInfo, GITHUB_RELEASES_PAGE
from gui.update_dialog import UpdateDialog


class UpdateController(QObject):
    """Kapselt den gesamten Update-Ablauf; die Dialoge haengen am uebergebenen
    Fenster (parent_window)."""

    def __init__(self, parent_window: QWidget):
        super().__init__(parent_window)
        self._window = parent_window
        self._update_checker: Optional[UpdateChecker] = None
        self._update_downloader: Optional[UpdateDownloader] = None

    def shutdown(self):
        """Beim Schliessen des Hauptfensters: Download abbrechen, Pruefung auslaufen lassen"""
        if self._update_downloader is not None and self._update_downloader.isRunning():
            self._update_downloader.cancel()
            self._update_downloader.wait(3000)
        if self._update_checker is not None and self._update_checker.isRunning():
            self._update_checker.wait(3000)

    def check_on_startup(self):
        """Automatische Update-Pruefung beim Programmstart - nur, wenn im
        Hilfe-Menue nicht deaktiviert. Ohne Drosselung, da ein GitHub-API-
        Request beim Start keinen nennenswerten Traffic verursacht. Schlaegt
        die Pruefung fehl, bleibt das hier bewusst unbemerkt (siehe
        UpdateChecker) - anders als bei der manuellen Pruefung ueber das
        Menue soll ein Start nie mit einer Fehlermeldung unterbrochen werden."""
        if not QSettings().value("updater/auto_check_enabled", True, type=bool):
            return
        self._run_update_check(manual=False)

    def check_manual(self):
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
            self._window,
            "Kein Update verfügbar",
            f"Sie verwenden bereits die neueste Version ({__version__})."
        )

    def _on_manual_check_failed(self, message: str):
        QMessageBox.warning(
            self._window,
            "Update-Prüfung fehlgeschlagen",
            f"Die Prüfung auf Updates ist fehlgeschlagen:\n{message}"
        )

    def on_auto_check_toggled(self, checked: bool):
        QSettings().setValue("updater/auto_check_enabled", checked)

    def _on_update_available(self, info: UpdateInfo):
        settings = QSettings()

        if settings.value("updater/ignored_version", "", type=str) == info.version:
            return

        dialog = UpdateDialog(info, __version__, self._window)
        dialog.exec()

        if dialog.result_choice == UpdateDialog.UPDATE_NOW:
            self._start_update_download(info)
        elif dialog.result_choice == UpdateDialog.IGNORE:
            settings.setValue("updater/ignored_version", info.version)

    def _start_update_download(self, info: UpdateInfo):
        """Laedt den passenden Installer herunter, mit Fortschrittsanzeige"""
        self._update_download_dialog = QProgressDialog(
            f"Lade Update {info.version} herunter...", "Abbrechen", 0, 100, self._window
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
            self._window,
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
            self._window,
            "Manuelle Installation erforderlich",
            f"Die Installationsdatei wurde heruntergeladen nach:\n{filepath}\n\n"
            f"Bitte führen Sie die Datei manuell aus, oder laden Sie sie erneut "
            f"herunter unter:\n{GITHUB_RELEASES_PAGE}"
        )
