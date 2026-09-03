"""
SD-Karten-Verwaltung fuer Tonuino
Erkennt und verwaltet Tonuio-konforme SD-Karten
"""

import os
import re
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict


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
    
    @property
    def display_name(self) -> str:
        """Lesbarer Name fuer die Anzeige"""
        if self.title:
            return f"{self.index:03d} - {self.title}"
        return self.filename


@dataclass
class Folder:
    """Repraesentiert einen Tonuio-Ordner (01-99)"""
    index: int
    path: str
    tracks: List[Track] = field(default_factory=list)
    cover_path: str = ""

    @property
    def track_count(self) -> int:
        return len(self.tracks)


class SDCard:
    """Repraesentiert eine Tonuio SD-Karte"""
    
    FOLDER_PATTERN = re.compile(r'^(\d{2})$')
    TRACK_PATTERN = re.compile(r'^(\d{3})\.mp3$', re.IGNORECASE)
    
    def __init__(self, path: str):
        self.path = Path(path)
        self.folders: Dict[int, Folder] = {}
        self.config_path = self.path / "tonuio.cfg"
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
                if self.FOLDER_PATTERN.match(item.name):
                    folder_count += 1
            elif item.suffix.lower() == '.mp3':
                mp3_count += 1
        
        return folder_count > 0 or mp3_count > 0
    
    def _scan_folders(self):
        """Scansi alle Tonuio-Ordner"""
        self.folders.clear()
        
        for item in sorted(self.path.iterdir()):
            if not item.is_dir():
                continue
                
            match = self.FOLDER_PATTERN.match(item.name)
            if not match:
                continue
                
            folder_index = int(match.group(1))
            
            if item.name.lower() == "admin":
                continue
            
            folder = Folder(
                index=folder_index,
                path=str(item)
            )
            
            self._scan_tracks(folder)
            self._find_folder_cover(folder)
            
            self.folders[folder_index] = folder
    
    def _scan_tracks(self, folder: Folder):
        """Scansi alle Tracks in einem Ordner"""
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
        self.reorder_tracks(folder, remaining)

    def reorder_tracks(self, folder: Folder, new_order: List[Track]):
        """Bringt die Tracks eines Ordners in die angegebene Reihenfolge und
        benennt die Dateien entsprechend fortlaufend um (001.mp3, 002.mp3, ...).
        Wird sowohl nach dem Loeschen als auch nach manuellem Umsortieren benutzt."""
        folder_path = Path(folder.path)

        # Schritt 1: alle betroffenen Dateien auf temporaere Namen umbenennen,
        # damit sich Ziel- und Quellname beim Umnummerieren nicht ueberschneiden
        # koennen (z.B. beim Vertauschen von 001.mp3 und 002.mp3).
        temp_paths = []
        for track in new_order:
            temp_path = folder_path / f".tmp_{track.filename}"
            Path(track.filepath).rename(temp_path)
            temp_paths.append(temp_path)

        # Schritt 2: von den temporaeren Namen auf die finalen, luecken- und
        # kollisionsfreien Namen umbenennen.
        updated_tracks = []
        for position, (track, temp_path) in enumerate(zip(new_order, temp_paths), start=1):
            final_name = f"{position:03d}.mp3"
            final_path = folder_path / final_name
            temp_path.rename(final_path)

            track.index = position
            track.filename = final_name
            track.filepath = str(final_path)
            updated_tracks.append(track)

        folder.tracks = updated_tracks

    @property
    def folder_count(self) -> int:
        return len(self.folders)

    @property
    def total_tracks(self) -> int:
        return sum(f.track_count for f in self.folders.values())
