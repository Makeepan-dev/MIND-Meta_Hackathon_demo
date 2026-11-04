"""
MIND Universal Studio — Meta Hackathon Edition
Conversational Chat Interface with Workflow Artifact Bubble Integration.
"""

from __future__ import annotations

import os
import sys
import time
import webbrowser
import subprocess
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QPlainTextEdit,
    QScrollArea,
    QComboBox,
    QProgressBar,
    QApplication,
)

from ..widgets import DesignPreviewManager
from ..widgets.design_preview_window import (
    STATE_AWAITING,
    STATE_APPROVAL_SENT,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_GENERATING,
)
from ..theme import MindPalette


def open_path_in_explorer(path: str) -> None:
    """Opens a file or containing directory in the system file manager."""
    try:
        abs_path = os.path.abspath(path)
        if sys.platform == "win32":
            if os.path.isdir(abs_path):
                os.startfile(abs_path)
            elif os.path.exists(abs_path):
                subprocess.Popen(f'explorer /select,"{abs_path}"')
            else:
                parent = os.path.dirname(abs_path)
                if os.path.exists(parent):
                    os.startfile(parent)
        else:
            target = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
            subprocess.Popen(["xdg-open", target])
    except Exception as e:
        print(f"Error opening explorer for '{path}': {e}")


def open_file_default(path: str) -> None:
    """Opens a file using the operating system's default viewer."""
    try:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            if sys.platform == "win32":
                os.startfile(abs_path)
            else:
                subprocess.Popen(["xdg-open", abs_path])
    except Exception as e:
        print(f"Error opening file '{path}': {e}")


def open_in_browser(path: str) -> None:
    """Opens an HTML artifact directly in the default web browser."""
    try:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            webbrowser.open(f"file:///{abs_path.replace(os.sep, '/')}")
    except Exception as e:
        print(f"Error opening browser for '{path}': {e}")


class ChatMessageBubble(QFrame):
    """Standard conversational chat message bubble for ordinary interactions."""

    def __init__(
        self,
        sender: str,
        text: str,
        model_tag: str = "",
        is_user: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardFrame")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # Header with sender & timestamp
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        if is_user:
            self.setStyleSheet("background-color: #0D1B33; border: 1px solid #1B3560; border-radius: 8px;")
            sender_lbl = QLabel("USER")
            sender_lbl.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        else:
            self.setStyleSheet("background-color: #101A2C; border: 1px solid #1B2A47; border-radius: 8px;")
            sender_lbl = QLabel(f"MIND // {model_tag or 'CORTEX'}")
            sender_lbl.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")

        hdr.addWidget(sender_lbl)
        hdr.addStretch()

        ts = time.strftime("%H:%M:%S")
        time_lbl = QLabel(ts)
        time_lbl.setStyleSheet("color: #8095AC; font-size: 10px; font-family: 'Consolas';")
        hdr.addWidget(time_lbl)

        # Copy button
        btn_copy = QPushButton("Copy")
        btn_copy.setStyleSheet(
            "background: transparent; color: #8095AC; border: 1px solid #1B2A47; "
            "border-radius: 4px; padding: 2px 8px; font-size: 10px;"
        )
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(text))
        hdr.addWidget(btn_copy)

        layout.addLayout(hdr)

        # Content
        content_lbl = QLabel(text)
        content_lbl.setWordWrap(True)
        content_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_lbl.setStyleSheet("color: #EAF7FF; font-size: 13px; line-height: 1.45;")
        layout.addWidget(content_lbl)


class WorkflowArtifactBubble(QFrame):
    """
    Rich interactive UI component displaying live multi-brain workflow progress,
    individual DAG task statuses, generated artifact listings, image/browser previews,
    verification metrics, design approval gates, and directory actions.
    """

    cancel_requested = pyqtSignal()
    approve_requested = pyqtSignal()
    reject_requested = pyqtSignal()
    reopen_preview_requested = pyqtSignal(str)  # design session key
    option_selected = pyqtSignal(str)  # discovery option label/description

    def __init__(
        self,
        workflow_id: str,
        initial_title: str = "Multi-Brain Autonomous Workflow",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.workflow_id = workflow_id
        self.design_session_key: Optional[str] = None
        self._artifacts: List[Dict[str, Any]] = []
        self._task_rows: Dict[str, QLabel] = {}
        self._option_buttons: List[QPushButton] = []
        self._build_ui(initial_title)

    def _build_ui(self, title: str) -> None:
        self.setStyleSheet(
            "background-color: #0A1326; border: 1px solid #1D3461; border-radius: 10px; padding: 4px;"
        )
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 14, 16, 14)
        self.main_layout.setSpacing(10)

        # 1. Top Header Bar
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        self.lbl_title = QLabel(f"⚡ WORKFLOW // {title}")
        self.lbl_title.setStyleSheet(
            "color: #00F5FF; font-family: 'Consolas'; font-weight: bold; font-size: 12px; letter-spacing: 0.5px;"
        )
        hdr.addWidget(self.lbl_title)
        hdr.addStretch()

        self.lbl_status_pill = QLabel("RUNNING")
        self.lbl_status_pill.setStyleSheet(
            "background-color: #00F5FF22; color: #00F5FF; border: 1px solid #00F5FF; "
            "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
        )
        hdr.addWidget(self.lbl_status_pill)

        self.btn_cancel = QPushButton("CANCEL ✕")
        self.btn_cancel.setStyleSheet(
            "background-color: #FF4D6D22; color: #FF4D6D; border: 1px solid #FF4D6D; "
            "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
        )
        self.btn_cancel.clicked.connect(self._handle_cancel)
        hdr.addWidget(self.btn_cancel)

        self.main_layout.addLayout(hdr)

        # 2. Overall Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(10)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #080D1A; border: 1px solid #1B2A47; border-radius: 4px; } "
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00F5FF, stop:1 #4DFFAA); border-radius: 3px; }"
        )
        self.main_layout.addWidget(self.progress_bar)

        # 3. Live Status Message
        self.lbl_message = QLabel("Initializing neural task nodes...")
        self.lbl_message.setStyleSheet("color: #8095AC; font-size: 11px; font-family: 'Consolas';")
        self.main_layout.addWidget(self.lbl_message)

        # 4. Individual Task Status Checklist Container
        self.tasks_box = QFrame()
        self.tasks_box.setStyleSheet(
            "background-color: #060A14; border: 1px solid #142036; border-radius: 6px; padding: 8px;"
        )
        self.tasks_layout = QVBoxLayout(self.tasks_box)
        self.tasks_layout.setContentsMargins(8, 6, 8, 6)
        self.tasks_layout.setSpacing(6)

        lbl_tasks_hdr = QLabel("TASK EXECUTION PIPELINE")
        lbl_tasks_hdr.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        self.tasks_layout.addWidget(lbl_tasks_hdr)

        self.main_layout.addWidget(self.tasks_box)

        # 5. Verification Results Section (Hidden until available)
        self.verification_box = QFrame()
        self.verification_box.setStyleSheet(
            "background-color: #071722; border: 1px solid #1B4B43; border-radius: 6px; padding: 8px;"
        )
        self.verification_layout = QVBoxLayout(self.verification_box)
        self.verification_layout.setContentsMargins(8, 6, 8, 6)
        self.verification_layout.setSpacing(4)
        self.lbl_verification = QLabel("VERIFICATION: PENDING")
        self.lbl_verification.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        self.verification_layout.addWidget(self.lbl_verification)
        self.verification_box.setVisible(False)
        self.main_layout.addWidget(self.verification_box)

        # 6. Artifacts Container (Hidden until deliverables available)
        self.artifacts_box = QFrame()
        self.artifacts_box.setStyleSheet(
            "background-color: #080E1C; border: 1px solid #1B2F52; border-radius: 6px; padding: 8px;"
        )
        self.artifacts_layout = QVBoxLayout(self.artifacts_box)
        self.artifacts_layout.setContentsMargins(8, 6, 8, 6)
        self.artifacts_layout.setSpacing(8)

        self.lbl_artifacts_hdr = QLabel("GENERATED ARTIFACTS")
        self.lbl_artifacts_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        self.artifacts_layout.addWidget(self.lbl_artifacts_hdr)

        self.artifacts_box.setVisible(False)
        self.main_layout.addWidget(self.artifacts_box)

        # 7. Summary / Error Note
        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet("color: #EAF7FF; font-size: 12px; line-height: 1.4;")
        self.lbl_summary.setVisible(False)
        self.main_layout.addWidget(self.lbl_summary)

        # 7a. Conversational Design Discovery Options Box
        self.options_box = QFrame()
        self.options_box.setStyleSheet(
            "background-color: #08152B; border: 1px solid #1B3560; border-radius: 8px; padding: 8px;"
        )
        self.options_layout = QVBoxLayout(self.options_box)
        self.options_layout.setContentsMargins(8, 6, 8, 6)
        self.options_layout.setSpacing(6)
        lbl_opt_hdr = QLabel("🧭 SELECT DESIGN DIRECTION OR REPLY IN CHAT:")
        lbl_opt_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        self.options_layout.addWidget(lbl_opt_hdr)
        self.options_box.setVisible(False)
        self.main_layout.addWidget(self.options_box)

        # 7b. Structured Design Brief Box (Shown once discovery synthesizes the brief)
        self.brief_box = QFrame()
        self.brief_box.setStyleSheet(
            "background-color: #061224; border: 1px solid #1B4B6B; border-radius: 8px; padding: 10px;"
        )
        self.brief_layout = QVBoxLayout(self.brief_box)
        self.brief_layout.setContentsMargins(8, 6, 8, 6)
        self.brief_layout.setSpacing(6)
        lbl_brief_hdr = QLabel("📋 STRUCTURED DESIGN BRIEF (SENT TO GOOGLE STITCH)")
        lbl_brief_hdr.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        self.brief_layout.addWidget(lbl_brief_hdr)
        self.lbl_brief_content = QLabel("")
        self.lbl_brief_content.setWordWrap(True)
        self.lbl_brief_content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_brief_content.setStyleSheet("color: #D4EEFF; font-family: 'Consolas'; font-size: 11px;")
        self.brief_layout.addWidget(self.lbl_brief_content)
        self.brief_box.setVisible(False)
        self.main_layout.addWidget(self.brief_box)

        # 8. Interactive Design Approval Box (Universal Design-First Workflow)
        self.approval_box = QFrame()
        self.approval_box.setStyleSheet(
            "background-color: #08152B; border: 1px solid #00F5FF; border-radius: 8px; padding: 10px;"
        )
        approval_layout = QVBoxLayout(self.approval_box)
        approval_layout.setContentsMargins(10, 8, 10, 8)
        approval_layout.setSpacing(8)

        lbl_appr_title = QLabel("🎨 DESIGN REVIEW & APPROVAL GATE")
        lbl_appr_title.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        approval_layout.addWidget(lbl_appr_title)

        self.lbl_appr_desc = QLabel("Inspect the design prototype in the MIND Design Preview window. Request changes here in chat. Full production development will begin only when you approve.")
        self.lbl_appr_desc.setWordWrap(True)
        self.lbl_appr_desc.setStyleSheet("color: #EAF7FF; font-size: 11px;")
        approval_layout.addWidget(self.lbl_appr_desc)

        appr_btns = QHBoxLayout()
        appr_btns.setSpacing(10)

        self.btn_approve = QPushButton("Approve & Develop ✅")
        self.btn_approve.setStyleSheet(
            "background-color: #4DFFAA; color: #050811; border: none; border-radius: 4px; "
            "padding: 6px 14px; font-size: 11px; font-weight: bold;"
        )
        self.btn_approve.clicked.connect(self.approve_requested.emit)
        appr_btns.addWidget(self.btn_approve)

        self.btn_reject = QPushButton("Reject ❌")
        self.btn_reject.setStyleSheet(
            "background-color: #1A2035; color: #FF4D6D; border: 1px solid #FF4D6D; border-radius: 4px; "
            "padding: 6px 14px; font-size: 11px; font-weight: bold;"
        )
        self.btn_reject.clicked.connect(self.reject_requested.emit)
        appr_btns.addWidget(self.btn_reject)

        # Reopen the dedicated design preview popup (never approves anything)
        self.btn_reopen_preview = QPushButton("🖼️ Open Design Preview")
        self.btn_reopen_preview.setStyleSheet(
            "background-color: #101E38; color: #00F5FF; border: 1px solid #1B3560; border-radius: 4px; "
            "padding: 6px 14px; font-size: 11px; font-weight: bold;"
        )
        self.btn_reopen_preview.clicked.connect(lambda: self.reopen_preview_requested.emit(self.design_session_key or ""))
        appr_btns.addWidget(self.btn_reopen_preview)

        appr_btns.addStretch()
        approval_layout.addLayout(appr_btns)

        self.approval_box.setVisible(False)
        self.main_layout.addWidget(self.approval_box)

        # 9. Bottom Global Actions
        self.bottom_bar = QHBoxLayout()
        self.bottom_bar.setSpacing(8)

        self.btn_open_folder = QPushButton("📁 OPEN WORKSPACE FOLDER")
        self.btn_open_folder.setStyleSheet(
            "background-color: #101E38; color: #00F5FF; border: 1px solid #1B3560; "
            "border-radius: 4px; padding: 6px 12px; font-size: 11px; font-weight: bold;"
        )
        self.btn_open_folder.setVisible(False)
        self.bottom_bar.addWidget(self.btn_open_folder)
        self.bottom_bar.addStretch()

        self.main_layout.addLayout(self.bottom_bar)

    def _handle_cancel(self) -> None:
        self.lbl_status_pill.setText("CANCELLING...")
        self.lbl_status_pill.setStyleSheet(
            "background-color: #FFB70322; color: #FFB703; border: 1px solid #FFB703; "
            "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
        )
        self.btn_cancel.setEnabled(False)
        self.cancel_requested.emit()

    def update_progress(self, data: Dict[str, Any]) -> None:
        """Updates live progress bar, active task description, and task checklist."""
        pct = data.get("progress_pct", 0.0)
        self.progress_bar.setValue(int(pct * 100))
        msg = data.get("message", "Processing workflow tasks...")
        self.lbl_message.setText(msg)

        # Update task checklist
        statuses = data.get("task_statuses", {})
        for t_id, t_info in statuses.items():
            title = t_info.get("title", t_id)
            brain = t_info.get("brain_id", "cortex")
            state = t_info.get("status", "pending")
            err = t_info.get("error")

            icon = "⏳"
            color = "#8095AC"
            if state == "running":
                icon = "🔄"
                color = "#00F5FF"
            elif state == "completed":
                icon = "✅"
                color = "#4DFFAA"
            elif state == "failed":
                icon = "❌"
                color = "#FF4D6D"
            elif state in ("skipped", "cancelled"):
                icon = "⏹️"
                color = "#FFB703"

            err_text = f" — {err}" if err else ""
            line_text = f"{icon} {title} [{brain}] — {state.upper()}{err_text}"

            if t_id not in self._task_rows:
                lbl = QLabel(line_text)
                lbl.setStyleSheet(f"color: {color}; font-family: 'Consolas'; font-size: 11px;")
                self.tasks_layout.addWidget(lbl)
                self._task_rows[t_id] = lbl
            else:
                self._task_rows[t_id].setText(line_text)
                self._task_rows[t_id].setStyleSheet(f"color: {color}; font-family: 'Consolas'; font-size: 11px;")

        # Check for current artifact
        art = data.get("current_artifact")
        if art and art not in self._artifacts:
            self._add_artifact_view(art)

    def complete_workflow(self, result_dict: Dict[str, Any]) -> None:
        """Finalizes workflow execution state, displays deliverables, verification, and previews."""
        self.btn_cancel.setVisible(False)
        wf_res = result_dict.get("workflow_result") or {}
        status = wf_res.get("status") or result_dict.get("status", "completed")

        is_design_gate = (
            status == "awaiting_approval"
            or result_dict.get("design_state") == "awaiting_design_approval"
            or (status == "APPROVAL_REQUIRED" and (result_dict.get("stage") == "DESIGN_APPROVAL" or "design_plan" in result_dict))
        )
        if is_design_gate:
            v = result_dict.get("version") or result_dict.get("design_version") or 1
            self.lbl_status_pill.setText(f"AWAITING DESIGN APPROVAL (v{v})")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #00F5FF22; color: #00F5FF; border: 1px solid #00F5FF; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText(f"Design prototype v{v} ready. Full development paused pending your approval.")
            self.approval_box.setVisible(True)
        elif status == "CONFIRMATION_REQUIRED":
            # Destructive operation confirmation — NEVER shows or triggers the design approval gate.
            self.lbl_status_pill.setText("CONFIRMATION REQUIRED")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #FFB70322; color: #FFB703; border: 1px solid #FFB703; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText(result_dict.get("message", "Confirmation required for destructive file operation."))
            self.approval_box.setVisible(False)
        elif status == "CLARIFY":
            stage = result_dict.get("discovery_stage") or "subtype"
            self.progress_bar.setValue(45 if stage == "subtype" else 75)
            self.lbl_status_pill.setText("DESIGN CONSULTATION")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #00F5FF22; color: #00F5FF; border: 1px solid #00F5FF; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText(
                "Conversational Design Discovery — gathering requirements before invoking Google Stitch."
            )
            self.approval_box.setVisible(False)
            self._populate_discovery_options(result_dict.get("options") or [])
        elif status in ("rejected", "REJECTED"):
            self.lbl_status_pill.setText("DESIGN REJECTED")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #FF4D6D22; color: #FF4D6D; border: 1px solid #FF4D6D; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText("Design prototype was rejected. Standing by for revised direction.")
            self.approval_box.setVisible(False)
        elif status == "DESIGN_APPROVED":
            v = result_dict.get("version") or result_dict.get("design_version") or 1
            self.progress_bar.setValue(100)
            self.lbl_status_pill.setText(f"DESIGN APPROVED (v{v})")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #4DFFAA22; color: #4DFFAA; border: 1px solid #4DFFAA; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText(
                result_dict.get("message", f"Stitch design v{v} marked as approved and available.")
            )
            self.approval_box.setVisible(False)
        elif status == "STITCH_ERROR":
            v = result_dict.get("version") or result_dict.get("design_version") or 1
            self.lbl_status_pill.setText(f"REVISION FAILED (v{v} ACTIVE)")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #FFB70322; color: #FFB703; border: 1px solid #FFB703; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText(
                result_dict.get("message", f"Stitch revision failed. Previous design (v{v}) remains active.")
            )
            self.approval_box.setVisible(bool(result_dict.get("preview_file") or result_dict.get("preview_url")))
        elif status == "STITCH_UNAVAILABLE":
            self.lbl_status_pill.setText("STITCH UNAVAILABLE")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #FF4D6D22; color: #FF4D6D; border: 1px solid #FF4D6D; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText(
                result_dict.get("message", "Google Stitch design generation is unavailable.")
            )
            self.approval_box.setVisible(False)
            self._populate_discovery_options(result_dict.get("options") or [])
        elif status in ("completed", "SUCCESS"):
            self.progress_bar.setValue(100)
            self.lbl_status_pill.setText("COMPLETED")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #4DFFAA22; color: #4DFFAA; border: 1px solid #4DFFAA; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText("Workflow execution verified, audited, and deliverables finalized.")
            self.approval_box.setVisible(False)
        elif status in ("cancelled", "CANCELLED"):
            has_active_preview = bool(result_dict.get("preview_file") or result_dict.get("preview_url"))
            v = result_dict.get("version") or result_dict.get("design_version") or 1
            self.lbl_status_pill.setText(f"CANCELLED (v{v} ACTIVE)" if has_active_preview else "CANCELLED")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #FFB70322; color: #FFB703; border: 1px solid #FFB703; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText(result_dict.get("message", "Workflow cancelled by user."))
            self.approval_box.setVisible(has_active_preview)
            self._populate_discovery_options(result_dict.get("options") or [])
        else:
            self.lbl_status_pill.setText("FAILED")
            self.lbl_status_pill.setStyleSheet(
                "background-color: #FF4D6D22; color: #FF4D6D; border: 1px solid #FF4D6D; "
                "border-radius: 4px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
            )
            self.lbl_message.setText("Workflow execution halted due to an error.")
            self.approval_box.setVisible(False)

        # Update summary text
        summary = (
            wf_res.get("summary")
            or result_dict.get("response")
            or result_dict.get("question")
            or result_dict.get("message")
            or ""
        )
        if summary:
            self.lbl_summary.setText(summary)
            self.lbl_summary.setVisible(True)

        # Render Structured Design Brief if present
        brief_md = result_dict.get("design_brief_markdown")
        if not brief_md and isinstance(result_dict.get("design_brief"), dict):
            db = result_dict["design_brief"]
            brief_md = "\n".join(
                f"• {k.replace('_', ' ').title()}: {v}"
                for k, v in db.items()
                if k in (
                    "project_type", "target_audience", "website_purpose",
                    "required_pages_and_screens", "navigation_structure",
                    "important_content_sections", "visual_direction",
                    "branding_requirements", "responsive_requirements",
                    "special_functionality",
                )
            )
        if brief_md:
            self.lbl_brief_content.setText(brief_md)
            self.brief_box.setVisible(True)

        # Update verification results
        evidence = result_dict.get("evidence", {})
        if evidence:
            self.verification_box.setVisible(True)
            v_lines = []
            for t_id, v in evidence.items():
                if isinstance(v, dict):
                    v_summary = v.get("summary") or "Verified"
                    v_lines.append(f"✔ [{t_id}]: {v_summary}")
                else:
                    v_lines.append(f"✔ [{t_id}]: {v}")
            self.lbl_verification.setText("VERIFICATION PASSED:\n" + "\n".join(v_lines))
            self.lbl_verification.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        elif wf_res.get("verification_summary"):
            vs = wf_res["verification_summary"]
            self.verification_box.setVisible(True)
            v_text = f"✔ Verification: {vs.get('completed', 0)}/{vs.get('total_tasks', 0)} tasks verified successfully."
            self.lbl_verification.setText(v_text)

        # Collect and render artifacts
        artifacts = result_dict.get("artifacts") or wf_res.get("artifacts") or []
        for art in artifacts:
            if art not in self._artifacts:
                self._add_artifact_view(art)

        # If partial artifacts exist (on failure or cancellation)
        partials = wf_res.get("partial_artifacts", [])
        for p in partials:
            if p not in self._artifacts:
                self._add_artifact_view(p, is_partial=True)

        # Setup primary workspace open folder button
        primary_dir = None
        for a in self._artifacts:
            path = a.get("path", "")
            if os.path.exists(path):
                primary_dir = path if os.path.isdir(path) else os.path.dirname(path)
                break

        if primary_dir:
            self.btn_open_folder.setVisible(True)
            self.btn_open_folder.clicked.connect(lambda: open_path_in_explorer(primary_dir))

    def _add_artifact_view(self, art: Dict[str, Any], is_partial: bool = False) -> None:
        """Renders an individual artifact card with inline preview and actions."""
        self._artifacts.append(art)
        self.artifacts_box.setVisible(True)

        path = art.get("path", "")
        mime = art.get("mime_type", "")
        preview_type = art.get("preview_type", "")
        if not preview_type:
            # Fallback inference
            p_lower = path.lower()
            if os.path.isdir(path):
                preview_type = "folder"
            elif p_lower.endswith(".html"):
                preview_type = "browser"
            elif p_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
                preview_type = "image"
            elif p_lower.endswith((".obj", ".stl", ".glb")):
                preview_type = "model3d"
            else:
                preview_type = "text"

        card = QFrame()
        card.setStyleSheet(
            "background-color: #0E1A33; border: 1px solid #1F3863; border-radius: 6px; padding: 8px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(6)

        # Title & Info
        info_row = QHBoxLayout()
        name = os.path.basename(path) or path
        partial_tag = " [PARTIAL]" if is_partial or art.get("is_partial") else ""
        icon = "📄"
        if preview_type == "browser":
            icon = "🌐"
        elif preview_type == "image":
            icon = "🖼️"
        elif preview_type == "model3d":
            icon = "🧊"
        elif preview_type == "folder":
            icon = "📁"

        lbl_name = QLabel(f"{icon} {name}{partial_tag}")
        lbl_name.setStyleSheet("color: #EAF7FF; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        info_row.addWidget(lbl_name)
        info_row.addStretch()

        size_kb = round(art.get("size_bytes", 0) / 1024, 1)
        lbl_size = QLabel(f"{size_kb} KB" if size_kb > 0 else "")
        lbl_size.setStyleSheet("color: #8095AC; font-size: 10px; font-family: 'Consolas';")
        info_row.addWidget(lbl_size)
        card_layout.addLayout(info_row)

        # Path display (selectable)
        lbl_path = QLabel(path)
        lbl_path.setWordWrap(True)
        lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_path.setStyleSheet("color: #8095AC; font-size: 10px; font-family: 'Consolas';")
        card_layout.addWidget(lbl_path)

        # Specific Previews
        # 1. Image Thumbnail Preview
        if preview_type == "image" and os.path.exists(path):
            try:
                pix = QPixmap(path)
                if not pix.isNull():
                    thumb = QLabel()
                    scaled = pix.scaledToHeight(120, Qt.TransformationMode.SmoothTransformation)
                    thumb.setPixmap(scaled)
                    thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    thumb.setStyleSheet("border: 1px solid #1B2A47; border-radius: 4px; padding: 2px;")
                    card_layout.addWidget(thumb)
            except Exception:
                pass

        # 2. 3D Mesh Details Badge
        if preview_type == "model3d":
            meta = art.get("metadata", {})
            v_cnt = meta.get("vertex_count", 0)
            f_cnt = meta.get("face_count", 0)
            lbl_3d = QLabel(f"3D Polygonal Mesh — Vertices: {v_cnt} | Faces: {f_cnt}")
            lbl_3d.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 10px;")
            card_layout.addWidget(lbl_3d)

        # Action Buttons Row
        actions = QHBoxLayout()
        actions.setSpacing(6)

        if preview_type == "browser" and os.path.exists(path):
            btn_browser = QPushButton("🌐 Open in Browser")
            btn_browser.setStyleSheet(
                "background-color: #00F5FF; color: #050811; border: none; border-radius: 4px; "
                "padding: 4px 10px; font-size: 10px; font-weight: bold;"
            )
            btn_browser.clicked.connect(lambda: open_in_browser(path))
            actions.addWidget(btn_browser)

        if preview_type == "image" and os.path.exists(path):
            btn_img = QPushButton("🖼️ View Full Image")
            btn_img.setStyleSheet(
                "background-color: #1A305A; color: #00F5FF; border: 1px solid #00F5FF; "
                "border-radius: 4px; padding: 4px 10px; font-size: 10px; font-weight: bold;"
            )
            btn_img.clicked.connect(lambda: open_file_default(path))
            actions.addWidget(btn_img)

        if preview_type == "model3d" and os.path.exists(path):
            btn_3d = QPushButton("🧊 Open 3D Model")
            btn_3d.setStyleSheet(
                "background-color: #1A305A; color: #00F5FF; border: 1px solid #00F5FF; "
                "border-radius: 4px; padding: 4px 10px; font-size: 10px; font-weight: bold;"
            )
            btn_3d.clicked.connect(lambda: open_file_default(path))
            actions.addWidget(btn_3d)

        # Open containing folder
        btn_fld = QPushButton("📁 Show in Folder")
        btn_fld.setStyleSheet(
            "background-color: #101E38; color: #8095AC; border: 1px solid #1B3560; "
            "border-radius: 4px; padding: 4px 8px; font-size: 10px;"
        )
        btn_fld.clicked.connect(lambda: open_path_in_explorer(path))
        actions.addWidget(btn_fld)

        actions.addStretch()
        card_layout.addLayout(actions)

        self.artifacts_layout.addWidget(card)

    def _populate_discovery_options(self, options: List[Dict[str, Any]]) -> None:
        """Renders interactive buttons for Conversational Design Discovery options."""
        for btn in self._option_buttons:
            btn.deleteLater()
        self._option_buttons.clear()

        if not options:
            self.options_box.setVisible(False)
            return

        for idx, opt in enumerate(options, start=1):
            label = str(opt.get("label") or opt.get("key") or f"Option {idx}")
            direction = str(opt.get("design_direction") or "")
            audience = str(opt.get("intended_audience") or "")
            tooltip_parts = []
            if direction:
                tooltip_parts.append(f"Design Direction: {direction}")
            if audience:
                tooltip_parts.append(f"Intended Audience: {audience}")

            btn = QPushButton(f"{idx}. {label}")
            if tooltip_parts:
                btn.setToolTip("\n".join(tooltip_parts))
            btn.setStyleSheet(
                "QPushButton { background-color: #101E38; color: #00F5FF; border: 1px solid #1B3560; "
                "border-radius: 5px; padding: 6px 12px; font-size: 11px; font-weight: bold; text-align: left; } "
                "QPushButton:hover { background-color: #1A305A; border-color: #00F5FF; color: #EAF7FF; }"
            )
            btn.clicked.connect(lambda checked=False, val=label: self.option_selected.emit(val))
            self.options_layout.addWidget(btn)
            self._option_buttons.append(btn)

        self.options_box.setVisible(True)

    def set_final_summary(self, summary_text: str) -> None:
        """Sets summary text on completed workflow bubble."""
        if summary_text:
            self.lbl_summary.setText(summary_text)
            self.lbl_summary.setVisible(True)


class UnifiedAssistantView(QWidget):
    """
    Primary workspace cockpit providing conversational intelligence, multi-brain routing,
    real-time workflow DAG execution, voice input, and a dedicated design-preview popup window.
    """

    prompt_sent = pyqtSignal(str, str)  # (prompt, brain_choice)
    cancel_requested = pyqtSignal()
    voice_toggled = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._active_workflow_bubble: Optional[WorkflowArtifactBubble] = None
        # Session key of the design currently awaiting approval in the backend.
        self._pending_design_session: Optional[str] = None
        # Single popup window + per-session preview records.
        self.design_preview = DesignPreviewManager(self)
        self.design_preview.approve_requested.connect(self._handle_popup_approve)
        self.design_preview.records_changed.connect(self._refresh_preview_controls)
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Top Control Bar
        # -------------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        title = QLabel("UNIFIED ASSISTANT // COGNITIVE WORKSPACE")
        title.setObjectName("HeaderLabel")
        title.setStyleSheet("color: #00F5FF; font-size: 13px; font-weight: bold; letter-spacing: 1px;")
        top_bar.addWidget(title)

        top_bar.addStretch()

        # Brain / Model Selector
        lbl_model = QLabel("Active Brain:")
        lbl_model.setStyleSheet("color: #8095AC; font-size: 11px;")
        top_bar.addWidget(lbl_model)

        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet(
            "background: #0A1020; color: #EAF7FF; border: 1px solid #1B2A47; "
            "border-radius: 6px; padding: 5px 10px; font-family: 'Consolas'; font-size: 11px;"
        )
        self.model_combo.addItems([
            "AUTO // Multi-Brain Router (Recommended)",
            "Coding Specialist (Qwen / Local)",
            "Creative Visual Specialist (FLUX / DALL-E)",
            "3D Generation Specialist (Blender / Mesh)",
            "Research & Knowledge Specialist (Gemma)",
            "Data & Logic Specialist (Python)",
            "Verification & QA Specialist (AST / PIL)",
            "GameDev & Web Studio Subsystem",
        ])
        top_bar.addWidget(self.model_combo)

        # Design Engine Selector (Auto / Native / Stitch)
        lbl_design = QLabel("Design Engine:")
        lbl_design.setStyleSheet("color: #8095AC; font-size: 11px;")
        top_bar.addWidget(lbl_design)

        self.design_engine_combo = QComboBox()
        self.design_engine_combo.setStyleSheet(
            "background: #0A1020; color: #00F5FF; border: 1px solid #1B2A47; "
            "border-radius: 6px; padding: 5px 10px; font-family: 'Consolas'; font-size: 11px; font-weight: bold;"
        )
        self.design_engine_combo.addItems([
            "AUTO (Stitch / Native Fallback)",
            "MIND Native Design Intelligence",
            "Google Stitch AI Specialist",
        ])
        self.design_engine_combo.currentIndexChanged.connect(self._handle_design_engine_changed)
        top_bar.addWidget(self.design_engine_combo)

        # Design Preview Status Pill (reflects the popup's current design session)
        self.workspace_status_pill = QLabel("● NO DESIGN PREVIEW")
        self.workspace_status_pill.setStyleSheet(
            "background: #0A1020; color: #8095AC; border: 1px solid #1B2A47; "
            "border-radius: 6px; padding: 5px 10px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
        )
        top_bar.addWidget(self.workspace_status_pill)

        # Opens / reopens the dedicated design preview popup window
        # (attribute name kept for backwards compatibility).
        self.btn_toggle_preview = QPushButton("🖼️ Open Design Preview")
        self.btn_toggle_preview.setStyleSheet("""
            QPushButton {
                background: #0A1020; color: #8095AC; border: 1px solid #1B2A47;
                border-radius: 6px; padding: 5px 12px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover:enabled {
                background: #101A2C; color: #00F5FF; border-color: #00F5FF;
            }
            QPushButton:disabled { color: #3A4A60; }
        """)
        self.btn_toggle_preview.setEnabled(False)
        self.btn_toggle_preview.clicked.connect(lambda: self.reopen_design_preview())
        top_bar.addWidget(self.btn_toggle_preview)

        # Clear button
        btn_clear = QPushButton("Clear Thread")
        btn_clear.setStyleSheet("background: #0A1020; color: #8095AC; border: 1px solid #1B2A47; font-size: 11px; padding: 5px 10px; border-radius: 6px;")
        btn_clear.clicked.connect(self._clear_chat)
        top_bar.addWidget(btn_clear)

        main_layout.addLayout(top_bar)

        # -------------------------------------------------------------
        # 2. Full-width Conversation Panel (design previews open in a popup)
        # -------------------------------------------------------------
        self.chat_panel = QWidget(self)
        chat_layout = QVBoxLayout(self.chat_panel)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(10)

        # Scroll Area for Messages
        self.scroll = QScrollArea(self.chat_panel)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #050811; border: 1px solid #1B2A47; border-radius: 8px;")

        self.messages_container = QWidget()
        self.messages_container.setStyleSheet("background-color: #050811;")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(14, 14, 14, 14)
        self.messages_layout.setSpacing(12)
        self.messages_layout.addStretch()

        self.scroll.setWidget(self.messages_container)
        chat_layout.addWidget(self.scroll, stretch=1)

        # Input Dock with Integrated Voice Button
        dock = QFrame(self.chat_panel)
        dock.setObjectName("PanelFrame")
        dock.setStyleSheet("background-color: #101A2C; border: 1px solid #1B2A47; border-radius: 8px;")
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(10, 8, 10, 8)
        dock_layout.setSpacing(8)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("Ask MIND or instruct development (e.g. 'build a cyberpunk portfolio website', 'analyze latency')...")
        self.input_edit.setMaximumHeight(60)
        self.input_edit.setStyleSheet("background: transparent; border: none; color: #EAF7FF; font-size: 13px;")
        dock_layout.addWidget(self.input_edit, stretch=1)

        # Voice Input Button (Directly inside primary workspace)
        self.btn_voice = QPushButton("🎙️ VOICE")
        self.btn_voice.setStyleSheet("""
            QPushButton {
                background: #1B2A47; color: #EAF7FF; border: 1px solid #2A3F67;
                border-radius: 6px; padding: 10px 14px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background: #2A3F67; color: #00F5FF; }
        """)
        self.btn_voice.clicked.connect(self.voice_toggled.emit)
        dock_layout.addWidget(self.btn_voice)

        # Send Button
        self.btn_send = QPushButton("TRANSMIT ⚡")
        self.btn_send.setObjectName("PrimaryBtn")
        self.btn_send.setStyleSheet(
            "background: #00F5FF; color: #050811; border: none; border-radius: 6px; padding: 10px 18px; font-weight: bold;"
        )
        self.btn_send.clicked.connect(self._handle_send)
        dock_layout.addWidget(self.btn_send)

        chat_layout.addWidget(dock)

        # The conversation owns the full width. Generated designs are shown in the
        # dedicated DesignPreviewWindow popup managed by self.design_preview.
        main_layout.addWidget(self.chat_panel, stretch=1)

        # Initial greeting
        self.add_message(
            "MIND",
            "MIND Unified General-Purpose Multi-Brain Architecture online. Autonomous workflow orchestrator ready. How can I assist you with development, research, 3D modeling, or analysis?",
            is_user=False,
        )

    # ------------------------------------------------------------------
    # Design preview popup integration
    # ------------------------------------------------------------------
    @property
    def preview_widget(self):
        """Backwards-compatible access to the popup's LiveWebsitePreviewWidget (or None)."""
        win = self.design_preview.window
        return win.preview_widget if win is not None else None

    def _handle_design_engine_changed(self, index: int) -> None:
        mode_map = {0: "auto", 1: "native", 2: "stitch"}
        chosen = mode_map.get(index, "auto")
        os.environ["MIND_DESIGN_MODE"] = chosen
        if self.preview_widget is not None:
            self.preview_widget.append_log(f"Design Engine switched to: {chosen.upper()}")

    def show_visual_workspace(self, visible: bool = True) -> None:
        """Backwards-compatible entry point: (re)opens the design preview popup if a design exists."""
        if visible:
            self.reopen_design_preview()
        else:
            self.design_preview.close_window()

    def reopen_design_preview(self, session_key: Optional[str] = None) -> bool:
        """Reopens a design preview. Never changes approval state."""
        key = session_key or self._pending_design_session or self.design_preview.active_session_key
        return self.design_preview.reopen(key)

    def shutdown_previews(self) -> None:
        """Called by the main window on shutdown to release the popup window."""
        self.design_preview.shutdown()

    @staticmethod
    def _extract_design_info(d: Dict[str, Any]) -> Dict[str, Any]:
        """Pulls session/version/title/preview data out of a progress or result dict."""
        wf_res = d.get("workflow_result") or {}
        proto = d.get("prototype") if isinstance(d.get("prototype"), dict) else {}
        spec = d.get("specification") if isinstance(d.get("specification"), dict) else {}
        design_plan = d.get("design_plan") if isinstance(d.get("design_plan"), dict) else None
        session_key = (
            d.get("design_session_id")
            or d.get("session_id")
            or proto.get("session_id")
            or wf_res.get("workflow_id")
            or d.get("workflow_id")
            or spec.get("project_name")
            or (design_plan.get("title") if design_plan else None)
        )
        version = d.get("version") or d.get("design_version") or proto.get("version") or 1
        title = (
            d.get("title")
            or proto.get("title")
            or spec.get("title")
            or (design_plan.get("title") if design_plan else None)
            or d.get("objective")
            or proto.get("objective")
            or wf_res.get("goal")
            or ""
        )
        preview_file = (
            d.get("preview_file")
            or proto.get("preview_file")
            or d.get("file_path")
            or d.get("entry_point")
        )
        if not (preview_file and os.path.exists(str(preview_file))):
            preview_file = None
            for art in (d.get("artifacts") or wf_res.get("artifacts") or proto.get("artifacts") or []):
                if isinstance(art, dict) and art.get("preview_type") == "browser":
                    p = art.get("path")
                    if p and os.path.exists(p):
                        preview_file = p
                        break
        preview_url = d.get("preview_url") or proto.get("preview_url")
        provider = (
            d.get("provider")
            or proto.get("provider")
            or (design_plan.get("provider") if design_plan else "")
            or ""
        )
        screens = d.get("screens") or proto.get("screens") or (design_plan.get("screens") if design_plan else None)
        try:
            version = int(version)
        except (TypeError, ValueError):
            version = 1
        return {
            "session_key": str(session_key) if session_key else None,
            "version": version,
            "title": str(title)[:120],
            "preview_file": preview_file,
            "preview_url": preview_url,
            "design_plan": design_plan,
            "provider": str(provider),
            "screens": screens if isinstance(screens, list) else None,
        }

    @staticmethod
    def _is_awaiting_design(d: Dict[str, Any]) -> bool:
        wf_res = d.get("workflow_result") or {}
        status = wf_res.get("status") or d.get("status")
        if status == "CONFIRMATION_REQUIRED":
            return False  # destructive confirmation is never design approval
        return (
            status == "awaiting_approval"
            or d.get("design_state") == "awaiting_design_approval"
            or (status == "APPROVAL_REQUIRED" and (d.get("stage") == "DESIGN_APPROVAL" or "design_plan" in d))
        )

    def _refresh_preview_controls(self) -> None:
        mgr = self.design_preview
        self.btn_toggle_preview.setEnabled(bool(mgr.records))
        rec = mgr.records.get(mgr.active_session_key) if mgr.active_session_key else None
        if rec is None:
            text, fg, bg, bd = "● NO DESIGN PREVIEW", "#8095AC", "#0A1020", "#1B2A47"
        elif rec.approval_state == STATE_AWAITING:
            text, fg, bg, bd = f"● DESIGN v{rec.version} AWAITING APPROVAL", "#FFB84D", "#2A1E0A", "#6B4A12"
        elif rec.approval_state == STATE_APPROVAL_SENT:
            text, fg, bg, bd = f"● DESIGN v{rec.version} APPROVAL SENT", "#00F5FF", "#0A1A2A", "#1B3560"
        elif rec.approval_state == STATE_APPROVED:
            text, fg, bg, bd = f"● DESIGN v{rec.version} APPROVED", "#4DFFAA", "#0A1E14", "#1A4D30"
        elif rec.approval_state == STATE_REJECTED:
            text, fg, bg, bd = f"● DESIGN v{rec.version} REJECTED", "#FF4D6D", "#2A1015", "#5A1F2A"
        else:
            text, fg, bg, bd = f"● DESIGN v{rec.version} GENERATING", "#00F5FF", "#0A1A2A", "#1B3560"
        self.workspace_status_pill.setText(text)
        self.workspace_status_pill.setStyleSheet(
            f"background: {bg}; color: {fg}; border: 1px solid {bd}; "
            "border-radius: 6px; padding: 5px 10px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
        )

    def _handle_popup_approve(self, session_key: str) -> None:
        """
        Explicit approval clicked inside the popup. Only forwarded when the popup's
        session is the one the backend is currently waiting on; the approval then
        travels through exactly the same chat → orchestrator path as the bubble button.
        """
        if not session_key or session_key != self._pending_design_session:
            win = self.design_preview.window
            if win is not None:
                win.set_approval_blocked(
                    "This design belongs to a different or superseded session. "
                    "Approve the current pending design instead."
                )
            return
        self._send_explicit_approval()

    def _handle_bubble_approve(self) -> None:
        self._send_explicit_approval()

    def _send_explicit_approval(self) -> None:
        if self._pending_design_session:
            self.design_preview.set_state(self._pending_design_session, STATE_APPROVAL_SENT)
        self._handle_approve_clicked()

    def _wire_bubble(self, bubble: "WorkflowArtifactBubble") -> None:
        bubble.cancel_requested.connect(self.cancel_requested.emit)
        bubble.approve_requested.connect(self._handle_bubble_approve)
        bubble.reject_requested.connect(self._handle_reject_clicked)
        bubble.reopen_preview_requested.connect(lambda key: self.reopen_design_preview(key or None))
        bubble.option_selected.connect(self._handle_option_selected)

    def _handle_option_selected(self, option_text: str) -> None:
        """Sends the user's selected discovery option directly through the chat pipeline."""
        if not option_text:
            return
        self.input_edit.setPlainText(option_text)
        self._handle_send()

    # ------------------------------------------------------------------
    # Chat actions
    # ------------------------------------------------------------------
    def _handle_approve_clicked(self) -> None:
        """Transmits explicit approval to begin full production development."""
        self.input_edit.setPlainText("Approve")
        self._handle_send()

    def _handle_reject_clicked(self) -> None:
        """Transmits explicit rejection of the current design prototype."""
        self.input_edit.setPlainText("Reject")
        self._handle_send()

    def _handle_send(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        self.input_edit.clear()

        # Add user message bubble
        self.add_message("USER", text, is_user=True)

        choice = self.model_combo.currentText().split()[0]
        self.prompt_sent.emit(text, choice)

    def add_message(self, sender: str, text: str, model_tag: str = "", is_user: bool = False) -> None:
        """Adds a standard chat message bubble to the thread."""
        bubble = ChatMessageBubble(sender, text, model_tag=model_tag, is_user=is_user, parent=self.messages_container)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        QApplication.processEvents()
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def update_workflow_progress(self, progress_dict: Dict[str, Any]) -> None:
        """Receives live workflow progress and displays or updates the WorkflowArtifactBubble."""
        wf_id = progress_dict.get("workflow_id", "cortex_wf")
        if self._active_workflow_bubble is None or self._active_workflow_bubble.workflow_id != wf_id:
            bubble = WorkflowArtifactBubble(
                workflow_id=wf_id,
                initial_title=progress_dict.get("active_task_title", "Multi-Brain Workflow"),
                parent=self.messages_container,
            )
            self._wire_bubble(bubble)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
            self._active_workflow_bubble = bubble

        self._active_workflow_bubble.update_progress(progress_dict)

        # Live design updates are routed to the popup (never to an embedded pane).
        try:
            self._route_progress_to_popup(progress_dict)
        except Exception:
            pass  # popup issues must never disturb the running workflow

        QApplication.processEvents()
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _route_progress_to_popup(self, progress_dict: Dict[str, Any]) -> None:
        info = self._extract_design_info(progress_dict)
        design_state = progress_dict.get("design_state")
        has_preview = bool(info["preview_file"] or info["preview_url"])
        key = info["session_key"]
        mgr = self.design_preview

        # Progress for an already-known design session (e.g. revision or post-approval build).
        if self._pending_design_session and (key is None or key not in mgr.records):
            key = self._pending_design_session

        rec = mgr.records.get(key) if key else None
        msg = progress_dict.get("message", "")

        if rec is not None:
            if has_preview:
                state = rec.approval_state
                if design_state == "awaiting_design_approval":
                    state = STATE_AWAITING
                mgr.present(
                    key,
                    info["title"] or rec.title,
                    info["version"] if progress_dict.get("version") else rec.version,
                    info["preview_file"],
                    info["preview_url"],
                    approval_state=state,
                    show=mgr.is_window_visible() or design_state == "awaiting_design_approval",
                )
            if msg and self.preview_widget is not None:
                self.preview_widget.append_log(msg)
            return

        if key and has_preview and design_state in ("prototyping", "revising", "awaiting_design_approval"):
            state = STATE_AWAITING if design_state == "awaiting_design_approval" else STATE_GENERATING
            mgr.present(
                key,
                info["title"] or "Design Prototype",
                info["version"],
                info["preview_file"],
                info["preview_url"],
                approval_state=state,
                show=True,
            )
            if state == STATE_AWAITING:
                self._pending_design_session = key

    def complete_workflow(self, result_dict: Dict[str, Any]) -> None:
        """Finalizes the active WorkflowArtifactBubble upon task completion."""
        wf_res = result_dict.get("workflow_result") or {}
        wf_id = wf_res.get("workflow_id") or result_dict.get("session_id") or "cortex_wf"

        if self._active_workflow_bubble is None or self._active_workflow_bubble.workflow_id != wf_id:
            bubble = WorkflowArtifactBubble(workflow_id=wf_id, parent=self.messages_container)
            self._wire_bubble(bubble)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
            self._active_workflow_bubble = bubble

        bubble = self._active_workflow_bubble
        bubble.complete_workflow(result_dict)

        try:
            self._route_result_to_popup(result_dict, bubble)
        except Exception:
            pass  # a popup failure must not cancel the task or touch generated files

        # If awaiting approval (or a revision failed/cancelled while keeping previous design pending), keep bubble active
        if self._is_awaiting_design(result_dict) or (
            result_dict.get("status") in ("STITCH_ERROR", "CANCELLED") and self._pending_design_session
        ):
            pass  # keep active
        else:
            self._active_workflow_bubble = None

        QApplication.processEvents()
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _route_result_to_popup(self, result_dict: Dict[str, Any], bubble: "WorkflowArtifactBubble") -> None:
        mgr = self.design_preview
        info = self._extract_design_info(result_dict)
        wf_res = result_dict.get("workflow_result") or {}
        status = wf_res.get("status") or result_dict.get("status")

        if status == "STITCH_UNAVAILABLE":
            # Never open a fake preview or mark anything approved when Stitch is unavailable.
            return

        if status == "STITCH_ERROR":
            # Preserve the previously rendered design version in the popup and show the revision error.
            key = info["session_key"] or self._pending_design_session or mgr.active_session_key or ""
            err_msg = str(result_dict.get("error") or result_dict.get("message") or "Google Stitch revision failed.")
            mgr.record_revision_failure(key, err_msg)
            return

        if self._is_awaiting_design(result_dict):
            # When a revision arrives for an existing pending session without an explicit session_id,
            # reuse the pending session key so the existing popup updates to v2 instead of duplicating.
            key = (
                self._pending_design_session
                if (self._pending_design_session and not result_dict.get("session_id") and not result_dict.get("design_session_id"))
                else (info["session_key"] or self._pending_design_session or "design_session")
            )
            bubble.design_session_key = key
            if info["preview_file"] or info["preview_url"] or info["design_plan"]:
                mgr.present(
                    key,
                    info["title"] or "Design Prototype",
                    info["version"],
                    info["preview_file"],
                    info["preview_url"],
                    approval_state=STATE_AWAITING,
                    show=True,
                    design_plan=info["design_plan"],
                    provider=info["provider"],
                    screens=info["screens"],
                )
            elif key in mgr.records:
                mgr.set_state(key, STATE_AWAITING)
            self._pending_design_session = key
            return

        if status == "CONFIRMATION_REQUIRED":
            # Destructive confirmation has no effect on design preview or design approval state.
            return

        # Backend outcome after an explicit approval / rejection.
        sent = [k for k, r in mgr.records.items() if r.approval_state == STATE_APPROVAL_SENT]
        targets = set(sent)
        if info["session_key"] in mgr.records:
            targets.add(info["session_key"])
        if not targets and self._pending_design_session in mgr.records and status in (
            "rejected", "REJECTED", "CANCELLED", "DESIGN_APPROVED"
        ):
            targets.add(self._pending_design_session)

        if status in ("rejected", "REJECTED"):
            for k in targets:
                mgr.set_state(k, STATE_REJECTED)
            self._pending_design_session = None
        elif status == "DESIGN_APPROVED":
            for k in (targets or sent):
                mgr.set_state(k, STATE_APPROVED)
            self._pending_design_session = None
        elif status in ("completed", "SUCCESS"):
            for k in sent:
                mgr.set_state(k, STATE_APPROVED)
                # Show the delivered build in the same window if it is already open.
                if info["preview_file"]:
                    rec = mgr.records[k]
                    mgr.present(k, rec.title, rec.version, info["preview_file"], None,
                                approval_state=STATE_APPROVED, show=mgr.is_window_visible())
            if sent:
                self._pending_design_session = None
        elif status in ("failed", "FAILED", "ERROR", "cancelled", "CANCELLED"):
            # Approval did not lead to completion: restore the pending state so the
            # user can retry. Nothing is approved implicitly.
            for k in sent:
                mgr.set_state(k, STATE_AWAITING)

    def handle_response_ready(self, response_text: str, model_tag: str) -> None:
        """Handles response ready signal. If a workflow bubble is active, updates it; otherwise adds message."""
        if self._active_workflow_bubble:
            self._active_workflow_bubble.set_final_summary(response_text)
            if not self._pending_design_session:
                self._active_workflow_bubble = None
        else:
            self.add_message("MIND", response_text, model_tag=model_tag)

    def _clear_chat(self) -> None:
        """Clears the visible thread. Pending design approval and previews are retained."""
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._active_workflow_bubble = None


# Backward-compatibility alias for existing references
ChatView = UnifiedAssistantView
