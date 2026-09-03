"""
SD-Karten-Verwaltung fuer Tonuino
Erkennt und verwaltet Tonuio-konforme SD-Karten
"""

import os
import re
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
    friendly_name: str = ""
    tracks: List[Track] = field(default_factory=list)
    cover_path: str = ""
    
    @property
    def display_name(self) -> str:
        """Lesbarer Name fuer die Anzeige"""
        if self.friendly_name:
            return f"{self.index:02d} - {self.friendly_name}"
        return f"Ordner {self.index:02d}"
    
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
        self._friendly_names: Dict[int, str] = {}
        
    def scan(self) -> bool:
        """Scannt die SD-Karte und erkennt Tonuio-Struktur"""
        if not self.path.exists():
            return False
            
        self.is_valid_tonuino = self._detect_tonuino_structure()
        self._load_friendly_names()
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
                path=str(item),
                friendly_name=self._friendly_names.get(folder_index, "")
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
    
    def _load_friendly_names(self):
        """Laedt freundliche Namen aus der Konfigurationsdatei"""
        self._friendly_names.clear()
        
        config_file = self.path / "friendly_names.txt"
        if not config_file.exists():
            return
            
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        idx_str, name = line.split(':', 1)
                        try:
                            idx = int(idx_str.strip())
                            self._friendly_names[idx] = name.strip()
                        except ValueError:
                            continue
        except Exception:
            pass
    
    def save_friendly_name(self, folder_index: int, name: str):
        """Speichert einen freundlichen Namen fuer einen Ordner"""
        self._friendly_names[folder_index] = name
        
        if folder_index in self.folders:
            self.folders[folder_index].friendly_name = name
        
        self._save_friendly_names()
    
    def _save_friendly_names(self):
        """Speichert alle freundliche Namen"""
        config_file = self.path / "friendly_names.txt"
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                for idx, name in sorted(self._friendly_names.items()):
                    f.write(f"{idx:02d}:{name}\n")
        except Exception as e:
            raise IOError(f"Fehler beim Speichern der Namen: {e}")
    
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
    
    @property
    def folder_count(self) -> int:
        return len(self.folders)
    
    @property
    def total_tracks(self) -> int:
        return sum(f.track_count for f in self.folders.values())
