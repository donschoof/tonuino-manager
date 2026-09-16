# Tonuino-Manager

**Version 1.2.4**

Ein hübsches Tool zum Verwalten von Tonuino SD-Karten und RFID-Karten.
<img width="1202" height="832" alt="image" src="https://github.com/user-attachments/assets/b4de6994-a1de-4682-bd77-5a0a43d3672a" />

**Plattformen**: Windows, Linux und macOS werden unterstützt und bei jedem Push/PR per CI gebaut und getestet ([.github/workflows/build.yml](.github/workflows/build.yml)).

## Features

- **SD-Karten-Verwaltung**: Automatische Erkennung der Tonuino-Ordnerstruktur, Ordner anlegen/löschen
- **Track-Verwaltung**: Tracks per Dateiauswahl hinzufügen, per Checkbox mehrfach löschen und per Auf/Ab-Buttons umsortieren – Dateien werden dabei automatisch lückenlos umbenannt (001.mp3, 002.mp3, …), wie von Tonuino benötigt
- **Audio-Konvertierung**: Unterstützt MP3, WAV, FLAC, OGG, AAC, WMA, M4A, OPUS – Konvertierung nach MP3 erfolgt automatisch über ein mitgeliefertes FFmpeg, keine separate Installation nötig
- **Metadaten-Editor**: ID3-Tags (Titel, Interpret, Album, Tracknummer, Genre, Jahr) direkt bearbeiten
- **Automatische Ordnernamen & Cover**: Ordnername wird aus dem Album-Tag des ersten Tracks abgeleitet, das Cover aus dem eingebetteten ID3-Cover-Art der Tracks
- **RFID-Programmierung**: Direkte Programmierung über den ACR122U-Reader – reguläre Ordnerkarten (mit Wiedergabemodus) und Admin-Karten, mit automatischer Kartentyp-Erkennung und Live-Status (Reader/Karte/Programmierstatus) in der Sidebar
- **Modernes UI**: Dark Theme mit eigenem App-Icon
- **Automatische Updates**: Prüft beim Start auf neue GitHub-Releases und zeigt einen Hinweis an

## Installation (für Endanwender)

Fertige Builds gibt es auf der [Releases-Seite](https://github.com/donschoof/tonuino-manager/releases/latest) – keine Python-Installation nötig.

| Betriebssystem | Datei | Hinweise |
| --- | --- | --- |
| Windows | `Tonuino-Manager-<Version>-Setup.exe` | Installer für `Program Files`, legt Startmenü-/optional Desktop-Verknüpfungen an, über *Einstellungen → Apps & Features* deinstallierbar |
| macOS | `Tonuino-Manager-<Version>.dmg` | Öffnen und `Tonuino-Manager.app` per Drag & Drop nach `/Applications` ziehen. Die App ist ad-hoc signiert (kein Apple Developer Account); beim ersten Start ist ein manueller Schritt nötig (siehe [macOS-Hinweis](#hinweis-zur-signatur-macos)) |
| Linux (Debian/Ubuntu-basiert) | `tonuino-manager_<Version>_amd64.deb` | `sudo apt install ./tonuino-manager_<Version>_amd64.deb`, Deinstallation über `sudo apt remove tonuino-manager` |

FFmpeg ist in allen drei Builds bereits enthalten, es muss nichts separat installiert werden.

Portable, nicht-installierte Programmdateien (z. B. für Linux-Distributionen ohne `apt`) lassen sich mit dem [lokalen Build](#eigene-builds-erzeugen) erzeugen.

### Hinweis zur Signatur (macOS)

Die App wird beim Bauen ad-hoc signiert (kostenlos, ohne Apple Developer Account) – das macht sie auf Apple Silicon überhaupt erst ausführbar (dort verweigert der Kernel unsignierten Code komplett), ersetzt aber keine echte Signatur mit Notarization. Beim ersten Start einer heruntergeladenen (Quarantäne-Flag gesetzte) Kopie zeigt Gatekeeper daher „‚Tonuino-Manager‘ ist beschädigt und sollte in den Papierkorb gelegt werden“ – das ist irreführend formuliert, liegt aber nicht an einer beschädigten Datei, sondern schlicht an der fehlenden Notarization (kostenpflichtiges Apple Developer Program, 99 $/Jahr, samt Einreichung bei Apple). Ein Rechtsklick → „Öffnen“ reicht bei dieser Meldung auf aktuellen macOS-Versionen nicht mehr aus; stattdessen im Terminal die Quarantäne entfernen:

```bash
xattr -cr /pfad/zu/Tonuino-Manager.app
```

Danach lässt sich die App normal per Doppelklick starten.

## Am Repo arbeiten (Entwicklung)

Für alle drei Betriebssysteme gilt: Python 3.10+ installieren, Repo klonen, danach in einem **virtuellen Environment** (venv) die Abhängigkeiten aus [requirements.txt](requirements.txt) installieren. Ein venv ist kein Extra-Schritt für Fortgeschrittene, sondern auf allen drei Plattformen empfehlenswert bzw. nötig, damit `pip install` nicht das System-Python verändert.

```bash
git clone https://github.com/donschoof/tonuino-manager.git
cd tonuino-manager
```

### Windows

```powershell
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Es werden keine zusätzlichen Systempakete benötigt (PC/SC-Unterstützung für den RFID-Reader ist Teil von Windows).

### Linux

Zusätzlich zu Python 3.10+ wird der PC/SC-Stack für den RFID-Reader, das Qt-„xcb“-Plattform-Plugin sowie die Laufzeit-Abhängigkeit von QtMultimedia (Audio-Player) benötigt (Debian/Ubuntu-Namen, für andere Distributionen entsprechend anpassen). `pyscard` wird beim `pip install` aus dem Quellcode gebaut, daher werden zusätzlich die PC/SC-Entwicklungsheader (`libpcsclite-dev`) sowie `swig` benötigt:

```bash
sudo apt install pcscd libpcsclite1 libpcsclite-dev swig \
  libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
  libxcb-xinerama0 libegl1 libpulse0
```

Auf aktuellen Debian/Ubuntu-Versionen verweigert `pip` die Installation direkt ins System (`error: externally-managed-environment`, siehe [PEP 668](https://peps.python.org/pep-0668/)) – ein venv ist hier also nicht nur empfohlen, sondern in der Regel erforderlich:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Alternativ kann die Prüfung mit `pip install --break-system-packages -r requirements.txt` umgangen werden (nicht empfohlen, da dabei System-Python-Pakete überschrieben werden können).

### macOS

`pyscard` wird auch auf macOS beim `pip install` aus dem Quellcode gebaut. Dafür werden die Xcode Command Line Tools sowie `swig` benötigt (nicht in macOS enthalten – anders als der PC/SC-Stack selbst, der für den RFID-Reader bereits Teil des Systems ist). Fehlt `swig`, bricht `pip install -r requirements.txt` beim Bauen von `pyscard` ab, und es scheint so, als würde gar nichts installiert werden, obwohl einzelne reine Python-Pakete (z. B. `PyQt6`) sich problemlos installieren lassen:

```bash
xcode-select --install
brew install swig
```

Danach wie gewohnt in einem venv installieren:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Eigene Builds erzeugen

Voraussetzung ist das [Entwicklungs-Setup](#am-repo-arbeiten-entwicklung) der jeweiligen Plattform (aktiviertes venv mit installierten Abhängigkeiten). `build_exe.py` erkennt das Betriebssystem automatisch und erzeugt die passende Programmdatei bzw. das passende Installationspaket im `dist`-Ordner. PyInstaller kompiliert nicht plattformübergreifend – der Build muss also auf jeder Zielplattform separat ausgeführt werden.

```bash
python build_exe.py
```

- **Windows**: `dist/Tonuino-Manager.exe` (portabel) sowie – falls [Inno Setup](https://jrsoftware.org/isdl.php) installiert ist – `dist/Tonuino-Manager-<Version>-Setup.exe`. Alternativ per Doppelklick auf `Build_EXE.bat`.
- **Linux**: `dist/Tonuino-Manager` (portabel) sowie `dist/tonuino-manager_<Version>_amd64.deb` (Debian/Ubuntu-basiert, benötigt `dpkg-deb`, i. d. R. bereits vorhanden). Auf nicht-Debian-basierten Distributionen (Fedora, Arch, …) lässt sich nur die portable Datei nutzen.
- **macOS**: `dist/Tonuino-Manager.app` sowie `dist/Tonuino-Manager-<Version>.dmg` (siehe [macOS-Hinweis](#hinweis-zur-signatur-macos) zur Gatekeeper-Warnung bei selbst gebauten, weitergegebenen Kopien).

Die Versionsnummer wird dabei automatisch aus [src/core/\_\_init\_\_.py](src/core/__init__.py) (`__version__`) übernommen.

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
