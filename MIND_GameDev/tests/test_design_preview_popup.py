"""
Tests for the dedicated MIND Design Preview popup window.

These tests drive the real Qt widgets (offscreen platform) through the same
public entry points the backend uses — ``UnifiedAssistantView.update_workflow_progress``
and ``complete_workflow`` — and assert on actual window/widget state, not only on
helper return values. No network or paid AI API is used.
"""

import os
import socket
import tempfile
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from MIND_GameDev.ui.views.chat_view import UnifiedAssistantView
from MIND_GameDev.ui.widgets import LiveWebsitePreviewWidget, DesignPreviewWindow
from MIND_GameDev.ui.widgets.design_preview_window import (
    STATE_AWAITING,
    STATE_APPROVAL_SENT,
    STATE_APPROVED,
    STATE_REJECTED,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _pump(ms: int = 50) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def _make_proto(root: Path, name: str, marker: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    f = d / "index.html"
    f.write_text(f"<html><body><h1>{marker}</h1><button id='b'>Go</button></body></html>", encoding="utf-8")
    return f


def _awaiting(session: str, version: int, html: Path, title: str = "School Website") -> dict:
    return {
        "status": "awaiting_approval",
        "design_state": "awaiting_design_approval",
        "session_id": session,
        "version": version,
        "title": title,
        "response": f"Design prototype v{version} generated.",
        "artifacts": [{"path": str(html), "mime_type": "text/html", "preview_type": "browser"}],
    }


@pytest.fixture
def view(qapp):
    v = UnifiedAssistantView()
    v.resize(1200, 800)
    v.show()
    sent = []
    v.prompt_sent.connect(lambda text, choice: sent.append(text))
    v._sent = sent
    yield v
    v.shutdown_previews()
    v.close()
    v.deleteLater()
    _pump()


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


def test_main_window_has_no_split_preview_pane(view):
    """Chat owns the full width: no splitter and no embedded preview widget."""
    assert not hasattr(view, "splitter")
    embedded = [w for w in view.findChildren(LiveWebsitePreviewWidget) if w.window() is view]
    assert embedded == []
    assert view.preview_widget is None  # no popup yet
    assert view.btn_toggle_preview.isEnabled() is False


def test_popup_opens_when_design_becomes_available(view, tmp):
    html = _make_proto(tmp, "ds_a_v1", "DESIGN-V1")
    view.complete_workflow(_awaiting("sess_A", 1, html))
    _pump()

    win = view.design_preview.window
    assert isinstance(win, DesignPreviewWindow)
    assert win.isVisible() and win.isWindow()
    assert win is not view.window()
    assert "DESIGN-V1" in win.preview_widget._last_valid_html
    assert win.lbl_version.text() == "DESIGN v1"
    assert "School Website" in win.windowTitle()
    assert win.btn_approve.isVisible() and win.btn_approve.isEnabled()
    assert "AWAITING" in view.workspace_status_pill.text()
    assert view.btn_toggle_preview.isEnabled()
    # Generating a preview must not approve anything.
    assert view._sent == []


def test_popup_is_resizable_and_maximizable(view, tmp):
    html = _make_proto(tmp, "ds_size", "SIZE")
    view.complete_workflow(_awaiting("sess_S", 1, html))
    win = view.design_preview.window
    from PyQt6.QtCore import Qt
    flags = win.windowFlags()
    assert flags & Qt.WindowType.WindowMaximizeButtonHint
    assert flags & Qt.WindowType.WindowCloseButtonHint
    win.resize(900, 600)
    _pump()
    assert win.width() == 900 and win.height() == 600
    win.showMaximized()
    _pump()
    win.showNormal()
    _pump()
    assert win.isVisible()


def test_revision_reuses_existing_popup(view, tmp):
    v1 = _make_proto(tmp, "ds_r_v1", "REV-ONE")
    v2 = _make_proto(tmp, "ds_r_v2", "REV-TWO")
    view.complete_workflow(_awaiting("sess_R", 1, v1))
    win1 = view.design_preview.window

    # User asks for changes in chat; MIND returns v2 for the same session.
    view.complete_workflow(_awaiting("sess_R", 2, v2))
    _pump()
    win2 = view.design_preview.window

    assert win1 is win2
    assert view.design_preview.window_open_count == 1
    assert win2.lbl_version.text() == "DESIGN v2"
    assert "REV-TWO" in win2.preview_widget._last_valid_html
    rec = view.design_preview.records["sess_R"]
    assert [v for v, _ in rec.history] == [1, 2]
    assert rec.approval_state == STATE_AWAITING
    assert view._sent == []


def test_progress_update_refreshes_open_popup(view, tmp):
    v1 = _make_proto(tmp, "ds_p_v1", "PROG-ONE")
    view.complete_workflow(_awaiting("sess_P", 1, v1))
    v2 = _make_proto(tmp, "ds_p_v2", "PROG-TWO")
    view.update_workflow_progress({
        "workflow_id": "sess_P", "session_id": "sess_P", "design_state": "revising",
        "version": 2, "preview_file": str(v2), "message": "Revising design", "progress_pct": 0.5,
    })
    _pump()
    win = view.design_preview.window
    assert view.design_preview.window_open_count == 1
    assert "PROG-TWO" in win.preview_widget._last_valid_html
    assert win.lbl_version.text() == "DESIGN v2"


def test_session_and_project_association(view, tmp):
    html = _make_proto(tmp, "ds_assoc", "ASSOC")
    view.complete_workflow(_awaiting("sess_X", 3, html, title="Observatory Portal"))
    rec = view.design_preview.window.record
    assert rec.session_key == "sess_X"
    assert rec.title == "Observatory Portal"
    assert rec.version == 3
    assert Path(rec.preview_file) == html
    assert view._pending_design_session == "sess_X"
    assert view._active_workflow_bubble.design_session_key == "sess_X"


def test_refresh_reloads_current_design(view, tmp):
    html = _make_proto(tmp, "ds_refresh", "BEFORE")
    view.complete_workflow(_awaiting("sess_F", 1, html))
    win = view.design_preview.window
    html.write_text("<html><body><h1>AFTER-EDIT</h1></body></html>", encoding="utf-8")
    win.btn_refresh.click()
    _pump()
    assert "AFTER-EDIT" in win.preview_widget._last_valid_html
    assert win.record.approval_state == STATE_AWAITING
    assert view._sent == []


def test_close_without_approving_keeps_pending_and_can_reopen(view, tmp):
    html = _make_proto(tmp, "ds_close", "CLOSE")
    view.complete_workflow(_awaiting("sess_C", 1, html))
    win = view.design_preview.window

    win.btn_close.click()          # explicit close control
    _pump()
    assert not win.isVisible()
    win.show(); win.close()        # title-bar close path (closeEvent)
    _pump()

    assert view._sent == []                                   # nothing transmitted
    assert view.design_preview.records["sess_C"].approval_state == STATE_AWAITING
    assert view._pending_design_session == "sess_C"
    assert "AWAITING" in view.workspace_status_pill.text()

    # Reopen from the top bar button and from the chat bubble.
    view.btn_toggle_preview.click()
    _pump()
    assert view.design_preview.window.isVisible()
    assert view.design_preview.window_open_count == 1
    view.design_preview.close_window()
    view._active_workflow_bubble.btn_reopen_preview.click()
    _pump()
    assert view.design_preview.window.isVisible()
    assert view._sent == []


def test_explicit_popup_approval_uses_existing_chat_pathway(view, tmp):
    html = _make_proto(tmp, "ds_approve", "APPROVE")
    view.complete_workflow(_awaiting("sess_OK", 1, html))
    win = view.design_preview.window

    win.btn_approve.click()
    _pump()
    # Exactly one explicit "Approve" message sent through prompt_sent → orchestrator.
    assert view._sent == ["Approve"]
    assert win.record.approval_state == STATE_APPROVAL_SENT
    assert not win.btn_approve.isEnabled()          # no double-approval
    win.btn_approve.click()
    assert view._sent == ["Approve"]

    # Backend reports production workflow completed → mirrored as approved.
    view.complete_workflow({"status": "completed", "session_id": "sess_OK", "response": "Built."})
    _pump()
    assert view.design_preview.records["sess_OK"].approval_state == STATE_APPROVED
    assert view._pending_design_session is None
    assert "APPROVED" in view.workspace_status_pill.text()


def test_failed_after_approval_restores_pending(view, tmp):
    html = _make_proto(tmp, "ds_fail", "FAIL")
    view.complete_workflow(_awaiting("sess_FL", 1, html))
    view.design_preview.window.btn_approve.click()
    view.complete_workflow({"status": "failed", "session_id": "sess_FL", "response": "Build error"})
    rec = view.design_preview.records["sess_FL"]
    assert rec.approval_state == STATE_AWAITING
    assert view.design_preview.window.btn_approve.isEnabled()


def test_rejection_marks_design_rejected(view, tmp):
    html = _make_proto(tmp, "ds_rej", "REJ")
    view.complete_workflow(_awaiting("sess_RJ", 1, html))
    view.complete_workflow({"status": "rejected", "session_id": "sess_RJ", "response": "Rejected"})
    assert view.design_preview.records["sess_RJ"].approval_state == STATE_REJECTED
    assert not view.design_preview.window.btn_approve.isVisible()


def test_preview_server_failure_is_contained(view, tmp):
    # Find a closed localhost port to simulate an unavailable preview server.
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    res = {
        "status": "awaiting_approval", "design_state": "awaiting_design_approval",
        "session_id": "sess_SRV", "version": 1, "title": "Server Down",
        "preview_url": f"http://127.0.0.1:{port}/index.html",
    }
    view.complete_workflow(res)   # must not raise
    _pump(600)                    # past the widget's 400 ms READY timer
    win = view.design_preview.window
    assert win is not None and win.isVisible()
    assert "ERROR" in win.preview_widget.status_badge.text()
    assert "⚠" in win.lbl_guidance.text()
    assert win.record.approval_state == STATE_AWAITING
    assert view._sent == []


def test_multiple_independent_sessions(view, tmp):
    a = _make_proto(tmp, "ds_ma", "SESSION-A")
    b = _make_proto(tmp, "ds_mb", "SESSION-B")
    view.complete_workflow(_awaiting("sess_MA", 1, a, title="Project A"))
    view.complete_workflow(_awaiting("sess_MB", 1, b, title="Project B"))
    _pump()
    mgr = view.design_preview
    assert mgr.window_open_count == 1                  # single window, no duplicates
    assert mgr.window.record.session_key == "sess_MB"
    assert "SESSION-B" in mgr.window.preview_widget._last_valid_html
    assert set(mgr.records) == {"sess_MA", "sess_MB"}

    # Reopen the older session A: it cannot be approved (backend is waiting on B).
    view.reopen_design_preview("sess_MA")
    _pump()
    assert "SESSION-A" in mgr.window.preview_widget._last_valid_html
    mgr.window.btn_approve.click()
    assert view._sent == []
    assert not mgr.window.btn_approve.isEnabled()

    # Session B approves normally.
    view.reopen_design_preview("sess_MB")
    mgr.window.btn_approve.click()
    assert view._sent == ["Approve"]
    assert mgr.records["sess_MA"].approval_state == STATE_AWAITING


def test_main_window_shutdown_cleans_up_popup(qapp, tmp):
    from MIND_GameDev.ui.main_window import MINDMainWindow
    win = MINDMainWindow()
    win.show()
    sent = []
    win.chat_view.prompt_sent.connect(lambda t, c: sent.append(t))
    html = _make_proto(tmp, "ds_shut", "SHUT")
    win.chat_view.complete_workflow(_awaiting("sess_SH", 1, html))
    popup = win.chat_view.design_preview.window
    assert popup.isVisible()

    win.close()
    _pump()
    assert win.chat_view.design_preview.window is None
    from PyQt6 import sip
    assert sip.isdeleted(popup)                        # popup window released, not just hidden
    assert sent == []                                  # shutdown never approves
    assert html.exists()                               # project files untouched
    win.deleteLater()
    _pump()


def test_live_preview_server_integration_and_refresh(view, tmp):
    """Popup renders live HTML/CSS/JS served over HTTP by WorkspacePreviewServer and refreshes on v2."""
    from MIND_GameDev.tools.preview_server import WorkspacePreviewServer

    site_dir = tmp / "live_site"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text(
        "<!DOCTYPE html><html><head><link rel='stylesheet' href='style.css'></head>"
        "<body><h1>SERVER-V1</h1><script src='main.js'></script></body></html>",
        encoding="utf-8",
    )
    (site_dir / "style.css").write_text("body { background: #050811; color: #00F5FF; }", encoding="utf-8")
    (site_dir / "main.js").write_text("console.log('ready');", encoding="utf-8")

    with WorkspacePreviewServer(site_dir) as srv:
        url = srv.get_url("index.html")
        view.complete_workflow({
            "status": "awaiting_approval",
            "design_state": "awaiting_design_approval",
            "session_id": "sess_HTTP",
            "version": 1,
            "title": "Live Server Prototype",
            "preview_url": url,
        })
        _pump(500)
        win = view.design_preview.window
        assert win.isVisible()
        assert "SERVER-V1" in win.preview_widget._last_valid_html

        # Revise design on disk and refresh the popup without approving.
        (site_dir / "index.html").write_text("<!DOCTYPE html><html><body><h1>SERVER-V2</h1></body></html>", encoding="utf-8")
        win.btn_refresh.click()
        _pump(500)
        assert "SERVER-V2" in win.preview_widget._last_valid_html
        assert win.record.approval_state == STATE_AWAITING
        assert view._sent == []


def test_orchestrator_end_to_end_revision_destructive_guard_and_explicit_approval(view, tmp):
    """
    Drives the popup against the real GameDevOrchestrator:
      1. Design v1 opens the popup in awaiting-approval state; target_dir does not exist yet.
      2. Design revision updates the SAME popup to v2.
      3. A destructive-operation confirmation (CONFIRMATION_REQUIRED) does NOT approve the design.
      4. Clicking the popup's explicit Approve button forwards 'Approve' to GameDevOrchestrator,
         which builds and verifies the real project on disk.
    """
    from MIND_GameDev.config import GameDevConfig
    from MIND_GameDev.orchestrator import GameDevOrchestrator
    from MIND_GameDev.tools.session_memory import SessionMemory
    from MIND_GameDev.tools.conversation_state import ConversationState

    target_dir = tmp / "PopupAcademy"
    cfg = GameDevConfig.load()
    cfg.test_mode = True
    cfg.require_design_approval = True
    cfg.workspace_root = tmp / "ws"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)
    mem = SessionMemory(db_path=tmp / "session.db")
    state = ConversationState(mem)
    orch = GameDevOrchestrator(config=cfg, enable_voice=False, session_memory=mem, conversation_state=state)

    # Wire chat prompt_sent directly into the real orchestrator when explicit approval is clicked.
    orch_calls = []
    def _forward(text: str, _choice: str) -> None:
        orch_calls.append(text)
        res = orch.execute_command(text)
        view.complete_workflow(res)
    view.prompt_sent.connect(_forward)

    # 1. Generate Design v1
    r1 = orch.execute_command(f"Create a school website, save to {target_dir}, and name it PopupAcademy")
    assert r1["status"] == "APPROVAL_REQUIRED"
    assert not (target_dir / "index.html").exists()
    view.complete_workflow(r1)
    _pump()

    win = view.design_preview.window
    assert win.isVisible()
    assert win.lbl_version.text() == "DESIGN v1"
    assert win.record.approval_state == STATE_AWAITING

    # 2. Request a revision -> updates the existing popup to v2 (no duplicate windows)
    r2 = orch.execute_command("Revise the design to use an emerald green palette and add contact.html")
    assert r2["status"] == "APPROVAL_REQUIRED"
    assert r2["design_version"] == 2
    view.complete_workflow(r2)
    _pump()
    assert view.design_preview.window is win
    assert view.design_preview.window_open_count == 1
    assert win.lbl_version.text() == "DESIGN v2"
    assert "#10b981" in win.preview_widget._last_valid_html
    assert not (target_dir / "index.html").exists()

    # 3. Destructive-operation confirmation must NOT approve the design
    view.complete_workflow({
        "status": "CONFIRMATION_REQUIRED",
        "conflicting_files_count": 2,
        "message": "Target directory is non-empty. Confirm overwrite?",
    })
    _pump()
    assert win.record.approval_state == STATE_AWAITING
    assert orch_calls == []
    assert not (target_dir / "index.html").exists()

    # 4. Explicit approval from the popup triggers GameDevOrchestrator implementation
    win.btn_approve.click()
    _pump()
    assert orch_calls == ["Approve"]
    assert (target_dir / "index.html").exists()
    assert win.record.approval_state == STATE_APPROVED

