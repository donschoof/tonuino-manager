# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec-Datei fuer Tonuino SD-Manager
"""

import imageio_ffmpeg

block_cipher = None

# Gebuendeltes FFmpeg (aus imageio-ffmpeg) mit ausliefern, damit die EXE ohne
# separat installiertes FFmpeg funktioniert. Der Zielpfad spiegelt die
# Paketstruktur, damit imageio_ffmpeg.get_ffmpeg_exe() es zur Laufzeit wiederfindet.
_ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src', 'src'),
        (_ffmpeg_exe, 'imageio_ffmpeg/binaries'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'mutagen',
        'PIL',
        'smartcard',
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
    name='TonuinoSDManager',
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
)
