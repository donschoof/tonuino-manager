"""
Audio-Konvertierung fuer Tonuino
Konvertiert verschiedene Audio-Formate nach MP3 via FFmpeg
"""

import subprocess
import shutil
import sys
from pathlib import Path
from typing import Optional, Callable
from enum import Enum


# Unter Windows sonst kurz aufblitzende Konsolenfenster bei jedem FFmpeg-Aufruf
# (die App laeuft als GUI ohne eigene Konsole).
_SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


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
                timeout=10,
                creationflags=_SUBPROCESS_FLAGS
            )
            self._available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._available = False
    
    @property
    def is_available(self) -> bool:
        """Gibt zurueck ob FFmpeg verfuegbar ist"""
        return self._available
    
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
            raise RuntimeError("FFmpeg ist nicht verfügbar")
        
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {input_path}")
        
        if input_path.suffix.lower() == '.mp3':
            shutil.copy2(input_path, output_path)
            if progress_callback:
                progress_callback(100.0)
            return True
        
        # Tags (Titel/Interpret/Album/...) und ein eingebettetes Cover werden
        # mitgenommen: ohne sie haetten konvertierte Tracks weder Namen noch Cover
        # (Ordnername und Ordner-Cover werden aus den Tags des Tracks gelesen).
        # "-map 0:v:0?" ist optional (kein Fehler, wenn die Quelle kein Bild hat);
        # "-c:v copy" uebernimmt das Bild unveraendert als ID3-APIC-Frame.
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-map", "0:a:0",
            "-map", "0:v:0?",
            "-codec:a", "libmp3lame",
            "-b:a", bitrate,
            "-ar", str(sample_rate),
            "-c:v", "copy",
            "-disposition:v:0", "attached_pic",
            "-map_metadata", "0",
            "-id3v2_version", "3",
            "-y",
            str(output_path)
        ]

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=_SUBPROCESS_FLAGS
            )
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100.0)
                return True
            else:
                raise RuntimeError(f"FFmpeg Fehler: {process.stderr}")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("Konvertierung abgebrochen (Timeout)")
    