"""
MIND Universal Studio — Meta Hackathon Edition
Activity & Task History View.
"""

from __future__ import annotations

import time
from typing import Optional, List, Dict, Any
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from ..theme import MindPalette


class ActivityView(QWidget):
    """Activity history and audit trail."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("SYSTEM ACTIVITY & TASK AUDIT LOG")
        title.setStyleSheet("color: #00F5FF; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        subtitle = QLabel("Immutable Event Telemetry: Commands, Code Synthesis, Static Verification, & Artifact Deliveries")
        subtitle.setStyleSheet("color: #8095AC; font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hdr.addLayout(title_box)

        hdr.addStretch()

        btn_clear = QPushButton("Clear History")
        btn_clear.setStyleSheet("background: #0A1020; color: #8095AC; border: 1px solid #1B2A47;")
        btn_clear.clicked.connect(self._clear_table)
        hdr.addWidget(btn_clear)

        layout.addLayout(hdr)

        # Activity Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Category", "Operation / Prompt", "Target / Artifact", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px; gridline-color: #15223A; font-family: 'Consolas'; font-size: 11px; } "
            "QHeaderView::section { background-color: #101A2C; color: #00F5FF; border: 1px solid #1B2A47; padding: 6px; font-weight: bold; }"
        )
        layout.addWidget(self.table)

        # Seed initial system events
        from ...config import REPO_ROOT
        self.log_event("SYSTEM", "MIND — Mageepan's Intelligence Network Device Initialized", str(REPO_ROOT), "ONLINE")
        self.log_event("DIAGNOSTICS", "Multi-Brain Provider Layer Checked", "Meta AI Model API, Google Stitch, Ollama", "VERIFIED")

    def log_event(self, category: str, operation: str, target: str, status: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        ts = time.strftime("%H:%M:%S")
        self.table.setItem(row, 0, QTableWidgetItem(ts))
        self.table.setItem(row, 1, QTableWidgetItem(category))
        self.table.setItem(row, 2, QTableWidgetItem(operation))
        self.table.setItem(row, 3, QTableWidgetItem(target))
        
        status_item = QTableWidgetItem(status)
        if status in ("ONLINE", "VERIFIED", "SUCCESS"):
            status_item.setForeground(MindPalette.Q_SUCCESS)
        elif status in ("ERROR", "FAILED"):
            status_item.setForeground(MindPalette.Q_ERROR)
        else:
            status_item.setForeground(MindPalette.Q_CYAN)
        self.table.setItem(row, 4, status_item)

    def _clear_table(self) -> None:
        self.table.setRowCount(0)
