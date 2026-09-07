"""
Update-Pruefung und -Download fuer Tonuino-Manager (GitHub Releases)
"""

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

GITHUB_API_URL = "https://api.github.com/repos/donschoof/tonuino-manager/releases/latest"
GITHUB_RELEASES_PAGE = "https://github.com/donschoof/tonuino-manager/releases/latest"
USER_AGENT = "Tonuino-Manager-UpdateChecker"
REQUEST_TIMEOUT = 10


@dataclass
class UpdateInfo:
    """Enthaelt die fuer ein verfuegbares Update noetigen Informationen"""
    version: str
    release_notes: str
    release_url: str
    asset_url: str
    asset_name: str
    asset_size: int


def parse_version(version: str) -> tuple:
    """Parst einen einfachen X.Y.Z-Versionsstring (optional mit 'v'-Prefix).
    Unparsbares liefert (0, 0, 0), damit Vergleiche nie eine Exception werfen -
    lieber "kein Update erkannt" als ein Crash beim Hintergrund-Check."""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def is_newer_version(remote: str, local: str) -> bool:
    """True, wenn die Remote-Version (z.B. Release-Tag) neuer als die lokale ist"""
    return parse_version(remote) > parse_version(local)


def _asset_pattern_for_platform() -> Optional[re.Pattern]:
    """Regex fuer den Installer-Asset-Namen der aktuellen Plattform - bewusst
    ein exakter Namens-Match (nicht nur Endung), damit z.B. die Windows-
    -portable.exe nie faelschlich als -Setup.exe erkannt wird."""
    if sys.platform.startswith("win"):
        return re.compile(r"^Tonuino-Manager-.*-Setup\.exe$")
    if sys.platform.startswith("linux"):
        return re.compile(r"^tonuino-manager_.*_amd64\.deb$")
    if sys.platform == "darwin":
        return re.compile(r"^Tonuino-Manager-.*\.dmg$")
    return None


def select_asset(assets: list) -> Optional[dict]:
    """Waehlt aus den Release-Assets das zur aktuellen Plattform passende
    Installer-Asset aus (nur Installer-Varianten, keine portablen Dateien)"""
    pattern = _asset_pattern_for_platform()
    if pattern is None:
        return None
    for asset in assets:
        if pattern.match(asset.get("name", "")):
            return asset
    return None


class UpdateChecker(QThread):
    """Prueft im Hintergrund, ob auf GitHub eine neuere Version verfuegbar ist.
    Schlaegt die Pruefung fehl (offline, Rate-Limit, kaputtes JSON, ...), wird
    das grundsaetzlich als 'kein Update' behandelt - ein Hintergrund-Check darf
    beim Start nie eine Fehlermeldung oder einen Crash verursachen."""

    update_available = pyqtSignal(object)  # UpdateInfo
    no_update = pyqtSignal()

    def __init__(self, current_version: str):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            request = urllib.request.Request(
                GITHUB_API_URL,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))

            tag = data.get("tag_name", "")
            if not tag or not is_newer_version(tag, self.current_version):
                self.no_update.emit()
                return

            asset = select_asset(data.get("assets", []))
            if asset is None:
                self.no_update.emit()
                return

            info = UpdateInfo(
                version=tag.lstrip("v"),
                release_notes=data.get("body", "") or "",
                release_url=data.get("html_url", GITHUB_RELEASES_PAGE),
                asset_url=asset["browser_download_url"],
                asset_name=asset["name"],
                asset_size=asset.get("size", 0),
            )
            self.update_available.emit(info)
        except Exception:
            self.no_update.emit()


class UpdateDownloader(QThread):
    """Laedt das Installer-Asset eines Updates in einen temporaeren Ordner
    herunter. Anders als UpdateChecker meldet dies Fehler sichtbar, da der
    Download eine bewusste Nutzeraktion ist."""

    progress = pyqtSignal(int, int)  # gelesene Bytes, Gesamtgroesse (0 = unbekannt)
    finished = pyqtSignal(str)  # lokaler Dateipfad
    error = pyqtSignal(str)

    def __init__(self, info: UpdateInfo):
        super().__init__()
        self.info = info
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        dest_path = os.path.join(tempfile.gettempdir(), self.info.asset_name)
        try:
            request = urllib.request.Request(
                self.info.asset_url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                total = int(response.headers.get("Content-Length", 0))
                read = 0
                with open(dest_path, "wb") as f:
                    while True:
                        if self._cancelled:
                            break
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        read += len(chunk)
                        self.progress.emit(read, total)

            if self._cancelled:
                os.remove(dest_path)
                return

            self.finished.emit(dest_path)
        except Exception as e:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            self.error.emit(str(e))
