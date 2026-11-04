"""
Automated Integration & Live Verification Tests for:
MIND Hackathon Edition — Google Stitch Direct Design-to-Preview Integration.

Covers:
1. Real provider routing to Google Stitch (`StitchAdapter`) with zero `CodingAgent` / `WebsiteWorkflow` invocation.
2. API authentication (`X-Goog-Api-Key`), JSON-RPC 2.0 `tools/call` format, and strict secret redaction.
3. HTML, CSS, JS, screenshot, and multi-screen extraction via `download_file`.
4. Actual preview rendering and multi-screen switching inside `DesignPreviewWindow`.
5. Natural-language revision requests via `edit_screens` updating the existing popup (`v1 -> v2`) while preserving `v1` on disk.
6. Failed revision requests preserving the previous `v1` preview in the popup without data loss.
7. Closing, refreshing, and reopening the popup without approving.
8. Explicit approval marking the Stitch design as `DESIGN_APPROVED` WITHOUT starting automatic website code implementation.
9. Session isolation across multiple Stitch design sessions.
10. Prevention of accidental internal website generation when Stitch is unavailable or unconfigured.
11. Live Google Stitch MCP verification check (clearly distinguished from mocked transport tests).
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from MIND_GameDev.adapters.stitch_adapter import (
    StitchAdapter,
    StitchDesignBundle,
    StitchError,
    StitchUnavailableError,
)
from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.orchestrator import GameDevOrchestrator
from MIND_GameDev.tools.conversation_state import ConversationState
from MIND_GameDev.tools.session_memory import SessionMemory
from MIND_GameDev.ui.views.chat_view import UnifiedAssistantView
from MIND_GameDev.ui.widgets.design_preview_window import (
    DesignPreviewWindow,
    STATE_APPROVED,
    STATE_AWAITING,
    STATE_REJECTED,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(ms: int = 60) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def view(qapp):
    v = UnifiedAssistantView()
    v.resize(1200, 800)
    v.show()
    sent: List[str] = []
    v.prompt_sent.connect(lambda text, _choice: sent.append(text))
    v._sent = sent
    yield v
    v.shutdown_previews()
    v.close()
    v.deleteLater()
    _pump()


# 1x1 transparent PNG in base64 for screenshot extraction tests
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class MockStitchMCPTransport:
    """
    Deterministic mock of the official Google Stitch JSON-RPC 2.0 MCP server
    (`https://stitch.googleapis.com/mcp`), returning real Stitch `outputComponents`
    structures and `download_file` payloads.
    """

    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.fail_next_edit: bool = False
        self.fail_all: bool = False
        self.multi_screen: bool = False

    def __call__(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        self.requests.append({
            "url": url,
            "headers": dict(headers),
            "payload": json.loads(json.dumps(payload)),
            "timeout": timeout,
        })

        if self.fail_all:
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id", 1),
                "error": {"code": -32000, "message": "Stitch service temporarily unreachable"},
            }

        params = payload.get("params") or {}
        tool = params.get("name")
        args = params.get("arguments") or {}
        rpc_id = payload.get("id", 1)

        if tool == "create_project":
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "structuredContent": {
                        "name": "projects/777000111",
                        "title": args.get("title", "MIND Website Design"),
                    }
                },
            }

        if tool == "generate_screen_from_text":
            pid = args.get("projectId", "777000111")
            screens = [
                {
                    "name": f"projects/{pid}/screens/scr_home_v1",
                    "title": "Robotics Landing — V1",
                    "deviceType": args.get("deviceType", "DESKTOP"),
                    "width": "1440",
                    "height": "1024",
                    "htmlCode": {
                        "name": f"projects/{pid}/files/file_html_v1_main",
                        "mimeType": "text/html",
                    },
                    "screenshot": {
                        "name": f"projects/{pid}/files/file_png_v1_main",
                        "mimeType": "png",
                    },
                }
            ]
            if self.multi_screen:
                screens.append({
                    "name": f"projects/{pid}/screens/scr_specs_v1",
                    "title": "Technical Specs — V1",
                    "deviceType": args.get("deviceType", "DESKTOP"),
                    "width": "1440",
                    "height": "1024",
                    "htmlCode": {
                        "name": f"projects/{pid}/files/file_html_v1_specs",
                        "mimeType": "text/html",
                    },
                })
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "structuredContent": {
                        "outputComponents": [
                            {
                                "designSystem": {
                                    "designSystem": {
                                        "name": "assets/ds_robotics_01",
                                        "displayName": "Precision Cybernetics",
                                    }
                                }
                            },
                            {"design": {"screens": screens}},
                            {"text": "Generated your robotics startup design with Stitch."},
                        ],
                        "projectId": pid,
                        "sessionId": f"stitch_sess_{pid}",
                    }
                },
            }

        if tool == "edit_screens":
            if self.fail_next_edit:
                self.fail_next_edit = False
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32603, "message": "Stitch edit_screens timed out on upstream model"},
                }
            pid = args.get("projectId", "777000111")
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "structuredContent": {
                        "outputComponents": [
                            {
                                "design": {
                                    "screens": [
                                        {
                                            "name": f"projects/{pid}/screens/scr_home_v2",
                                            "title": "Robotics Landing — V2 Revised",
                                            "deviceType": args.get("deviceType", "DESKTOP"),
                                            "width": "1440",
                                            "height": "1200",
                                            "htmlCode": {
                                                "name": f"projects/{pid}/files/file_html_v2_main",
                                                "mimeType": "text/html",
                                            },
                                        }
                                    ]
                                }
                            },
                            {"text": f"Revised screen with: {args.get('prompt', '')}"},
                        ],
                        "projectId": pid,
                        "sessionId": f"stitch_sess_{pid}",
                    }
                },
            }

        if tool == "download_file":
            fname = args.get("name", "")
            if "file_html_v1_main" in fname:
                html = (
                    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
                    "<title>Stitch V1 Robotics</title>"
                    "<style>body { background: #0b0f19; color: #38bdf8; }</style></head>"
                    "<body><header><h1>STITCH-V1-ROBOTICS-HERO</h1></header>"
                    "<script>window.stitchVersion = 1;</script></body></html>"
                )
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"structuredContent": {"html": html}}}
            if "file_html_v1_specs" in fname:
                html = (
                    "<!DOCTYPE html><html><head><title>Stitch V1 Specs</title></head>"
                    "<body><h1>STITCH-V1-SPECS-SCREEN-2</h1></body></html>"
                )
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"structuredContent": {"html": html}}}
            if "file_html_v2_main" in fname:
                html = (
                    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
                    "<title>Stitch V2 Midnight Pricing</title>"
                    "<style>body { background: #020617; color: #34d399; }</style></head>"
                    "<body><header><h1>STITCH-V2-MIDNIGHT-PRICING-TABLE</h1></header>"
                    "<section id='pricing'>Enterprise Tier</section>"
                    "<script>window.stitchVersion = 2;</script></body></html>"
                )
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"structuredContent": {"html": html}}}
            if "file_png_v1_main" in fname:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "structuredContent": {
                            "image": _TINY_PNG_B64,
                            "image_metadata": {"mime_type": "image/png", "width": 1, "height": 1},
                        }
                    },
                }

        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"structuredContent": {}}}


# =============================================================================
# 1–3. Provider Routing, Auth & Secret Redaction, HTML/CSS/JS/Multi-Screen Extraction
# =============================================================================

def test_stitch_adapter_authentication_redaction_and_extraction(tmp_path):
    """
    Verifies X-Goog-Api-Key header transmission, secret redaction, outputComponents
    parsing, HTML download via download_file, CSS/JS extraction, and PNG screenshot saving.
    """
    transport = MockStitchMCPTransport()
    transport.multi_screen = True
    secret_key = "AQ.TestSecretStitchKey_9988776655"
    adapter = StitchAdapter(api_key=secret_key, transport=transport)

    assert adapter.is_configured is True
    assert secret_key not in adapter.masked_key()
    assert secret_key not in adapter._sanitize(f"Failed with key {secret_key} in header")

    bundle = adapter.generate_design(
        prompt="Design a robotics startup website with a technical specs page",
        session_dir=tmp_path / "stitch_session_1",
        title="Apex Robotics",
    )

    # Check MCP tool calls
    called_tools = [r["payload"]["params"]["name"] for r in transport.requests]
    assert called_tools == [
        "create_project",
        "generate_screen_from_text",
        "download_file",  # screen 1 html
        "download_file",  # screen 1 screenshot
        "download_file",  # screen 2 html
    ]
    assert transport.requests[0]["headers"]["X-Goog-Api-Key"] == secret_key

    # Check extracted bundle & files on disk
    assert bundle.provider == "stitch"
    assert bundle.project_id == "777000111"
    assert bundle.version == 1
    assert len(bundle.screens) == 2
    assert bundle.screen_ids == ["scr_home_v1", "scr_specs_v1"]

    v1_dir = Path(bundle.version_dir)
    assert (v1_dir / "index.html").exists()
    assert "STITCH-V1-ROBOTICS-HERO" in (v1_dir / "index.html").read_text(encoding="utf-8")
    assert (v1_dir / "stitch_extracted.css").exists()
    assert "#38bdf8" in (v1_dir / "stitch_extracted.css").read_text(encoding="utf-8")
    assert (v1_dir / "stitch_extracted.js").exists()
    assert "stitchVersion = 1" in (v1_dir / "stitch_extracted.js").read_text(encoding="utf-8")
    assert bundle.screens[0].screenshot_path and Path(bundle.screens[0].screenshot_path).exists()
    assert Path(bundle.screens[1].html_path).exists()
    assert "STITCH-V1-SPECS-SCREEN-2" in Path(bundle.screens[1].html_path).read_text(encoding="utf-8")
    assert (v1_dir / "stitch_manifest.json").exists()


# =============================================================================
# 4–8. End-to-End Orchestrator + Popup Preview + Revisions + Failure Recovery + Approval
# =============================================================================

def test_end_to_end_stitch_popup_preview_revision_failure_recovery_and_approval(view, tmp_path):
    """
    Tests the complete Google Stitch Direct Design-to-Preview workflow:
      1. User describes a website in MIND Chat -> routed to StitchAdapter (CodingAgent/WebsiteWorkflow NEVER called).
      2. Stitch HTML (multi-screen) renders inside DesignPreviewWindow; user switches screens.
      3. User requests a revision in MIND Chat -> sent to Stitch edit_screens; popup updates in-place to v2 while v1 is preserved on disk.
      4. A subsequent failed Stitch revision preserves v2 in the popup and shows the error banner.
      5. Closing and reopening the popup does not approve the design.
      6. Explicit approval marks the Stitch design as DESIGN_APPROVED without starting website code implementation.
    """
    transport = MockStitchMCPTransport()
    transport.multi_screen = True
    stitch_adapter = StitchAdapter(api_key="AQ.MockKey123456789", transport=transport)

    cfg = GameDevConfig.load()
    cfg.test_mode = False
    cfg.require_design_approval = True
    cfg.workspace_root = tmp_path / "workspace"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)

    mem = SessionMemory(db_path=tmp_path / "session.db")
    state = ConversationState(mem)
    orch = GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=mem,
        conversation_state=state,
        stitch_adapter=stitch_adapter,
    )

    # Wire chat prompt_sent directly into GameDevOrchestrator
    def _on_prompt(text: str, _choice: str) -> None:
        res = orch.execute_command(text)
        view.complete_workflow(res)

    view.prompt_sent.connect(_on_prompt)

    # Guard against any internal website code generation during design, revision, or approval
    with patch.object(orch.project_creator, "create_project", side_effect=AssertionError("Internal website generator must NOT run!")) as mock_creator:
        # --- Step 1: User requests website design ---
        r1 = orch.execute_command("Create a website for an autonomous robotics startup")
        assert r1["status"] == "APPROVAL_REQUIRED"
        assert r1["provider"] == "stitch"
        assert r1["version"] == 1
        assert len(r1["screens"]) == 2
        view.complete_workflow(r1)
        _pump(150)

        win = view.design_preview.window
        assert isinstance(win, DesignPreviewWindow)
        assert win.isVisible()
        assert view.design_preview.window_open_count == 1
        assert win.lbl_version.text() == "DESIGN v1"
        assert "STITCH-V1-ROBOTICS-HERO" in win.preview_widget._last_valid_html

        # Multi-screen selector bar is visible and switches screens inside the popup
        assert win.screens_bar.isVisible()
        win.select_screen(1)
        _pump(100)
        assert "STITCH-V1-SPECS-SCREEN-2" in win.preview_widget._last_valid_html
        assert win.record.approval_state == STATE_AWAITING

        v1_index_path = Path(r1["version_dir"]) / "index.html"
        assert v1_index_path.exists()

        # --- Step 2: User requests modification through MIND Chat ---
        r2 = orch.execute_command("Make the hero background midnight blue and add an enterprise pricing table")
        assert r2["status"] == "APPROVAL_REQUIRED"
        assert r2["provider"] == "stitch"
        assert r2["version"] == 2
        view.complete_workflow(r2)
        _pump(150)

        # Same popup window is updated to v2; v1 files are preserved on disk
        assert view.design_preview.window is win
        assert view.design_preview.window_open_count == 1
        assert win.lbl_version.text() == "DESIGN v2"
        assert "STITCH-V2-MIDNIGHT-PRICING-TABLE" in win.preview_widget._last_valid_html
        assert v1_index_path.exists(), "Previous version v1 must be preserved on disk"
        assert "STITCH-V1-ROBOTICS-HERO" in v1_index_path.read_text(encoding="utf-8")

        # Verify edit_screens was called with the Stitch projectId and screen IDs
        edit_calls = [r for r in transport.requests if r["payload"]["params"]["name"] == "edit_screens"]
        assert len(edit_calls) == 1
        assert edit_calls[0]["payload"]["params"]["arguments"]["projectId"] == "777000111"
        assert edit_calls[0]["payload"]["params"]["arguments"]["selectedScreenIds"] == ["scr_home_v1", "scr_specs_v1"]

        # --- Step 3: Failed revision preserves v2 in the popup ---
        transport.fail_next_edit = True
        r_fail = orch.execute_command("Change the font to Comic Sans")
        assert r_fail["status"] == "STITCH_ERROR"
        assert r_fail["version"] == 2
        view.complete_workflow(r_fail)
        _pump(100)

        assert win.lbl_version.text() == "DESIGN v2"
        assert "STITCH-V2-MIDNIGHT-PRICING-TABLE" in win.preview_widget._last_valid_html
        assert "⚠ Revision failed:" in win.lbl_guidance.text()
        assert win.record.approval_state == STATE_AWAITING
        assert orch.conversation_state.pending_design_approval["version"] == 2

        # --- Step 4: Closing and reopening the popup does NOT approve ---
        win.btn_close.click()
        _pump()
        assert not win.isVisible()
        assert orch.conversation_state.pending_design_approval is not None
        assert win.record.approval_state == STATE_AWAITING

        view.reopen_design_preview()
        _pump()
        assert win.isVisible()
        assert win.record.approval_state == STATE_AWAITING

        # --- Step 5: Explicit approval marks Stitch design approved WITHOUT starting code build ---
        win.btn_approve.click()
        _pump(100)

        assert view._sent == ["Approve"]
        assert win.record.approval_state == STATE_APPROVED
        assert orch.conversation_state.pending_design_approval is None
        assert orch.conversation_state.approved_stitch_design is not None
        assert orch.conversation_state.approved_stitch_design["version"] == 2
        assert orch.conversation_state.approved_stitch_design["status"] == "approved"
        assert mock_creator.call_count == 0


# =============================================================================
# 9–10. Prevention of Accidental Internal Website Generation & Session Isolation
# =============================================================================

def test_stitch_unavailable_never_falls_back_to_internal_website_generator(view, tmp_path):
    """
    When Google Stitch is unconfigured or unreachable, MIND must report that Stitch
    is unavailable and must NEVER fabricate HTML or invoke CodingAgent / WebsiteWorkflow.
    """
    unconfigured_stitch = StitchAdapter(api_key="")
    cfg = GameDevConfig.load()
    cfg.test_mode = False
    cfg.require_design_approval = True
    cfg.workspace_root = tmp_path / "ws_unavail"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)

    mem = SessionMemory(db_path=tmp_path / "unavail.db")
    state = ConversationState(mem)
    orch = GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=mem,
        conversation_state=state,
        stitch_adapter=unconfigured_stitch,
    )

    with patch.object(orch.project_creator, "create_project", side_effect=AssertionError("Must not build fallback site!")):
        res = orch.execute_command("Create a website for a boutique bakery")
        assert res["status"] == "STITCH_UNAVAILABLE"
        assert res["provider"] == "stitch"
        assert "STITCH_API_KEY" in res["message"]
        assert orch.conversation_state.pending_design_approval is None

        view.complete_workflow(res)
        _pump()
        # No fake preview popup opened
        assert view.design_preview.window is None
        assert view.design_preview.records == {}


def test_stitch_session_isolation_across_multiple_designs(view, tmp_path):
    """
    Verifies multiple Stitch sessions keep independent records and reuse the single
    popup window without cross-contaminating project/screen state.
    """
    t1 = MockStitchMCPTransport()
    s1 = StitchAdapter(api_key="AQ.Key1", transport=t1)
    b1 = s1.generate_design("Site One", session_dir=tmp_path / "s1", project_id="1001", title="Alpha Site")

    t2 = MockStitchMCPTransport()
    s2 = StitchAdapter(api_key="AQ.Key2", transport=t2)
    b2 = s2.generate_design("Site Two", session_dir=tmp_path / "s2", project_id="2002", title="Beta Site")

    view.complete_workflow({
        "status": "APPROVAL_REQUIRED",
        "stage": "DESIGN_APPROVAL",
        "design_state": "awaiting_design_approval",
        "provider": "stitch",
        "session_id": b1.session_id,
        "version": 1,
        "title": b1.title,
        "preview_file": b1.preview_file,
        "screens": [s.to_dict() for s in b1.screens],
    })
    view.complete_workflow({
        "status": "APPROVAL_REQUIRED",
        "stage": "DESIGN_APPROVAL",
        "design_state": "awaiting_design_approval",
        "provider": "stitch",
        "session_id": b2.session_id,
        "version": 1,
        "title": b2.title,
        "preview_file": b2.preview_file,
        "screens": [s.to_dict() for s in b2.screens],
    })
    _pump()

    mgr = view.design_preview
    assert mgr.window_open_count == 1
    assert set(mgr.records.keys()) == {"stitch_sess_1001", "stitch_sess_2002"}
    assert mgr.window.record.session_key == "stitch_sess_2002"

    # Reopen older session 1001: cannot approve superseded session
    view.reopen_design_preview("stitch_sess_1001")
    _pump()
    mgr.window.btn_approve.click()
    assert view._sent == []
    assert not mgr.window.btn_approve.isEnabled()


# =============================================================================
# 11. Live Google Stitch MCP Verification Check (Distinguished from Mocked Tests)
# =============================================================================

@pytest.mark.skipif(
    not os.getenv("STITCH_API_KEY") or os.getenv("STITCH_API_KEY", "").startswith("your_"),
    reason="Live Google Stitch API key not configured in environment.",
)
def test_live_google_stitch_mcp_connection_and_html_retrieval(view, tmp_path):
    """
    LIVE API VERIFICATION:
    Connects to the real Google Stitch MCP endpoint (`https://stitch.googleapis.com/mcp`)
    using the configured STITCH_API_KEY, lists projects/screens, downloads actual
    Stitch-generated HTML via `download_file`, and renders it inside `DesignPreviewWindow`.
    """
    live_adapter = StitchAdapter()
    assert live_adapter.is_configured is True

    try:
        projects = live_adapter.list_projects()
    except StitchUnavailableError as exc:
        pytest.skip(f"Live Google Stitch service unavailable: {exc}")
    assert isinstance(projects, list) and len(projects) > 0

    # Find a project with generated screens or generate one
    target_pid = None
    target_screens = []
    for p in projects[:5]:
        pid = live_adapter.normalize_project_id(p.get("name", ""))
        if not pid:
            continue
        scrs = live_adapter.list_screens(pid)
        if scrs:
            target_pid = pid
            target_screens = scrs
            break

    if target_pid is None or len(target_screens) == 0:
        pytest.skip("No pre-existing screens in live Stitch account to download; live connection verified via list_projects.")

    version_dir = tmp_path / "live_stitch_v1"
    artifacts = live_adapter._materialize_screens(target_pid, target_screens[:1], version_dir)
    assert len(artifacts) == 1
    art = artifacts[0]
    assert Path(art.html_path).exists()
    assert art.html_size_bytes > 5000  # Real Stitch HTML is ~50KB+

    html_content = Path(art.html_path).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_content or "<html" in html_content

    # Render live Stitch artifact inside MIND's dedicated DesignPreviewWindow
    view.complete_workflow({
        "status": "APPROVAL_REQUIRED",
        "stage": "DESIGN_APPROVAL",
        "design_state": "awaiting_design_approval",
        "provider": "stitch",
        "session_id": f"live_stitch_{target_pid}",
        "version": 1,
        "title": art.title,
        "preview_file": art.html_path,
        "screens": [art.to_dict()],
    })
    _pump(200)

    win = view.design_preview.window
    assert win is not None and win.isVisible()
    assert len(win.preview_widget._last_valid_html) > 5000
    assert win.record.provider == "stitch"
    assert win.record.approval_state == STATE_AWAITING
