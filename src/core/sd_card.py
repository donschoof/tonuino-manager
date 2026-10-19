"""
SD-Karten-Verwaltung fuer Tonuino
Erkennt und verwaltet Tonuio-konforme SD-Karten
"""

import os
import re
import shutil
import stat
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict


# Maximale Anzahl Tracks pro Ordner (TonUINO adressiert Tracks mit einem Byte)
MAX_TRACKS_PER_FOLDER = 255


@dataclass
class Track:
    """Repraesentiert einen einzelnen Track"""
    index: int
    filename: str
    filepath: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    has_cover: bool = False
    # Nummer so, wie sie im Dateinamen steht (z.B. "0007" in den Systemordnern);
    # leer bei normalen Ordnern, dort gilt der dreistellige Index
    number: str = ""

    @property
    def display_name(self) -> str:
        """Lesbarer Name fuer die Anzeige"""
        label = self.number or (f"{self.index:03d}" if self.index else "")
        if self.title and label:
            return f"{label} - {self.title}"
        if self.title:
            return self.title
        return self.filename


@dataclass
class Folder:
    """Repraesentiert einen Tonuio-Ordner (01-99) oder einen Tonuio-Systemordner
    (mp3/advert, dann ist index=None, name gesetzt und is_special=True)"""
    index: Optional[int]
    path: str
    tracks: List[Track] = field(default_factory=list)
    cover_path: str = ""
    name: Optional[str] = None
    is_special: bool = False

    @property
    def track_count(self) -> int:
        return len(self.tracks)


@dataclass
class PurgePreview:
    """Vorschau dessen, was SDCard.purge() entfernen wuerde - fuer die
    Bestaetigungsabfrage vor dem eigentlichen (unwiderruflichen) Bereinigen."""
    root_files: List[str] = field(default_factory=list)
    root_dirs: List[str] = field(default_factory=list)
    foreign_items_in_folders: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.root_files and not self.root_dirs and not self.foreign_items_in_folders


class SDCard:
    """Repraesentiert eine Tonuio SD-Karte"""

    FOLDER_PATTERN = re.compile(r'^(\d{2})$')
    TRACK_PATTERN = re.compile(r'^(\d{3})\.mp3$', re.IGNORECASE)
    LEADING_DIGITS = re.compile(r'^(\d+)')
    SPECIAL_FOLDER_NAMES = ("mp3", "advert")

    def __init__(self, path: str):
        self.path = Path(path)
        self.folders: Dict[int, Folder] = {}
        self.special_folders: Dict[str, Folder] = {}
        self.is_valid_tonuino = False

    def scan(self) -> bool:
        """Scannt die SD-Karte und erkennt Tonuio-Struktur"""
        if not self.path.exists():
            return False

        self.is_valid_tonuino = self._detect_tonuino_structure()
        self._scan_folders()

        return True
    
    def _detect_tonuino_structure(self) -> bool:
        """Erkennt ob die SD-Karte Tonuio-Struktur hat"""
        mp3_count = 0
        folder_count = 0

        for item in self.path.iterdir():
            if item.is_dir():
                if self.FOLDER_PATTERN.match(item.name) or item.name in self.SPECIAL_FOLDER_NAMES:
                    folder_count += 1
            elif item.suffix.lower() == '.mp3':
                mp3_count += 1

        return folder_count > 0 or mp3_count > 0

    def _scan_folders(self):
        """Scansi alle Tonuio-Ordner sowie die Tonuio-Systemordner (mp3/advert)"""
        self.folders.clear()
        self.special_folders.clear()

        for item in sorted(self.path.iterdir()):
            if not item.is_dir():
                continue

            if item.name in self.SPECIAL_FOLDER_NAMES:
                folder = Folder(
                    index=None,
                    path=str(item),
                    name=item.name,
                    is_special=True
                )

                self._scan_tracks(folder)
                self._find_folder_cover(folder)

                self.special_folders[item.name] = folder
                continue

            match = self.FOLDER_PATTERN.match(item.name)
            if not match:
                continue

            folder_index = int(match.group(1))

            folder = Folder(
                index=folder_index,
                path=str(item)
            )

            self._scan_tracks(folder)
            self._find_folder_cover(folder)

            self.folders[folder_index] = folder
    
    def _scan_special_tracks(self, folder: Folder):
        """Liest alle MP3-Dateien eines Systemordners (mp3/advert) ein. Dort gilt
        nicht das 3-stellige Schema der Ordner 01-99: Nummern sind 4-stellig, haben
        Luecken und teils Buchstaben im Namen (z.B. 0007_Intro.mp3). Fuehrende Ziffern
        ergeben die Nummer, Dateien ohne Ziffern stehen am Ende. Die Ordner werden
        nur angezeigt und abgespielt, nie umbenannt."""
        tracks = []
        for item in Path(folder.path).iterdir():
            if not item.is_file() or item.suffix.lower() != ".mp3" or self._is_appledouble(item.name):
                continue
            match = self.LEADING_DIGITS.match(item.name)
            tracks.append(Track(
                index=int(match.group(1)) if match else 0,
                filename=item.name,
                filepath=str(item),
                number=match.group(1) if match else "",
            ))
        tracks.sort(key=lambda t: (t.index == 0 and not t.number, t.index, t.filename.lower()))
        folder.tracks = tracks

    def _scan_tracks(self, folder: Folder):
        """Scansi alle Tracks in einem Ordner"""
        if folder.is_special:
            self._scan_special_tracks(folder)
            return

        folder_path = Path(folder.path)
        tracks = []
        
        for item in sorted(folder_path.iterdir()):
            if not item.is_file():
                continue
                
            match = self.TRACK_PATTERN.match(item.name)
            if not match:
                continue
            
            track_index = int(match.group(1))
            
            track = Track(
                index=track_index,
                filename=item.name,
                filepath=str(item)
            )
            
            tracks.append(track)
        
        folder.tracks = tracks
    
    def _find_folder_cover(self, folder: Folder):
        """Sucht nach einem Cover-Bild im Ordner"""
        cover_names = ['cover.jpg', 'cover.png', 'folder.jpg', 'folder.png', 'front.jpg']
        folder_path = Path(folder.path)
        
        for name in cover_names:
            cover_file = folder_path / name
            if cover_file.exists():
                folder.cover_path = str(cover_file)
                break
    
    def create_folder(self, folder_index: int) -> Folder:
        """Erstellt einen neuen Tonuio-Ordner"""
        if folder_index < 1 or folder_index > 99:
            raise ValueError("Ordner-Nummer muss zwischen 1 und 99 liegen")
            
        folder_name = f"{folder_index:02d}"
        folder_path = self.path / folder_name
        
        if folder_path.exists():
            raise FileExistsError(f"Ordner {folder_name} existiert bereits")
        
        folder_path.mkdir(parents=True)
        
        folder = Folder(index=folder_index, path=str(folder_path))
        self.folders[folder_index] = folder
        
        return folder
    
    def get_folder(self, index: int) -> Optional[Folder]:
        """Gibt einen Ordner zurueck"""
        return self.folders.get(index)

    def get_special_folder(self, name: str) -> Optional[Folder]:
        """Gibt einen Tonuio-Systemordner (mp3/advert) zurueck"""
        return self.special_folders.get(name)

    def get_any_folder(self, identity) -> Optional[Folder]:
        """Gibt einen Ordner unabhaengig davon zurueck, ob er ueber seine
        Nummer (int, normaler Ordner) oder seinen Namen (str, Systemordner
        mp3/advert) identifiziert wird"""
        if isinstance(identity, int):
            return self.folders.get(identity)
        return self.special_folders.get(identity)

    def delete_folder(self, folder_index: int):
        """Loescht einen Ordner samt Inhalt von der SD-Karte"""
        folder = self.folders.get(folder_index)
        if not folder:
            raise ValueError(f"Ordner {folder_index:02d} nicht gefunden")

        shutil.rmtree(folder.path)
        del self.folders[folder_index]

    def delete_tracks(self, folder: Folder, tracks_to_delete: List[Track]):
        """Loescht die angegebenen Tracks von der SD-Karte und benennt die
        verbleibenden Tracks anschliessend fortlaufend um (001.mp3, 002.mp3, ...),
        wie von Tonuino benoetigt (keine Luecken in der Nummerierung)."""
        delete_paths = {t.filepath for t in tracks_to_delete}

        for track in tracks_to_delete:
            Path(track.filepath).unlink(missing_ok=True)

        remaining = [t for t in folder.tracks if t.filepath not in delete_paths]
        self.close_track_gaps(folder, remaining)

    @classmethod
    def _rename_second_step(cls, temp_paths: List[Path], finals: List[Path], originals: List[Path]):
        """Zweiter Umbenennungsschritt (temporaer -> final). Bei einem Fehler
        gehen alle Eintraege zurueck auf ihre urspruenglichen Namen."""
        try:
            cls._rename_all_or_restore(temp_paths, finals)
        except OSError:
            for temp_path, original in zip(temp_paths, originals):
                try:
                    temp_path.rename(original)
                except OSError:
                    pass
            raise

    @staticmethod
    def _rename_all_or_restore(sources: List[Path], targets: List[Path]):
        """Benennt sources[i] -> targets[i] um. Schlaegt eine Umbenennung fehl,
        werden die bereits umbenannten Eintraege zurueckbenannt und der Fehler
        weitergereicht."""
        done = []
        try:
            for index, (source, target) in enumerate(zip(sources, targets)):
                source.rename(target)
                done.append(index)
        except OSError:
            for index in reversed(done):
                try:
                    targets[index].rename(sources[index])
                except OSError:
                    pass
            raise

    def reorder_tracks(self, folder: Folder, new_order: List[Track]):
        """Bringt die Tracks eines Ordners in die angegebene Reihenfolge und
        benennt die Dateien entsprechend fortlaufend um (001.mp3, 002.mp3, ...).
        Wird sowohl nach dem Loeschen als auch nach manuellem Umsortieren benutzt."""
        folder_path = Path(folder.path)

        # Schritt 1: alle betroffenen Dateien auf temporaere Namen umbenennen,
        # damit sich Ziel- und Quellname beim Umnummerieren nicht ueberschneiden
        # koennen (z.B. beim Vertauschen von 001.mp3 und 002.mp3).
        # Schritt 2: von den temporaeren Namen auf die finalen, luecken- und
        # kollisionsfreien Namen umbenennen.
        # Schlaegt dabei etwas fehl (Karte gezogen, Sperre), werden die
        # Originalnamen soweit moeglich wiederhergestellt, statt .tmp_*-Dateien
        # liegen zu lassen.
        originals = [Path(t.filepath) for t in new_order]
        temp_paths = [folder_path / f".tmp_{t.filename}" for t in new_order]
        finals = [folder_path / f"{pos:03d}.mp3" for pos in range(1, len(new_order) + 1)]

        self._rename_all_or_restore(originals, temp_paths)
        self._rename_second_step(temp_paths, finals, originals)

        updated_tracks = []
        for position, (track, final_path) in enumerate(zip(new_order, finals), start=1):
            track.index = position
            track.filename = final_path.name
            track.filepath = str(final_path)
            updated_tracks.append(track)

        folder.tracks = updated_tracks

    @staticmethod
    def _is_gapless(tracks: List[Track]) -> bool:
        """True, wenn die Tracknummern lueckenlos bei 001 beginnen."""
        return [t.index for t in tracks] == list(range(1, len(tracks) + 1))

    @classmethod
    def has_track_gaps(cls, folder: Folder) -> bool:
        """True, wenn die Tracknummern des Ordners Luecken haben (z.B. 001, 003
        oder 002, 003)."""
        return not cls._is_gapless(folder.tracks)

    def close_track_gaps(self, folder: Folder, tracks: Optional[List[Track]] = None,
                         clear_conflicts: bool = False) -> bool:
        """Gemeinsamer Weg fuer alle Aktionen, die Luecken in der Tracknummerierung
        schliessen (Loeschen, Hinzufuegen, Verschieben ohne Wirkung, Bereinigen).
        `tracks` ist die gewuenschte Reihenfolge der verbleibenden Tracks
        (Standard: der Ordner nach bisheriger Nummer). Umbenannt wird nur, wenn
        wirklich Luecken da sind; sonst wird lediglich die Trackliste des Ordners
        aktualisiert. `clear_conflicts` raeumt vorab Fremdordner weg, die wie ein
        Ziel-Track heissen (z.B. "001.mp3/") und das Umbenennen blockieren
        wuerden - nur fuer das Bereinigen gedacht. Gibt zurueck, ob umbenannt wurde."""
        order = sorted(folder.tracks, key=lambda t: t.index) if tracks is None else list(tracks)

        if self._is_gapless(order):
            folder.tracks = order
            return False

        if clear_conflicts:
            for pos in range(1, len(order) + 1):
                target = Path(folder.path) / f"{pos:03d}.mp3"
                if target.is_dir():
                    self._force_rmtree(target)

        self.reorder_tracks(folder, order)
        return True

    def preview_purge(self) -> PurgePreview:
        """Ermittelt, was purge() entfernen wuerde, ohne dabei etwas zu
        loeschen - nutzt dieselbe Whitelist-Logik wie purge()."""
        allowed_dir = lambda name: bool(self.FOLDER_PATTERN.match(name)) or name in self.SPECIAL_FOLDER_NAMES

        preview = PurgePreview()

        for item in self.path.iterdir():
            if item.is_file():
                preview.root_files.append(item.name)
            elif item.is_dir() and not allowed_dir(item.name):
                preview.root_dirs.append(item.name)

        for item in self.path.iterdir():
            if not item.is_dir() or not allowed_dir(item.name):
                continue

            for child in item.iterdir():
                if child.is_dir() or self._is_appledouble(child.name) or child.suffix.lower() != ".mp3":
                    preview.foreign_items_in_folders += 1

        return preview

    @staticmethod
    def _is_appledouble(name: str) -> bool:
        """True fuer macOS-AppleDouble-Schattendateien (._001.mp3 usw.) - die
        sind trotz .mp3-Endung reiner Metadaten-Muell, nie echter Tonuio-Track."""
        return name.startswith("._")

    @staticmethod
    def _clear_readonly_and_retry(func, path, exc_info):
        """onerror-Handler fuer shutil.rmtree(): macOS setzt beim Beschreiben
        von FAT/exFAT-Karten (z.B. .Spotlight-V100, AppleDouble-Dateien) unter
        Windows oft das Nur-Lesen-Attribut. Ohne das zu entfernen schlaegt das
        Loeschen dort mit PermissionError fehl - mit ignore_errors=True bisher
        lautlos, die Datei/der Ordner blieb unbemerkt liegen."""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass

    @classmethod
    def _force_unlink(cls, path: Path):
        """Wie Path.unlink(missing_ok=True), aber entfernt bei Bedarf zuerst
        das Nur-Lesen-Attribut (siehe _clear_readonly_and_retry)."""
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            try:
                os.chmod(path, stat.S_IWRITE)
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def _force_rmtree(cls, path: Path):
        shutil.rmtree(path, onerror=cls._clear_readonly_and_retry)

    def _remove_foreign_items(self):
        """Entfernt alles, was nicht zur Tonuio-Struktur gehoert (Whitelist:
        Ordner 01-99, mp3, advert), inklusive Fremddateien innerhalb dieser
        Ordner. Wird sowohl vor als auch nach dem Umbenennen/Umnummerieren
        aufgerufen, da macOS auf Schreibvorgaenge (Renames) reagiert und dabei
        selbst neue Metadatendateien anlegt (z.B. .Spotlight-V100 oder
        AppleDouble-Schattendateien wie ._001.mp3 fuer jede umbenannte Datei)."""
        allowed_dir = lambda name: bool(self.FOLDER_PATTERN.match(name)) or name in self.SPECIAL_FOLDER_NAMES

        # Root-Ebene: lose Dateien loeschen, nicht erlaubte Verzeichnisse rekursiv loeschen
        for item in list(self.path.iterdir()):
            if item.is_file():
                self._force_unlink(item)
            elif item.is_dir() and not allowed_dir(item.name):
                self._force_rmtree(item)

        # Innerhalb erlaubter Verzeichnisse: alles ausser echten mp3-Dateien
        # entfernen - AppleDouble-Schattendateien (._*.mp3) zaehlen trotz
        # .mp3-Endung nicht als Track und werden immer entfernt.
        for item in self.path.iterdir():
            if not item.is_dir() or not allowed_dir(item.name):
                continue

            for child in item.iterdir():
                if child.is_dir():
                    self._force_rmtree(child)
                elif self._is_appledouble(child.name) or child.suffix.lower() != ".mp3":
                    self._force_unlink(child)

    def purge(self):
        """Entfernt alles von der SD-Karte, was nicht zur Tonuio-Struktur
        gehoert (Whitelist: Ordner 01-99, mp3, advert), raeumt Fremddateien
        auch innerhalb dieser Ordner auf und nummeriert die Tracks je Ordner
        anschliessend luecken- und kollisionsfrei durch. Die Ordnernummern
        bleiben dabei unveraendert, damit bereits programmierte RFID-Karten
        weiter auf den richtigen Ordner zeigen."""
        # 1. Zustand von der Karte einlesen. Fremddateien muessen dafuer nicht
        #    vorher weg: _scan_tracks() erkennt nur echte NNN.mp3-Dateien (keine
        #    AppleDouble-Dateien, keine Unterordner).
        self.scan()

        # 2. Numerierte Ordner ohne Tracks entfernen (samt Fremdinhalt); die
        #    uebrigen Ordner behalten ihre Nummer, auch wenn dadurch Luecken
        #    entstehen
        for idx in list(self.folders.keys()):
            if self.folders[idx].track_count == 0:
                self.delete_folder(idx)

        # 3. Verbleibende mp3s je numeriertem Ordner luecken- und kollisionsfrei
        #    durchnummerieren; nur Ordner mit Luecken werden umbenannt, die
        #    Systemordner mp3/advert bleiben unberuehrt
        for folder in self.folders.values():
            self.close_track_gaps(folder, clear_conflicts=True)

        # 4. Fremddateien/-ordner einmalig am Ende entfernen. Das Umbenennen in
        #    Schritt 3 kann macOS dazu bringen, fuer die umbenannten Dateien neue
        #    Metadatendateien anzulegen (siehe _remove_foreign_items) - ein
        #    Durchgang danach erfasst deshalb alles.
        self._remove_foreign_items()

    @property
    def folder_count(self) -> int:
        return len(self.folders)

    @property
    def total_tracks(self) -> int:
        return sum(f.track_count for f in self.folders.values())
