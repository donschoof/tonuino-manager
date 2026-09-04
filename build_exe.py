"""
Build-Skript fuer Tonuino-Manager
Erstellt eine standalone .exe Datei mit PyInstaller
"""

import subprocess
import sys
import os
import re
import shutil
from pathlib import Path


def get_version() -> str:
    """Liest die Versionsnummer aus src/core/__init__.py (einzige Quelle im
    Projekt). Liest den Text nur per Regex statt zu importieren, damit das
    Build-Skript nicht von den Laufzeit-Abhaengigkeiten (PyQt6 etc.) abhaengt."""
    init_file = Path("src/core/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_file)
    if not match:
        raise RuntimeError("Konnte __version__ nicht in src/core/__init__.py finden")
    return match.group(1)


def clean_build():
    """Raeumt alte Build-Ordner auf"""
    build_dir = Path("build")
    dist_dir = Path("dist")
    
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print("Build-Ordner geloescht")
    
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        print("Dist-Ordner geloescht")


def binary_name() -> str:
    """Name der von PyInstaller erzeugten Programmdatei (mit .exe unter
    Windows, ohne Endung unter Linux/macOS)"""
    return "Tonuino-Manager.exe" if sys.platform == "win32" else "Tonuino-Manager"


def create_exe():
    """Erstellt die Programmdatei mit PyInstaller (muss auf jeder Zielplattform
    separat ausgefuehrt werden - PyInstaller kompiliert nicht plattformuebergreifend)"""

    # Spec-Datei verwenden
    spec_file = "Tonuino-Manager.spec"

    args = [
        sys.executable, "-m", "PyInstaller",
        spec_file,
        "--clean",
        "--noconfirm",
    ]

    print("Erstelle Programmdatei...")
    print(f"Kommando: {' '.join(args)}")

    result = subprocess.run(args, capture_output=False)

    if result.returncode == 0:
        print("\n" + "="*50)
        print("ERFOLG! Programmdatei erstellt.")
        print("="*50)
        print(f"\nDie Datei befindet sich in: dist/{binary_name()}")
    else:
        print("\nFEHLER beim Erstellen der Programmdatei!")
        sys.exit(1)


def find_inno_setup_compiler() -> str:
    """Sucht den Inno Setup Kommandozeilen-Compiler (ISCC.exe)"""
    candidates = [
        shutil.which("ISCC"),
        shutil.which("ISCC.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def create_windows_installer():
    """Erstellt den Windows-Installer mit Inno Setup (registriert sich
    automatisch korrekt fuer 'Apps & Features' in den Windows-Einstellungen)"""
    iscc = find_inno_setup_compiler()
    if not iscc:
        print("\nHINWEIS: Inno Setup (ISCC.exe) wurde nicht gefunden - "
              "Installer wird uebersprungen.")
        print("Installierbar unter: https://jrsoftware.org/isdl.php")
        return

    version = get_version()
    print(f"Erstelle Installer mit Inno Setup (Version {version})...")
    result = subprocess.run(
        [iscc, f"/DMyAppVersion={version}", "installer.iss"],
        capture_output=False
    )

    if result.returncode == 0:
        print("\n" + "="*50)
        print("ERFOLG! Installer erstellt.")
        print("="*50)
        print(f"\nDer Installer befindet sich in: dist/Tonuino-Manager-{version}-Setup.exe")
    else:
        print("\nFEHLER beim Erstellen des Installers!")
        sys.exit(1)


def create_linux_package():
    """Erstellt ein .deb-Paket (Menueintrag, Icon-Integration, sauberes
    Deinstallieren via 'apt remove'/'dpkg -r') - analog zum Windows-Installer.

    Bewusst kein AppImage: dafuer muesste appimagetool separat heruntergeladen
    werden. dpkg-deb ist auf Debian/Ubuntu (und damit dem ubuntu-latest
    CI-Runner) bereits Teil des Basissystems, genauso wie Inno Setup bereits
    auf windows-latest vorinstalliert ist - kein zusaetzliches Tool noetig.
    Einschraenkung: laeuft nativ nur auf Debian/Ubuntu-basierten Distros."""
    dist_dir = Path("dist")
    exe_name = binary_name()
    version = get_version()
    package_name = "tonuino-manager"
    arch = "amd64"

    pkg_root = dist_dir / "deb-build"
    if pkg_root.exists():
        shutil.rmtree(pkg_root)

    bin_dir = pkg_root / "usr" / "bin"
    icon_dir = pkg_root / "usr" / "share" / "icons" / "hicolor" / "1024x1024" / "apps"
    desktop_dir = pkg_root / "usr" / "share" / "applications"
    debian_dir = pkg_root / "DEBIAN"
    for directory in (bin_dir, icon_dir, desktop_dir, debian_dir):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(dist_dir / exe_name, bin_dir / package_name)
    os.chmod(bin_dir / package_name, 0o755)

    icon_src = Path("src/resources/icon.png")
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dir / f"{package_name}.png")

    desktop_content = f"""[Desktop Entry]
Type=Application
Name=Tonuino-Manager
Comment=Tonuino SD-Karten und RFID-Karten verwalten
Exec={package_name}
Icon={package_name}
Terminal=false
Categories=AudioVideo;Audio;
"""
    (desktop_dir / f"{package_name}.desktop").write_text(desktop_content, encoding="utf-8")

    # Depends: pcscd/libpcsclite1 werden zur Laufzeit fuer den RFID-Zugriff
    # (PC/SC-Stack) benoetigt, nicht nur zum Bauen - apt installiert sie beim
    # Installieren des Pakets automatisch mit.
    control_content = f"""Package: {package_name}
Version: {version}
Section: sound
Priority: optional
Architecture: {arch}
Depends: pcscd, libpcsclite1
Maintainer: Tonuino-Manager <tonuino-manager@localhost>
Homepage: https://github.com/donschoof/tonuino-manager
Description: Tonuino SD-Karten und RFID-Karten verwalten
 Tonuino-Manager verwaltet SD-Karten (Ordner/Dateien fuer den DIY-Audio-
 Player Tonuino) und die zugehoerigen RFID-Karten.
"""
    (debian_dir / "control").write_text(control_content, encoding="utf-8")

    archive_name = f"{package_name}_{version}_{arch}.deb"
    archive_path = dist_dir / archive_name
    # --root-owner-group: setzt root:root-Eigentuemerschaft im Paket, ohne
    # dass der Build selbst als root laufen muss (wichtig fuer CI ohne sudo).
    result = subprocess.run(
        ["dpkg-deb", "--build", "--root-owner-group", str(pkg_root), str(archive_path)],
        capture_output=False,
    )
    shutil.rmtree(pkg_root)

    if result.returncode != 0:
        print("\nFEHLER beim Erstellen des .deb-Pakets!")
        sys.exit(1)

    print("\n" + "="*50)
    print("ERFOLG! Linux-Installer (.deb) erstellt.")
    print("="*50)
    print(f"\nPaket: dist/{archive_name}")
    print(f"Installation: sudo apt install ./{archive_name}")
    print(f"Deinstallation: sudo apt remove {package_name}")


if __name__ == "__main__":
    print("="*50)
    print(f"  Tonuino-Manager {get_version()} - Build")
    print("="*50)
    print()
    
    # Alten Build saeubern
    clean_build()

    # Programmdatei erstellen
    create_exe()

    # Plattformspezifische Paketierung
    if sys.platform == "win32":
        create_windows_installer()
    elif sys.platform.startswith("linux"):
        create_linux_package()
    else:
        print(f"\nHINWEIS: Keine Paketierung fuer Plattform '{sys.platform}' "
              "eingerichtet - nur die Programmdatei wurde erstellt.")

    print("\n" + "="*50)
    print("Build abgeschlossen!")
    print("="*50)
    print(f"\nSchau im 'dist'-Ordner nach den erzeugten Dateien ({binary_name()} und ggf. Installer/Paket).")
