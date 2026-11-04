"""
MIND Universal Studio — Dedicated Design Preview Popup Window.

Replaces the permanent split-screen preview pane with a separate, resizable
MIND-styled window that hosts the existing ``LiveWebsitePreviewWidget``.

Design rules enforced here:
  * The popup NEVER approves a design. Closing / hiding the window, pressing the
    title-bar close button, or refreshing does not change approval state.
  * The popup's "Approve & Develop" button only emits ``approve_requested``;
    the owning chat view decides whether to forward an explicit "Approve"
    message through the existing orchestrator pathway.
  * One popup window is reused for every design session (no duplicates);
    each session keeps its own ``DesignPreviewRecord`` so a closed or
    superseded design can be reopened later.
  * Any rendering failure is contained inside the popup and never propagates
    to the development task or touches generated project files.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .live_website_preview import LiveWebsitePreviewWidget

logger = logging.getLogger("mind.ui.design_preview_window")


# Approval states mirrored from the backend. The UI never invents "approved";
# it only moves to APPROVAL_SENT when the user clicks the explicit control and
# to APPROVED when the backend reports the workflow continued/completed.
STATE_AWAITING = "awaiting_approval"
STATE_APPROVAL_SENT = "approval_sent"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"
STATE_GENERATING = "generating"

_STATE_LABELS = {
    STATE_AWAITING: ("⏳ AWAITING YOUR APPROVAL", "#FFB84D", "#2A1E0A"),
    STATE_APPROVAL_SENT: ("📨 APPROVAL SENT — WAITING FOR MIND", "#00F5FF", "#0A1A2A"),
    STATE_APPROVED: ("✅ APPROVED — DEVELOPMENT AUTHORIZED", "#4DFFAA", "#0A1E14"),
    STATE_REJECTED: ("❌ REJECTED", "#FF4D6D", "#2A1015"),
    STATE_GENERATING: ("🔄 GENERATING DESIGN…", "#00F5FF", "#0A1A2A"),
}


@dataclass
class DesignPreviewRecord:
    """State of one design session's preview, independent of any window."""

    session_key: str
    title: str = "Design Prototype"
    version: int = 1
    provider: str = ""
    preview_file: Optional[str] = None
    preview_url: Optional[str] = None
    design_plan: Optional[Dict[str, Any]] = None
    screens: list = field(default_factory=list)
    active_screen_index: int = 0
    approval_state: str = STATE_AWAITING
    last_error: str = ""
    history: list = field(default_factory=list)  # [(version, preview_file)]

    @property
    def is_pending(self) -> bool:
        return self.approval_state in (STATE_AWAITING, STATE_APPROVAL_SENT)


class DesignPreviewWindow(QWidget):
    """Top-level MIND-styled window hosting the live interactive design preview."""

    approve_requested = pyqtSignal(str)   # session_key
    window_closed = pyqtSignal(str)       # session_key (closing != approval)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Independent, resizable top-level window with min/max/close controls.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("MIND — Design Preview")
        self.setMinimumSize(640, 480)
        self.resize(1180, 800)
        self.setStyleSheet("background-color: #050811; color: #EAF7FF;")

        self.record: Optional[DesignPreviewRecord] = None
        self._force_close = False
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(self)
        header.setStyleSheet("background-color: #0A1020; border-bottom: 1px solid #1B2A47;")
        h = QHBoxLayout(header)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(10)

        brand = QLabel("⚡ MIND // DESIGN PREVIEW")
        brand.setStyleSheet("color: #00F5FF; font-family: 'Consolas'; font-size: 12px; font-weight: bold;")
        h.addWidget(brand)

        self.lbl_title = QLabel("—")
        self.lbl_title.setStyleSheet("color: #EAF7FF; font-size: 12px; font-weight: bold;")
        h.addWidget(self.lbl_title, stretch=1)

        self.lbl_version = QLabel("v1")
        self.lbl_version.setStyleSheet(
            "color: #00F5FF; background: #101A2C; border: 1px solid #00F5FF; border-radius: 4px; "
            "padding: 2px 8px; font-family: 'Consolas'; font-size: 11px; font-weight: bold;"
        )
        h.addWidget(self.lbl_version)

        self.lbl_state = QLabel("")
        h.addWidget(self.lbl_state)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setStyleSheet(self._btn_style("#101A2C", "#00F5FF"))
        self.btn_refresh.clicked.connect(self.refresh)
        h.addWidget(self.btn_refresh)

        self.btn_approve = QPushButton("Approve && Develop ✅")
        self.btn_approve.setStyleSheet(
            "QPushButton { background: #4DFFAA; color: #050811; border: none; border-radius: 4px; "
            "padding: 6px 14px; font-size: 11px; font-weight: bold; } "
            "QPushButton:disabled { background: #1B2A47; color: #556B82; }"
        )
        self.btn_approve.clicked.connect(self._on_approve_clicked)
        h.addWidget(self.btn_approve)

        self.btn_close = QPushButton("✕ Close")
        self.btn_close.setStyleSheet(self._btn_style("#1A2035", "#FF4D6D"))
        self.btn_close.clicked.connect(self.close)
        h.addWidget(self.btn_close)

        layout.addWidget(header)

        # Guidance / error strip
        self.lbl_guidance = QLabel(
            "Review the design here. Request changes in the main MIND chat — this window updates automatically. "
            "Closing this window does NOT approve the design; reopen it from the chat at any time."
        )
        self.lbl_guidance.setWordWrap(True)
        self.lbl_guidance.setStyleSheet(
            "background-color: #080D18; color: #8095AC; font-size: 11px; padding: 6px 14px; "
            "border-bottom: 1px solid #142036;"
        )
        layout.addWidget(self.lbl_guidance)

        # Multi-screen selector bar (shown when Stitch returns multiple screens)
        self.screens_bar = QFrame(self)
        self.screens_bar.setStyleSheet("background-color: #070C17; border-bottom: 1px solid #142036;")
        self.screens_layout = QHBoxLayout(self.screens_bar)
        self.screens_layout.setContentsMargins(14, 4, 14, 4)
        self.screens_layout.setSpacing(6)
        self.screens_bar.setVisible(False)
        self._screen_buttons: list = []
        layout.addWidget(self.screens_bar)

        # Reuse the existing live preview infrastructure (WebEngine / native browser,
        # viewport presets, dev logs, open-in-browser).
        self.preview_widget = LiveWebsitePreviewWidget(self)
        layout.addWidget(self.preview_widget, stretch=1)

    @staticmethod
    def _btn_style(bg: str, fg: str) -> str:
        return (
            f"QPushButton {{ background: {bg}; color: {fg}; border: 1px solid #1B2A47; border-radius: 4px; "
            f"padding: 5px 12px; font-size: 11px; font-weight: bold; }} "
            f"QPushButton:hover {{ border-color: {fg}; }}"
        )

    # ------------------------------------------------------------- content
    def show_record(self, record: DesignPreviewRecord, reload_content: bool = True) -> None:
        """Binds the window to a session record and renders its current version."""
        self.record = record
        self.lbl_title.setText(record.title)
        self.lbl_version.setText(f"DESIGN v{record.version}")
        self.setWindowTitle(f"MIND — Design Preview — {record.title} (v{record.version})")
        self.update_approval_state(record.approval_state)
        self._rebuild_screen_buttons(record)
        if reload_content:
            self._render(record)

    def _rebuild_screen_buttons(self, record: DesignPreviewRecord) -> None:
        """Populates multi-screen navigation tabs when a Stitch design has multiple screens."""
        while self.screens_layout.count():
            item = self.screens_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._screen_buttons.clear()

        screens = record.screens or []
        if len(screens) <= 1:
            self.screens_bar.setVisible(False)
            return

        lbl = QLabel("SCREENS:")
        lbl.setStyleSheet("color: #8095AC; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        self.screens_layout.addWidget(lbl)

        for idx, scr in enumerate(screens):
            s_title = scr.get("title", f"Screen {idx + 1}") if isinstance(scr, dict) else getattr(scr, "title", f"Screen {idx + 1}")
            btn = QPushButton(f"{idx + 1}. {s_title}")
            is_active = idx == record.active_screen_index
            btn.setStyleSheet(
                self._btn_style("#10243E" if is_active else "#0A1020", "#00F5FF" if is_active else "#8095AC")
            )
            btn.clicked.connect(lambda _checked=False, i=idx: self.select_screen(i))
            self.screens_layout.addWidget(btn)
            self._screen_buttons.append(btn)

        self.screens_layout.addStretch()
        self.screens_bar.setVisible(True)

    def select_screen(self, index: int) -> None:
        """Switches the active Stitch screen inside the popup without changing approval state."""
        if self.record is None or not self.record.screens:
            return
        if index < 0 or index >= len(self.record.screens):
            return
        self.record.active_screen_index = index
        scr = self.record.screens[index]
        html_p = scr.get("html_path") if isinstance(scr, dict) else getattr(scr, "html_path", None)
        if html_p and os.path.exists(str(html_p)):
            self.record.preview_file = str(html_p)
        self._rebuild_screen_buttons(self.record)
        self._render(self.record)

    def show_revision_error(self, error_message: str) -> None:
        """Displays a non-destructive revision error banner while keeping the previous design rendered."""
        if self.record is not None:
            self.record.last_error = error_message
        self.lbl_guidance.setText(
            f"⚠ Revision failed: {error_message} — Previous design (v{self.record.version if self.record else 1}) remains active."
        )
        self.lbl_guidance.setStyleSheet(
            "background-color: #2A1015; color: #FFB4AB; font-size: 11px; padding: 6px 14px;"
        )

    def _render(self, record: DesignPreviewRecord) -> None:
        """Renders the actual generated prototype. Failures stay inside the popup."""
        record.last_error = ""
        is_stitch = (
            record.provider == "stitch"
            or (isinstance(record.design_plan, dict) and record.design_plan.get("provider") == "stitch")
        )
        try:
            if record.preview_file and os.path.exists(record.preview_file):
                ext = os.path.splitext(record.preview_file)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    uri = Path(record.preview_file).resolve().as_uri()
                    self.preview_widget.set_html(
                        f"<body style='background:#050811;margin:0;text-align:center'>"
                        f"<img src='{uri}' style='max-width:100%'></body>"
                    )
                else:
                    self.preview_widget.load_local_file(record.preview_file)
            elif record.preview_url:
                self.preview_widget.load_url(record.preview_url)
            elif record.design_plan and not is_stitch:
                self.preview_widget.set_html(self._render_design_plan_html(record))
            else:
                record.last_error = (
                    "Google Stitch design output is unavailable."
                    if is_stitch
                    else "No preview artifact is available for this design yet."
                )
                self.preview_widget.show_build_error(record.last_error)
        except Exception as e:  # never propagate into the workflow
            record.last_error = f"Preview rendering failed: {e}"
            logger.warning(record.last_error)
            try:
                self.preview_widget.show_build_error(record.last_error)
            except Exception:
                pass

        if record.last_error or "ERROR" in self.preview_widget.status_badge.text():
            self.lbl_guidance.setText(
                f"⚠ {record.last_error or 'The preview could not be rendered.'} "
                "Generated project files are untouched. Use Refresh to retry."
            )
            self.lbl_guidance.setStyleSheet(
                "background-color: #2A1015; color: #FFB4AB; font-size: 11px; padding: 6px 14px;"
            )
        else:
            self.lbl_guidance.setText(
                "Review the design here. Request changes in the main MIND chat — this window updates automatically. "
                "Closing this window does NOT approve the design; reopen it from the chat at any time."
            )
            self.lbl_guidance.setStyleSheet(
                "background-color: #080D18; color: #8095AC; font-size: 11px; padding: 6px 14px; "
                "border-bottom: 1px solid #142036;"
            )

    @staticmethod
    def _render_design_plan_html(record: DesignPreviewRecord) -> str:
        """Synthesizes an interactive HTML preview for an orchestrator design_plan proposal."""
        plan = record.design_plan or {}
        palette = plan.get("palette") or {}
        primary = palette.get("primary", "#00F5FF")
        accent = palette.get("accent", "#4DFFAA")
        bg_dark = palette.get("bg_dark", "#050811")
        text_light = palette.get("text_light", "#EAF7FF")
        pages = plan.get("pages") or ["index.html"]
        direction = plan.get("visual_direction", "Clean, high-performance interface")
        rev = plan.get("latest_revision", "")
        nav_links = "".join(f"<a href='#{p}' style='color:{accent};margin-right:16px;text-decoration:none;'>{p}</a>" for p in pages)
        rev_html = f"<div style='margin-top:12px;padding:10px;border-left:3px solid {accent};background:#101A2C;'>Revision applied: {rev}</div>" if rev else ""
        return (
            f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>{record.title} (v{record.version})</title>"
            f"<style>body{{background:{bg_dark};color:{text_light};font-family:'Segoe UI',sans-serif;margin:0;padding:24px;}}"
            f".hero{{border:1px solid {primary};border-radius:10px;padding:28px;background:#0A1020;margin-top:16px;}}"
            f".btn{{background:{primary};color:#050811;border:none;border-radius:6px;padding:10px 18px;font-weight:bold;cursor:pointer;}}"
            f"</style></head><body>"
            f"<header style='display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1B2A47;padding-bottom:12px;'>"
            f"<strong>{record.title} — Design Proposal v{record.version}</strong><nav>{nav_links}</nav></header>"
            f"<section class='hero'><h1 style='color:{primary};margin-top:0;'>{record.title}</h1>"
            f"<p>{direction}</p>{rev_html}"
            f"<p style='font-size:12px;color:#8095AC;'>Palette: primary {primary} · accent {accent} · pages: {', '.join(pages)}</p>"
            f"<button class='btn'>Interactive Prototype CTA</button></section></body></html>"
        )

    def refresh(self) -> None:
        """Reloads the current design version (does not change approval)."""
        if self.record is None:
            return
        self._render(self.record)

    def update_approval_state(self, state: str) -> None:
        if self.record is not None:
            self.record.approval_state = state
        text, fg, bg = _STATE_LABELS.get(state, (state.upper(), "#8095AC", "#101A2C"))
        self.lbl_state.setText(text)
        self.lbl_state.setStyleSheet(
            f"color: {fg}; background: {bg}; border: 1px solid {fg}; border-radius: 4px; "
            f"padding: 2px 8px; font-family: 'Consolas'; font-size: 10px; font-weight: bold;"
        )
        # Explicit approval control only while awaiting approval.
        self.btn_approve.setVisible(state in (STATE_AWAITING, STATE_APPROVAL_SENT))
        self.btn_approve.setEnabled(state == STATE_AWAITING)

    def set_approval_blocked(self, reason: str) -> None:
        """Disables approval (e.g. design belongs to a superseded session)."""
        self.btn_approve.setEnabled(False)
        self.btn_approve.setToolTip(reason)
        self.lbl_guidance.setText(f"ℹ {reason}")

    # --------------------------------------------------------------- events
    def _on_approve_clicked(self) -> None:
        if self.record is None or self.record.approval_state != STATE_AWAITING:
            return
        self.approve_requested.emit(self.record.session_key)

    def force_close(self) -> None:
        """Closes and releases the window (used on main window shutdown)."""
        self._force_close = True
        self.close()
        self.deleteLater()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # Closing is purely visual: approval state is left exactly as it was.
        key = self.record.session_key if self.record else ""
        super().closeEvent(event)
        if not self._force_close:
            self.window_closed.emit(key)


class DesignPreviewManager(QObject):
    """
    Owns the single popup window and per-session preview records.

    The manager is a pure UI coordinator: it never talks to the orchestrator
    and cannot approve anything on its own.
    """

    approve_requested = pyqtSignal(str)   # session_key
    records_changed = pyqtSignal()

    def __init__(self, parent_widget: Optional[QWidget] = None) -> None:
        super().__init__(parent_widget)
        self._parent_widget = parent_widget
        self._window: Optional[DesignPreviewWindow] = None
        self.records: Dict[str, DesignPreviewRecord] = {}
        self.active_session_key: Optional[str] = None
        self.window_open_count = 0  # number of window instances ever created

    # ------------------------------------------------------------- window
    @property
    def window(self) -> Optional[DesignPreviewWindow]:
        return self._window

    def _ensure_window(self) -> DesignPreviewWindow:
        if self._window is None:
            win = DesignPreviewWindow(self._parent_widget)
            win.approve_requested.connect(self.approve_requested.emit)
            win.window_closed.connect(lambda _k: self.records_changed.emit())
            self._window = win
            self.window_open_count += 1
        return self._window

    def is_window_visible(self) -> bool:
        return self._window is not None and self._window.isVisible()

    # ------------------------------------------------------------ records
    def present(
        self,
        session_key: str,
        title: str,
        version: int,
        preview_file: Optional[str] = None,
        preview_url: Optional[str] = None,
        approval_state: str = STATE_AWAITING,
        show: bool = True,
        design_plan: Optional[Dict[str, Any]] = None,
        provider: str = "",
        screens: Optional[list] = None,
    ) -> DesignPreviewRecord:
        """Creates/updates a session record and shows it in the (single) popup."""
        rec = self.records.get(session_key)
        if rec is None:
            rec = DesignPreviewRecord(session_key=session_key)
            self.records[session_key] = rec
        rec.title = title or rec.title
        rec.version = int(version or rec.version or 1)
        if provider:
            rec.provider = provider
        if preview_file:
            rec.preview_file = str(preview_file)
        if preview_url:
            rec.preview_url = preview_url
        if design_plan is not None:
            rec.design_plan = design_plan
        if screens is not None:
            rec.screens = list(screens)
            rec.active_screen_index = 0
        rec.approval_state = approval_state
        if not rec.history or rec.history[-1][0] != rec.version:
            rec.history.append((rec.version, rec.preview_file))

        self.active_session_key = session_key
        try:
            win = self._ensure_window()
            win.show_record(rec)
            if show:
                win.show()
                win.raise_()
        except Exception as e:  # popup failure must not affect the task
            logger.warning("Design preview popup failed: %s", e)
            rec.last_error = str(e)
        self.records_changed.emit()
        return rec

    def record_revision_failure(self, session_key: str, error_message: str) -> Optional[DesignPreviewRecord]:
        """
        Records a revision failure without overwriting the existing preview version or HTML.
        Keeps the popup displaying the last valid version (`v1`, etc.) in `STATE_AWAITING`.
        """
        key = session_key or self.active_session_key
        rec = self.records.get(key) if key else None
        if rec is None:
            return None
        rec.approval_state = STATE_AWAITING
        rec.last_error = error_message
        if self._window is not None and self._window.record is rec:
            self._window.update_approval_state(STATE_AWAITING)
            self._window.show_revision_error(error_message)
        self.records_changed.emit()
        return rec

    def reopen(self, session_key: Optional[str] = None) -> bool:
        """Reopens a previously shown design (pending or not). Returns success."""
        key = session_key or self.active_session_key
        rec = self.records.get(key) if key else None
        if rec is None:
            return False
        win = self._ensure_window()
        same = win.record is rec
        win.show_record(rec, reload_content=not same or not win.isVisible())
        win.show()
        win.raise_()
        return True

    def set_state(self, session_key: str, state: str) -> None:
        rec = self.records.get(session_key)
        if rec is None:
            return
        rec.approval_state = state
        if self._window is not None and self._window.record is rec:
            self._window.update_approval_state(state)
        self.records_changed.emit()

    def pending_record(self) -> Optional[DesignPreviewRecord]:
        rec = self.records.get(self.active_session_key) if self.active_session_key else None
        return rec if rec and rec.is_pending else None

    def close_window(self) -> None:
        if self._window is not None:
            self._window.close()

    def shutdown(self) -> None:
        """Releases the popup window (main window closing). Approval state is untouched."""
        if self._window is not None:
            try:
                self._window.force_close()
            except RuntimeError:
                pass
            self._window = None
