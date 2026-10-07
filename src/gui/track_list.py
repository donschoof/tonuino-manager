"""
Track-Liste des Tonuino-Managers
"""

from PyQt6.QtWidgets import QListWidget
from PyQt6.QtCore import QPoint, pyqtSignal


class HoverListWidget(QListWidget):
    """QListWidget, das meldet, ueber welcher Zeile die Maus steht (-1 = keine).
    Dient den Abspielen-Symbolen der Track-Liste, die beim Ueberfahren erscheinen."""
    hovered_row_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._hover_row = -1
        # Position des letzten Mausklicks (Viewport-Koordinaten): itemClicked
        # liefert sie nicht mit, wird aber fuer die Klick-Zone der Symbole gebraucht
        self.last_press_pos = QPoint()

    def _set_hover_row(self, row: int):
        if row != self._hover_row:
            self._hover_row = row
            self.hovered_row_changed.emit(row)

    def mouseMoveEvent(self, event):
        self._set_hover_row(self.indexAt(event.position().toPoint()).row())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self.last_press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self._set_hover_row(-1)
        super().leaveEvent(event)


def reorder_with_selection(tracks: list, selected_ids: set, delta: int):
    """Berechnet die neue Reihenfolge, wenn die markierten Tracks um eine
    Position nach oben (delta=-1) oder unten (delta=1) verschoben werden.
    Verstreute Markierungen werden dabei unter Beibehaltung ihrer
    Reihenfolge zu einem Block zusammengezogen, der am obersten (bzw. beim
    Verschieben nach unten untersten) markierten Track ansetzt und ueber den
    naechsten nicht markierten Track springt. Gibt (neue_reihenfolge,
    zeilen_der_markierten) zurueck."""
    marked = [i for i, t in enumerate(tracks) if id(t) in selected_ids]
    block = [tracks[i] for i in marked]
    rest = [t for t in tracks if id(t) not in selected_ids]

    if delta < 0:
        anchor = marked[0]  # so viele nicht markierte Tracks stehen davor
        insert_at = max(anchor - 1, 0)
    else:
        anchor = marked[-1] - (len(marked) - 1)
        insert_at = min(anchor + 1, len(rest))

    new_order = rest[:insert_at] + block + rest[insert_at:]
    return new_order, list(range(insert_at, insert_at + len(block)))
