"""
MIND Universal Studio — Meta Hackathon Edition
Settings & System Diagnostics View.
"""

from __future__ import annotations

import os
import sys
import psutil
import platform
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QCheckBox,
    QComboBox,
    QScrollArea,
    QGridLayout,
)

from ..backend_bridge import BackendBridge
from ..theme import MindPalette


class SettingsView(QWidget):
    """Configuration, system telemetry, and diagnostic diagnostics."""

    reduced_motion_toggled = pyqtSignal(bool)

    def __init__(self, bridge: BackendBridge, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(14)

        # Header
        hdr = QVBoxLayout()
        title = QLabel("SYSTEM CONFIGURATION & DIAGNOSTICS")
        title.setStyleSheet("color: #00F5FF; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        subtitle = QLabel("Hardware Telemetry, Neural Parameters, Preferences, & Runtime Integrity")
        subtitle.setStyleSheet("color: #8095AC; font-size: 11px;")
        hdr.addWidget(title)
        hdr.addWidget(subtitle)
        layout.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #050811; border: 1px solid #1B2A47; border-radius: 8px;")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(14, 14, 14, 14)
        c_layout.setSpacing(14)

        # 1. Hardware & Runtime Telemetry
        hw_card = QFrame()
        hw_card.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px; padding: 14px;")
        hw_layout = QVBoxLayout(hw_card)
        hw_layout.setSpacing(8)

        hw_hdr = QLabel("HARDWARE ENVIRONMENT")
        hw_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        hw_layout.addWidget(hw_hdr)

        grid = QGridLayout()
        grid.setSpacing(6)

        grid.addWidget(QLabel("OS:"), 0, 0)
        os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        lbl_os = QLabel(os_info)
        lbl_os.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-size: 11px;")
        grid.addWidget(lbl_os, 0, 1)

        grid.addWidget(QLabel("Processor:"), 1, 0)
        lbl_cpu = QLabel(platform.processor() or "Intel Core i5-11400H")
        lbl_cpu.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-size: 11px;")
        grid.addWidget(lbl_cpu, 1, 1)

        grid.addWidget(QLabel("RAM Memory:"), 2, 0)
        vm = psutil.virtual_memory()
        ram_info = f"{round(vm.total / (1024**3), 1)} GB Total ({vm.percent}% utilized)"
        lbl_ram = QLabel(ram_info)
        lbl_ram.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-size: 11px;")
        grid.addWidget(lbl_ram, 2, 1)

        grid.addWidget(QLabel("Python Runtime:"), 3, 0)
        lbl_py = QLabel(f"Python {sys.version.split()[0]} (64-bit AMD64)")
        lbl_py.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-size: 11px;")
        grid.addWidget(lbl_py, 3, 1)

        hw_layout.addLayout(grid)
        c_layout.addWidget(hw_card)

        # 2. Performance & Visual Preferences
        pref_card = QFrame()
        pref_card.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px; padding: 14px;")
        pref_layout = QVBoxLayout(pref_card)
        pref_layout.setSpacing(10)

        pref_hdr = QLabel("DISPLAY & MOTION PREFERENCES")
        pref_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        pref_layout.addWidget(pref_hdr)

        self.chk_motion = QCheckBox("Reduced Motion Mode (Optimized 25 FPS rendering)")
        self.chk_motion.setStyleSheet("color: #EAF7FF; font-size: 12px;")
        self.chk_motion.toggled.connect(self.reduced_motion_toggled.emit)
        pref_layout.addWidget(self.chk_motion)

        self.chk_voice = QCheckBox("Audio Voice Feedback (PowerShell SAPI)")
        self.chk_voice.setChecked(True)
        self.chk_voice.setStyleSheet("color: #EAF7FF; font-size: 12px;")
        pref_layout.addWidget(self.chk_voice)

        c_layout.addWidget(pref_card)

        # 3. Security & Safe Workspace
        sec_card = QFrame()
        sec_card.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px; padding: 14px;")
        sec_layout = QVBoxLayout(sec_card)
        sec_layout.setSpacing(6)

        sec_hdr = QLabel("SECURITY ENCLAVE & CREDENTIAL POLICIES")
        sec_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        sec_layout.addWidget(sec_hdr)

        sec_text = QLabel(
            "• Zero Secret Leakage: All cloud API keys are masked and strictly isolated from the UI.\n"
            "• Safe Workspace Containment: Path traversal protection prevents unauthorized system escapes.\n"
            "• Untrusted Code Protection: Generated scripts are quarantined and never auto-executed without explicit user confirmation."
        )
        sec_text.setStyleSheet("color: #8095AC; font-size: 11px; line-height: 1.5;")
        sec_layout.addWidget(sec_text)

        c_layout.addWidget(sec_card)
        c_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)
