"""
Audio-Player-Leiste fuer Tonuino-Manager - erlaubt das Anhoeren von Tracks
direkt im Tool, ohne die Datei extern zu oeffnen.
"""

import ctypes
import sys

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


def _silence_ffmpeg_logging():
    """Unterdrueckt die rohen FFmpeg-Logzeilen des von Qt intern genutzten
    Decoders (z.B. 'Input #0, mp3, from ...', 'Skipping N bytes of junk',
    'MFT name: ...'), die bei jedem Laden eines Tracks auf stderr landen.
    QT_LOGGING_RULES allein reicht dafuer nicht aus: der grosse Stream-Dump
    laeuft zwar ueber Qts Kategorie-Logging (qt.multimedia.ffmpeg), die
    einzelnen Warn-/Info-Zeilen der Demuxer/Decoder kommen aber direkt ueber
    FFmpegs eigenes av_log() am Qt-Logging vorbei. Da PyQt6 fuer die
    QtMultimedia-FFmpeg-Backend bereits eine avutil-DLL/-.so/-.dylib laedt,
    kann deren av_log_set_level() per ctypes direkt angesprochen werden.
    Best-effort: schlaegt das fehl (z.B. abweichender Bibliotheksname), bleibt
    die (rein kosmetische) Logausgabe einfach bestehen."""
    AV_LOG_QUIET = -8
    if sys.platform == "win32":
        candidates = ["avutil-59.dll", "avutil-58.dll", "avutil-57.dll", "avutil-56.dll"]
    elif sys.platform == "darwin":
        candidates = ["libavutil.59.dylib", "libavutil.58.dylib", "libavutil.dylib"]
    else:
        candidates = ["libavutil.so.59", "libavutil.so.58", "libavutil.so"]

    for name in candidates:
        try:
            ctypes.CDLL(name).av_log_set_level(AV_LOG_QUIET)
            return
        except (OSError, AttributeError):
            continue


_silence_ffmpeg_logging()

# Material-Icons-Codepoints (dieselbe gebuendelte Schriftart wie im Hauptfenster)
_ICON_PLAY = ""
_ICON_PAUSE = ""
_ICON_PREV = ""
_ICON_NEXT = ""
_ICON_VOLUME = ""


def _icon_from_glyph(glyph: str, color: str = "#cdd6f4", size: int = 16) -> QIcon:
    """Rendert ein Material-Icons-Glyph als QIcon (siehe MainWindow._icon_from_glyph)"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    font = QFont("Material Icons")
    font.setPointSize(int(size * 0.65))
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()

    return QIcon(pixmap)


def _format_time(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


class AudioPlayerBar(QFrame):
    """Kompakter, klassischer Player fuer den Kopfbereich (neben dem Cover):
    Titel, Zurueck/Play-Pause/Weiter, Fortschritt und Lautstaerke.
    Die Zurueck/Weiter-Navigation kennt selbst keine Ordner-/Tracklogik -
    dafuer werden prev_clicked/next_clicked emittiert, die das Hauptfenster
    mit dem naechsten/vorherigen Track aus der aktuellen Ordnerliste fuellt."""

    prev_clicked = pyqtSignal()
    next_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardFrame")

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.7)

        self._current_path = None
        self._seeking = False

        self._setup_ui()

        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.errorOccurred.connect(self._on_error)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.title_label = QLabel("Kein Track ausgewählt")
        self.title_label.setObjectName("subtitleLabel")
        self.title_label.setWordWrap(False)
        layout.addWidget(self.title_label)

        transport_row = QHBoxLayout()
        transport_row.setSpacing(8)
        transport_row.addStretch()

        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(_icon_from_glyph(_ICON_PREV, color="#cdd6f4"))
        self.btn_prev.setFixedWidth(36)
        self.btn_prev.setEnabled(False)
        self.btn_prev.setToolTip("Vorheriger Track")
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        transport_row.addWidget(self.btn_prev)

        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setIcon(_icon_from_glyph(_ICON_PLAY, color="#cdd6f4"))
        self.btn_play_pause.setFixedWidth(40)
        self.btn_play_pause.setEnabled(False)
        self.btn_play_pause.setToolTip("Wiedergabe starten/pausieren")
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        transport_row.addWidget(self.btn_play_pause)

        self.btn_next = QPushButton()
        self.btn_next.setIcon(_icon_from_glyph(_ICON_NEXT, color="#cdd6f4"))
        self.btn_next.setFixedWidth(36)
        self.btn_next.setEnabled(False)
        self.btn_next.setToolTip("Nächster Track")
        self.btn_next.clicked.connect(self.next_clicked.emit)
        transport_row.addWidget(self.btn_next)

        transport_row.addStretch()
        layout.addLayout(transport_row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self.position_label = QLabel("00:00")
        progress_row.addWidget(self.position_label)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        self.seek_slider.sliderPressed.connect(self._on_seek_start)
        self.seek_slider.sliderReleased.connect(self._on_seek_end)
        progress_row.addWidget(self.seek_slider, 1)

        self.duration_label = QLabel("00:00")
        progress_row.addWidget(self.duration_label)

        layout.addLayout(progress_row)

        volume_row = QHBoxLayout()
        volume_row.setSpacing(8)
        volume_row.addStretch()

        volume_icon = QLabel()
        volume_icon.setPixmap(_icon_from_glyph(_ICON_VOLUME, color="#cdd6f4").pixmap(16, 16))
        volume_row.addWidget(volume_icon)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setToolTip("Lautstärke")
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_row.addWidget(self.volume_slider)

        layout.addLayout(volume_row)

    def load_track(self, filepath: str, title: str, autoplay: bool = True):
        """Laedt einen Track in den Player und startet optional die Wiedergabe"""
        self._current_path = filepath
        self.title_label.setText(title)
        self.player.setSource(QUrl.fromLocalFile(filepath))
        self.btn_play_pause.setEnabled(True)
        self.btn_prev.setEnabled(True)
        self.btn_next.setEnabled(True)
        self.seek_slider.setEnabled(True)
        if autoplay:
            self.player.play()

    def toggle_track(self, filepath: str, title: str):
        """Spielt den Track ab, oder pausiert/setzt fort, falls er bereits geladen ist"""
        if self._current_path == filepath:
            self._toggle_play_pause()
        else:
            self.load_track(filepath, title, autoplay=True)

    def stop(self):
        self.player.stop()

    def stop_and_clear(self):
        """Stoppt die Wiedergabe und setzt den Player zurueck (z.B. bei Ordnerwechsel
        oder wenn sich die Track-Liste aendert und der aktuelle Pfad ungueltig werden koennte)"""
        self.player.stop()
        self.player.setSource(QUrl())
        self._current_path = None
        self.title_label.setText("Kein Track ausgewählt")
        self.btn_play_pause.setIcon(_icon_from_glyph(_ICON_PLAY, color="#cdd6f4"))
        self.btn_play_pause.setEnabled(False)
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.position_label.setText("00:00")
        self.duration_label.setText("00:00")

    @property
    def current_path(self) -> str:
        return self._current_path

    def is_current(self, filepath: str) -> bool:
        return self._current_path == filepath

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _toggle_play_pause(self):
        if self.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state):
        glyph = _ICON_PAUSE if state == QMediaPlayer.PlaybackState.PlayingState else _ICON_PLAY
        self.btn_play_pause.setIcon(_icon_from_glyph(glyph, color="#cdd6f4"))

    def _on_position_changed(self, position: int):
        if not self._seeking:
            self.seek_slider.setValue(position)
        self.position_label.setText(_format_time(position))

    def _on_duration_changed(self, duration: int):
        self.seek_slider.setRange(0, duration)
        self.duration_label.setText(_format_time(duration))

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self.player.setPosition(self.seek_slider.value())
        self._seeking = False

    def _on_volume_changed(self, value: int):
        self.audio_output.setVolume(value / 100)

    def _on_error(self, error, error_string: str):
        if error != QMediaPlayer.Error.NoError:
            self.title_label.setText(f"Fehler: {error_string}")
