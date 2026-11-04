"""
MIND Universal Studio — Meta Hackathon Edition
Main Desktop Window with Collapsible Navigation Rail and Intelligence Panel.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QFont, QColor
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QFrame,
    QSplitter,
    QScrollArea,
    QApplication,
)

from .theme import MindPalette, GLOBAL_STYLESHEET
from .backend_bridge import BackendBridge, AIWorker, DevStudioWorker
from .core_widget import CoreState

from .views.home_view import HomeView
from .views.chat_view import ChatView
from .views.models_view import ModelsView
from .views.studio_view import StudioView
from .views.voice_view import VoiceView
from .views.activity_view import ActivityView
from .views.settings_view import SettingsView
from .views.evidence_view import EvidenceView
from ..tools.screenshot_manager import WorkflowScreenshotManager


class NavButton(QPushButton):
    """Custom styled navigation button for the left rail."""

    def __init__(self, icon_str: str, text: str, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(f"  {icon_str}  {text}", parent)
        self.index = index
        self.setCheckable(True)
        self.setFixedHeight(42)
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8095AC;
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding-left: 14px;
                font-size: 12px;
                font-weight: 600;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: #0A1020;
                color: #00F5FF;
            }
            QPushButton:checked {
                background: #101A2C;
                color: #00F5FF;
                border-left: 3px solid #00F5FF;
            }
        """)


class MINDMainWindow(QMainWindow):
    """
    Main Application Window for MIND — Meta Global AI Hackathon Edition.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MIND — Mageepan's Intelligence Network Device // Meta Hackathon Edition")
        self.resize(1280, 820)
        self.setMinimumSize(1000, 680)

        self.bridge = BackendBridge(self)

        self.setStyleSheet(GLOBAL_STYLESHEET)
        self._build_ui()
        self._connect_signals()

        # Connect Central Screenshot Manager to desktop window
        WorkflowScreenshotManager.get_instance().set_active_window(self)

        # Default to Unified Assistant (Primary Workspace)
        self.set_active_view(0)

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. Left Navigation Rail
        # -------------------------------------------------------------
        self.nav_rail = QFrame(self)
        self.nav_rail.setFixedWidth(220)
        self.nav_rail.setStyleSheet("background-color: #050811; border-right: 1px solid #1B2A47;")
        nav_layout = QVBoxLayout(self.nav_rail)
        nav_layout.setContentsMargins(0, 16, 0, 16)
        nav_layout.setSpacing(4)

        # Brand Logo Header
        logo_box = QHBoxLayout()
        logo_box.setContentsMargins(16, 4, 16, 16)
        lbl_logo = QLabel("⚡ MIND")
        lbl_logo.setStyleSheet("color: #00F5FF; font-size: 16px; font-weight: bold; font-family: 'Consolas'; letter-spacing: 2px;")
        lbl_ver = QLabel("v2.5")
        lbl_ver.setStyleSheet("color: #397BFF; font-size: 10px; font-family: 'Consolas';")
        logo_box.addWidget(lbl_logo)
        logo_box.addWidget(lbl_ver)
        logo_box.addStretch()
        nav_layout.addLayout(logo_box)

        # Navigation Buttons
        self.nav_buttons: list[NavButton] = []
        nav_items = [
            ("🤖", "Unified Assistant", 0),
            ("⭕", "Home / System Overview", 1),
            ("🧠", "AI Models", 2),
            ("🛠️", "Dev Studio", 3),
            ("📜", "Task History", 4),
            ("📸", "Visual Evidence", 5),
            ("⚙️", "Settings", 6),
        ]

        for icon_str, label_str, idx in nav_items:
            btn = NavButton(icon_str, label_str, idx, self.nav_rail)
            btn.clicked.connect(lambda checked, i=idx: self.set_active_view(i))
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)

        nav_layout.addStretch()

        # Bottom System Tag
        sys_tag = QLabel("META HACKATHON\nREADY // 2026")
        sys_tag.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 9px; font-weight: bold; padding: 16px;")
        nav_layout.addWidget(sys_tag)

        main_layout.addWidget(self.nav_rail)

        # -------------------------------------------------------------
        # 2. Center Workspace Stack
        # -------------------------------------------------------------
        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background-color: #050811;")

        # Views
        self.chat_view = ChatView(self.stack)
        self.home_view = HomeView(self.stack)
        self.models_view = ModelsView(self.bridge, self.stack)
        self.studio_view = StudioView(self.stack)
        self.activity_view = ActivityView(self.stack)
        self.evidence_view = EvidenceView(self.stack)
        self.settings_view = SettingsView(self.bridge, self.stack)

        self.stack.addWidget(self.chat_view)      # 0: Unified Assistant (Primary)
        self.stack.addWidget(self.home_view)      # 1: Home / System Overview
        self.stack.addWidget(self.models_view)    # 2: AI Models
        self.stack.addWidget(self.studio_view)    # 3: Dev Studio
        self.stack.addWidget(self.activity_view)  # 4: Task History
        self.stack.addWidget(self.evidence_view)  # 5: Visual Evidence
        self.stack.addWidget(self.settings_view)  # 6: Settings

        main_layout.addWidget(self.stack, stretch=1)

        # -------------------------------------------------------------
        # 3. Right Intelligence Telemetry Panel (Collapsible)
        # -------------------------------------------------------------
        self.intel_panel = QFrame(self)
        self.intel_panel.setFixedWidth(260)
        self.intel_panel.setStyleSheet("background-color: #0A1020; border-left: 1px solid #1B2A47;")
        intel_layout = QVBoxLayout(self.intel_panel)
        intel_layout.setContentsMargins(16, 16, 16, 16)
        intel_layout.setSpacing(14)

        # Panel Title
        intel_hdr = QHBoxLayout()
        lbl_intel = QLabel("SYSTEM INTELLIGENCE")
        lbl_intel.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        intel_hdr.addWidget(lbl_intel)
        intel_hdr.addStretch()

        btn_toggle = QPushButton("✕")
        btn_toggle.setFixedSize(22, 22)
        btn_toggle.setStyleSheet("background: transparent; color: #8095AC; border: none; font-size: 11px;")
        btn_toggle.clicked.connect(lambda: self.intel_panel.setVisible(not self.intel_panel.isVisible()))
        intel_hdr.addWidget(btn_toggle)
        intel_layout.addLayout(intel_hdr)

        # Status Cards
        # 1. System Health
        c1 = QFrame()
        c1.setStyleSheet("background: #101A2C; border: 1px solid #1B2A47; border-radius: 6px; padding: 10px;")
        c1_layout = QVBoxLayout(c1)
        c1_layout.setSpacing(4)
        c1_layout.addWidget(QLabel("STATUS: ONLINE"))
        self.lbl_intel_status = QLabel("● All Systems Nominal")
        self.lbl_intel_status.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        c1_layout.addWidget(self.lbl_intel_status)
        intel_layout.addWidget(c1)

        # 2. Selected Provider & Model
        c2 = QFrame()
        c2.setStyleSheet("background: #101A2C; border: 1px solid #1B2A47; border-radius: 6px; padding: 10px;")
        c2_layout = QVBoxLayout(c2)
        c2_layout.setSpacing(4)
        c2_layout.addWidget(QLabel("PRIMARY BRAIN:"))
        self.lbl_intel_model = QLabel("Llama 3.3 70B (Groq)")
        self.lbl_intel_model.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px;")
        c2_layout.addWidget(self.lbl_intel_model)
        intel_layout.addWidget(c2)

        # 3. Active Task Card
        c3 = QFrame()
        c3.setStyleSheet("background: #101A2C; border: 1px solid #1B2A47; border-radius: 6px; padding: 10px;")
        c3_layout = QVBoxLayout(c3)
        c3_layout.setSpacing(4)
        c3_layout.addWidget(QLabel("ACTIVE TASK:"))
        self.lbl_intel_task = QLabel("Standby / Listening")
        self.lbl_intel_task.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-size: 11px;")
        c3_layout.addWidget(self.lbl_intel_task)
        intel_layout.addWidget(c3)

        # 4. Capabilities Detected
        c4 = QFrame()
        c4.setStyleSheet("background: #101A2C; border: 1px solid #1B2A47; border-radius: 6px; padding: 10px;")
        c4_layout = QVBoxLayout(c4)
        c4_layout.setSpacing(4)
        c4_layout.addWidget(QLabel("CAPABILITIES:"))
        cap_text = QLabel("✔ Autonomous Web Builder\n✔ Component Contract\n✔ Multi-Brain Router\n✔ PowerShell SAPI TTS\n✔ Safe Workspace")
        cap_text.setStyleSheet("color: #8095AC; font-family: 'Consolas'; font-size: 10px; line-height: 1.5;")
        c4_layout.addWidget(cap_text)
        intel_layout.addWidget(c4)

        intel_layout.addStretch()
        main_layout.addWidget(self.intel_panel)
        # Initially hide telemetry panel so Unified Assistant owns the full width on startup
        self.intel_panel.hide()

    def _connect_signals(self) -> None:
        # Unified Assistant signals
        self.chat_view.prompt_sent.connect(self._handle_chat_prompt)
        self.chat_view.voice_toggled.connect(self._handle_voice_toggle)

        # Home View signals
        self.home_view.command_submitted.connect(self._handle_prompt_submission)
        self.home_view.voice_toggled.connect(self._handle_voice_toggle)

        # Studio View signals
        self.studio_view.build_requested.connect(self._handle_studio_build)

        # Settings signals
        self.settings_view.reduced_motion_toggled.connect(self.home_view.core_widget.set_reduced_motion)

    def set_active_view(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        # Telemetry panel belongs exclusively to Home / System Overview (index 1), NOT the Unified Assistant
        self.intel_panel.setVisible(index == 1)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        if index == 5 and hasattr(self, "evidence_view"):
            self.evidence_view.refresh()

    def _handle_prompt_submission(self, prompt: str) -> None:
        """Processes prompts submitted via Home view, transitioning to Unified Assistant to display live workflow and artifacts."""
        self.set_active_view(0)
        self.chat_view.add_message("User", prompt)
        self._handle_chat_prompt(prompt, "AUTO")

    def _handle_chat_prompt(self, prompt: str, brain_choice: str) -> None:
        """Processes prompts submitted via Chat view."""
        self.lbl_intel_task.setText(f"Chat: {brain_choice}")
        self.activity_view.log_event("CHAT", prompt[:40], brain_choice, "THINKING")

        worker = AIWorker(prompt, brain_type=brain_choice, parent=self)
        worker.workflow_progress.connect(self.chat_view.update_workflow_progress)
        worker.workflow_completed.connect(self.chat_view.complete_workflow)
        worker.response_ready.connect(self.chat_view.handle_response_ready)
        worker.task_failed.connect(lambda err: self.chat_view.add_message("MIND", f"[ERROR] {err}", model_tag="FAULT"))
        self.chat_view.cancel_requested.connect(worker.cancel)
        worker.start()
        self.bridge.track_worker(worker)

    def _on_prompt_success(self, response: str, model_tag: str) -> None:
        self.home_view.set_response(response, model_tag)
        self.lbl_intel_task.setText("Standby / Ready")
        self.activity_view.log_event("RESPONSE", response[:40], model_tag, "SUCCESS")
        # Vocalize first sentence
        first_sentence = response.split(".")[0] if "." in response else response[:60]
        self.bridge.speak(first_sentence)

    def _on_prompt_failure(self, err_msg: str) -> None:
        self.home_view.set_error(err_msg)
        self.lbl_intel_task.setText("Fault Detected")
        self.activity_view.log_event("FAULT", err_msg[:40], "Cortex", "ERROR")

    def _handle_studio_build(self, command: str, dest_dir: Optional[str]) -> None:
        """Processes autonomous development requests from Studio view."""
        self.home_view.set_generating(command, progress=0.2)
        self.lbl_intel_task.setText("Autonomous Build")
        self.activity_view.log_event("STUDIO", command[:40], dest_dir or "Default Workspace", "BUILDING")

        worker = DevStudioWorker(command, dest_dir, parent=self)
        worker.step_update.connect(self.studio_view.update_progress)
        worker.build_complete.connect(self._on_build_complete)
        worker.build_failed.connect(self.studio_view.on_build_failed)
        worker.start()
        self.bridge.track_worker(worker)

    def _on_build_complete(self, result: dict) -> None:
        self.studio_view.on_build_complete(result)
        self.home_view.set_response(f"Project '{result.get('title', 'Generated Project')}' forged and verified.", model_tag="STUDIO")
        self.lbl_intel_task.setText("Project Verified")
        self.activity_view.log_event("STUDIO", result.get("title", "Project"), str(result.get("project_path", "")), "VERIFIED")
        self.bridge.speak("Project creation complete and verified.")

    def _handle_voice_toggle(self) -> None:
        enabled = not self.bridge.config.voice_enabled
        self.bridge.config.voice_enabled = enabled
        self.home_view.btn_mic.setText("🎙️ ACTIVE" if enabled else "🔇 MUTED")
        self.bridge.speak("Voice output enabled." if enabled else "Voice muted.")

    def closeEvent(self, event) -> None:
        # Release the design preview popup first. This is purely a UI cleanup:
        # it never approves a pending design and never touches project files.
        try:
            self.chat_view.shutdown_previews()
        except Exception:
            pass
        try:
            from ..tools.preview_server import WorkspacePreviewServer
            WorkspacePreviewServer.stop_all()
        except Exception:
            pass
        super().closeEvent(event)
