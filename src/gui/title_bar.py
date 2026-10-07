"""
Eigene Titelleiste fuer Tonuino-Manager (nur Windows)

Die native Windows-Titelleiste kann keine Widgets aufnehmen. Statt ihr eine
zweite Menueleiste hinzuzufuegen, ersetzt diese Leiste sie: App-Icon, das
Menue "Einstellungen" und die Fenster-Buttons in einer Zeile. Verschieben,
Groesse aendern und Einrasten uebernimmt Windows selbst ueber WM_NCHITTEST
(siehe MainWindow.nativeEvent und TitleBar.is_draggable_at).
"""

from PyQt6.QtCore import Qt, QSize, QPointF, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QMenuBar, QToolButton

ICON_COLOR = "#cdd6f4"
BUTTON_SIZE = QSize(46, 32)


def _window_icon(kind: str, color: str = ICON_COLOR) -> QIcon:
    """Zeichnet die Symbole der Fenster-Buttons (minimize/maximize/restore/close)."""
    size, scale = 10, 4
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.0))
    if kind == "minimize":
        painter.drawLine(QPointF(0.5, 5.5), QPointF(9.5, 5.5))
    elif kind == "maximize":
        painter.drawRect(1, 1, 8, 8)
    elif kind == "restore":
        painter.drawRect(1, 3, 6, 6)
        painter.drawLine(QPointF(3.5, 3), QPointF(3.5, 1))
        painter.drawLine(QPointF(3, 1.5), QPointF(9.5, 1.5))
        painter.drawLine(QPointF(9.5, 1), QPointF(9.5, 7))
        painter.drawLine(QPointF(7, 6.5), QPointF(9.5, 6.5))
    elif kind == "close":
        painter.drawLine(QPointF(0.5, 0.5), QPointF(9.5, 9.5))
        painter.drawLine(QPointF(9.5, 0.5), QPointF(0.5, 9.5))
    painter.end()
    return QIcon(pixmap)


class TitleBar(QWidget):
    """Titelleiste mit App-Icon, Menueleiste und Fenster-Buttons"""

    def __init__(self, window, icon_path: str):
        super().__init__(window)
        self._window = window
        self.setObjectName("titleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(BUTTON_SIZE.height())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(6)

        icon_label = QLabel()
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap.scaled(
                18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
        layout.addWidget(icon_label)

        self.menu_bar = QMenuBar()
        self.menu_bar.setObjectName("titleMenuBar")
        layout.addWidget(self.menu_bar)
        layout.addStretch(1)

        self.btn_minimize = self._make_button("minimize", "Minimieren", window.showMinimized)
        self.btn_maximize = self._make_button("maximize", "Maximieren", self._toggle_maximize)
        self.btn_close = self._make_button("close", "Schließen", window.close)
        self.btn_close.setObjectName("windowCloseButton")
        for btn in (self.btn_minimize, self.btn_maximize, self.btn_close):
            layout.addWidget(btn)

    def _make_button(self, kind: str, tooltip: str, slot) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("windowButton")
        btn.setIcon(_window_icon(kind))
        btn.setIconSize(QSize(10, 10))
        btn.setFixedSize(BUTTON_SIZE)
        btn.setToolTip(tooltip)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(slot)
        return btn

    def _toggle_maximize(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def update_maximize_button(self):
        """Wechselt Symbol und Tooltip passend zum Fensterzustand"""
        if self._window.isMaximized():
            self.btn_maximize.setIcon(_window_icon("restore"))
            self.btn_maximize.setToolTip("Wiederherstellen")
        else:
            self.btn_maximize.setIcon(_window_icon("maximize"))
            self.btn_maximize.setToolTip("Maximieren")

    def is_draggable_at(self, pos: QPoint) -> bool:
        """True, wenn pos (in Fensterkoordinaten) auf freier Titelleistenflaeche
        liegt, also Windows das Fenster dort per Titelleiste bewegen darf."""
        if not self.rect().contains(self.mapFrom(self._window, pos)):
            return False
        child = self.childAt(self.mapFrom(self._window, pos))
        if child is None or child is self:
            return True
        if child is self.menu_bar:
            return self.menu_bar.actionAt(self.menu_bar.mapFrom(self._window, pos)) is None
        # Icon-Label ist ebenfalls ein Griff, Buttons nicht
        return isinstance(child, QLabel)
