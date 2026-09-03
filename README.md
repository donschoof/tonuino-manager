# Tonuino-Manager

Ein hübsches Windows-Tool zum Verwalten von Tonuio SD-Karten und RFID-Karten.

## Features

- **SD-Karten-Verwaltung**: Automatische Erkennung von Tonuio-Struktur
- **Audio-Konvertierung**: Unterstützt MP3, WAV, FLAC, OGG, AAC, WMA, M4A, OPUS
- **Metadaten-Editor**: ID3-Tags und Cover-Art bearbeiten
- **Freundliche Namen**: Ordner umbenennen ohne das Tonuio-Format zu verletzen
- **RFID-Programmierung**: Direkte Programmierung über ACR122U
- **Modernes UI**: Dark Theme mit anpassbarem Styling

## Installation

### Option 1: Als Python-Skript

1. Python 3.10+ installieren
2. FFmpeg installieren und zum PATH hinzufügen
3. Abhängigkeiten installieren:

```bash
pip install -r requirements.txt
```

4. Starten:

```bash
python main.py
```

### Option 2: Als EXE-Datei (standalone)

1. Python 3.10+ installieren
2. FFmpeg installieren und zum PATH hinzufügen
3. Doppelklick auf `Build_EXE.bat` oder im Terminal:

```bash
pip install -r requirements.txt
python build_exe.py
```

Die EXE-Datei befindet sich dann im `dist`-Ordner und kann ohne Python verwendet werden.

**Hinweis**: Die EXE benötigt trotzdem FFmpeg im System-PATH für die Audio-Konvertierung.

## SD-Karten-Format

Das Tool erwartet folgende Struktur auf der SD-Karte:

```
SD-Karte/
├── 01/              → Ordner 01 (z.B. "Bibi Blocksberg")
│   ├── 001.mp3      → Track 1
│   ├── 002.mp3      → Track 2
│   └── cover.jpg    → Cover-Bild (optional)
├── 02/              → Ordner 02
├── ...
├── admin/           → Admin-Ordner (wird ignoriert)
├── tonuio.cfg       → Konfigurationsdatei (optional)
└── friendly_names.txt  → Freundliche Namen (optional)
```

## Freundliche Namen

Die Datei `friendly_names.txt` erlaubt es, Ordner umbenennen ohne das Format zu verletzen:

```
01:Bibi Blocksberg
02:Die Biene Maja
03:Peter Pan
```

## RFID-Karten

Das Tool unterstützt MIFARE Classic 1K Karten über den ACR122U Reader.

## Lizenz

MIT License

