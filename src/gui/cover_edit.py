"""
Cover-Anzeige mit Bearbeiten-Funktion fuer Tonuino-Manager

Zeigt ein quadratisches Cover (oder einen Platzhalter). Faehrt die Maus darueber,
blendet ein dunkler Overlay mit Stift-Symbol und Hinweis ein; ein Klick loest
`clicked` aus. Wird im Track-Editor und im Ordner-Kopfbereich verwendet.
"""

from typing import Optional

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap

# Material-Icons-Codepoints (gebuendelte Schriftart, siehe main.py)
_GLYPH_EDIT = ""   # edit
_GLYPH_IMAGE = ""  # image (Platzhalter ohne Cover)


class CoverEditWidget(QWidget):
    """Quadratisches Cover mit Hover-Overlay 'Cover aendern' und Klick-Signal"""

    clicked = pyqtSignal()

    def __init__(self, size: int = 150, radius: int = 10, parent=None):
        super().__init__(parent)
        self._radius = radius
        self._pixmap: Optional[QPixmap] = None
        self._hovered = False
        self.setFixedSize(size, size)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ------------------------------------------------------------------ API
    def set_cover(self, pixmap: Optional[QPixmap]):
        """Setzt das angezeigte Cover; None oder ein leeres Pixmap zeigt den Platzhalter"""
        self._pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()

    def has_cover(self) -> bool:
        return self._pixmap is not None

    # --------------------------------------------------------------- Zustand
    def changeEvent(self, event):
        # Deaktiviert (z.B. Systemordner): kein Hover-Overlay, kein Klick-Cursor
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if self.isEnabled() else Qt.CursorShape.ArrowCursor
        )
        if not self.isEnabled():
            self._hovered = False
        self.update()
        super().changeEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.isEnabled()
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    # --------------------------------------------------------------- Zeichnen
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(clip)

        if self._pixmap is not None:
            scaled = self._pixmap.scaled(
                self.size() * self.devicePixelRatioF(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(self.devicePixelRatioF())
            x = (self.width() - scaled.width() / self.devicePixelRatioF()) / 2
            y = (self.height() - scaled.height() / self.devicePixelRatioF()) / 2
            painter.drawPixmap(int(x), int(y), scaled)
        else:
            painter.fillRect(rect, QColor("#313244"))
            if not (self._hovered and self.isEnabled()):  # unter dem Overlay nicht durchscheinen lassen
                self._draw_glyph(painter, _GLYPH_IMAGE, self.height() * 0.36, QColor("#6c7086"), rect, 0.0)

        if self._hovered and self.isEnabled():
            painter.fillRect(rect, QColor(17, 17, 27, 190))
            self._draw_glyph(painter, _GLYPH_EDIT, self.height() * 0.2, QColor("#cdd6f4"), rect, -0.07)

            font = QFont(self.font())
            font.setBold(True)
            font.setPointSizeF(10)
            painter.setFont(font)
            painter.setPen(QColor("#cdd6f4"))
            text = "Cover ändern" if self._pixmap is not None else "Cover hinzufügen"
            text_rect = QRectF(rect.left(), rect.center().y() + self.height() * 0.02, rect.width(), self.height() * 0.3)
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), text)

        painter.end()

    @staticmethod
    def _draw_glyph(painter: QPainter, glyph: str, pixel_size: float, color: QColor, rect: QRectF, y_offset: float):
        """Zeichnet ein Material-Icons-Glyph mittig, um y_offset (Anteil der Hoehe) verschoben"""
        font = QFont("Material Icons")
        font.setPixelSize(max(8, int(pixel_size)))
        painter.setFont(font)
        painter.setPen(color)
        target = QRectF(rect)
        target.translate(0, rect.height() * y_offset)
        painter.drawText(target, int(Qt.AlignmentFlag.AlignCenter), glyph)
