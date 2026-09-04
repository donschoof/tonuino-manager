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
        print("\nDer Installer befindet sich in: dist/Tonuino-Manager-Setup.exe")
    else:
        print("\nFEHLER beim Erstellen des Installers!")
        sys.exit(1)


def create_linux_package():
    """Erstellt eine .desktop-Datei fuer die Desktop-Integration und packt
    Programmdatei + Icon + .desktop-Datei in ein portables .tar.gz.

    Bewusst kein AppImage/.deb/.rpm: diese Tools sind selbst nicht ueber pip
    installierbar und muessten separat auf der Build-Maschine vorhanden sein
    (aehnlich wie Inno Setup unter Windows) - das .tar.gz funktioniert ohne
    weitere Abhaengigkeiten auf jeder Linux-Distribution."""
    import tarfile

    dist_dir = Path("dist")
    exe_name = binary_name()
    version = get_version()

    desktop_content = f"""[Desktop Entry]
Type=Application
Name=Tonuino-Manager
Comment=Tonuino SD-Karten und RFID-Karten verwalten
Exec={exe_name}
Icon=icon
Terminal=false
Categories=AudioVideo;Audio;
"""
    desktop_file = dist_dir / "tonuino-manager.desktop"
    desktop_file.write_text(desktop_content, encoding="utf-8")
    print("tonuino-manager.desktop erstellt")

    icon_src = Path("src/resources/icon.png")
    if icon_src.exists():
        shutil.copy2(icon_src, dist_dir / "icon.png")
        print("icon.png kopiert")

    archive_name = f"Tonuino-Manager-{version}-linux-x86_64.tar.gz"
    archive_path = dist_dir / archive_name
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(dist_dir / exe_name, arcname=exe_name)
        tar.add(desktop_file, arcname="tonuino-manager.desktop")
        if icon_src.exists():
            tar.add(dist_dir / "icon.png", arcname="icon.png")

    print("\n" + "="*50)
    print("ERFOLG! Linux-Paket erstellt.")
    print("="*50)
    print(f"\nArchiv: dist/{archive_name}")
    print("Enthaelt die Programmdatei, ein Icon und eine .desktop-Datei fuer")
    print("die Desktop-Integration (z.B. nach ~/.local/share/applications/")
    print("kopieren, Programmdatei ausfuehrbar machen: chmod +x).")
    print("\nHinweis: Fuer RFID-Support wird der PC/SC-Daemon benoetigt:")
    print("  sudo apt install pcscd libpcsclite1")


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
