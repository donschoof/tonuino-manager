"""
Stylesheet fuer den Tonuino-Manager
Modernes Dark Theme mit Akzentfarben
"""

MAIN_STYLESHEET = """
/* === Globale Styles === */
QMainWindow {
    background-color: #1e1e2e;
}

QWidget {
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 10pt;
}

/* === Sidebar === */
QFrame#sidebar {
    background-color: #181825;
    border-right: 1px solid #313244;
}

QLabel#sidebarTitle {
    color: #89b4fa;
    font-size: 14pt;
    font-weight: bold;
    padding: 10px;
}

/* === Buttons === */
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}

QPushButton:pressed {
    background-color: #585b70;
}

QPushButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}

QPushButton#primaryButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-color: #89b4fa;
    font-weight: bold;
}

QPushButton#primaryButton:hover {
    background-color: #b4d0fb;
}

QPushButton#primaryButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}

QPushButton#dangerButton {
    background-color: #f38ba8;
    color: #1e1e2e;
    border-color: #f38ba8;
}

QPushButton#dangerButton:hover {
    background-color: #f5a0b8;
}

QPushButton#dangerButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}

QPushButton#successButton {
    background-color: #a6e3a1;
    color: #1e1e2e;
    border-color: #a6e3a1;
}

QPushButton#successButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}

/* === List Widgets === */
QListWidget {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 4px;
}

QListWidget::item {
    padding: 8px;
    border-radius: 4px;
    margin: 2px 0px;
}

QListWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}

QListWidget::item:hover {
    background-color: #282838;
}

/* Ordnerliste nutzt ein eigenes Zeilen-Widget (Badge + Name) mit eigenem
   Innenabstand - das generische 8px-Item-Padding wuerde dafuer zu viel
   Hoehe wegnehmen und die Badge zusammenquetschen. */
QListWidget#folderList::item {
    padding: 2px 4px;
}

/* === Ordnerliste: Nummer-Badge + Name === */
QLabel#folderBadge {
    background-color: #313244;
    color: #89b4fa;
    border-radius: 6px;
    font-weight: bold;
    font-size: 9pt;
    padding: 2px 6px;
}

QLabel#folderNameLabel {
    color: #cdd6f4;
    font-size: 10pt;
}

/* === Tree Widget === */
QTreeWidget {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 4px;
}

QTreeWidget::item {
    padding: 6px;
    border-radius: 4px;
}

QTreeWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}

QTreeWidget::item:hover {
    background-color: #282838;
}

/* === Table Widget === */
QTableWidget {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 6px;
    gridline-color: #313244;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}

QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px;
    border: none;
    border-right: 1px solid #45475a;
    font-weight: bold;
}

/* === Scroll Bars === */
QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #1e1e2e;
    height: 12px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 6px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #585b70;
}

/* === Line Edit === */
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: #89b4fa;
}

QLineEdit:focus {
    border-color: #89b4fa;
}

/* === Combo Box === */
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    min-width: 100px;
}

QComboBox:hover {
    border-color: #585b70;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
}

/* === Spin Box === */
QSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
}

QSpinBox:focus {
    border-color: #89b4fa;
}

/* === Group Box === */
QGroupBox {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 20px;
    font-weight: bold;
}

QGroupBox::title {
    color: #89b4fa;
    subcontrol-origin: margin;
    left: 12px;
    padding: 0px 8px;
}

/* === Progress Bar === */
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}

/* === Status Bar === */
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
}

/* === Label === */
QLabel#coverLabel {
    background-color: #313244;
    border: 2px solid #45475a;
    border-radius: 8px;
}

QLabel#titleLabel {
    font-size: 14pt;
    font-weight: bold;
    color: #cdd6f4;
}

QLabel#subtitleLabel {
    font-size: 10pt;
    color: #a6adc8;
}

/* === Frame === */
QFrame#cardFrame {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
}

/* === RFID-Status ===
   Alle drei Status-Icons nutzen dieselbe Icon-Schriftart (Segoe Fluent Icons /
   Segoe MDL2 Assets) in derselben Groesse, damit sie einheitlich aussehen -
   unabhaengig vom jeweiligen Glyph. Die Boxgroesse wird zusaetzlich fix in
   main_window.py gesetzt (setFixedSize), die Farbe je nach Status hier. */
QLabel#statusIcon {
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets";
    font-size: 22pt;
    color: #585b70;
}

QLabel#statusIcon[state="ok"] {
    color: #a6e3a1;
}

QLabel#statusIcon[state="warning"] {
    color: #f9e2af;
}

QLabel#statusIcon[state="error"] {
    color: #f38ba8;
}

QLabel#statusIcon[state="neutral"] {
    color: #585b70;
}

QLabel#statusCaption {
    font-size: 8pt;
    color: #a6adc8;
}
"""

