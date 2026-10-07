"""
Sicherheitspruefung des Laufwerks vor dem SD-Karte-bereinigen-Vorgang.
Bereinigen loescht unwiderruflich Dateien - diese Pruefung soll verhindern,
dass versehentlich ein falsch ausgewaehltes Laufwerk (z.B. eine interne
Festplatte statt der SD-Karte) getroffen wird.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

# Handelsuebliche Tonuino-SD-Karten sind bis 32GB gross. Hersteller rechnen in
# dezimalen GB (32e9 Bytes ~ 29.8 GiB formatiert), daher ist 32 GiB als
# Obergrenze grosszuegig genug fuer echte 32GB-Karten, faengt aber deutlich
# groessere Laufwerke (64GB+ Karten, interne Platten) zuverlaessig ab.
MAX_SD_CARD_BYTES = 32 * 1024 ** 3


def get_total_size(path) -> Optional[int]:
    """Liefert die Gesamtgroesse des Laufwerks, auf dem path liegt, in Bytes,
    oder None wenn sie nicht ermittelt werden konnte."""
    try:
        return shutil.disk_usage(path).total
    except OSError:
        return None


def is_removable_drive(path) -> Optional[bool]:
    """Prueft, ob path auf einem Wechseldatentraeger (SD-Kartenleser, USB)
    liegt. Gibt None zurueck, wenn sich das auf der aktuellen Plattform nicht
    zuverlaessig ermitteln laesst - dann darf der Aufrufer nicht blockieren,
    sondern nur warnen."""
    if sys.platform == "win32":
        return _is_removable_windows(path)
    if sys.platform.startswith("linux"):
        return _is_removable_linux(path)
    return None  # macOS u.a.: keine abhaengigkeitsfreie zuverlaessige Erkennung


def _is_removable_windows(path) -> Optional[bool]:
    import ctypes

    drive = Path(path).drive
    if not drive:
        return None

    DRIVE_UNKNOWN = 0
    DRIVE_NO_ROOT_DIR = 1
    DRIVE_REMOVABLE = 2

    drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
    if drive_type in (DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR):
        return None
    return drive_type == DRIVE_REMOVABLE


def _is_removable_linux(path) -> Optional[bool]:
    try:
        real_path = Path(path).resolve()

        best_mount, best_device = "", ""
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                device, mount_point = parts[0], parts[1].replace("\\040", " ")
                # Auf Pfadgrenzen vergleichen: "/mnt/sd" darf nicht fuer "/mnt/sdb/x" gelten
                mount = Path(mount_point)
                if (real_path == mount or mount in real_path.parents) and len(mount_point) > len(best_mount):
                    best_mount, best_device = mount_point, device

        if not best_device or not best_device.startswith("/dev/"):
            return None

        # Partition auf das uebergeordnete Blockgeraet abbilden: ueber sysfs, da
        # die Namensschemata (sdb1, mmcblk0p1, nvme0n1p1) sich nicht per
        # Zeichenregel trennen lassen - /sys/class/block/<partition>/.. ist die Platte.
        dev_name = os.path.basename(os.path.realpath(best_device))
        sys_entry = Path(f"/sys/class/block/{dev_name}")
        if not sys_entry.exists():
            return None
        disk_dir = sys_entry.resolve().parent if (sys_entry / "partition").exists() else sys_entry.resolve()

        removable_flag = disk_dir / "removable"
        if not removable_flag.exists():
            return None
        return removable_flag.read_text().strip() == "1"
    except OSError:
        return None
