"""
MIND Universal Studio — Meta Hackathon Edition
Visual Workflow Evidence & Screenshot Gallery View.

Provides real-time inspection of captured visual evidence across all 15 workflow stages:
Chronological timeline, high-resolution preview viewer, stage filters,
failure status, and one-click access to the HTML dossier and evidence directory.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPixmap, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QScrollArea,
    QFrame,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
)

from ...tools.screenshot_manager import (
    WorkflowScreenshotManager,
    WorkflowStage,
    ScreenshotMetadata,
    STAGE_DISPLAY_NAMES,
)


class EvidenceView(QWidget):
    """Interactive visual evidence viewer integrated into MIND's desktop cockpit."""

    _capture_received = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = WorkflowScreenshotManager.get_instance()
        self.active_meta: Optional[ScreenshotMetadata] = None
        self._build_ui()
        self._capture_received.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        self.manager.add_listener(self._on_screenshot_captured)
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        # Header bar
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("WORKFLOW VISUAL EVIDENCE & AUDIT TRAIL")
        title.setStyleSheet("color: #00F5FF; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        subtitle = QLabel("Chronological Visual Record of Design, Execution, Automated Repair, & Independent Verification")
        subtitle.setStyleSheet("color: #8095AC; font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hdr.addLayout(title_box)

        hdr.addStretch()

        # Action Buttons
        self.btn_open_folder = QPushButton("📁 Open Evidence Folder")
        self.btn_open_folder.setStyleSheet("background: #101A2C; color: #EAF7FF; border: 1px solid #1B2A47; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        self.btn_open_folder.clicked.connect(self._open_evidence_dir)
        hdr.addWidget(self.btn_open_folder)

        self.btn_open_report = QPushButton("🌐 View HTML Dossier")
        self.btn_open_report.setStyleSheet("background: #00F5FF; color: #050811; border: none; padding: 6px 14px; border-radius: 4px; font-weight: bold;")
        self.btn_open_report.clicked.connect(self._open_html_report)
        hdr.addWidget(self.btn_open_report)

        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setStyleSheet("background: #0A1020; color: #8095AC; border: 1px solid #1B2A47; padding: 6px 10px; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.refresh)
        hdr.addWidget(self.btn_refresh)

        layout.addLayout(hdr)

        # Control Bar: Stage Filter & Session Status
        ctrl_bar = QHBoxLayout()
        lbl_filter = QLabel("STAGE FILTER:")
        lbl_filter.setStyleSheet("color: #8095AC; font-size: 11px; font-weight: bold;")
        ctrl_bar.addWidget(lbl_filter)

        self.stage_filter = QComboBox()
        self.stage_filter.setStyleSheet("background: #101A2C; color: #00F5FF; border: 1px solid #1B2A47; padding: 4px 8px; border-radius: 4px; min-width: 220px;")
        self.stage_filter.addItem("ALL STAGES (Complete Lifecycle)", "")
        for st in WorkflowStage:
            self.stage_filter.addItem(STAGE_DISPLAY_NAMES.get(st, st.value), st.value)
        self.stage_filter.currentIndexChanged.connect(self._apply_filter)
        ctrl_bar.addWidget(self.stage_filter)

        ctrl_bar.addStretch()

        self.lbl_stats = QLabel("Session: Ready | Captures: 0")
        self.lbl_stats.setStyleSheet("color: #4DFFAA; font-family: 'Consolas'; font-size: 11px;")
        ctrl_bar.addWidget(self.lbl_stats)

        layout.addLayout(ctrl_bar)

        # Splitter: Left = Table of Captures, Right = High-Res Preview & Details
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #1B2A47; width: 2px; }")

        # Left: Captures Table
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "Stage", "Event Name", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0A1020;
                color: #EAF7FF;
                border: 1px solid #1B2A47;
                border-radius: 6px;
                gridline-color: #152238;
                font-size: 11px;
            }
            QHeaderView::section {
                background: #101A2C;
                color: #8095AC;
                border: none;
                padding: 6px 8px;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background: #162640;
                color: #00F5FF;
            }
        """)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        left_layout.addWidget(self.table)
        splitter.addWidget(left_widget)

        # Right: High-Res Screenshot Preview & Metadata
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(8)

        # High-Res Image Area in Scroll Area
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet("background: #070C18; border: 1px solid #1B2A47; border-radius: 6px;")
        
        self.lbl_image = QLabel("Select an evidence record to inspect full-resolution capture.")
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setStyleSheet("color: #8095AC; font-size: 12px; padding: 20px;")
        self.preview_scroll.setWidget(self.lbl_image)
        right_layout.addWidget(self.preview_scroll, stretch=1)

        # Details Panel
        self.details_box = QFrame()
        self.details_box.setStyleSheet("background: #0A1020; border: 1px solid #1B2A47; border-radius: 6px; padding: 10px;")
        det_layout = QVBoxLayout(self.details_box)
        det_layout.setSpacing(4)
        
        self.lbl_det_title = QLabel("NO EVIDENCE SELECTED")
        self.lbl_det_title.setStyleSheet("color: #00F5FF; font-weight: bold; font-size: 12px;")
        det_layout.addWidget(self.lbl_det_title)

        self.lbl_det_desc = QLabel("Captures will appear here automatically as workflows execute.")
        self.lbl_det_desc.setStyleSheet("color: #EAF7FF; font-size: 11px;")
        self.lbl_det_desc.setWordWrap(True)
        det_layout.addWidget(self.lbl_det_desc)

        self.lbl_det_meta = QLabel("")
        self.lbl_det_meta.setStyleSheet("color: #8095AC; font-family: 'Consolas'; font-size: 10px;")
        det_layout.addWidget(self.lbl_det_meta)

        right_layout.addWidget(self.details_box)
        splitter.addWidget(right_widget)

        splitter.setSizes([450, 750])
        layout.addWidget(splitter, stretch=1)

    def refresh(self) -> None:
        """Reloads captures from the central manager."""
        self.lbl_stats.setText(f"Session: {self.manager.session_id} | Total Captures: {len(self.manager.captures)}")
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Filters table according to selected workflow stage."""
        stage_filter = self.stage_filter.currentData()
        self.table.setRowCount(0)

        captures = self.manager.captures
        if stage_filter:
            captures = [c for c in captures if c.stage.value == stage_filter]

        for row, c in enumerate(captures):
            self.table.insertRow(row)
            
            # Col 0: Seq
            item_seq = QTableWidgetItem(f"#{c.sequence_number:02d}")
            item_seq.setData(Qt.ItemDataRole.UserRole, c)
            self.table.setItem(row, 0, item_seq)

            # Col 1: Stage
            stage_display = STAGE_DISPLAY_NAMES.get(c.stage, str(c.stage))
            self.table.setItem(row, 1, QTableWidgetItem(stage_display))

            # Col 2: Event Name
            self.table.setItem(row, 2, QTableWidgetItem(c.event_name))

            # Col 3: Status
            status_item = QTableWidgetItem("VERIFIED" if c.success else "FAILED")
            status_item.setForeground(QColor("#4DFFAA" if c.success else "#FF4D4D"))
            self.table.setItem(row, 3, status_item)

        if self.table.rowCount() > 0:
            self.table.selectRow(self.table.rowCount() - 1)

    def _on_row_selected(self) -> None:
        """Displays high-resolution image and metadata for selected row."""
        selected = self.table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        item = self.table.item(row, 0)
        if not item:
            return

        c: ScreenshotMetadata = item.data(Qt.ItemDataRole.UserRole)
        self.active_meta = c

        self.lbl_det_title.setText(f"STAGE: {STAGE_DISPLAY_NAMES.get(c.stage, str(c.stage)).upper()} — {c.event_name}")
        self.lbl_det_desc.setText(c.description)
        self.lbl_det_meta.setText(f"ID: {c.screenshot_id}  |  TIME: {c.timestamp_iso}  |  METHOD: {c.capture_method}  |  TYPE: {c.evidence_type.upper()}")

        # Load pixmap
        img_path = Path(c.file_path)
        if img_path.exists():
            pix = QPixmap(str(img_path))
            scaled = pix.scaledToWidth(700, Qt.TransformationMode.SmoothTransformation)
            self.lbl_image.setPixmap(scaled)
        else:
            self.lbl_image.setText(f"File missing on disk: {img_path}")

    def _on_screenshot_captured(self, meta: ScreenshotMetadata) -> None:
        """Real-time update listener triggered upon capture (thread-safe via queued signal)."""
        try:
            self._capture_received.emit()
        except Exception:
            pass

    def _open_evidence_dir(self) -> None:
        """Opens active session evidence directory in OS explorer."""
        p = self.manager.session_dir
        if sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.run(["xdg-open", str(p)])

    def _open_html_report(self) -> None:
        """Opens interactive HTML report in default browser."""
        rep = self.manager.session_dir / "workflow_report.html"
        if not rep.exists():
            rep = self.manager.generate_html_report()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(rep.resolve())))
