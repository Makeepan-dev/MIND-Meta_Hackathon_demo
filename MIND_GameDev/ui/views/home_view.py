"""
MIND Universal Studio — Meta Hackathon Edition
Home View with JARVIS Circular AI Core and Integrated Command Hub.
"""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QPlainTextEdit,
    QSizePolicy,
)

from ..core_widget import JarvisAICoreWidget, CoreState
from ..theme import MindPalette


class HomeView(QWidget):
    """
    Primary cockpit displaying the animated circular AI core,
    system identity, quick status telemetry, and interactive command console.
    """

    command_submitted = pyqtSignal(str)
    voice_toggled = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        # 1. Top Telemetry Banner
        telemetry = QHBoxLayout()
        telemetry.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel("MIND // UNIVERSAL INTELLIGENCE NETWORK")
        title_label.setObjectName("HeaderLabel")
        title_label.setStyleSheet("color: #00F5FF; font-size: 15px; font-weight: bold; letter-spacing: 1.5px;")
        
        subtitle_label = QLabel("JARVIS-Class Cognitive Operating System • Meta Global AI Hackathon Edition")
        subtitle_label.setStyleSheet("color: #8095AC; font-size: 11px;")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)
        telemetry.addLayout(title_box)

        telemetry.addStretch()

        # Quick Status Badges
        self.badge_status = QLabel("● CORTEX ACTIVE")
        self.badge_status.setStyleSheet(
            "background: #0A1020; color: #4DFFAA; border: 1px solid #1B2A47; "
            "border-radius: 4px; padding: 4px 10px; font-family: 'Consolas'; font-weight: bold; font-size: 11px;"
        )
        telemetry.addWidget(self.badge_status)

        self.badge_model = QLabel("Llama 3.3 70B [Groq]")
        self.badge_model.setStyleSheet(
            "background: #0A1020; color: #00F5FF; border: 1px solid #1B2A47; "
            "border-radius: 4px; padding: 4px 10px; font-family: 'Consolas'; font-size: 11px;"
        )
        telemetry.addWidget(self.badge_model)

        layout.addLayout(telemetry)

        # 2. Central JARVIS Circular AI Core
        self.core_widget = JarvisAICoreWidget(self)
        self.core_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.core_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # 3. Response Display Area (Expandable/collapsible)
        self.response_card = QFrame(self)
        self.response_card.setObjectName("PanelFrame")
        self.response_card.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px;")
        resp_layout = QVBoxLayout(self.response_card)
        resp_layout.setContentsMargins(14, 10, 14, 10)
        resp_layout.setSpacing(4)

        self.response_header = QLabel("MIND CORTEX TELEMETRY")
        self.response_header.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        resp_layout.addWidget(self.response_header)

        self.response_text = QLabel("System standing by. Enter a natural-language command or prompt below.")
        self.response_text.setWordWrap(True)
        self.response_text.setStyleSheet("color: #EAF7FF; font-size: 12px; line-height: 1.4;")
        resp_layout.addWidget(self.response_text)
        layout.addWidget(self.response_card)

        # 4. Integrated Command Hub (Bottom Input)
        command_box = QFrame(self)
        command_box.setObjectName("CardFrame")
        command_box.setStyleSheet("background-color: #101A2C; border: 1px solid #1B2A47; border-radius: 8px;")
        cmd_layout = QHBoxLayout(command_box)
        cmd_layout.setContentsMargins(10, 8, 10, 8)
        cmd_layout.setSpacing(10)

        self.input_edit = QPlainTextEdit(command_box)
        self.input_edit.setPlaceholderText("Ask MIND or instruct development (e.g., 'create a cyberpunk portfolio website', 'analyze model latency')...")
        self.input_edit.setMaximumHeight(54)
        self.input_edit.setStyleSheet(
            "background: transparent; border: none; color: #EAF7FF; font-size: 13px; font-family: 'Segoe UI', sans-serif;"
        )
        cmd_layout.addWidget(self.input_edit, stretch=1)

        # Voice Button
        self.btn_mic = QPushButton("🎙️ MIC", command_box)
        self.btn_mic.setToolTip("Toggle Voice Synthesis / Audio Intake")
        self.btn_mic.setStyleSheet(
            "background: #0A1020; color: #4DFFAA; border: 1px solid #1B2A47; border-radius: 6px; padding: 8px 12px; font-weight: bold;"
        )
        self.btn_mic.clicked.connect(self.voice_toggled.emit)
        cmd_layout.addWidget(self.btn_mic)

        # Send / Execute Button
        self.btn_send = QPushButton("TRANSMIT ⚡", command_box)
        self.btn_send.setObjectName("PrimaryBtn")
        self.btn_send.setStyleSheet(
            "background: #00F5FF; color: #050811; border: none; border-radius: 6px; padding: 10px 18px; font-weight: bold; font-family: 'Consolas';"
        )
        self.btn_send.clicked.connect(self._handle_send)
        cmd_layout.addWidget(self.btn_send)

        layout.addWidget(command_box)

    def _handle_send(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if text:
            self.input_edit.clear()
            self.command_submitted.emit(text)

    def set_thinking(self, prompt: str) -> None:
        self.core_widget.set_state(CoreState.THINKING, "NEURAL SYNTHESIS")
        self.badge_status.setText("● THINKING")
        self.badge_status.setStyleSheet("background: #0A1020; color: #00F5FF; border: 1px solid #00F5FF; border-radius: 4px; padding: 4px 10px; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        self.response_header.setText("MIND CORTEX REASONING")
        self.response_text.setText(f"Processing query: '{prompt}'...")

    def set_generating(self, task_name: str, progress: float = 0.5) -> None:
        self.core_widget.set_state(CoreState.GENERATING, "CODE SYNTHESIS")
        self.core_widget.set_progress(progress)
        self.badge_status.setText("● GENERATING")
        self.badge_status.setStyleSheet("background: #0A1020; color: #8B5CFF; border: 1px solid #8B5CFF; border-radius: 4px; padding: 4px 10px; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        self.response_header.setText("AUTONOMOUS SOFTWARE BUILDER")
        self.response_text.setText(f"Active task: {task_name}")

    def set_response(self, text: str, model_tag: str = "") -> None:
        self.core_widget.set_state(CoreState.IDLE, "READY")
        self.badge_status.setText("● ONLINE")
        self.badge_status.setStyleSheet("background: #0A1020; color: #4DFFAA; border: 1px solid #1B2A47; border-radius: 4px; padding: 4px 10px; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        if model_tag:
            self.badge_model.setText(model_tag)
        self.response_header.setText(f"MIND RESPONSE // {model_tag or 'CORTEX'}")
        self.response_text.setText(text[:450] + ("..." if len(text) > 450 else ""))

    def set_error(self, err_msg: str) -> None:
        self.core_widget.set_state(CoreState.ERROR, "ERROR DETECTED")
        self.badge_status.setText("● ERROR")
        self.badge_status.setStyleSheet("background: #0A1020; color: #FF5577; border: 1px solid #FF5577; border-radius: 4px; padding: 4px 10px; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        self.response_header.setText("EXECUTION FAULT")
        self.response_text.setText(err_msg)
