"""
Audio-Konvertierung fuer Tonuino
Konvertiert verschiedene Audio-Formate nach MP3 via FFmpeg
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Callable
from enum import Enum


class AudioFormat(Enum):
    """Unterstuetzte Audio-Formate"""
    MP3 = "mp3"
    WAV = "wav"
    FLAC = "flac"
    OGG = "ogg"
    AAC = "aac"
    WMA = "wma"
    M4A = "m4a"
    OPUS = "opus"
    
    @classmethod
    def from_extension(cls, ext: str) -> Optional['AudioFormat']:
        """Erkennt das Format anhand der Dateiendung"""
        ext = ext.lower().lstrip('.')
        for fmt in cls:
            if fmt.value == ext:
                return fmt
        return None
    
    @classmethod
    def supported_extensions(cls) -> list:
        """Gibt alle unterstuetzten Dateiendungen zurueck"""
        return [f".{fmt.value}" for fmt in cls]


class AudioConverter:
    """Konvertiert Audio-Dateien nach MP3"""

    def __init__(self, ffmpeg_path: str = None):
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()
        self._verify_ffmpeg()

    @staticmethod
    def _find_ffmpeg() -> str:
        """Nutzt das mit der Anwendung gebuendelte FFmpeg (imageio-ffmpeg), falls
        vorhanden. Andernfalls wird auf ein FFmpeg im System-PATH zurueckgegriffen."""
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def _verify_ffmpeg(self):
        """Prueft ob FFmpeg verfuegbar ist"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            self._available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._available = False
    
    @property
    def is_available(self) -> bool:
        """Gibt zurueck ob FFmpeg verfuegbar ist"""
        return self._available
    
    def get_audio_info(self, filepath: str) -> dict:
        """Holt Informationen ueber eine Audio-Datei"""
        info = {
            'duration': 0.0,
            'bitrate': 0,
            'sample_rate': 0,
            'channels': 0,
            'format': ''
        }
        
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-i", filepath],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = result.stderr  # FFmpeg schreibt Info nach stderr
            
            # Parse Duration
            if 'Duration' in output:
                import re
                match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', output)
                if match:
                    h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
                    info['duration'] = h * 3600 + m * 60 + s
            
            # Parse Bitrate
            if 'bitrate' in output:
                import re
                match = re.search(r'bitrate: (\d+) kb/s', output)
                if match:
                    info['bitrate'] = int(match.group(1))
            
            # Parse Audio Stream
            if 'Audio:' in output:
                import re
                match = re.search(r'Audio: .+, (\d+) Hz, (.+),', output)
                if match:
                    info['sample_rate'] = int(match.group(1))
                    info['channels'] = match.group(2)
                    
        except Exception:
            pass
        
        return info
    
    def needs_conversion(self, filepath: str) -> bool:
        """Prueft ob eine Datei konvertiert werden muss"""
        ext = Path(filepath).suffix.lower()
        return ext != '.mp3'

    def convert_to_mp3(
        self,
        input_path: str,
        output_path: str,
        bitrate: str = "192k",
        sample_rate: int = 44100,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> bool:
        """
        Konvertiert eine Audio-Datei nach MP3
        """
        if not self._available:
            raise RuntimeError("FFmpeg ist nicht verfuegbar")
        
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {input_path}")
        
        if input_path.suffix.lower() == '.mp3':
            shutil.copy2(input_path, output_path)
            if progress_callback:
                progress_callback(100.0)
            return True
        
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-codec:a", "libmp3lame",
            "-b:a", bitrate,
            "-ar", str(sample_rate),
            "-map_metadata", "-1",
            "-y",
            str(output_path)
        ]
        
        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100.0)
                return True
            else:
                raise RuntimeError(f"FFmpeg Fehler: {process.stderr}")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("Konvertierung abgebrochen (Timeout)")
    
    def convert_with_metadata(
        self,
        input_path: str,
        output_path: str,
        title: str = "",
        artist: str = "",
        album: str = "",
        track_num: int = 0,
        cover_path: str = "",
        bitrate: str = "192k"
    ) -> bool:
        """
        Konvertiert eine Datei nach MP3 mit Metadaten
        """
        if not self._available:
            raise RuntimeError("FFmpeg ist nicht verfuegbar")
        
        input_path = Path(input_path)
        output_path = Path(output_path)
        temp_output = output_path.with_suffix('.temp.mp3')
        
        try:
            if not self.convert_to_mp3(str(input_path), str(temp_output), bitrate):
                return False
            
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, APIC
            
            audio = MP3(str(temp_output))
            
            if audio.tags is None:
                audio.add_tags()
            
            if title:
                audio.tags["TIT2"] = TIT2(encoding=3, text=title)
            if artist:
                audio.tags["TPE1"] = TPE1(encoding=3, text=artist)
            if album:
                audio.tags["TALB"] = TALB(encoding=3, text=album)
            if track_num > 0:
                audio.tags["TRCK"] = TRCK(encoding=3, text=str(track_num))
            
            if cover_path and Path(cover_path).exists():
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
            temp_output.rename(output_path)
            
            return True
            
        except Exception as e:
            if temp_output.exists():
                temp_output.unlink()
            raise RuntimeError(f"Konvertierungsfehler: {e}")
