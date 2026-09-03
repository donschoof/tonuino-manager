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


def create_exe():
    """Erstellt die EXE mit PyInstaller"""

    # Spec-Datei verwenden
    spec_file = "Tonuino-Manager.spec"

    args = [
        sys.executable, "-m", "PyInstaller",
        spec_file,
        "--clean",
        "--noconfirm",
    ]

    print("Erstelle EXE-Datei...")
    print(f"Kommando: {' '.join(args)}")

    result = subprocess.run(args, capture_output=False)

    if result.returncode == 0:
        print("\n" + "="*50)
        print("ERFOLG! EXE-Datei erstellt.")
        print("="*50)
        print("\nDie EXE-Datei befindet sich in: dist/Tonuino-Manager.exe")
    else:
        print("\nFEHLER beim Erstellen der EXE-Datei!")
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


def create_installer():
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


if __name__ == "__main__":
    print("="*50)
    print(f"  Tonuino-Manager {get_version()} - Build")
    print("="*50)
    print()
    
    # Alten Build saeubern
    clean_build()

    # EXE erstellen
    create_exe()

    # Installer erstellen (falls Inno Setup verfuegbar ist)
    create_installer()

    print("\n" + "="*50)
    print("Build abgeschlossen!")
    print("="*50)
    print("\nIm 'dist'-Ordner findest du:")
    print("  - Tonuino-Manager.exe        (portable, ohne Installation lauffaehig)")
    print("  - Tonuino-Manager-Setup.exe  (Installer, ueber Windows-Einstellungen deinstallierbar)")
