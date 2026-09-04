# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec-Datei fuer Tonuino-Manager

Funktioniert plattformuebergreifend (Windows/Linux/macOS), muss aber auf jeder
Zielplattform separat gebaut werden - PyInstaller kompiliert nicht ueber
Plattformgrenzen hinweg (ein Windows-Build erzeugt keine Linux/macOS-Binary
und umgekehrt).
"""

import re
import sys
from pathlib import Path

import imageio_ffmpeg

block_cipher = None

# Einzige Quelle fuer die Versionsnummer (siehe src/core/__init__.py) - wird
# unten fuer den CFBundleVersion/CFBundleShortVersionString der macOS-App
# gebraucht (PyInstaller kompiliert build_exe.py's get_version() hier nicht
# mit, daher die eigene, minimale Regex-Lektuere).
def _get_version() -> str:
    init_file = Path('src/core/__init__.py').read_text(encoding='utf-8')
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_file)
    return match.group(1) if match else '0.0.0'

# .ico ist ein Windows-Format (Multi-Resolution-Icon fuer die EXE), .icns das
# macOS-Pendant fuer die App-Bundle. Auf Linux ignoriert PyInstaller den
# icon-Parameter fuer EXE() ohnehin (ELF-Binaries betten keine Icons ein - die
# Desktop-Integration erfolgt stattdessen ueber eine .desktop-Datei +
# icon.png, siehe build_exe.py).
if sys.platform == 'win32':
    _icon = 'src/resources/icon.ico'
elif sys.platform == 'darwin':
    _icon = 'src/resources/icon.icns'
else:
    _icon = None

# Gebuendeltes FFmpeg (aus imageio-ffmpeg) mit ausliefern, damit die EXE ohne
# separat installiertes FFmpeg funktioniert. Der Zielpfad spiegelt die
# Paketstruktur, damit imageio_ffmpeg.get_ffmpeg_exe() es zur Laufzeit wiederfindet.
_ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

# WICHTIG: 'src' steht in pathex, NICHT nur in datas. main.py importiert
# "from gui.main_window import MainWindow" erst nach einem sys.path-Trick zur
# Laufzeit - ohne pathex wuerde PyInstallers statische Analyse diesen Import
# nie aufloesen und dadurch auch nie in gui/core hineinschauen. Die Folge waere,
# dass saemtliche dortigen Importe (PIL, mutagen, smartcard, sogar
# Standardbibliotheks-Module wie configparser) im Build fehlen, da sie nirgends
# im Analyse-Graph auftauchen. Mit pathex=['src'] loest PyInstaller den Import
# ganz normal auf und verfolgt automatisch alle echten Importe von dort aus.
a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/resources', 'src/resources'),
        (_ffmpeg_exe, 'imageio_ffmpeg/binaries'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Tonuino-Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

# Auf macOS wird zusaetzlich eine .app-Bundle gebraucht (das reine EXE()-Binary
# waere nur ein Unix-Kommandozeilenprogramm, kein per Doppelklick startbares,
# im Finder/Dock erkennbares Programm mit eigenem Icon). Unsigned - fuer eine
# spaetere Codesignatur/Notarisierung (Voraussetzung fuer Verteilung ausserhalb
# des eigenen Rechners ohne Gatekeeper-Warnung) waere ein Apple Developer
# Account noetig, der hier nicht vorausgesetzt wird.
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='Tonuino-Manager.app',
        icon=_icon,
        bundle_identifier='de.tonuino-manager.app',
        info_plist={
            'CFBundleName': 'Tonuino-Manager',
            'CFBundleDisplayName': 'Tonuino-Manager',
            'CFBundleVersion': _get_version(),
            'CFBundleShortVersionString': _get_version(),
            'NSHighResolutionCapable': True,
            'NSHumanReadableCopyright': 'Tonuino-Manager',
        },
    )
