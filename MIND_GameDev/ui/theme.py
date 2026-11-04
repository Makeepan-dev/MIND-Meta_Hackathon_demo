"""
MIND Universal Studio — Meta Hackathon Edition
Theme, Palette, and Global Qt Stylesheet.

Implements the JARVIS-inspired cyan, electric blue, and deep navy aesthetic:
- Background: #050811
- Secondary background: #0A1020
- Panel background: #101A2C
- Primary cyan: #00F5FF
- Electric blue: #397BFF
- Secondary violet: #8B5CFF
- Primary text: #EAF7FF
- Muted text: #8095AC
- Success: #4DFFAA
- Warning: #FFCB6B
- Error: #FF5577
"""

from __future__ import annotations
from dataclasses import dataclass
from PyQt6.QtGui import QColor, QFont


@dataclass(frozen=True)
class MindPalette:
    BG_DARK = "#050811"
    BG_SECONDARY = "#0A1020"
    BG_PANEL = "#101A2C"
    BG_PANEL_HOVER = "#15223A"
    BG_INPUT = "#0D1527"
    
    CYAN_PRIMARY = "#00F5FF"
    CYAN_GLOW = "#00F5FF"
    CYAN_MUTED = "#00A8B3"
    
    BLUE_ELECTRIC = "#397BFF"
    BLUE_DARK = "#1E3A8A"
    
    VIOLET_ACCENT = "#8B5CFF"
    
    TEXT_PRIMARY = "#EAF7FF"
    TEXT_MUTED = "#8095AC"
    TEXT_DIM = "#4B5E75"
    
    BORDER_SUBTLE = "#1B2A47"
    BORDER_ACTIVE = "#00F5FF"
    BORDER_GLOW = "rgba(0, 245, 255, 0.4)"
    
    SUCCESS = "#4DFFAA"
    WARNING = "#FFCB6B"
    ERROR = "#FF5577"
    
    # QColor objects
    Q_BG_DARK = QColor("#050811")
    Q_BG_SECONDARY = QColor("#0A1020")
    Q_BG_PANEL = QColor("#101A2C")
    Q_CYAN = QColor("#00F5FF")
    Q_BLUE = QColor("#397BFF")
    Q_VIOLET = QColor("#8B5CFF")
    Q_SUCCESS = QColor("#4DFFAA")
    Q_WARNING = QColor("#FFCB6B")
    Q_ERROR = QColor("#FF5577")
    Q_TEXT = QColor("#EAF7FF")
    Q_TEXT_MUTED = QColor("#8095AC")


GLOBAL_STYLESHEET = """
QMainWindow, QWidget#CentralWidget {
    background-color: #050811;
    color: #EAF7FF;
    font-family: 'Segoe UI', 'Consolas', 'Arial', sans-serif;
}

QWidget {
    font-family: 'Segoe UI', 'Consolas', 'Arial', sans-serif;
    color: #EAF7FF;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #0A1020;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #1B2A47;
    min-height: 25px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #00F5FF;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #0A1020;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #1B2A47;
    min-width: 25px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #00F5FF;
}

/* Tooltips */
QToolTip {
    background-color: #101A2C;
    color: #00F5FF;
    border: 1px solid #00F5FF;
    border-radius: 4px;
    padding: 6px 10px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
}

/* Standard Buttons */
QPushButton {
    background-color: #101A2C;
    color: #EAF7FF;
    border: 1px solid #1B2A47;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #15223A;
    border: 1px solid #00F5FF;
    color: #00F5FF;
}
QPushButton:pressed {
    background-color: #1A2D4E;
    border: 1px solid #397BFF;
}
QPushButton:disabled {
    background-color: #0A1020;
    color: #4B5E75;
    border: 1px solid #131E33;
}

/* Primary Action Button (Cyan Glow) */
QPushButton#PrimaryBtn {
    background-color: #00F5FF;
    color: #050811;
    border: none;
    font-weight: bold;
}
QPushButton#PrimaryBtn:hover {
    background-color: #70FBFF;
}
QPushButton#PrimaryBtn:pressed {
    background-color: #00C8D1;
}

/* Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #0D1527;
    color: #EAF7FF;
    border: 1px solid #1B2A47;
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: #397BFF;
    selection-color: #FFFFFF;
    font-size: 13px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #00F5FF;
    background-color: #101B30;
}

/* Labels */
QLabel {
    color: #EAF7FF;
}
QLabel#MutedLabel {
    color: #8095AC;
    font-size: 11px;
}
QLabel#HeaderLabel {
    color: #00F5FF;
    font-size: 15px;
    font-weight: bold;
    letter-spacing: 1px;
}

/* Panels and Cards */
QFrame#PanelFrame {
    background-color: #101A2C;
    border: 1px solid #1B2A47;
    border-radius: 8px;
}
QFrame#CardFrame {
    background-color: #0A1020;
    border: 1px solid #1B2A47;
    border-radius: 6px;
}
QFrame#CardFrame:hover {
    border: 1px solid #397BFF;
}

/* Lists and Tables */
QListWidget, QTreeWidget, QTableWidget {
    background-color: #0A1020;
    color: #EAF7FF;
    border: 1px solid #1B2A47;
    border-radius: 6px;
    padding: 4px;
}
QListWidget::item, QTreeWidget::item {
    padding: 8px 12px;
    border-radius: 4px;
    margin-bottom: 2px;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background-color: #101A2C;
    color: #00F5FF;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #15223A;
    color: #00F5FF;
    border-left: 3px solid #00F5FF;
}

/* Tab Bar */
QTabBar::tab {
    background: #0A1020;
    color: #8095AC;
    border: 1px solid #1B2A47;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 18px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #101A2C;
    color: #00F5FF;
    border-bottom: 2px solid #00F5FF;
}
QTabBar::tab:hover:!selected {
    color: #EAF7FF;
    background: #0F172B;
}
"""
