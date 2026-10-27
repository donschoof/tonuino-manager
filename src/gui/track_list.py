"""
Track-Liste des Tonuino-Managers
"""

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QHeaderView, QLineEdit, QWidget, QStyledItemDelegate, QStyle,
    QToolTip, QStyleOptionViewItem, QApplication,
)
from PyQt6.QtCore import Qt, QPoint, QEvent, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QBrush, QColor

from gui import theme

# Zeilen mit diesem Wert (Qt.ItemDataRole.UserRole + 1) lassen sich in der
# Mehrfachauswahl nicht markieren und zeigen keinen Auswahlkreis
ROW_NOT_CHECKABLE_ROLE = Qt.ItemDataRole.UserRole + 1


class InlineLineEdit(QLineEdit):
    """Eingabefeld zum direkten Bearbeiten eines Namens: Enter bzw. Fokusverlust
    beenden die Eingabe (editingFinished), Escape verwirft sie (cancelled)."""
    cancelled = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)


class FloatingIconRow(QWidget):
    """Zeile aus Label, Eingabefeld und kleinem Symbol: Das Label ist so breit wie
    sein Text (hoechstens die volle Breite) und das Symbol schliesst direkt daran
    an. Im Bearbeiten-Modus fuellt das Eingabefeld die Zeile."""
    GAP = 0

    def __init__(self, label, edit, icon, parent=None):
        super().__init__(parent)
        self.label, self.edit, self.icon = label, edit, icon
        for child in (label, edit, icon):
            child.setParent(self)
        self.editing = False
        edit.setVisible(False)

    def set_editing(self, editing: bool):
        self.editing = editing
        self.label.setVisible(not editing)
        self.icon.setVisible(not editing)
        self.edit.setVisible(editing)
        self.relayout()
        if editing:
            self.edit.setFocus()
            self.edit.selectAll()

    def relayout(self):
        width, height = self.width(), self.height()
        if self.editing:
            self.edit.setGeometry(0, 0, width, height)
            return
        icon_size = self.icon.sizeHint()
        text_width = QFontMetrics(self.label.font()).horizontalAdvance(self.label.text()) + 4
        label_width = max(0, min(text_width, width - icon_size.width() - self.GAP))
        self.label.setGeometry(0, 0, label_width, height)
        self.icon.setGeometry(
            label_width + self.GAP, (height - icon_size.height()) // 2,
            icon_size.width(), icon_size.height()
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout()


class RowBackgroundDelegate(QStyledItemDelegate):
    """Zeichnet einen per setBackground() gesetzten Zeilenhintergrund auch dann,
    wenn das Stylesheet fuer ::item:hover einen eigenen Hintergrund vorgibt und
    ihn sonst ueberdecken wuerde. Ausgewaehlte Zeilen behalten die normale
    Auswahlfarbe."""

    def paint(self, painter, option, index):
        brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if isinstance(brush, QBrush) and brush.style() != Qt.BrushStyle.NoBrush:
            painter.fillRect(option.rect, brush)
            option = type(option)(option)
            option.state &= ~QStyle.StateFlag.State_MouseOver
            super().paint(painter, option, index)
            if index.data(ROW_NOT_CHECKABLE_ROLE):
                self._hide_check_indicator(painter, option, index, brush)
            return
        super().paint(painter, option, index)

    def _hide_check_indicator(self, painter, option, index, row_brush):
        """Uebermalt den Auswahlkreis der Mehrfachauswahl: die Zeile reserviert
        seinen Platz (damit die Spalten buendig bleiben), ist aber nicht
        auswaehlbar und soll deshalb keinen Kreis zeigen"""
        if index.data(Qt.ItemDataRole.CheckStateRole) is None:
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = option.widget.style() if option.widget else QApplication.style()
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, option.widget)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        cover = QBrush(QColor(theme.SURFACE0)) if selected else row_brush
        painter.fillRect(rect.adjusted(-2, -2, 2, 2), cover)


class HoverListWidget(QTreeWidget):
    """Track-Tabelle (Track, Titel, Album) mit feststehender Kopfzeile. Meldet,
    ueber welcher Zeile die Maus steht (-1 = keine); das dient den
    Abspielen-Symbolen, die beim Ueberfahren erscheinen. Bietet die gewohnte
    Listen-API (count, item, addItem, setCurrentRow) fuer die Zeilen."""
    hovered_row_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setColumnCount(4)
        # Die schmale vierte Spalte traegt das Warnsymbol hinter dem Album
        self.setHeaderLabels(["Track", "Titel", "Album", ""])
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionsMovable(False)
        # feste Breite: ResizeToContents misst bei jeder Symbol-/Textaenderung alle
        # Zeilen neu und macht Hover und Ordnerwechsel spuerbar langsam
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 110)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(3, 36)
        self.setItemDelegate(RowBackgroundDelegate(self))
        self._hover_row = -1
        self._tip_cell = (-1, -1)
        # Position des letzten Mausklicks (Viewport-Koordinaten): itemClicked
        # liefert sie nicht mit, wird aber fuer die Klick-Zone der Symbole gebraucht
        self.last_press_pos = QPoint()

    def count(self) -> int:
        return self.topLevelItemCount()

    def item(self, row: int) -> QTreeWidgetItem:
        return self.topLevelItem(row)

    def addItem(self, item: QTreeWidgetItem):
        self.addTopLevelItem(item)

    def setCurrentRow(self, row: int):
        self.setCurrentItem(self.topLevelItem(row))

    def _set_hover_row(self, row: int):
        if row != self._hover_row:
            self._hover_row = row
            self.hovered_row_changed.emit(row)

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        self._set_hover_row(index.row())
        self._show_tooltip_now(index, event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def _show_tooltip_now(self, index, global_pos: QPoint):
        """Blendet den Tooltip einer Zelle sofort beim Ueberfahren ein (Qt wartet
        sonst rund eine halbe Sekunde) und blendet ihn beim Verlassen aus"""
        cell = (index.row(), index.column()) if index.isValid() else (-1, -1)
        if cell == self._tip_cell:
            return
        self._tip_cell = cell
        text = index.data(Qt.ItemDataRole.ToolTipRole) if index.isValid() else None
        if text:
            QToolTip.showText(global_pos, text, self.viewport(), self.visualRect(index))
        else:
            QToolTip.hideText()

    def viewportEvent(self, event):
        # die verzoegerten Standard-Tooltips ersetzt _show_tooltip_now
        if event.type() == QEvent.Type.ToolTip:
            return True
        return super().viewportEvent(event)

    def mousePressEvent(self, event):
        self.last_press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self._set_hover_row(-1)
        self._tip_cell = (-1, -1)
        QToolTip.hideText()
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
