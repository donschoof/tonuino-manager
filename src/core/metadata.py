"""
Metadaten-Verwaltung fuer Tonuino
Liest und schreibt ID3-Tags und Cover-Art
"""

from typing import Optional, Tuple
from dataclasses import dataclass
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
        return self.read_metadata_and_cover(filepath)[0]

    def read_metadata_and_cover(self, filepath: str) -> Tuple[TrackMetadata, Optional[bytes]]:
        """Liest Metadaten und rohe Cover-Daten (APIC) in einem Durchgang -
        die Datei wird nur einmal geoeffnet (auf einer SD-Karte ist jeder
        Zugriff teuer)."""
        metadata = TrackMetadata()
        cover_bytes = None

        if not self._mutagen_available:
            return metadata, cover_bytes

        try:
            audio = self._open_mp3(filepath)

            if audio.info:
                metadata.duration = audio.info.length

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

                for key in tags.keys():
                    if key.startswith('APIC'):
                        metadata.has_cover = True
                        metadata.cover_mime = tags[key].mime
                        cover_bytes = tags[key].data
                        break

        except Exception as e:
            print(f"Fehler beim Lesen der Metadaten: {e}")

        return metadata, cover_bytes

    def write_metadata(
        self,
        filepath: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        album_artist: Optional[str] = None,
        track_number: Optional[int] = None,
        total_tracks: int = 0,
        genre: Optional[str] = None,
        year: Optional[str] = None
    ) -> bool:
        """Schreibt Metadaten in eine MP3-Datei.

        None = Feld unveraendert lassen, leerer String (bzw. Tracknummer 0) =
        vorhandenen Tag entfernen, sonst Tag setzen."""
        if not self._mutagen_available:
            return False

        try:
            from mutagen.id3 import TIT2, TPE1, TALB, TPE2, TRCK, TCON, TDRC

            audio = self._open_mp3(filepath)

            # ID3-Tags erstellen falls nicht vorhanden
            if audio.tags is None:
                audio.add_tags()

            tags = audio.tags

            def apply(key, frame_cls, value):
                if value is None:
                    return
                if value:
                    tags[key] = frame_cls(encoding=3, text=value)
                else:
                    tags.delall(key)

            apply("TIT2", TIT2, title)
            apply("TPE1", TPE1, artist)
            apply("TALB", TALB, album)
            apply("TPE2", TPE2, album_artist)
            if track_number is not None:
                if track_number > 0:
                    text = f"{track_number}/{total_tracks}" if total_tracks > 0 else str(track_number)
                    tags["TRCK"] = TRCK(encoding=3, text=text)
                else:
                    tags.delall("TRCK")
            apply("TCON", TCON, genre)
            apply("TDRC", TDRC, year)

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

    def set_cover(self, filepath: str, cover_path: str) -> bool:
        """Setzt das Cover fuer eine MP3-Datei"""
        if not self._mutagen_available:
            return False
        
        try:
            from mutagen.id3 import APIC

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
    