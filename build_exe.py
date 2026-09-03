"""
Build-Skript fuer Tonuino SD-Manager
Erstellt eine standalone .exe Datei mit PyInstaller
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path


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
    spec_file = "TonuinoSDManager.spec"
    
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
        print("\nDie EXE-Datei befindet sich in: dist/TonuinoSDManager.exe")
    else:
        print("\nFEHLER beim Erstellen der EXE-Datei!")
        sys.exit(1)


def copy_additional_files():
    """Kopiert zusaetzliche Dateien in den dist-Ordner"""
    dist_dir = Path("dist")
    
    # README kopieren
    if Path("README.md").exists():
        shutil.copy2("README.md", dist_dir / "README.md")
        print("README.md kopiert")
    
    # Leere resources-Ordner erstellen falls nicht vorhanden
    resources_dir = dist_dir / "resources"
    if not resources_dir.exists():
        resources_dir.mkdir()
        print("resources-Ordner erstellt")


if __name__ == "__main__":
    print("="*50)
    print("  Tonuino SD-Manager - Build")
    print("="*50)
    print()
    
    # Alten Build saeubern
    clean_build()
    
    # EXE erstellen
    create_exe()
    
    # Zusaetzliche Dateien
    copy_additional_files()
    
    
    print("\n" + "="*50)
    print("Build abgeschlossen!")
    print("="*50)
    print("\nDu findest die EXE-Datei im 'dist'-Ordner.")
    print("Starte sie mit: dist/TonuinoSDManager.exe")
