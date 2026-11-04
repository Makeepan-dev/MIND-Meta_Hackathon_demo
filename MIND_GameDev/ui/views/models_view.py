"""
MIND Universal Studio — Meta Hackathon Edition
AI Model & Provider Management Console.
"""

from __future__ import annotations

import time
from typing import Optional, List, Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QGridLayout,
)

from ..backend_bridge import BackendBridge
from ..theme import MindPalette


class ProviderCard(QFrame):
    """Card displaying a configured AI model provider."""

    test_requested = pyqtSignal(str)

    def __init__(self, provider_data: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.p_data = provider_data
        self.setObjectName("CardFrame")
        self.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px; padding: 12px;")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header: Name + Status Badge
        hdr = QHBoxLayout()
        name_lbl = QLabel(provider_data.get("name", "Unknown"))
        name_lbl.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 13px; font-weight: bold;")
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        status = provider_data.get("status", "READY")
        status_lbl = QLabel(f"● {status}")
        if status in ("READY", "ONLINE"):
            status_lbl.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        else:
            status_lbl.setStyleSheet("color: #8095AC; font-family: 'Consolas'; font-size: 10px;")
        hdr.addWidget(status_lbl)
        layout.addLayout(hdr)

        # Model and Tier Details
        grid = QGridLayout()
        grid.setSpacing(4)
        
        grid.addWidget(QLabel("Model:"), 0, 0)
        m_val = QLabel(provider_data.get("model", "Default"))
        m_val.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-size: 11px;")
        grid.addWidget(m_val, 0, 1)

        grid.addWidget(QLabel("Tier:"), 1, 0)
        t_val = QLabel(provider_data.get("tier", "Cloud"))
        t_val.setStyleSheet("color: #8095AC; font-size: 11px;")
        grid.addWidget(t_val, 1, 1)

        grid.addWidget(QLabel("Key Auth:"), 2, 0)
        k_val = QLabel(provider_data.get("key_masked", "None"))
        k_val.setStyleSheet("color: #8095AC; font-family: 'Consolas'; font-size: 11px;")
        grid.addWidget(k_val, 2, 1)

        layout.addLayout(grid)

        # Test button
        btn_test = QPushButton("Test Latency")
        btn_test.setStyleSheet(
            "background: #101A2C; color: #00F5FF; border: 1px solid #1B2A47; "
            "border-radius: 4px; padding: 5px 10px; font-size: 11px; font-family: 'Consolas';"
        )
        btn_test.clicked.connect(lambda: self.test_requested.emit(self.p_data.get("name", "")))
        layout.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignRight)


class ModelsView(QWidget):
    """View managing connected local and cloud AI models."""

    def __init__(self, bridge: BackendBridge, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(14)

        # Header Banner
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AI MODEL & PROVIDER CONSOLE")
        title.setStyleSheet("color: #00F5FF; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        subtitle = QLabel("Hybrid Multi-Brain Orchestration: Local Ollama Daemons + High-Performance Cloud LPUs")
        subtitle.setStyleSheet("color: #8095AC; font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hdr.addLayout(title_box)

        hdr.addStretch()

        btn_refresh = QPushButton("Refresh Status 🔄")
        btn_refresh.setStyleSheet("background: #0A1020; color: #00F5FF; border: 1px solid #1B2A47;")
        btn_refresh.clicked.connect(self.reload_providers)
        hdr.addWidget(btn_refresh)
        layout.addLayout(hdr)

        # Scroll area with cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #050811; border: 1px solid #1B2A47; border-radius: 8px;")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(14, 14, 14, 14)
        self.cards_layout.setSpacing(12)

        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, stretch=1)

        self.reload_providers()

    def reload_providers(self) -> None:
        """Clears and re-populates provider cards."""
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        providers = self.bridge.get_configured_providers()
        for p in providers:
            card = ProviderCard(p, self.cards_container)
            card.test_requested.connect(self._handle_test)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def _handle_test(self, provider_name: str) -> None:
        # Quick non-blocking feedback
        pass
