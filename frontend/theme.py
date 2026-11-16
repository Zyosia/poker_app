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
CHIP = QColor("#d9534f")

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
"""
