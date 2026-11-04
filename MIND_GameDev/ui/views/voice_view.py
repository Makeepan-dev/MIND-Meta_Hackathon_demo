"""
MIND Universal Studio — Meta Hackathon Edition
Voice Console View.
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
    QSlider,
    QCheckBox,
    QPlainTextEdit,
)

from ..theme import MindPalette


class VoiceView(QWidget):
    """Voice interaction and speech synthesis console."""

    speak_requested = pyqtSignal(str)
    voice_toggled = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(14)

        # Header
        hdr = QVBoxLayout()
        title = QLabel("NEURAL AUDIO & VOICE CONSOLE")
        title.setStyleSheet("color: #00F5FF; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        subtitle = QLabel("Hands-Free Speech Synthesis (Windows SAPI) & Hardware Audio Intake Telemetry")
        subtitle.setStyleSheet("color: #8095AC; font-size: 11px;")
        hdr.addWidget(title)
        hdr.addWidget(subtitle)
        layout.addLayout(hdr)

        # Telemetry Card
        tel_card = QFrame()
        tel_card.setStyleSheet("background-color: #101A2C; border: 1px solid #1B2A47; border-radius: 8px; padding: 14px;")
        tel_layout = QVBoxLayout(tel_card)
        tel_layout.setSpacing(10)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Speech Synthesizer:"))
        s_val = QLabel("System.Speech.Synthesis (Active)")
        s_val.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-weight: bold;")
        r1.addWidget(s_val)
        r1.addStretch()

        self.chk_mute = QCheckBox("Voice Feedback Enabled")
        self.chk_mute.setChecked(True)
        self.chk_mute.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-size: 11px;")
        self.chk_mute.toggled.connect(self.voice_toggled.emit)
        r1.addWidget(self.chk_mute)
        tel_layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Microphone Status:"))
        mic_val = QLabel("Hardware Query Standby")
        mic_val.setStyleSheet("color: #FFCB6B; font-family: 'Consolas';")
        r2.addWidget(mic_val)
        r2.addStretch()
        tel_layout.addLayout(r2)

        layout.addWidget(tel_card)

        # Voice Test Box
        test_card = QFrame()
        test_card.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px; padding: 14px;")
        test_layout = QVBoxLayout(test_card)
        test_layout.setSpacing(8)

        test_hdr = QLabel("TEST SPEECH SYNTHESIS")
        test_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        test_layout.addWidget(test_hdr)

        self.test_input = QPlainTextEdit()
        self.test_input.setPlaceholderText("Enter phrase for vocal delivery...")
        self.test_input.setPlainText("MIND Universal Studio online. Neural core functioning within normal parameters.")
        self.test_input.setMaximumHeight(65)
        self.test_input.setStyleSheet("background: #0D1527; border: 1px solid #1B2A47; color: #EAF7FF; font-size: 12px;")
        test_layout.addWidget(self.test_input)

        btn_speak = QPushButton("Speak Phrase 🔊")
        btn_speak.setObjectName("PrimaryBtn")
        btn_speak.setStyleSheet("background: #00F5FF; color: #050811; border: none; font-weight: bold; padding: 8px 16px;")
        btn_speak.clicked.connect(self._handle_speak)
        test_layout.addWidget(btn_speak, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(test_card)

        # Audio Activity Log
        log_hdr = QLabel("AUDIO ACTIVITY & TRANSCRIPTS")
        log_hdr.setStyleSheet("color: #8095AC; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        layout.addWidget(log_hdr)

        self.voice_log = QPlainTextEdit()
        self.voice_log.setReadOnly(True)
        self.voice_log.setStyleSheet("background: #050811; border: 1px solid #1B2A47; border-radius: 6px; font-family: 'Consolas'; font-size: 11px; color: #8095AC;")
        self.voice_log.appendPlainText("[VOICE] Subsystem initialized. Speech synthesis ready via PowerShell SAPI.")
        layout.addWidget(self.voice_log, stretch=1)

    def _handle_speak(self) -> None:
        text = self.test_input.toPlainText().strip()
        if text:
            self.voice_log.appendPlainText(f"[SPEECH OUT]: {text}")
            self.speak_requested.emit(text)
