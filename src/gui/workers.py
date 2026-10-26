"""
Hintergrund-Threads des Tonuino-Managers (Scan, Dateiarbeit, RFID, Serial)
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.sd_card import SDCard, Folder, Track, MAX_TRACKS_PER_FOLDER
from core.audio_converter import AudioConverter
from core import loudness
from core.metadata import MetadataManager
from core.rfid import RFIDReader, RfidStatus
from core.tonuino_serial import TonuinoSerial, TonuinoSerialError, TonuinoWriteCancelled

log = logging.getLogger(__name__)


class SDCardScanner(QThread):
    """Thread fuer das Scannen der SD-Karte"""
    completed = pyqtSignal(bool)
    progress = pyqtSignal(int)
    
    def __init__(self, sd_card: SDCard):
        super().__init__()
        self.sd_card = sd_card
    
    def run(self):
        try:
            self.progress.emit(10)
            # Kurze Pause um Signal zu verarbeiten
            self.msleep(50)
            success = self.sd_card.scan()
            self.progress.emit(100)
            self.completed.emit(success)
        except Exception:
            log.exception("Scan-Fehler")
            self.completed.emit(False)


class TrackAddWorker(QThread):
    """Thread zum Hinzufuegen (Kopieren/Konvertieren) von Tracks, damit die
    UI waehrend FFmpeg-Konvertierung/Datei-I/O nicht einfriert."""
    progress = pyqtSignal(int, int, str)  # aktueller Index, Gesamtzahl, Dateiname
    track_added = pyqtSignal(object)  # neuer Track
    error = pyqtSignal(str, str)  # Dateiname, Fehlermeldung
    completed = pyqtSignal(int)  # Anzahl erfolgreich hinzugefuegter Tracks

    def __init__(self, folder: Folder, filepaths: list,
                 audio_converter: AudioConverter, metadata_manager: MetadataManager):
        super().__init__()
        self.folder = folder
        self.filepaths = filepaths
        self.audio_converter = audio_converter
        self.metadata_manager = metadata_manager
        self._cancelled = False
        # Bereits belegte Tracknummern werden hier fortlaufend gefuehrt, da die
        # eigentliche Ordnerliste (folder.tracks) erst im GUI-Thread aktualisiert wird
        self._used_numbers = {t.index for t in folder.tracks}

    def cancel(self):
        self._cancelled = True

    def run(self):
        added = 0
        # Hat der Ordner einen manuell vergebenen Namen (steht im ersten Track),
        # erben ihn die neuen Tracks; sonst bleibt der Ordner unberuehrt
        first = min(self.folder.tracks, key=lambda t: t.index, default=None)
        folder_name = self.metadata_manager.read_metadata(first.filepath).folder_name if first else ""
        for i, filepath in enumerate(self.filepaths, start=1):
            if self._cancelled:
                break

            self.progress.emit(i, len(self.filepaths), os.path.basename(filepath))

            next_number = 1
            while next_number in self._used_numbers:
                next_number += 1
            if next_number > MAX_TRACKS_PER_FOLDER:
                break

            dest_filename = f"{next_number:03d}.mp3"
            dest_path = Path(self.folder.path) / dest_filename

            try:
                if self.audio_converter.needs_conversion(filepath):
                    if not self.audio_converter.is_available:
                        self.error.emit(os.path.basename(filepath), "FFmpeg ist nicht verfügbar.")
                        continue
                    self.audio_converter.convert_to_mp3(filepath, str(dest_path))
                else:
                    shutil.copy2(filepath, dest_path)

                # Tags stehen jetzt in der Zieldatei (bei Konvertierung von FFmpeg
                # uebernommen, bei MP3 mitkopiert) - dort lesen statt in der Quelle,
                # die ggf. kein MP3 ist und von mutagen.mp3 nicht gelesen werden kann.
                metadata = self.metadata_manager.read_metadata(str(dest_path))
                if metadata.title or folder_name:
                    self.metadata_manager.write_metadata(
                        str(dest_path),
                        track_number=next_number if metadata.title else None,
                        folder_name=folder_name or None,
                    )

                new_track = Track(
                    index=next_number,
                    filename=dest_filename,
                    filepath=str(dest_path),
                    title=metadata.title
                )
                self._used_numbers.add(next_number)
                self.track_added.emit(new_track)
                added += 1

            except Exception as e:
                self.error.emit(os.path.basename(filepath), str(e))

        self.completed.emit(added)


class FolderRenameWorker(QThread):
    """Schreibt den manuell vergebenen Ordnernamen (leer = entfernen) in die Tags
    aller Tracks des Ordners; bei vielen Dateien auf der SD-Karte dauert das."""
    progress = pyqtSignal(int, int)  # aktueller Index, Gesamtzahl
    completed = pyqtSignal(int, str)  # Ordnernummer, Fehlertext (leer bei Erfolg)

    def __init__(self, folder: Folder, name: str, metadata_manager: MetadataManager):
        super().__init__()
        self.folder_index = folder.index
        self.filepaths = [t.filepath for t in folder.tracks]
        self.name = name
        self.metadata_manager = metadata_manager

    def run(self):
        failed = 0
        for i, filepath in enumerate(self.filepaths, start=1):
            self.progress.emit(i, len(self.filepaths))
            if not self.metadata_manager.write_metadata(filepath, folder_name=self.name):
                failed += 1
        error = f"{failed} von {len(self.filepaths)} Dateien konnten nicht beschrieben werden." if failed else ""
        self.completed.emit(self.folder_index, error)


class LoudnessAnalysisWorker(QThread):
    """Misst die Lautheit aller Tracks eines Ordners (nur lesend), damit die UI
    waehrend der FFmpeg-Aufrufe nicht einfriert."""
    progress = pyqtSignal(int, int, str)  # aktueller Index, Gesamtzahl, Dateiname
    # Track, gemessene Lautheit in LUFS (None bei Stille/Fehler), Fehlertext (leer bei Erfolg)
    measured = pyqtSignal(object, object, str)
    completed = pyqtSignal()

    def __init__(self, tracks: list, audio_converter: AudioConverter):
        super().__init__()
        self.tracks = list(tracks)
        self.audio_converter = audio_converter
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def was_cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        for i, track in enumerate(self.tracks, start=1):
            if self._cancelled:
                break
            self.progress.emit(i, len(self.tracks), track.filename)
            try:
                result = self.audio_converter.measure_loudness(track.filepath)
                self.measured.emit(track, result.integrated, "")
            except Exception as e:
                log.warning("Lautheitsmessung fehlgeschlagen (%s): %s", track.filename, e)
                self.measured.emit(track, None, str(e))
        self.completed.emit()


class LoudnessApplyWorker(QThread):
    """Gleicht die Lautstaerke der uebergebenen Tracks an. Jede Datei wird zuerst
    in eine temporaere Datei im selben Ordner geschrieben und ersetzt das Original
    erst bei Erfolg - ein Fehler oder Abbruch laesst die Originaldatei unberuehrt."""
    progress = pyqtSignal(int, int, str)  # aktueller Index, Gesamtzahl, Dateiname
    error = pyqtSignal(str, str)  # Dateiname, Fehlermeldung
    completed = pyqtSignal(int)  # Anzahl angepasster Tracks

    def __init__(self, items: list, audio_converter: AudioConverter):
        super().__init__()
        self.items = list(items)  # [(Track, Verstaerkung in dB)]
        self.audio_converter = audio_converter
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @staticmethod
    def _source_bitrate(filepath: str) -> Optional[int]:
        try:
            from mutagen.mp3 import MP3
            return int(MP3(filepath).info.bitrate)
        except Exception:
            return None

    def run(self):
        done = 0
        for i, (track, gain_db) in enumerate(self.items, start=1):
            if self._cancelled:
                break
            self.progress.emit(i, len(self.items), track.filename)

            source = Path(track.filepath)
            temp = source.with_name(f".tmp_norm_{source.name}")
            try:
                bitrate = loudness.pick_bitrate_kbps(self._source_bitrate(track.filepath))
                self.audio_converter.apply_gain(str(source), str(temp), gain_db, bitrate)
                os.replace(temp, source)
                done += 1
            except Exception as e:
                log.warning("Lautstaerke-Anpassung fehlgeschlagen (%s): %s", track.filename, e)
                self.error.emit(track.filename, str(e))
            finally:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
        self.completed.emit(done)


class RfidPoller(QThread):
    """Fragt Reader- und Kartenstatus regelmaessig im Hintergrund ab - die
    PC/SC-Aufrufe (Transmit, Reconnect) koennen sonst den GUI-Thread
    spuerbar blockieren."""
    status_changed = pyqtSignal(object)  # RfidStatus

    def __init__(self, reader: RFIDReader, interval_ms: int = 500):
        super().__init__()
        self.reader = reader
        self.interval_ms = interval_ms
        self.paused = False  # z.B. im TonUINO-seriell-Modus
        self._stopped = False

    def stop(self):
        self._stopped = True

    def run(self):
        while not self._stopped:
            if not self.paused:
                try:
                    self.status_changed.emit(self.reader.poll())
                except Exception as e:
                    self.status_changed.emit(RfidStatus(reader="error", error=str(e)))
            self.msleep(self.interval_ms)


class TonuinoConnectWorker(QThread):
    """Oeffnet die serielle Verbindung zum TonUINO - der Arduino resettet dabei
    und die Verbindung wartet ca. 2 s, was im GUI-Thread die Oberflaeche einfriert."""
    completed = pyqtSignal(bool, str)  # Erfolg, Fehlermeldung

    def __init__(self, tonuino: TonuinoSerial, port: str):
        super().__init__()
        self.tonuino = tonuino
        self.port = port

    def run(self):
        try:
            self.tonuino.connect(self.port)
            self.completed.emit(True, "")
        except TonuinoSerialError as e:
            self.completed.emit(False, str(e))
        except Exception as e:
            self.completed.emit(False, f"Unerwarteter Fehler: {e}")


class FolderNameWorker(QThread):
    """Ermittelt die Ordnernamen (Album-Tag des ersten getaggten Tracks) im
    Hintergrund - auf einer SD-Karte mit vielen untaggten Ordnern waeren das
    sonst tausende Dateizugriffe im GUI-Thread direkt nach dem Oeffnen."""
    name_found = pyqtSignal(int, str)  # Ordnernummer, Name
    completed = pyqtSignal()

    def __init__(self, folders: list, metadata_manager: MetadataManager):
        super().__init__()
        self.folders = folders
        self.metadata_manager = metadata_manager
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        for folder in self.folders:
            for position, track in enumerate(sorted(folder.tracks, key=lambda t: t.index)):
                if self._cancelled:
                    return
                metadata = self.metadata_manager.read_metadata(track.filepath)
                # Ein manuell vergebener Name steht in allen Tracks - der erste genuegt
                name = (metadata.folder_name if position == 0 else "") or metadata.album
                if name:
                    self.name_found.emit(folder.index, name)
                    break
        self.completed.emit()


class TrackMetaWorker(QThread):
    """Liest die Metadaten der Tracks eines Ordners genau einmal pro Datei
    (Tags, Dauer und - nur vom ersten Track mit Cover - das Cover)."""
    track_loaded = pyqtSignal(int, int, object, object)  # Generation, Zeile, TrackMetadata, Cover-Bytes|None
    completed = pyqtSignal(int)  # Generation

    def __init__(self, generation: int, tracks: list, metadata_manager: MetadataManager):
        super().__init__()
        self.generation = generation
        self.tracks = tracks
        self.metadata_manager = metadata_manager
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        cover_sent = False
        for row, track in enumerate(self.tracks):
            if self._cancelled:
                return
            metadata, cover = self.metadata_manager.read_metadata_and_cover(track.filepath)
            if cover_sent:
                cover = None
            elif cover:
                cover_sent = True
            self.track_loaded.emit(self.generation, row, metadata, cover)
        self.completed.emit(self.generation)


class PurgeWorker(QThread):
    """Thread fuer das Bereinigen der SD-Karte (Whitelist-Purge), damit die
    UI waehrend der Dateisystem-Operationen nicht einfriert."""
    completed = pyqtSignal(bool, str)  # Erfolg, Fehlermeldung (leer bei Erfolg)

    def __init__(self, sd_card: SDCard):
        super().__init__()
        self.sd_card = sd_card

    def run(self):
        try:
            self.sd_card.purge()
            self.completed.emit(True, "")
        except Exception as e:
            self.completed.emit(False, str(e))


class TonuinoCardWorker(QThread):
    """Fuehrt eine Karten-Programmierung ueber den seriell verbundenen TonUINO aus
    (WRITECARD-Befehl), damit die UI waehrend der - potenziell langen, da die
    Firmware ohne eigenes Timeout auf das Auflegen der Karte wartet - Antwort
    nicht einfriert."""
    completed = pyqtSignal(bool, str)  # Erfolg, Meldungstext (Firmware-Text bzw. Fehler)

    def __init__(self, tonuino: TonuinoSerial, mode: int,
                 folder: Optional[int] = None, special: Optional[int] = None,
                 special2: Optional[int] = None):
        super().__init__()
        self.tonuino = tonuino
        self.mode = mode
        self.folder = folder
        self.special = special
        self.special2 = special2

    def run(self):
        try:
            message = self.tonuino.write_card(
                self.mode, folder=self.folder, special=self.special, special2=self.special2
            )
            self.completed.emit(True, message)
        except TonuinoWriteCancelled as e:
            self.completed.emit(False, str(e))
        except (TonuinoSerialError, ValueError) as e:
            self.completed.emit(False, str(e))
        except Exception as e:
            self.completed.emit(False, f"Unerwarteter Fehler: {e}")
