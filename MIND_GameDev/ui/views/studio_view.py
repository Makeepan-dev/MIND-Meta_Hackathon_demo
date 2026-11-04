"""
MIND Universal Studio — Meta Hackathon Edition
Autonomous Development Studio View.
"""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QComboBox,
    QProgressBar,
    QListWidget,
    QSplitter,
    QFileDialog,
)

from ..theme import MindPalette


class StudioView(QWidget):
    """Integrated Autonomous Software Development Studio."""

    build_requested = pyqtSignal(str, str)  # (command, dest_dir)
    verify_requested = pyqtSignal(str)     # (project_dir)
    serve_requested = pyqtSignal(str)      # (project_dir)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_project_dir: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        # Header Banner
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("MIND DEVELOPMENT STUDIO // AUTONOMOUS BUILDER")
        title.setStyleSheet("color: #00F5FF; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        subtitle = QLabel("Cross-Domain Software Creation: Websites, Web Apps, 3D Games, Backend APIs, & Automations")
        subtitle.setStyleSheet("color: #8095AC; font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hdr.addLayout(title_box)

        hdr.addStretch()

        self.lbl_status = QLabel("● IDLE")
        self.lbl_status.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        hdr.addWidget(self.lbl_status)
        layout.addLayout(hdr)

        # Input & Configuration Card
        cfg_card = QFrame()
        cfg_card.setObjectName("PanelFrame")
        cfg_card.setStyleSheet("background-color: #101A2C; border: 1px solid #1B2A47; border-radius: 8px; padding: 12px;")
        cfg_layout = QVBoxLayout(cfg_card)
        cfg_layout.setSpacing(10)

        # Domain Picker + Destination Row
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Project Domain:"))
        self.domain_combo = QComboBox()
        self.domain_combo.setStyleSheet("background: #0A1020; color: #00F5FF; border: 1px solid #1B2A47; border-radius: 4px; padding: 5px;")
        self.domain_combo.addItems([
            "AI Image-to-3D Reconstruction (Blender GLB)",
            "Website (HTML5/CSS3/JS Multi-Page)",
            "Web App (Single-Page App Dashboard)",
            "AI Image / Concept Art (Diffusion)",
            "3D Game (Three.js WebGL Runner)",
            "Backend API (FastAPI Microservice)",
            "Desktop App (Tkinter Diagnostic Utility)",
            "Mobile App (Android Kotlin)",
        ])
        row1.addWidget(self.domain_combo, stretch=1)

        row1.addWidget(QLabel("Destination:"))
        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Default Workspace (or click Browse...)")
        self.dest_edit.setStyleSheet("background: #0A1020; color: #EAF7FF; border: 1px solid #1B2A47; padding: 5px;")
        row1.addWidget(self.dest_edit, stretch=1)

        btn_browse = QPushButton("Browse...")
        btn_browse.setStyleSheet("background: #0A1020; color: #8095AC; border: 1px solid #1B2A47;")
        btn_browse.clicked.connect(self._browse_dest)
        row1.addWidget(btn_browse)

        cfg_layout.addLayout(row1)

        # Prompt input + Build Button
        row2 = QHBoxLayout()
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setPlaceholderText("Natural language description (e.g. 'Create a sports day registration website with cricket & football details')...")
        self.prompt_edit.setStyleSheet("background: #0A1020; color: #EAF7FF; border: 1px solid #1B2A47; border-radius: 6px; padding: 8px 12px; font-size: 13px;")
        row2.addWidget(self.prompt_edit, stretch=1)

        self.btn_build = QPushButton("FORGE PROJECT ⚡")
        self.btn_build.setObjectName("PrimaryBtn")
        self.btn_build.setStyleSheet("background: #00F5FF; color: #050811; border: none; border-radius: 6px; padding: 10px 18px; font-weight: bold; font-family: 'Consolas';")
        self.btn_build.clicked.connect(self._handle_build)
        row2.addWidget(self.btn_build)

        cfg_layout.addLayout(row2)
        layout.addWidget(cfg_card)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #0A1020; border: none; border-radius: 2px; } "
            "QProgressBar::chunk { background: #00F5FF; border-radius: 2px; }"
        )
        layout.addWidget(self.progress_bar)

        # Main Splitter: Left = Live Execution Log, Right = Artifacts & Actions
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #1B2A47; width: 2px; }")

        # Left: Execution Log
        log_panel = QFrame()
        log_panel.setObjectName("CardFrame")
        log_panel.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px;")
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(12, 10, 12, 10)
        log_layout.setSpacing(6)

        log_hdr = QLabel("LIVE BUILD TELEMETRY")
        log_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        log_layout.addWidget(log_hdr)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "background: transparent; border: none; color: #8095AC; font-family: 'Consolas'; font-size: 11px; line-height: 1.4;"
        )
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_panel)

        # Right: Artifacts and Actions
        art_panel = QFrame()
        art_panel.setObjectName("CardFrame")
        art_panel.setStyleSheet("background-color: #0A1020; border: 1px solid #1B2A47; border-radius: 8px;")
        art_layout = QVBoxLayout(art_panel)
        art_layout.setContentsMargins(12, 10, 12, 10)
        art_layout.setSpacing(8)

        art_hdr = QLabel("PROJECT ARTIFACTS & ACTIONS")
        art_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        art_layout.addWidget(art_hdr)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet(
            "background: #050811; border: 1px solid #1B2A47; border-radius: 6px; font-family: 'Consolas'; font-size: 11px;"
        )
        art_layout.addWidget(self.file_list, stretch=1)

        # Action Buttons Row
        act_row = QHBoxLayout()
        self.btn_serve = QPushButton("Serve / Launch 🌐")
        self.btn_serve.setEnabled(False)
        self.btn_serve.setStyleSheet("background: #101A2C; color: #00F5FF; border: 1px solid #1B2A47; font-size: 11px;")
        self.btn_serve.clicked.connect(self._handle_serve)
        act_row.addWidget(self.btn_serve)

        self.btn_verify = QPushButton("Run Tests ✔")
        self.btn_verify.setEnabled(False)
        self.btn_verify.setStyleSheet("background: #101A2C; color: #4DFFAA; border: 1px solid #1B2A47; font-size: 11px;")
        self.btn_verify.clicked.connect(self._handle_verify)
        act_row.addWidget(self.btn_verify)

        self.btn_open = QPushButton("Open Folder 📁")
        self.btn_open.setEnabled(False)
        self.btn_open.setStyleSheet("background: #101A2C; color: #8095AC; border: 1px solid #1B2A47; font-size: 11px;")
        self.btn_open.clicked.connect(self._handle_open_dir)
        act_row.addWidget(self.btn_open)

        art_layout.addLayout(act_row)
        splitter.addWidget(art_panel)

        splitter.setSizes([450, 350])
        layout.addWidget(splitter, stretch=1)

        # Initial log message
        self.append_log("MIND Universal Studio ready. Select domain, enter instructions, and click FORGE PROJECT.")

    def _browse_dest(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.dest_edit.setText(folder)

    def _handle_build(self) -> None:
        prompt = self.prompt_edit.text().strip()
        if not prompt:
            return
        
        domain_choice = self.domain_combo.currentText()
        if "3D Reconstruction" in domain_choice:
            cmd = prompt if any(k in prompt.lower() for k in ["3d", "dragon", "model", "mesh", "reconstruct"]) else f"create 3d model of {prompt}"
        else:
            cmd = f"create {prompt}"
        dest = self.dest_edit.text().strip() or None

        self.lbl_status.setText("● SYNTHESIZING")
        self.lbl_status.setStyleSheet("color: #8B5CFF; font-family: 'Consolas'; font-weight: bold;")
        self.btn_build.setEnabled(False)
        self.progress_bar.setValue(15)
        self.append_log(f"\n[NEW TASK] Command: '{cmd}'")
        if dest:
            self.append_log(f"[CONFIG] Destination: {dest}")

        self.build_requested.emit(cmd, dest)

    def append_log(self, text: str) -> None:
        self.log_text.appendPlainText(text)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def update_progress(self, msg: str, val: float) -> None:
        self.append_log(f">> {msg}")
        self.progress_bar.setValue(int(val * 100))

    def on_build_complete(self, result: Dict[str, Any]) -> None:
        self.btn_build.setEnabled(True)
        self.lbl_status.setText("● VERIFIED")
        self.lbl_status.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-weight: bold;")
        self.progress_bar.setValue(100)

        p_path = result.get("project_path") or result.get("destination") or ""
        self.current_project_dir = p_path

        self.append_log(f"\n[BUILD SUCCESS] Project generated at: {p_path}")
        if result.get("action") == "reconstruct_3d":
            self.append_log(f"\n⚡ [AI 3D RECONSTRUCTION COMPLETE]")
            self.append_log(f"  • Asset Name:       {result.get('asset_name')}")
            self.append_log(f"  • Reference Image:  {result.get('reference_image')}")
            self.append_log(f"  • Exported GLB:     {result.get('glb_path')}")
            self.append_log(f"  • Rendered Preview: {result.get('preview_path')}")
            self.append_log(f"  • GLB File Size:    {result.get('file_size_bytes')} bytes")
            attr = result.get("model_attribution", {})
            self.append_log(f"  • AI Orchestration Telemetry:")
            self.append_log(f"     - Vision Model:   {attr.get('vision_analysis', {}).get('provider')} // {attr.get('vision_analysis', {}).get('model')}")
            self.append_log(f"     - Coding Model:   {attr.get('code_generation', {}).get('provider')} // {attr.get('code_generation', {}).get('model')}")
            self.append_log(f"     - Blender Engine: {attr.get('3d_execution_engine', {}).get('engine')} // {attr.get('3d_execution_engine', {}).get('version')}")
        else:
            self.append_log(f"[METRICS] AI Tier: {result.get('ai_provider', 'default')} | Model: {result.get('ai_model', 'default')}")

        # Populate file tree
        self.file_list.clear()
        if p_path and os.path.exists(p_path):
            self.btn_serve.setEnabled(True)
            self.btn_verify.setEnabled(True)
            self.btn_open.setEnabled(True)

            p_obj = Path(p_path)
            for f in sorted(list(p_obj.rglob("*"))):
                if f.is_file():
                    rel = f.relative_to(p_obj)
                    size = f.stat().st_size
                    self.file_list.addItem(f"📄 {rel}  ({size} bytes)")

    def on_build_failed(self, error_msg: str) -> None:
        self.btn_build.setEnabled(True)
        self.lbl_status.setText("● FAULT")
        self.lbl_status.setStyleSheet("color: #FF5577; font-family: 'Consolas'; font-weight: bold;")
        self.progress_bar.setValue(0)
        self.append_log(f"\n[BUILD ERROR] Execution failed: {error_msg}")

    def _handle_serve(self) -> None:
        if self.current_project_dir:
            idx = Path(self.current_project_dir) / "index.html"
            if idx.exists():
                webbrowser.open(f"file:///{idx.resolve()}")
                self.append_log(f"[BROWSER] Launched preview: {idx.resolve()}")

    def _handle_verify(self) -> None:
        if self.current_project_dir:
            self.verify_requested.emit(self.current_project_dir)

    def _handle_open_dir(self) -> None:
        if self.current_project_dir and os.path.exists(self.current_project_dir):
            os.startfile(self.current_project_dir)
