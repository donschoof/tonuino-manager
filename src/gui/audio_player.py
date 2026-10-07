"""
Audio-Player-Leiste fuer Tonuino-Manager - erlaubt das Anhoeren von Tracks
direkt im Tool, ohne die Datei extern zu oeffnen.
"""

import ctypes
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QStyle, QWidget
from PyQt6.QtCore import Qt, QUrl, QCoreApplication, QSize, QRectF, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QPixmap, QPainter, QPainterPath, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from gui.common import icon_from_glyph
from gui import theme


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
_ICON_PREV = "\ue020"  # fast_rewind
_ICON_NEXT = "\ue01f"  # fast_forward
_ICON_NOTE = "\ue405"  # music_note (Platzhalter ohne Cover)
_ICON_VOLUME_UP = "\ue050"    # volume_up
_ICON_VOLUME_DOWN = "\ue04d"  # volume_down
_ICON_VOLUME_OFF = "\ue04f"   # volume_off


# Farbe deaktivierter Steuerelemente (muss zu QSlider:disabled/QLabel:disabled in styles.py passen)
_DISABLED_COLOR = theme.SURFACE1


def _transport_icon(glyph: str, size: int, main_color: str, hover_color: str) -> QIcon:
    """Symbol fuer die flachen Player-Steuerelemente: in main_color, beim
    Ueberfahren (QIcon.Mode.Active) in hover_color, deaktiviert deutlich
    abgedunkelt (QIcon.Mode.Disabled)"""
    icon = QIcon()
    for mode, color in (
        (QIcon.Mode.Normal, main_color),
        (QIcon.Mode.Active, hover_color),
        (QIcon.Mode.Disabled, _DISABLED_COLOR),
    ):
        icon.addPixmap(icon_from_glyph(glyph, color=color, size=size).pixmap(size, size), mode)
    return icon


class ClickSlider(QSlider):
    """Horizontaler QSlider, bei dem ein Klick auf die Leiste den Wert direkt
    dorthin setzt und Ziehen ihm folgt. Bei duennen Slidern ist der Griff sonst
    schwer zu treffen, und der Standard springt nur seitenweise."""

    HANDLE_MARGIN = 5  # halbe Griffbreite (siehe QSlider#volumeSlider in styles.py)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._dragging = False
        self._hovered = False

    def _update_hovered(self):
        """Eigenschaft 'hovered' fuers Stylesheet: Griff nur beim Ueberfahren/Ziehen zeigen"""
        hovered = self._hovered or self._dragging
        if self.property("hovered") != hovered:
            self.setProperty("hovered", hovered)
            self.style().unpolish(self)
            self.style().polish(self)

    def enterEvent(self, event):
        self._hovered = True
        self._update_hovered()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._update_hovered()
        super().leaveEvent(event)

    def _value_at(self, x: float) -> int:
        span = max(1, self.width() - 2 * self.HANDLE_MARGIN)
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), round(x - self.HANDLE_MARGIN), span
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._dragging = True
            self._update_hovered()
            self.setValue(self._value_at(event.position().x()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.setValue(self._value_at(event.position().x()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._update_hovered()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


@dataclass
class TrackInfo:
    """Anzeigedaten des laufenden Tracks (aus den ID3-Tags)"""
    title: str = ""
    artist: str = ""
    album: str = ""
    cover: Optional[QPixmap] = None


class ElidedLabel(QLabel):
    """QLabel, das zu langen Text mit '...' kuerzt statt das Layout aufzuweiten"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setMinimumWidth(10)
        self.setText(text)

    def setText(self, text: str):
        self._full_text = text
        self.setToolTip(text if text else "")
        self.update()

    def text(self) -> str:
        return self._full_text

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(min(metrics.horizontalAdvance(self._full_text), 400), metrics.height() + 2)

    def minimumSizeHint(self) -> QSize:
        return QSize(10, QFontMetrics(self.font()).height() + 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        elided = QFontMetrics(self.font()).elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), int(self.alignment()), elided)
        painter.end()


def rounded_cover(source: Optional[QPixmap], size: int, radius: int = 6) -> QPixmap:
    """Quadratisches Cover mit abgerundeten Ecken (mittig zugeschnitten); ohne
    Cover ein Platzhalter mit Notensymbol"""
    scale = 2  # doppelte Aufloesung fuer scharfe Kanten
    px = size * scale
    result = QPixmap(px, px)
    result.setDevicePixelRatio(scale)
    result.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)

    if source is not None and not source.isNull():
        scaled = source.scaled(
            px, px, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
        x = (scaled.width() - px) // 2
        y = (scaled.height() - px) // 2
        crop = scaled.copy(x, y, px, px)
        crop.setDevicePixelRatio(scale)
        painter.drawPixmap(0, 0, crop)
    else:
        painter.fillRect(QRectF(0, 0, size, size), QColor(theme.SURFACE0))
        painter.setClipping(False)
        note = icon_from_glyph(_ICON_NOTE, color=theme.OVERLAY0, size=int(size * 0.6)).pixmap(int(size * 0.6), int(size * 0.6))
        offset = (size - note.width()) // 2
        painter.drawPixmap(offset, offset, note)
    painter.end()
    return result


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

    CENTER_WIDTH = 420  # feste Breite des Mittelblocks (Now-Playing + Playbar)
    COVER_SIZE = 40  # Hoehe der Now-Playing-Zeile, bestimmt die Hoehe des Players mit

    prev_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    # Geladener Track bzw. Wiedergabezustand hat sich geaendert (Play/Pause/
    # Laden/Leeren) - die Track-Liste aktualisiert damit ihre Zeilen-Symbole
    playback_changed = pyqtSignal()
    # Play wurde gedrueckt, obwohl noch kein Track geladen ist - das Hauptfenster
    # laedt daraufhin den in der Liste ausgewaehlten Track
    play_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardFrame")

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.7)

        self._current_path = None
        self._seeking = False
        self._idle_playable = False
        self._muted = False
        # Liefert zu einem Dateipfad die Anzeigedaten (Titel, Interpret, Album,
        # Cover); setzt das Hauptfenster, das die Metadaten kennt
        self.track_info_provider: Optional[Callable[[str], Optional[TrackInfo]]] = None

        self._setup_ui()
        self._set_loaded_state(False)

        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.errorOccurred.connect(self._on_error)

    def _setup_ui(self):
        # Eine Zeile (wie in Apple Music): Steuerelemente links, Now-Playing mit
        # Playbar in der Mitte, Lautstaerke rechts. Die Karte (self) fuellt die
        # verfuegbare Breite; die beiden Seiten teilen sich den Rest gleich auf,
        # so bleibt der Mittelblock exakt zentriert.
        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 8, 14, 8)
        outer.setSpacing(24)  # Abstand zwischen Steuerung, Mittelblock und Lautstaerke

        # --- links: Zurueck / Play / Weiter
        # rechtsbuendig in der linken Spalte: die Steuerung sitzt direkt am Mittelblock
        transport = QHBoxLayout()
        transport.setSpacing(8)
        transport.addStretch(1)

        self.btn_prev = QPushButton()
        self.btn_prev.setObjectName("transportButton")
        self.btn_prev.setIcon(_transport_icon(_ICON_PREV, 30, theme.OVERLAY2, theme.TEXT))
        self.btn_prev.setIconSize(QSize(30, 30))
        self.btn_prev.setFixedSize(38, 38)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setEnabled(False)
        self.btn_prev.setToolTip("Vorheriger Track")
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        transport.addWidget(self.btn_prev, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setObjectName("transportButton")
        self.btn_play_pause.setIcon(_transport_icon(_ICON_PLAY, 40, theme.TEXT, theme.WHITE))
        self.btn_play_pause.setIconSize(QSize(40, 40))
        self.btn_play_pause.setFixedSize(46, 46)
        self.btn_play_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play_pause.setEnabled(False)
        self.btn_play_pause.setToolTip("Wiedergabe starten/pausieren")
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        transport.addWidget(self.btn_play_pause, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_next = QPushButton()
        self.btn_next.setObjectName("transportButton")
        self.btn_next.setIcon(_transport_icon(_ICON_NEXT, 30, theme.OVERLAY2, theme.TEXT))
        self.btn_next.setIconSize(QSize(30, 30))
        self.btn_next.setFixedSize(38, 38)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setEnabled(False)
        self.btn_next.setToolTip("Nächster Track")
        self.btn_next.clicked.connect(self.next_clicked.emit)
        transport.addWidget(self.btn_next, 0, Qt.AlignmentFlag.AlignVCenter)

        outer.addLayout(transport, 1)

        # --- Mitte: Cover, Titel, Interpret/Album und darunter die Playbar
        center = QWidget()
        center.setObjectName("playerContent")
        center.setFixedWidth(self.CENTER_WIDTH)
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        now_playing = QHBoxLayout()
        now_playing.setSpacing(10)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(self.COVER_SIZE, self.COVER_SIZE)
        now_playing.addWidget(self.cover_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        # Zentriert statt addStretch(): Stretches machen das Layout vertikal
        # "gierig" und blaehen den Player in der Ordneransicht auf
        text_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.title_label = ElidedLabel("Kein Track ausgewählt")
        self.title_label.setObjectName("playerTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setFixedHeight(20)
        text_col.addWidget(self.title_label)

        self.meta_label = ElidedLabel("")
        self.meta_label.setObjectName("playerMeta")
        self.meta_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.meta_label.setFixedHeight(16)
        text_col.addWidget(self.meta_label)

        now_playing.addLayout(text_col, 1)
        layout.addLayout(now_playing)

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
        outer.addWidget(center, 0)

        # --- rechts: Stumm-Schalter + schlanker Lautstaerke-Slider
        # linksbuendig in der rechten Spalte: sitzt im selben Abstand am Mittelblock
        # wie die Steuerung links, so bleibt die ganze Gruppe beim Skalieren zentriert
        volume_box = QHBoxLayout()
        volume_box.setSpacing(6)

        self.btn_mute = QPushButton()
        self.btn_mute.setObjectName("transportButton")
        self.btn_mute.setFixedSize(38, 38)  # wie Zurueck/Weiter
        self.btn_mute.setIconSize(QSize(30, 30))
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.clicked.connect(self._toggle_mute)
        volume_box.addWidget(self.btn_mute, 0, Qt.AlignmentFlag.AlignVCenter)

        self.volume_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setToolTip("Lautstärke")
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_box.addWidget(self.volume_slider, 0, Qt.AlignmentFlag.AlignVCenter)
        volume_box.addStretch(1)

        outer.addLayout(volume_box, 1)

        self._update_volume_ui()
        self._show_track_info(None, "Kein Track ausgewählt")

    def load_track(self, filepath: str, title: str, autoplay: bool = True):
        """Laedt einen Track in den Player und startet optional die Wiedergabe"""
        self._current_path = filepath
        info = None
        if self.track_info_provider is not None:
            try:
                info = self.track_info_provider(filepath)
            except Exception:
                info = None  # Anzeige faellt auf den Dateinamen zurueck
        self._show_track_info(info, title)
        self.player.setSource(QUrl.fromLocalFile(filepath))
        self.playback_changed.emit()
        self._set_loaded_state(True)
        self._update_play_enabled()
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

    def release_file(self):
        """Gibt die aktuell geladene Datei frei (Wiedergabe stoppen, Quelle entladen),
        damit sie umbenannt, ueberschrieben oder geloescht werden kann - unter Windows
        haelt QMediaPlayer sie sonst gesperrt. Ruft vor jeder Dateiaktion auf."""
        if self._current_path is not None:
            self.stop_and_clear()

    def stop_and_clear(self):
        """Stoppt die Wiedergabe und setzt den Player zurueck (z.B. bei Ordnerwechsel
        oder wenn sich die Track-Liste aendert und der aktuelle Pfad ungueltig werden koennte)"""
        self.player.stop()
        self.player.setSource(QUrl())
        # Dem Medien-Backend Gelegenheit geben, das Dateihandle wirklich zu schliessen
        QCoreApplication.processEvents()
        self._current_path = None
        self._show_track_info(None, "Kein Track ausgewählt")
        self.btn_play_pause.setIcon(_transport_icon(_ICON_PLAY, 40, theme.TEXT, theme.WHITE))
        self._update_play_enabled()
        self._set_loaded_state(False)
        self.seek_slider.setRange(0, 0)
        self.position_label.setText("00:00")
        self.duration_label.setText("00:00")
        self.playback_changed.emit()

    @property
    def current_path(self) -> str:
        return self._current_path

    def _show_track_info(self, info: Optional[TrackInfo], fallback_title: str):
        """Zeigt Cover, Titel und 'Interpret - Album' des Tracks (zentriert).
        Ohne Metadaten bleibt der Dateiname als Titel stehen."""
        title = (info.title if info and info.title else fallback_title) or ""
        parts = [x for x in ((info.artist if info else ""), (info.album if info else "")) if x]
        self.title_label.setText(title)
        # Die Zeile bleibt auch ohne Interpret/Album im Layout (nur leer), sonst
        # aendert der Player beim Abspielen seine Hoehe
        self.meta_label.setText(" — ".join(parts))
        # Gesamthoehe der beiden Zeilen bleibt gleich (20 + 2 + 16 = 36 + 2 + 0);
        # ohne Interpret/Album bekommt der Titel die Hoehe und steht mittig am Cover
        has_meta = bool(parts)
        self.title_label.setFixedHeight(20 if has_meta else 36)
        self.meta_label.setFixedHeight(16 if has_meta else 0)
        self.cover_label.setPixmap(rounded_cover(info.cover if info else None, self.COVER_SIZE))

    def _set_loaded_state(self, loaded: bool):
        """Fortschritt (Slider, Zeiten) ist nur mit geladenem Track bedienbar.
        Zurueck/Weiter haengen zusaetzlich von der Position in der Liste ab und
        werden vom Hauptfenster ueber set_navigation_enabled() gesetzt."""
        self.seek_slider.setEnabled(loaded)
        self.position_label.setEnabled(loaded)
        self.duration_label.setEnabled(loaded)
        if not loaded:
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)

    def set_navigation_enabled(self, can_prev: bool, can_next: bool):
        """Zurueck/Weiter nur aktiv, wenn es in dieser Richtung noch einen Track gibt"""
        self.btn_prev.setEnabled(can_prev)
        self.btn_next.setEnabled(can_next)

    def set_idle_playable(self, playable: bool):
        """Meldet, ob es etwas gibt, das Play starten koennte, solange noch kein
        Track geladen ist (ein in der Liste ausgewaehlter Track). Aktiviert dann
        den Play-Button."""
        self._idle_playable = playable
        self._update_play_enabled()

    def _update_play_enabled(self):
        self.btn_play_pause.setEnabled(self._current_path is not None or self._idle_playable)

    def is_current(self, filepath: str) -> bool:
        return self._current_path == filepath

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _toggle_play_pause(self):
        if self._current_path is None:
            self.play_requested.emit()
            return
        if self.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state):
        glyph = _ICON_PAUSE if state == QMediaPlayer.PlaybackState.PlayingState else _ICON_PLAY
        self.btn_play_pause.setIcon(_transport_icon(glyph, 40, theme.TEXT, theme.WHITE))
        self.playback_changed.emit()

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
        if self._muted and value > 0:
            # Der Regler wurde bewegt: Stumm aufheben
            self._muted = False
            self.audio_output.setMuted(False)
        self._update_volume_ui()

    def _toggle_mute(self):
        if self._muted or self.volume_slider.value() == 0:
            # Stumm aufheben (stand der Regler auf 0, auf eine hoerbare Stufe setzen)
            self._muted = False
            self.audio_output.setMuted(False)
            if self.volume_slider.value() == 0:
                self.volume_slider.setValue(50)  # ruft _on_volume_changed auf
        else:
            self._muted = True
            self.audio_output.setMuted(True)
        self._update_volume_ui()

    def _update_volume_ui(self):
        """Symbol (laut/leise/stumm), Tooltip und Slider-Darstellung passend zum
        Zustand. Stumm gilt auch bei Reglerstand 0."""
        value = self.volume_slider.value()
        silent = self._muted or value == 0

        if silent:
            glyph, main_color = _ICON_VOLUME_OFF, theme.SURFACE2
        elif value < 50:
            glyph, main_color = _ICON_VOLUME_DOWN, theme.OVERLAY2
        else:
            glyph, main_color = _ICON_VOLUME_UP, theme.OVERLAY2
        self.btn_mute.setIcon(_transport_icon(glyph, 30, main_color, theme.TEXT))
        self.btn_mute.setToolTip("Stummschaltung aufheben" if silent else "Stumm schalten")

        # Slider im Stumm-Zustand abgedunkelt (QSlider#volumeSlider[muted="true"])
        self.volume_slider.setProperty("muted", silent)
        self.volume_slider.style().unpolish(self.volume_slider)
        self.volume_slider.style().polish(self.volume_slider)

    def _on_error(self, error, error_string: str):
        if error != QMediaPlayer.Error.NoError:
            self.title_label.setText(f"Fehler: {error_string}")
