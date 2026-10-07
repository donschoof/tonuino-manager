"""
Erzeugt alle App-Icons aus einem einzigen, im Code gezeichneten Entwurf:
src/resources/icon.png (1024 px, Titelleiste/Sidebar/Linux), icon.ico (Windows)
und icon.icns (macOS). So sehen Programmdatei, Installer, Fenster und App
ueberall gleich aus.

Aufruf (aus dem Projektordner):  python tools/make_icons.py
Benoetigt PyQt6 und Pillow (pip install pillow).
"""

import math
import os
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient, QTransform,
)
from PIL import Image

SIZE = 1024
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "resources")


def _tile(p: QPainter):
    """Abgerundete Kachel mit ruhigem, dunklem Verlauf und feinem Rand"""
    margin = 36
    rect = QRectF(margin, margin, SIZE - 2 * margin, SIZE - 2 * margin)
    path = QPainterPath()
    path.addRoundedRect(rect, 224, 224)
    bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
    bg.setColorAt(0.0, QColor("#2c2d4a"))
    bg.setColorAt(1.0, QColor("#11111c"))
    p.fillPath(path, bg)
    # sanfter Lichtschein oben links
    glow = QRadialGradient(QPointF(rect.left() + 220, rect.top() + 160), 620)
    glow.setColorAt(0.0, QColor(137, 180, 250, 52))
    glow.setColorAt(1.0, QColor(137, 180, 250, 0))
    p.fillPath(path, glow)
    p.setPen(QPen(QColor(205, 214, 244, 36), 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    return path


def _card(p: QPainter):
    """SD-Karte mit abgeschraegter Ecke, Kontaktstegen und Notensymbol"""
    x, y, w, h, cut, r = 262, 236, 392, 560, 104, 64
    card = QPainterPath()
    card.moveTo(x + r, y)
    card.lineTo(x + w - cut, y)
    card.lineTo(x + w, y + cut)
    card.lineTo(x + w, y + h - r)
    card.quadTo(x + w, y + h, x + w - r, y + h)
    card.lineTo(x + r, y + h)
    card.quadTo(x, y + h, x, y + h - r)
    card.lineTo(x, y + r)
    card.quadTo(x, y, x + r, y)
    card.closeSubpath()

    # Schatten
    shadow = QTransform().translate(0, 22)
    p.fillPath(shadow.map(card), QColor(0, 0, 0, 90))

    grad = QLinearGradient(x, y, x + w, y + h)
    grad.setColorAt(0.0, QColor("#b4d0fb"))
    grad.setColorAt(1.0, QColor("#6f9ef2"))
    p.fillPath(card, grad)

    # Kontaktstege
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1b1c33"))
    for i in range(5):
        p.drawRoundedRect(QRectF(x + 44 + i * 58, y + 44, 34, 96), 12, 12)

    # Notensymbol (dunkel, wie ausgestanzt)
    head = QPainterPath()
    head.addEllipse(QRectF(-58, -42, 116, 84))
    head = QTransform().translate(x + 150, y + 400).rotate(-22).map(head)
    stem = QPainterPath()
    stem.addRoundedRect(QRectF(x + 176, y + 202, 30, 200), 12, 12)
    flag = QPainterPath()
    flag.moveTo(x + 192, y + 202)
    flag.cubicTo(x + 260, y + 222, x + 316, y + 256, x + 296, y + 340)
    flag.cubicTo(x + 288, y + 296, x + 252, y + 276, x + 192, y + 268)
    flag.closeSubpath()
    # vereinigen, damit sich die Teile nicht gegenseitig ausloeschen
    note = head.united(stem).united(flag.simplified())
    p.setBrush(QColor(27, 39, 84, 235))
    p.drawPath(note)


def _waves(p: QPainter):
    """Funkwellen (RFID) an der oberen rechten Ecke der Karte"""
    center = QPointF(694, 330)
    p.setBrush(QColor("#a6e3a1"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(center, 24, 24)
    for i, radius in enumerate((84, 150, 216)):
        pen = QPen(QColor("#a6e3a1"), 34)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
        # Kreisbogen von -62 bis +8 Grad (Qt: 1/16 Grad, gegen den Uhrzeigersinn)
        p.drawArc(rect, int(-8 * 16), int(70 * 16))


def render() -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    _tile(p)
    _card(p)
    _waves(p)
    p.end()
    return image


def main():
    QGuiApplication(sys.argv)
    png = os.path.join(OUT, "icon.png")
    render().save(png)
    master = Image.open(png).convert("RGBA")
    master.save(os.path.join(OUT, "icon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    master.save(os.path.join(OUT, "icon.icns"))
    print("Icons geschrieben nach", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
