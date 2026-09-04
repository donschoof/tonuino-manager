# Tonuino-Manager

**Version 1.1.0**

Ein hübsches Tool zum Verwalten von Tonuino SD-Karten und RFID-Karten.

**Plattformen**: Windows (Installer + portable EXE) und Linux (portable Programmdatei) werden unterstützt und per CI gebaut/getestet ([.github/workflows/build.yml](.github/workflows/build.yml)). macOS ist (noch) nicht eingerichtet.

## Features

- **SD-Karten-Verwaltung**: Automatische Erkennung der Tonuino-Ordnerstruktur, Ordner anlegen/löschen
- **Track-Verwaltung**: Tracks per Dateiauswahl hinzufügen, per Checkbox mehrfach löschen und per Auf/Ab-Buttons umsortieren – Dateien werden dabei automatisch lückenlos umbenannt (001.mp3, 002.mp3, …), wie von Tonuino benötigt
- **Audio-Konvertierung**: Unterstützt MP3, WAV, FLAC, OGG, AAC, WMA, M4A, OPUS – Konvertierung nach MP3 erfolgt automatisch über ein mitgeliefertes FFmpeg, keine separate Installation nötig
- **Metadaten-Editor**: ID3-Tags (Titel, Interpret, Album, Tracknummer, Genre, Jahr) direkt bearbeiten
- **Automatische Ordnernamen & Cover**: Ordnername wird aus dem Album-Tag des ersten Tracks abgeleitet, das Cover aus dem eingebetteten ID3-Cover-Art der Tracks
- **RFID-Programmierung**: Direkte Programmierung über den ACR122U-Reader – reguläre Ordnerkarten (mit Wiedergabemodus) und Admin-Karten, mit automatischer Kartentyp-Erkennung und Live-Status (Reader/Karte/Programmierstatus) in der Sidebar
- **Modernes UI**: Dark Theme mit eigenem App-Icon
- **Windows-Installer**: Optionaler Setup-Installer (Program Files, über „Apps & Features“ deinstallierbar) neben der portablen EXE

## Installation

### Option 1: Installer oder portable EXE (empfohlen)

Für Endanwender ohne Python-Installation:

- **Installer** (`Tonuino-Manager-Setup.exe`): führt durch die Installation nach `Program Files`, legt Start­menü-/optional Desktop-Verknüpfungen an und lässt sich über *Einstellungen → Apps → Apps & Features* wieder deinstallieren.
- **Portable EXE** (`Tonuino-Manager.exe`): keine Installation nötig, einfach starten. FFmpeg ist bereits eingebettet.

Beide Dateien werden mit `python build_exe.py` erzeugt (siehe unten) und landen im `dist`-Ordner.

### Option 2: Als Python-Skript

1. Python 3.10+ installieren
2. Abhängigkeiten installieren:

```bash
pip install -r requirements.txt
```

3. Starten:

```bash
python main.py
```

FFmpeg muss nicht separat installiert werden – das Paket `imageio-ffmpeg` bringt eine passende FFmpeg-Binary automatisch mit.

### Option 3: EXE / Installer selbst bauen

1. Python 3.10+ installieren
2. Für den Installer zusätzlich [Inno Setup](https://jrsoftware.org/isdl.php) installieren (optional – ohne Inno Setup wird nur die portable EXE erstellt)
3. Doppelklick auf `Build_EXE.bat` oder im Terminal:

```bash
pip install -r requirements.txt
python build_exe.py
```

Auf Windows liegen danach im `dist`-Ordner:

- `Tonuino-Manager.exe` – portabel, ohne Installation lauffähig
- `Tonuino-Manager-Setup.exe` – Installer (falls Inno Setup gefunden wurde)

Die Versionsnummer wird dabei automatisch aus `src/core/__init__.py` (`__version__`) übernommen.

### Linux

Zusätzlich zu Python 3.10+ und den pip-Abhängigkeiten wird der PC/SC-Stack für den RFID-Reader sowie das Qt-„xcb“-Plattform-Plugin benötigt (Debian/Ubuntu-Namen, für andere Distributionen entsprechend anpassen):

```bash
sudo apt install pcscd libpcsclite1 libxcb-cursor0
pip install -r requirements.txt
python build_exe.py
```

`build_exe.py` erkennt Linux automatisch und erzeugt statt des Windows-Installers:

- `dist/Tonuino-Manager` – die portable Programmdatei
- `dist/Tonuino-Manager-<Version>-linux-x86_64.tar.gz` – dieselbe Datei zusammen mit Icon und `.desktop`-Eintrag für die Desktop-Integration (z.B. nach `~/.local/share/applications/` kopieren)

Der Linux-Build wird bei jedem Push/PR automatisch per GitHub Actions gebaut **und** headless gestartet (siehe [.github/workflows/build.yml](.github/workflows/build.yml)), um fehlende Systembibliotheken frühzeitig zu erkennen.

## SD-Karten-Format

Das Tool erwartet folgende Struktur auf der SD-Karte:

```
SD-Karte/
├── 01/              → Ordner 01 (Name & Cover werden aus den ID3-Tags der Tracks ermittelt)
│   ├── 001.mp3      → Track 1
│   ├── 002.mp3      → Track 2
│   └── ...
├── 02/              → Ordner 02
├── ...
├── admin/           → Admin-Ordner (wird ignoriert)
└── tonuio.cfg       → Konfigurationsdatei (optional)
```

## Ordnernamen & Cover

Anzeigename und Cover eines Ordners werden **automatisch aus den ID3-Metadaten** des ersten Tracks (mit gesetztem Tag) ermittelt – ein manuelles Umbenennen der Ordner oder eine separate `cover.jpg` ist nicht mehr nötig:

- **Name**: aus dem Album-Tag (`TALB`) des ersten Tracks mit gesetztem Album-Namen; ohne passenden Tag wird als Fallback „Ordner NN“ angezeigt
- **Cover**: aus dem eingebetteten Cover-Art (`APIC`) des ersten Tracks mit Cover; als Fallback wird zusätzlich weiterhin eine `cover.jpg`/`cover.png`/`folder.jpg`/`folder.png`/`front.jpg`-Datei im Ordner unterstützt

Über den Metadaten-Editor (Doppelklick auf einen Track) oder per Klick auf das Cover-Bild lassen sich Album-Tag und Cover für die Tracks eines Ordners bequem setzen.

## RFID-Karten

Das Tool unterstützt MIFARE Mini, MIFARE Classic 1K/4K sowie MIFARE Ultralight/NTAG21x-Karten über den ACR122U-Reader. Der Kartentyp wird automatisch anhand der ATR erkannt, sodass beim Programmieren keine manuelle Auswahl nötig ist.

Programmierbar sind:

- **Ordnerkarten**: verknüpfen eine Karte mit einem Ordner und einem Wiedergabemodus (Hörspiel, Album, Party, Einzelner Track, Hörbuch)
- **Admin-Karten**: öffnen am TonUINO das Admin-Menü, sind keinem Ordner zugeordnet

## Lizenz

MIT License

Enthält [Material Icons](https://github.com/google/material-design-icons) (Apache License 2.0, siehe `src/resources/fonts/MaterialIcons-LICENSE.txt`) als gebündelte Icon-Schriftart – plattformneutrale Alternative zu den Windows-exklusiven Segoe Fluent Icons.
