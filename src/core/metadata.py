"""
Metadaten-Verwaltung fuer Tonuino
Liest und schreibt ID3-Tags und Cover-Art
"""

from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
from PIL import Image
import io
import time


@dataclass
class TrackMetadata:
    """Metadaten eines Tracks"""
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track_number: int = 0
    total_tracks: int = 0
    genre: str = ""
    year: str = ""
    duration: float = 0.0
    has_cover: bool = False
    cover_mime: str = ""


    def is_empty(self) -> bool:
        """Prueft ob Metadaten leer sind"""
        return not any([self.title, self.artist, self.album])


class MetadataManager:
    """Verwaltet MP3-Metadaten"""
    
    def __init__(self):
        self._mutagen_available = self._check_mutagen()
    
    def _check_mutagen(self) -> bool:
        """Prueft ob mutagen verfuegbar ist"""
        try:
            import mutagen
            return True
        except ImportError:
            return False

    @staticmethod
    def _open_mp3(filepath: str, attempts: int = 4, delay: float = 0.15):
        """Oeffnet eine MP3-Datei, mit Retry bei kurzzeitigen Zugriffssperren
        (z.B. durch Virenscanner oder Windows-Indexer auf Wechseldatentraegern)"""
        from mutagen.mp3 import MP3

        last_error = None
        for attempt in range(attempts):
            try:
                return MP3(filepath)
            except PermissionError as e:
                last_error = e
                if attempt < attempts - 1:
                    time.sleep(delay)
        raise last_error

    def read_metadata(self, filepath: str) -> TrackMetadata:
        """Liest Metadaten aus einer MP3-Datei"""
        metadata = TrackMetadata()
        
        if not self._mutagen_available:
            return metadata
        
        try:
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TCON, TDRC, APIC

            audio = self._open_mp3(filepath)

            # Laenge
            if audio.info:
                metadata.duration = audio.info.length
            
            # ID3-Tags
            if audio.tags:
                tags = audio.tags
                
                if 'TIT2' in tags:
                    metadata.title = str(tags['TIT2'])
                if 'TPE1' in tags:
                    metadata.artist = str(tags['TPE1'])
                if 'TALB' in tags:
                    metadata.album = str(tags['TALB'])
                if 'TPE2' in tags:
                    metadata.album_artist = str(tags['TPE2'])
                if 'TRCK' in tags:
                    track_str = str(tags['TRCK'])
                    if '/' in track_str:
                        parts = track_str.split('/')
                        metadata.track_number = int(parts[0]) if parts[0].isdigit() else 0
                        metadata.total_tracks = int(parts[1]) if parts[1].isdigit() else 0
                    elif track_str.isdigit():
                        metadata.track_number = int(track_str)
                if 'TCON' in tags:
                    metadata.genre = str(tags['TCON'])
                if 'TDRC' in tags:
                    metadata.year = str(tags['TDRC'])[:4]
                
                # Cover
                for key in tags.keys():
                    if key.startswith('APIC'):
                        metadata.has_cover = True
                        metadata.cover_mime = tags[key].mime
                        break
                        
        except Exception as e:
            print(f"Fehler beim Lesen der Metadaten: {e}")
        
        return metadata
    
    def write_metadata(
        self,
        filepath: str,
        title: str = "",
        artist: str = "",
        album: str = "",
        album_artist: str = "",
        track_number: int = 0,
        total_tracks: int = 0,
        genre: str = "",
        year: str = ""
    ) -> bool:
        """Schreibt Metadaten in eine MP3-Datei"""
        if not self._mutagen_available:
            return False
        
        try:
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TCON, TDRC

            audio = self._open_mp3(filepath)

            # ID3-Tags erstellen falls nicht vorhanden
            if audio.tags is None:
                audio.add_tags()
            
            tags = audio.tags
            
            if title:
                tags["TIT2"] = TIT2(encoding=3, text=title)
            if artist:
                tags["TPE1"] = TPE1(encoding=3, text=artist)
            if album:
                tags["TALB"] = TALB(encoding=3, text=album)
            if album_artist:
                tags["TPE2"] = TPE2(encoding=3, text=album_artist)
            if track_number > 0:
                if total_tracks > 0:
                    tags["TRCK"] = TRCK(encoding=3, text=f"{track_number}/{total_tracks}")
                else:
                    tags["TRCK"] = TRCK(encoding=3, text=str(track_number))
            if genre:
                tags["TCON"] = TCON(encoding=3, text=genre)
            if year:
                tags["TDRC"] = TDRC(encoding=3, text=year)
            
            audio.save()
            return True
            
        except Exception as e:
            print(f"Fehler beim Schreiben der Metadaten: {e}")
            return False

    def get_cover_bytes(self, filepath: str) -> Optional[bytes]:
        """Gibt die rohen Cover-Bilddaten (APIC) einer MP3-Datei zurueck, falls vorhanden"""
        if not self._mutagen_available:
            return None

        try:
            audio = self._open_mp3(filepath)

            if audio.tags:
                for key in audio.tags.keys():
                    if key.startswith('APIC'):
                        return audio.tags[key].data

            return None

        except Exception as e:
            print(f"Fehler beim Lesen des Covers: {e}")
            return None

    def extract_cover(self, filepath: str, output_path: str) -> bool:
        """Extrahiert das Cover aus einer MP3-Datei"""
        if not self._mutagen_available:
            return False
        
        try:
            from mutagen.id3 import APIC

            audio = self._open_mp3(filepath)

            if audio.tags:
                for key in audio.tags.keys():
                    if key.startswith('APIC'):
                        cover_data = audio.tags[key].data
                        with open(output_path, 'wb') as f:
                            f.write(cover_data)
                        return True
            
            return False
            
        except Exception as e:
            print(f"Fehler beim Extrahieren des Covers: {e}")
            return False
    
    def get_cover_image(self, filepath: str, max_size: Tuple[int, int] = (300, 300)) -> Optional[Image.Image]:
        """Gibt das Cover als PIL Image zurueck"""
        if not self._mutagen_available:
            return None
        
        try:
            from mutagen.id3 import APIC

            audio = self._open_mp3(filepath)

            if audio.tags:
                for key in audio.tags.keys():
                    if key.startswith('APIC'):
                        cover_data = audio.tags[key].data
                        image = Image.open(io.BytesIO(cover_data))
                        image.thumbnail(max_size, Image.Resampling.LANCZOS)
                        return image
            
            return None
            
        except Exception as e:
            print(f"Fehler beim Laden des Covers: {e}")
            return None
    
    def set_cover(self, filepath: str, cover_path: str) -> bool:
        """Setzt das Cover fuer eine MP3-Datei"""
        if not self._mutagen_available:
            return False
        
        try:
            from mutagen.id3 import ID3, APIC

            audio = self._open_mp3(filepath)

            if audio.tags is None:
                audio.add_tags()

            keys_to_remove = [key for key in audio.tags.keys() if key.startswith('APIC')]
            for key in keys_to_remove:
                del audio.tags[key]

            with open(cover_path, 'rb') as f:
                cover_data = f.read()
            
            mime = 'image/jpeg' if cover_path.lower().endswith('.jpg') else 'image/png'
            
            audio.tags["APIC"] = APIC(
                encoding=3,
                mime=mime,
                type=3,
                desc='Cover',
                data=cover_data
            )
            
            audio.save()
            return True
            
        except Exception as e:
            print(f"Fehler beim Setzen des Covers: {e}")
            return False
    
    def remove_cover(self, filepath: str) -> bool:
        """Entfernt das Cover aus einer MP3-Datei"""
        if not self._mutagen_available:
            return False
        
        try:
            audio = self._open_mp3(filepath)

            if audio.tags:
                keys_to_remove = [key for key in audio.tags.keys() if key.startswith('APIC')]
                for key in keys_to_remove:
                    del audio.tags[key]
                audio.save()
            
            return True
            
        except Exception as e:
            print(f"Fehler beim Entfernen des Covers: {e}")
            return False
    
    @staticmethod
    def create_thumbnail(image_path: str, output_path: str, size: Tuple[int, int] = (150, 150)) -> bool:
        """Erstellt ein Thumbnail eines Bildes"""
        try:
            with Image.open(image_path) as img:
                img.thumbnail(size, Image.Resampling.LANCZOS)
                img.save(output_path)
            return True
        except Exception as e:
            print(f"Fehler beim Erstellen des Thumbnails: {e}")
            return False
