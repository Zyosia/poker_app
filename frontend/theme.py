"""Colors and stylesheet shared by the whole interface."""

from PySide6.QtGui import QColor

BACKGROUND = QColor("#14181f")
FELT_CENTER = QColor("#2f8f5b")
FELT_EDGE = QColor("#17603a")
TABLE_RIM = QColor("#3b2a1f")
TABLE_RIM_LIGHT = QColor("#6b4a34")
GOLD = QColor("#f2c14e")
TEXT = QColor("#eef1f5")
MUTED_TEXT = QColor("#9aa4b2")
CARD_FACE = QColor("#fbfbf8")
CARD_BACK = QColor("#28508f")
CARD_BACK_PATTERN = QColor("#3f6fb8")
CARD_RED = QColor("#c8102e")
CARD_BLACK = QColor("#16181d")
CARD_BLUE = QColor("#1f5fc4")
CARD_GREEN = QColor("#1d8a3c")
CHIP = QColor("#d9534f")
GRID = QColor("#2c3442")
POSITIVE = QColor("#3ddc84")
NEGATIVE = QColor("#ff7b7b")

SETTINGS_BUTTON_SIZE = 34
SETTINGS_BUTTON_MARGIN = 10
SETTINGS_BUTTON_ROOM = SETTINGS_BUTTON_SIZE + SETTINGS_BUTTON_MARGIN
"""Left free at the start of a top bar for the settings button above it."""

SERIES_COLORS = (
    QColor("#f2c14e"),
    QColor("#4ea8f2"),
    QColor("#3ddc84"),
    QColor("#e0607e"),
    QColor("#b48cf2"),
    QColor("#f29a4e"),
)
"""One colour per player line in the charts."""

STYLESHEET = """
QMainWindow { background-color: #14181f; }

QWidget {
    color: #eef1f5;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
}

QLabel { background: transparent; }

QLabel#title {
    font-size: 44px;
    font-weight: 700;
    color: #f2c14e;
}

QLabel#subtitle { font-size: 16px; color: #9aa4b2; }
QLabel#sectionTitle { font-size: 13px; font-weight: 600; color: #9aa4b2; }
QPushButton#tableButton { padding: 6px 12px; font-size: 13px; }
QPushButton#tableButton[yourTurn="true"] {
    background-color: #f2c14e;
    color: #14181f;
    font-weight: 700;
}
QStackedWidget#tableFrame[yourTurn="true"] { border: 3px solid #f2c14e; }

QScrollArea#handHistory {
    background-color: #10141a;
    border: 1px solid #2c3442;
    border-radius: 10px;
}
QWidget#handHistoryContent { background: transparent; }
QFrame#historyHand { background-color: #1b212b; border-radius: 8px; }
QLabel#historyHandTitle { font-size: 13px; font-weight: 700; color: #f2c14e; }
QLabel#historyBlinds { font-size: 11px; color: #9aa4b2; }
QLabel#historySection {
    font-size: 11px;
    font-weight: 700;
    color: #9aa4b2;
    letter-spacing: 1px;
}
QLabel#historyName { font-size: 12px; color: #9aa4b2; }
QLabel#historyName[hero="true"] { color: #eef1f5; font-weight: 700; }
QLabel#historyAction, QLabel#historyNote { font-size: 12px; }
QLabel[tone="post"] { color: #7d8794; }
QLabel[tone="fold"] { color: #7d8794; }
QLabel[tone="passive"] { color: #eef1f5; }
QLabel[tone="aggressive"] { color: #f2a33a; font-weight: 600; }
QLabel[tone="allIn"] { color: #ff7b7b; font-weight: 700; }
QLabel[tone="result"] { color: #3ddc84; font-weight: 600; }
QLabel[tone="note"] { color: #9aa4b2; font-style: italic; }
QLabel[tone="alert"] { color: #f2a33a; }
QLabel#resultText { font-size: 16px; font-weight: 600; }

QFrame#panel {
    background-color: #1c222c;
    border: 1px solid #2c3442;
    border-radius: 12px;
}

QPushButton {
    background-color: #2c3442;
    border: 1px solid #3a4456;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
}

QPushButton:hover { background-color: #384356; }
QPushButton:pressed { background-color: #232a36; }
QPushButton:disabled {
    color: #5d6675;
    background-color: #1c222c;
    border-color: #262d39;
}

QPushButton#primary { background-color: #2f8f5b; border-color: #3aa76b; }
QPushButton#primary:hover { background-color: #37a369; }
QPushButton#primary:disabled { background-color: #1e3b2c; border-color: #244836; }

QPushButton#danger { background-color: #8f2f3a; border-color: #a83a47; }
QPushButton#danger:hover { background-color: #a53643; }
QPushButton#danger:disabled { background-color: #3a1f24; border-color: #47262c; }

QPushButton#accent { background-color: #b9861d; border-color: #d39b25; }
QPushButton#accent:hover { background-color: #cf9722; }
QPushButton#accent:disabled { background-color: #40331a; border-color: #4d3d1f; }

QPushButton#small { padding: 6px 10px; font-size: 12px; }
QPushButton#danger { color: #ff7b7b; border-color: #7a3434; }
QPushButton#danger:hover { background-color: #3a1f22; }
QPushButton#danger:disabled { color: #5a6270; border-color: #2c3442; }
QPushButton#help {
    min-width: 26px;
    max-width: 26px;
    padding: 4px 0;
    border-radius: 13px;
    font-weight: 700;
    color: #f2c14e;
}

QWidget#guideWindow, QScrollArea#guidePage, QWidget#guidePageContent {
    background-color: #14181f;
}
QListWidget#guideNavigation {
    background-color: #101319;
    border: none;
    border-right: 1px solid #2c3442;
    padding-top: 12px;
    font-size: 14px;
}
QListWidget#guideNavigation::item { padding: 9px 16px; }
QListWidget#guideNavigation::item:selected {
    background-color: #222a36;
    color: #f2c14e;
    border-left: 3px solid #f2c14e;
}
QLabel#guideTitle { font-size: 26px; font-weight: 700; color: #f2c14e; }
QLabel#guideHeading { font-size: 16px; font-weight: 600; color: #eef1f5; }
QLabel#guideText { font-size: 14px; color: #d4d9e1; }
QFrame#guideCard {
    background-color: #1b212b;
    border: 1px solid #2c3442;
    border-radius: 10px;
}
QLabel#guideCardName { font-size: 18px; font-weight: 700; color: #f2c14e; }
QLabel#guideMeter { color: #f2c14e; font-size: 13px; letter-spacing: 2px; }
QPushButton#toggle { padding: 6px 10px; font-size: 12px; }
QPushButton#toggle:checked {
    background-color: #f2c14e;
    color: #14181f;
    font-weight: 700;
}
QPushButton#toggle:checked:disabled { background-color: #3a4456; color: #9aa4b2; }

QLineEdit, QSpinBox, QComboBox {
    background-color: #232a36;
    border: 1px solid #3a4456;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 22px;
}

QComboBox QAbstractItemView {
    background-color: #232a36;
    selection-background-color: #2f8f5b;
}

QPlainTextEdit {
    background-color: #1c222c;
    border: 1px solid #2c3442;
    border-radius: 8px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 12px;
}

QSlider::groove:horizontal { height: 6px; background: #2c3442; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #b9861d; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #f2c14e;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:disabled { background: #5d6675; }

QPushButton#modeCard {
    background-color: #1c222c;
    border: 1px solid #2c3442;
    border-radius: 14px;
    padding: 0;
    text-align: left;
}
QPushButton#modeCard:hover { background-color: #222a36; border-color: #b9861d; }
QPushButton#modeCard:disabled { background-color: #171b22; border-color: #222833; }
QLabel#modeSymbol { font-size: 30px; color: #f2c14e; }
QLabel#modeSymbol:disabled { color: #5d6675; }
QLabel#modeName { font-size: 17px; font-weight: 700; }
QLabel#modeName:disabled { color: #6c7584; }
QLabel#modeDescription { font-size: 12px; color: #9aa4b2; }
QLabel#modeNote { font-size: 11px; font-weight: 600; color: #b9861d; }
QLabel#errorText { color: #ff7b7b; }
QLabel#summaryText { font-size: 15px; }
QLabel#playerName { font-weight: 700; color: #f2c14e; }
QLabel#statusText { font-size: 13px; font-weight: 600; color: #c9d1dc; }
QLabel#noticeText {
    font-size: 14px;
    font-weight: 600;
    color: #1a1a1a;
    background-color: #f2c14e;
    border-radius: 8px;
    padding: 6px 14px;
}
QLabel#revealText {
    font-size: 44px;
    font-weight: 800;
    color: #f2c14e;
    padding: 10px;
}

QDialog#settingsDialog { background-color: #14181f; }
QGroupBox {
    background-color: #1c222c;
    border: 1px solid #2c3442;
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 12px 10px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #f2c14e;
}
QLabel#hintText { font-size: 12px; color: #9aa4b2; }
QPushButton#settingsButton {
    background-color: #1c222c;
    border: 1px solid #2c3442;
    border-radius: 17px;
    padding: 0;
}
QPushButton#settingsButton:hover { border-color: #b9861d; }

QCheckBox { spacing: 8px; }
QCheckBox:disabled { color: #5d6675; }

QTableWidget {
    background-color: #1c222c;
    alternate-background-color: #202733;
    border: 1px solid #2c3442;
    border-radius: 8px;
    gridline-color: #2c3442;
}
QHeaderView::section {
    background-color: #232a36;
    color: #9aa4b2;
    border: none;
    border-bottom: 1px solid #3a4456;
    padding: 6px 8px;
    font-weight: 600;
}

QTabWidget::pane { border: 1px solid #2c3442; border-radius: 8px; top: -1px; }
QTabBar::tab {
    background: #1c222c;
    border: 1px solid #2c3442;
    padding: 8px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: #9aa4b2;
}
QTabBar::tab:selected { background: #232a36; color: #f2c14e; }

QProgressBar {
    background-color: #232a36;
    border: 1px solid #3a4456;
    border-radius: 8px;
    height: 22px;
    text-align: center;
}
QProgressBar::chunk { background-color: #2f8f5b; border-radius: 7px; }

QScrollArea { border: none; background: transparent; }
QScrollArea QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollArea QScrollBar::handle:vertical {
    background: #3a4456;
    border-radius: 3px;
    min-height: 30px;
}
QScrollArea QScrollBar::add-line:vertical,
QScrollArea QScrollBar::sub-line:vertical { height: 0; }
"""
