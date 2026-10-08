"""
Stylesheet fuer den Tonuino-Manager
Modernes Dark Theme mit Akzentfarben
"""

import sys

from gui import theme

# 'Segoe UI' ist eine Windows-exklusive Schriftart und dort das native
# Default - unter macOS/Linux existiert sie nicht. Als fest codierter
# QSS-Font-Family-Name fuehrt sie dort zu einer Qt-Log-Warnung ("Populating
# font family aliases... Replace uses of missing font family") beim Start.
# Auf anderen Plattformen wird die Angabe daher weggelassen, damit Qt die
# native System-Schriftart der jeweiligen Plattform verwendet.
_FONT_FAMILY = "'Segoe UI', " if sys.platform == "win32" else ""

# __FONT_FAMILY__ und die @FARBEN@ (siehe gui/theme.py) werden per str.replace() ersetzt - das Stylesheet bleibt
# dadurch ein normaler (kein f-) String, sodass die zahlreichen QSS-{}-Bloecke
# nicht escaped werden muessen.
_TEMPLATE = """
/* === Globale Styles === */
QMainWindow {
    background-color: @BASE@;
}

/* === Dialoge (QDialog, QMessageBox, QInputDialog) ===
   Ohne diese Regel bleibt der Dialog-Hintergrund beim hellen
   Windows-Standard, waehrend QWidget weiter unten die Schrift hell faerbt -
   das ergibt helle Schrift auf hellem Grund und damit kaum lesbare Dialoge. */
QDialog, QMessageBox {
    background-color: @MENU_BG@;
    border: 1px solid @OVERLAY0@;
}

/* Dialog ist heller als das Hauptfenster - Eingabefelder und Buttons
   brauchen darin eigene Toene, sonst gehen sie im Dialoggrund unter. */
QDialog QLineEdit, QDialog QTextEdit, QDialog QComboBox, QDialog QSpinBox {
    background-color: @BASE@;
}

QDialog QPushButton {
    background-color: @HOVER_MID@;
}

QDialog QPushButton:hover {
    background-color: @HOVER_STRONG@;
}

QMessageBox QLabel {
    color: @TEXT@;
}

QWidget {
    color: @TEXT@;
    font-family: __FONT_FAMILY__'Arial', sans-serif;
    font-size: 10pt;
}

/* === Titelleiste / Menueleiste (siehe gui/title_bar.py, MainWindow._create_menu_bar) === */
QWidget#titleBar {
    background-color: @MANTLE@;
    border-bottom: 1px solid @SURFACE0@;
}

QMenuBar, QMenuBar#titleMenuBar {
    background-color: transparent;
    color: @TEXT@;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: @SURFACE0@;
}

QToolButton#windowButton, QToolButton#windowCloseButton {
    background: transparent;
    border: none;
    border-radius: 0px;
}

QToolButton#windowButton:hover {
    background-color: @SURFACE0@;
}

QToolButton#windowCloseButton:hover {
    background-color: @RED@;
}

QMenu {
    background-color: @BASE@;
    border: 1px solid @SURFACE0@;
}

QMenu::item {
    padding: 6px 24px;
}

QMenu::item:selected {
    background-color: @SURFACE0@;
}

QMenu::separator {
    height: 1px;
    background-color: @SURFACE0@;
    margin: 4px 8px;
}

/* === Sidebar === */
QFrame#sidebar {
    background-color: @MANTLE@;
    border-right: 1px solid @SURFACE0@;
}

QLabel#sidebarTitle {
    color: @BLUE@;
    font-size: 14pt;
    font-weight: bold;
    padding: 10px;
}

/* === Buttons === */
QPushButton {
    background-color: @SURFACE0@;
    color: @TEXT@;
    border: 1px solid @SURFACE1@;
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 20px;
}

/* Eingeschalteter Umschalter (z.B. Mehrfachauswahl) */
QPushButton:checked {
    background-color: @BLUE@;
    color: @BASE@;
    border-color: @BLUE@;
    font-weight: bold;
}

QPushButton:hover {
    background-color: @SURFACE1@;
    border-color: @SURFACE2@;
}

QPushButton:pressed {
    background-color: @SURFACE2@;
}

QPushButton:disabled {
    background-color: @BASE@;
    color: @SURFACE2@;
    border-color: @SURFACE0@;
}

/* === Slider (Player: Fortschritt, Lautstaerke) === */
QSlider::groove:horizontal {
    height: 4px;
    background: @SURFACE1@;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: @BLUE@;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: @TEXT@;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}

QSlider::handle:horizontal:hover {
    background: @WHITE@;
}

/* deaktiviert: nichts gefuellt, Griff abgedunkelt */
QSlider::sub-page:horizontal:disabled {
    background: @SURFACE0@;
}

QSlider::groove:horizontal:disabled {
    background: @SURFACE0@;
}

QSlider::handle:horizontal:disabled {
    background: @SURFACE1@;
}

/* Lautstaerke: schlank und zurueckhaltend, Griff erst beim Ueberfahren sichtbar */
QSlider#volumeSlider {
    background: transparent;
}

QSlider#volumeSlider::groove:horizontal {
    height: 3px;
    background: @SURFACE1@;
    border-radius: 1px;
}

QSlider#volumeSlider::sub-page:horizontal {
    background: @TEXT@;
    border-radius: 1px;
}

QSlider#volumeSlider::handle:horizontal {
    background: transparent;
    width: 10px;
    height: 10px;
    margin: -4px 0;
    border-radius: 5px;
}

/* "hovered" setzt ClickSlider beim Ueberfahren/Ziehen (die Pseudo-Klasse :hover
   vor ::handle versteht Qt nicht und faerbt sonst den ganzen Slider) */
QSlider#volumeSlider[hovered="true"]::handle:horizontal {
    background: @WHITE@;
}

/* stumm: Leiste abgedunkelt */
QSlider#volumeSlider[muted="true"]::sub-page:horizontal {
    background: @SURFACE2@;
}

QSlider#volumeSlider[muted="true"][hovered="true"]::handle:horizontal {
    background: @OVERLAY2@;
}

QLabel:disabled {
    color: @SURFACE2@;
}

/* Flache Player-Steuerelemente (Zurueck/Play/Weiter) ohne Button-Hintergrund */
QPushButton#transportButton,
QPushButton#transportButton:hover,
QPushButton#transportButton:pressed,
QPushButton#transportButton:disabled {
    background: transparent;
    border: none;
    padding: 0px;
}

QPushButton#primaryButton {
    background-color: @BLUE@;
    color: @BASE@;
    border-color: @BLUE@;
    font-weight: bold;
}

QPushButton#primaryButton:hover {
    background-color: @BLUE_HOVER@;
}

QPushButton#primaryButton:disabled {
    background-color: @BASE@;
    color: @SURFACE2@;
    border-color: @SURFACE0@;
}

QPushButton#dangerButton {
    background-color: @RED@;
    color: @BASE@;
    border-color: @RED@;
}

QPushButton#dangerButton:hover {
    background-color: @RED_HOVER@;
}

QPushButton#dangerButton:disabled {
    background-color: @BASE@;
    color: @SURFACE2@;
    border-color: @SURFACE0@;
}

/* Werkzeugleiste ueber der Track-Liste: gleiche Optik wie die uebrigen Buttons,
   nur kompakter (weniger Padding) */
QPushButton#ghostButton {
    padding: 6px 12px;
}

QPushButton#ghostButton:checked {
    font-weight: normal;
}

/* Eingeschaltet: beim Ueberfahren etwas hellers Blau statt des grauen Hover-Hintergrunds */
QPushButton#ghostButton:checked:hover {
    background-color: @BLUE_HOVER@;
    border-color: @BLUE_HOVER@;
    color: @BASE@;
}

QPushButton#softDangerButton {
    background-color: rgba(243, 139, 168, 30);
    color: @RED@;
    border: 1px solid rgba(243, 139, 168, 70);
}

QPushButton#softDangerButton:hover {
    background-color: rgba(243, 139, 168, 60);
    border-color: rgba(243, 139, 168, 120);
}

QPushButton#softDangerButton:disabled {
    background-color: @BASE@;
    color: @SURFACE2@;
    border-color: @SURFACE0@;
}
QPushButton#successButton {
    background-color: @GREEN@;
    color: @BASE@;
    border-color: @GREEN@;
}

QPushButton#successButton:disabled {
    background-color: @BASE@;
    color: @SURFACE2@;
    border-color: @SURFACE0@;
}

/* === List Widgets === */
QListWidget {
    background-color: @BASE@;
    border: 1px solid @SURFACE0@;
    border-radius: 6px;
    padding: 4px;
}

QListWidget::item {
    padding: 8px;
    border-radius: 4px;
    margin: 2px 0px;
}

/* Auswahlkreise der Mehrfachauswahl (wie in Apple Mail) */
QListWidget::indicator {
    width: 16px;
    height: 16px;
    border-radius: 9px;
    border: 2px solid @OVERLAY0@;
    background: transparent;
}

/* markiert: grauer Ring bleibt, innen sitzt ein deutlich kleinerer blauer Punkt
   (wie ein Radiobutton) */
QListWidget::indicator:checked {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 @BLUE@, stop:0.38 @BLUE@, stop:0.5 transparent, stop:1 transparent);
}

/* Track-Liste: schlanke Zeilen ohne Rahmen */
QListWidget#trackList {
    background: transparent;
    border: none;
    padding: 0px;
    outline: none;
}

QListWidget#trackList::item {
    padding: 4px 10px;
    margin: 1px 0px;
    border-radius: 8px;
}

QListWidget::item:selected {
    background-color: @SURFACE0@;
    color: @BLUE@;
}

QListWidget::item:hover {
    background-color: @SURFACE_DEEP@;
}

/* Ordnerliste nutzt ein eigenes Zeilen-Widget (Badge + Name) mit eigenem
   Innenabstand - das generische 8px-Item-Padding wuerde dafuer zu viel
   Hoehe wegnehmen und die Badge zusammenquetschen. */
QListWidget#folderList::item {
    padding: 2px 4px;
}

/* === Ordnerliste: Nummer-Badge + Name === */
QLabel#folderBadge {
    background-color: @SURFACE0@;
    color: @BLUE@;
    border-radius: 6px;
    font-weight: bold;
    font-size: 9pt;
    padding: 2px 6px;
}

QLabel#folderNameLabel {
    color: @TEXT@;
    font-size: 10pt;
}

/* Read-only Ordnerliste: mp3/advert Tonuio-Systemordner */
QLabel#folderBadgeSpecial {
    background-color: @BASE@;
    color: @SURFACE2@;
    border: 1px solid @SURFACE0@;
    border-radius: 6px;
    font-weight: bold;
    font-size: 9pt;
    padding: 2px 6px;
}

QLabel#folderNameLabelSpecial {
    color: @SURFACE2@;
    font-size: 10pt;
    font-style: italic;
}

/* === Tree Widget === */
QTreeWidget {
    background-color: @BASE@;
    border: 1px solid @SURFACE0@;
    border-radius: 6px;
    padding: 4px;
}

QTreeWidget::item {
    padding: 6px;
    border-radius: 4px;
}

QTreeWidget::item:selected {
    background-color: @SURFACE0@;
    color: @BLUE@;
}

QTreeWidget::item:hover {
    background-color: @SURFACE_DEEP@;
}

/* === Table Widget === */
QTableWidget {
    background-color: @BASE@;
    border: 1px solid @SURFACE0@;
    border-radius: 6px;
    gridline-color: @SURFACE0@;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: @SURFACE0@;
    color: @BLUE@;
}

QHeaderView::section {
    background-color: @SURFACE0@;
    color: @TEXT@;
    padding: 8px;
    border: none;
    border-right: 1px solid @SURFACE1@;
    font-weight: bold;
}

/* === Scroll Bars === */
QScrollBar:vertical {
    background-color: @BASE@;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: @SURFACE1@;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: @SURFACE2@;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: @BASE@;
    height: 12px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background-color: @SURFACE1@;
    border-radius: 6px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background-color: @SURFACE2@;
}

/* === Line Edit === */
QLineEdit {
    background-color: @SURFACE0@;
    color: @TEXT@;
    border: 1px solid @SURFACE1@;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: @BLUE@;
}

QLineEdit:focus {
    border-color: @BLUE@;
}

/* === Text Edit === */
QTextEdit {
    background-color: @SURFACE0@;
    color: @TEXT@;
    border: 1px solid @SURFACE1@;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: @BLUE@;
}

QTextEdit:focus {
    border-color: @BLUE@;
}

/* === Combo Box === */
QComboBox {
    background-color: @SURFACE0@;
    color: @TEXT@;
    border: 1px solid @SURFACE1@;
    border-radius: 6px;
    padding: 8px;
    min-width: 100px;
}

QComboBox:hover {
    border-color: @SURFACE2@;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox QAbstractItemView {
    background-color: @SURFACE0@;
    color: @TEXT@;
    border: 1px solid @SURFACE1@;
    selection-background-color: @SURFACE1@;
}

/* === Spin Box === */
QSpinBox {
    background-color: @SURFACE0@;
    color: @TEXT@;
    border: 1px solid @SURFACE1@;
    border-radius: 6px;
    padding: 8px;
}

QSpinBox:focus {
    border-color: @BLUE@;
}

/* === Group Box === */
QGroupBox {
    background-color: @MANTLE@;
    border: 1px solid @SURFACE0@;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 20px;
    font-weight: bold;
}

QGroupBox::title {
    color: @BLUE@;
    subcontrol-origin: margin;
    left: 12px;
    padding: 0px 8px;
}

/* === Progress Bar === */
QProgressBar {
    background-color: @SURFACE0@;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: @TEXT@;
    height: 20px;
}

QProgressBar::chunk {
    background-color: @BLUE@;
    border-radius: 4px;
}

/* === Status Bar === */
QStatusBar {
    background-color: @MANTLE@;
    color: @SUBTEXT0@;
}

/* === Label === */
/* === Ordner-Kopfbereich (Name, Ordnernummer, Infozeile) === */
QLabel#folderTitle {
    font-size: 24pt;
    font-weight: bold;
    color: @TEXT@;
}

QLabel#folderSubtitle {
    font-size: 15pt;
    color: @BLUE@;
}

QLabel#folderMeta {
    font-size: 9pt;
    font-weight: bold;
    color: @OVERLAY1@;
}

QLabel#titleLabel {
    font-size: 14pt;
    font-weight: bold;
    color: @TEXT@;
}

QLabel#subtitleLabel {
    font-size: 10pt;
    color: @SUBTEXT0@;
}

/* Inhaltsblock des Players: durchsichtig, damit die Karte dahinter sichtbar bleibt */
QWidget#playerContent {
    background: transparent;
}

/* === Player: Now-Playing-Anzeige === */
QLabel#playerTitle {
    font-size: 11pt;
    font-weight: bold;
    color: @TEXT@;
}

QLabel#playerMeta {
    font-size: 9pt;
    color: @OVERLAY2@;
}

/* Kopfkarte des Ordners (Cover, Name, Aktionen) */
QFrame#heroCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 @SURFACE0@, stop:1 @MANTLE@);
    border: 1px solid @SURFACE0@;
    border-radius: 14px;
}

QLabel#sectionTitle {
    font-size: 13pt;
    font-weight: bold;
    color: @TEXT@;
}

/* Play/Pause im Player: heller Kreis */
QPushButton#playButton,
QPushButton#playButton:pressed {
    background-color: @TEXT@;
    border: none;
    border-radius: 22px;
    padding: 0px;
    min-width: 44px;
    max-width: 44px;
    min-height: 44px;
    max-height: 44px;
}

QPushButton#playButton:hover {
    background-color: @WHITE@;
}

QPushButton#playButton:disabled {
    background-color: @SURFACE0@;
    border: none;
    border-radius: 22px;
}

/* Player-Fusszeile: buendig am unteren Rand, nur Trennlinie oben */
QFrame#playerFooter {
    background-color: @MANTLE@;
    border: none;
    border-top: 1px solid @SURFACE0@;
    border-radius: 0;
}

/* === Frame === */
QFrame#cardFrame {
    background-color: @MANTLE@;
    border: 1px solid @SURFACE0@;
    border-radius: 8px;
}

/* === RFID-Status ===
   Alle drei Status-Icons nutzen dieselbe Icon-Schriftart (Material Icons,
   Apache-2.0, gebuendelt in resources/fonts/ - siehe main.py) in derselben
   Groesse, damit sie einheitlich aussehen - unabhaengig vom jeweiligen Glyph
   und plattformneutral (Windows/macOS/Linux). Die Boxgroesse wird zusaetzlich
   fix in main_window.py gesetzt (setFixedSize), die Farbe je nach Status hier. */
QLabel#statusIcon {
    font-family: "Material Icons";
    font-size: 22pt;
    color: @SURFACE2@;
}

QLabel#statusIcon[state="ok"] {
    color: @GREEN@;
}

QLabel#statusIcon[state="warning"] {
    color: @YELLOW@;
}

QLabel#statusIcon[state="error"] {
    color: @RED@;
}

QLabel#statusIcon[state="neutral"] {
    color: @SURFACE2@;
}

QLabel#statusCaption {
    font-size: 8pt;
    color: @SUBTEXT0@;
}
""".replace("__FONT_FAMILY__", _FONT_FAMILY)

MAIN_STYLESHEET = theme.apply(_TEMPLATE)
