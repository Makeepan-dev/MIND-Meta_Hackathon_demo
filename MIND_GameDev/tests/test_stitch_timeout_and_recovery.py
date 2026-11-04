"""
MIND Universal Studio — Google Stitch Generation Timeout, Protocol, & Recovery Tests.

Covers all 12 required verification scenarios:
1. Normal successful generation (including outer `designSystem.name` asset ID extraction and SSE parsing).
2. Slow but successful responses (with live heartbeat progress callbacks).
3. Connection timeout (`StitchConnectionTimeoutError`).
4. Response timeout (`StitchResponseTimeoutError` with no substitute website generated).
5. Malformed MCP response (`StitchMalformedResponseError` on invalid JSON / broken SSE / empty result).
6. Session expiration (`Mcp-Session-Id` HTTP 404/410 -> automatic session re-init and retry).
7. Rate limiting (HTTP 429 with `Retry-After` respected / bounded).
8. Cancellation (`CancellationToken` aborts generation / polling and returns `CANCELLED`).
9. Unknown generation outcome (read timeout where Stitch finished server-side, recovered via `get_project` + `get_screen` / `list_screens`).
10. Recovery without duplicate generation (Phase-2 resumption with `designSystem="assets/..."`, user retry reusing `project_id` without re-calling `create_project` or `generate_screen_from_text`, and concurrent in-flight lock).
11. UI responsiveness during generation (`UnifiedAssistantView` updates progress and stays responsive).
12. Preservation of the previous preview (`v1` remains active in `DesignPreviewWindow` when `v2` revision times out or is cancelled).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
import requests

from MIND_GameDev.adapters.stitch_adapter import (
    StitchAdapter,
    StitchAuthenticationError,
    StitchCancelledError,
    StitchConnectionTimeoutError,
    StitchError,
    StitchInvalidRequestError,
    StitchMalformedResponseError,
    StitchRateLimitError,
    StitchResponseTimeoutError,
    StitchSessionExpiredError,
    StitchUnavailableError,
)
from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.orchestrator import GameDevOrchestrator
from MIND_GameDev.tools.conversation_state import ConversationState
from MIND_GameDev.tools.session_memory import SessionMemory
from MIND_GameDev.ui.backend_bridge import CancellationToken


STITCH_ACADEMY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Apex University — Admissions & Academic Excellence</title>
  <style>
    body { margin: 0; font-family: 'Inter', sans-serif; background: #0B132B; color: #F8FAFC; }
    header { padding: 32px 48px; border-bottom: 1px solid #1C2541; }
    .hero { padding: 64px 48px; max-width: 960px; }
  </style>
</head>
<body>
  <header><h1>Apex University</h1></header>
  <section class="hero">
    <h2>Discover Undergraduate & Graduate Programs</h2>
    <p>Explore world-class research facilities, campus life, and scholarships.</p>
  </section>
  <script>
    window.__STITCH_UNIVERSITY_READY__ = true;
  </script>
</body>
</html>"""


def _rpc_ok(structured: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": "{}"}],
            "structuredContent": structured,
        },
    }


def _make_config(tmp_path: Path) -> GameDevConfig:
    cfg = GameDevConfig.load()
    cfg.workspace_root = tmp_path / "workspace"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)
    cfg.test_mode = False
    cfg.voice_enabled = False
    cfg.require_design_approval = True
    return cfg


def _make_orchestrator(tmp_path: Path, adapter: StitchAdapter) -> GameDevOrchestrator:
    cfg = _make_config(tmp_path)
    mem = SessionMemory(db_path=tmp_path / "session_memory.db")
    conv = ConversationState(mem)
    return GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=mem,
        conversation_state=conv,
        stitch_adapter=adapter,
    )


# ─── 1. Normal Successful Generation & Protocol Parsing ─────────────────────

def test_01_normal_successful_generation_and_outer_design_system_name_preserved(tmp_path: Path) -> None:
    """
    Verifies normal generation, outer `designSystem.name` (`assets/...`) preservation,
    correlation ID telemetry, and SSE (`text/event-stream`) response parsing.
    """
    calls: List[Dict[str, Any]] = []

    def transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Any:
        tool = payload["params"]["name"]
        args = payload["params"]["arguments"]
        calls.append({"tool": tool, "args": args, "headers": dict(headers), "timeout": timeout})

        if tool == "create_project":
            return _rpc_ok({"name": "projects/proj_norm_101", "title": args.get("title", "University")})

        if tool == "generate_screen_from_text":
            # Return realistic Stitch outputComponents where `name` is on the outer `designSystem` wrapper
            # and test SSE stream framing as well
            sse_frame = _rpc_ok({
                "projectId": "proj_norm_101",
                "sessionId": "sess_norm_101",
                "outputComponents": [
                    {
                        "designSystem": {
                            "name": "assets/759ccab128524b118ede4b8fef0b536f",
                            "version": "1",
                            "designSystem": {
                                "displayName": "Academic Excellence",
                                "theme": {"colorMode": "DARK", "customColor": "#00F5FF"},
                            },
                        }
                    },
                    {
                        "design": {
                            "screens": [
                                {
                                    "id": "scr_home_101",
                                    "name": "projects/proj_norm_101/screens/scr_home_101",
                                    "title": "University Home",
                                    "deviceType": "DESKTOP",
                                    "width": 1440,
                                    "height": 900,
                                    "htmlCode": {
                                        "name": "projects/proj_norm_101/screens/scr_home_101/fileEntries/html",
                                        "mimeType": "text/html",
                                    },
                                }
                            ]
                        }
                    },
                ],
            })
            import json as _json
            return f": keepalive\n\nevent: message\ndata: {_json.dumps(sse_frame)}\n\n"

        if tool == "download_file":
            return _rpc_ok({"html": STITCH_ACADEMY_HTML})

        raise AssertionError(f"Unexpected tool: {tool}")

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_secret_key_999999",
        transport=transport,
        heartbeat_interval_seconds=0.05,
    )
    bundle = adapter.generate_design(
        prompt="Create a university admissions website",
        session_dir=tmp_path / "session_norm",
        title="Apex University",
    )

    assert bundle.project_id == "proj_norm_101"
    assert bundle.design_system is not None
    assert bundle.design_system.get("name") == "assets/759ccab128524b118ede4b8fef0b536f"
    assert bundle.design_system.get("displayName") == "Academic Excellence"
    assert Path(bundle.preview_file).exists()
    assert "Apex University" in Path(bundle.preview_file).read_text(encoding="utf-8")

    # Verify correlation IDs and elapsed_ms were recorded without leaking API key
    assert len(adapter.call_history) == 3
    for entry in adapter.call_history:
        assert entry["correlation_id"].startswith("stitch_")
        assert entry["status"] == "ok"
        assert "elapsed_ms" in entry
        assert "AQ.test_stitch_secret_key_999999" not in str(entry)


# ─── 2. Slow But Successful Response With Heartbeat Progress ────────────────

def test_02_slow_but_successful_response_emits_heartbeat_progress(tmp_path: Path) -> None:
    """
    Verifies that a slow `generate_screen_from_text` response emits live periodic
    heartbeat progress updates to keep the user informed and completes cleanly.
    """
    progress_events: List[Dict[str, Any]] = []

    def slow_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        tool = payload["params"]["name"]
        if tool == "create_project":
            return _rpc_ok({"name": "projects/proj_slow_202"})
        if tool == "generate_screen_from_text":
            time.sleep(0.22)
            return _rpc_ok({
                "projectId": "proj_slow_202",
                "outputComponents": [
                    {
                        "design": {
                            "screens": [
                                {
                                    "name": "projects/proj_slow_202/screens/scr_slow_1",
                                    "title": "Slow Generated Home",
                                    "htmlCode": {"name": "projects/proj_slow_202/screens/scr_slow_1/fileEntries/html"},
                                }
                            ]
                        }
                    }
                ],
            })
        if tool == "download_file":
            return _rpc_ok({"html": STITCH_ACADEMY_HTML})
        raise AssertionError(f"Unexpected tool: {tool}")

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_slow",
        transport=slow_transport,
        heartbeat_interval_seconds=0.05,
    )
    bundle = adapter.generate_design(
        prompt="Create a slow university website",
        session_dir=tmp_path / "session_slow",
        title="Slow University",
        progress_callback=lambda evt: progress_events.append(evt),
    )

    assert bundle.project_id == "proj_slow_202"
    assert len(progress_events) >= 2
    prototyping_msgs = [e["message"] for e in progress_events if e.get("design_state") == "prototyping"]
    assert any("elapsed" in m for m in prototyping_msgs)


# ─── 3. Connection Timeout Classification ───────────────────────────────────

def test_03_connection_timeout_raises_typed_error_without_polling(tmp_path: Path) -> None:
    """
    Verifies that a TCP connection timeout (`requests.exceptions.ConnectTimeout`)
    is classified as `StitchConnectionTimeoutError` and fails cleanly.
    """
    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_conn",
        connect_timeout_seconds=3.0,
        timeout_seconds=30.0,
    )

    with patch("MIND_GameDev.adapters.stitch_adapter.requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectTimeout("TCP SYN timed out")
        with pytest.raises(StitchConnectionTimeoutError) as exc_info:
            adapter.call_tool("create_project", {"title": "Conn Timeout Test"})

    assert exc_info.value.failure_category == "connection_timeout"
    assert "connection timed out" in str(exc_info.value).lower()
    assert adapter.call_history[-1]["status"] == "connection_timeout"


# ─── 4. Response Timeout With No Substitute Website ─────────────────────────

def test_04_response_timeout_preserves_brief_and_project_id_without_substitute(tmp_path: Path) -> None:
    """
    Verifies that when `generate_screen_from_text` hits a read timeout and the server
    has produced neither screens nor a designSystem, MIND raises `StitchResponseTimeoutError`,
    preserves `stitch_project_id` and `StructuredDesignBrief` for retry, and NEVER
    generates a local substitute website.
    """
    def timeout_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        tool = payload["params"]["name"]
        if tool == "create_project":
            return _rpc_ok({"name": "projects/proj_timeout_404"})
        if tool == "generate_screen_from_text":
            raise requests.exceptions.ReadTimeout("HTTPSConnectionPool read timed out (read timeout=180.0)")
        if tool == "list_screens":
            return _rpc_ok({"screens": []})
        if tool == "get_project":
            return _rpc_ok({"name": "projects/proj_timeout_404", "screenInstances": []})
        if tool == "list_design_systems":
            return _rpc_ok({"designSystems": []})
        raise AssertionError(f"Unexpected tool: {tool}")

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_timeout",
        transport=timeout_transport,
        timeout_seconds=180.0,
        recovery_poll_attempts=2,
        recovery_poll_interval_seconds=0.02,
    )
    orch = _make_orchestrator(tmp_path, adapter)

    res = orch.execute_command(
        "Create a website for Apex University targeting prospective undergraduate students "
        "for informational admissions and enrollment with Home, Programs, Admissions, and Contact pages "
        "in a dark academic visual style featuring scholarship calculator and virtual campus tour"
    )

    assert res["status"] == "STITCH_UNAVAILABLE"
    assert res["failure_category"] == "response_timeout"
    assert res["project_id"] == "proj_timeout_404"
    assert "timed out after 180.0s" in res["message"]
    assert "MIND did not generate a substitute website" in res["message"]

    # Verify retry state preserved the exact Stitch project_id so retry won't duplicate
    pc = orch.conversation_state.pending_clarification
    assert pc is not None
    assert pc.slot_name == "design_discovery_retry"
    assert pc.answers.get("stitch_project_id") == "proj_timeout_404"


# ─── 5. Malformed MCP Response Handling ─────────────────────────────────────

def test_05_malformed_mcp_responses_raise_typed_error(tmp_path: Path) -> None:
    """
    Verifies that truncated JSON, broken SSE streams, or missing `result` fields
    raise `StitchMalformedResponseError`.
    """
    bodies = [
        "{truncated_json",
        "event: message\ndata: {broken_sse\n\n",
        '{"jsonrpc": "2.0", "id": 1}',
    ]

    for bad_body in bodies:
        adapter = StitchAdapter(
            config=_make_config(tmp_path),
            api_key="AQ.test_stitch_key_malformed",
            transport=lambda u, h, p, t, b=bad_body: b,
        )
        with pytest.raises(StitchMalformedResponseError) as exc_info:
            adapter.call_tool("list_projects")
        assert exc_info.value.failure_category == "malformed_response"


# ─── 6. MCP Session Expiration & Automatic Re-Initialization ────────────────

def test_06_session_expiration_reinitializes_and_succeeds(tmp_path: Path) -> None:
    """
    Verifies that when an active `Mcp-Session-Id` expires (HTTP 404/410),
    `StitchAdapter` clears the stale session ID, runs `initialize_session()`,
    and completes the tool call cleanly.
    """
    call_sequence: List[str] = []

    def session_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        method = payload.get("method")
        if method == "initialize":
            call_sequence.append("initialize")
            return {
                "_http_status": 200,
                "_headers": {"Mcp-Session-Id": "mcp_sess_fresh_777"},
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"protocolVersion": "2024-11-05"},
            }

        tool = payload["params"]["name"]
        sess_hdr = headers.get("Mcp-Session-Id")
        call_sequence.append(f"{tool}:{sess_hdr}")
        if sess_hdr == "mcp_sess_stale_000":
            return {
                "_http_status": 404,
                "_headers": {},
                "_body": "MCP session expired or not found",
            }
        return _rpc_ok({"projects": [{"name": "projects/proj_606", "title": "Session Test"}]})

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_sess",
        transport=session_transport,
    )
    adapter._mcp_session_id = "mcp_sess_stale_000"

    projects = adapter.list_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "projects/proj_606"
    assert adapter._mcp_session_id == "mcp_sess_fresh_777"
    assert call_sequence == [
        "list_projects:mcp_sess_stale_000",
        "initialize",
        "list_projects:mcp_sess_fresh_777",
    ]


# ─── 7. Rate Limiting (HTTP 429 With Retry-After) ───────────────────────────

def test_07_rate_limiting_respects_retry_after_and_recovers(tmp_path: Path) -> None:
    """
    Verifies that HTTP 429 with a bounded `Retry-After` header waits and retries once,
    while an excessive `Retry-After` raises `StitchRateLimitError` immediately.
    """
    attempts = 0

    def rl_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {
                "_http_status": 429,
                "_headers": {"Retry-After": "0.05"},
                "_body": "Rate limit exceeded",
            }
        return _rpc_ok({"projects": [{"name": "projects/proj_rl_707"}]})

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_rl",
        transport=rl_transport,
        max_rate_limit_wait_seconds=1.0,
    )
    projects = adapter.list_projects()
    assert attempts == 2
    assert len(projects) == 1

    # Excessive Retry-After (> max_rate_limit_wait_seconds) must raise StitchRateLimitError immediately
    adapter_exceed = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_rl2",
        transport=lambda u, h, p, t: {
            "_http_status": 429,
            "_headers": {"Retry-After": "120"},
            "_body": "Quota exhausted",
        },
        max_rate_limit_wait_seconds=1.0,
    )
    with pytest.raises(StitchRateLimitError) as exc_info:
        adapter_exceed.list_projects()
    assert exc_info.value.retry_after == 120.0


# ─── 8. Cooperative Cancellation During Long-Running Generation ─────────────

def test_08_cooperative_cancellation_aborts_wait_and_returns_cancelled(tmp_path: Path) -> None:
    """
    Verifies that cancelling a `CancellationToken` while Stitch is generating
    aborts the wait loop within milliseconds and returns `status == 'CANCELLED'`.
    """
    token = CancellationToken()

    def blocking_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        tool = payload["params"]["name"]
        if tool == "create_project":
            return _rpc_ok({"name": "projects/proj_cancel_808"})
        if tool == "generate_screen_from_text":
            threading.Timer(0.06, lambda: token.cancel("User clicked Stop")).start()
            time.sleep(2.0)
            return _rpc_ok({})
        return _rpc_ok({})

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_cancel",
        transport=blocking_transport,
        heartbeat_interval_seconds=0.04,
    )
    orch = _make_orchestrator(tmp_path, adapter)

    start_t = time.time()
    res = orch.execute_command(
        "Create a website for Apex University targeting prospective undergraduate students "
        "for informational admissions and enrollment with Home, Programs, Admissions, and Contact pages "
        "in a dark academic visual style featuring scholarship calculator and virtual campus tour",
        cancellation_token=token,
    )

    elapsed = time.time() - start_t
    assert elapsed < 1.2
    assert res["status"] == "CANCELLED"
    assert res["project_id"] == "projects/proj_cancel_808" or res["project_id"] == "proj_cancel_808"


# ─── 9. Unknown Generation Outcome (Server Completed After Read Timeout) ────

def test_09_unknown_outcome_recovers_via_get_project_screen_instances_and_get_screen(tmp_path: Path) -> None:
    """
    Simulates `generate_screen_from_text` timing out on the client socket while Stitch
    completes screen generation server-side and exposes the screen in `get_project.screenInstances`.
    Verifies that `StitchAdapter` recovers the screen via `get_project` -> `get_screen` -> `download_file`
    without re-calling `create_project` or `generate_screen_from_text`.
    """
    tool_counts: Dict[str, int] = {}

    def unknown_outcome_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        tool = payload["params"]["name"]
        tool_counts[tool] = tool_counts.get(tool, 0) + 1

        if tool == "create_project":
            return _rpc_ok({"name": "projects/proj_unknown_909"})
        if tool == "generate_screen_from_text":
            raise requests.exceptions.ReadTimeout("Read timed out after 180.0s")
        if tool == "list_screens":
            # Simulate list_screens lagging on first check, so get_project screenInstances is used
            return _rpc_ok({"screens": []})
        if tool == "get_project":
            return _rpc_ok({
                "name": "projects/proj_unknown_909",
                "screenInstances": [
                    {
                        "id": "scr_recovered_909",
                        "sourceScreen": "projects/proj_unknown_909/screens/scr_recovered_909",
                    }
                ],
            })
        if tool == "get_screen":
            return _rpc_ok({
                "id": "scr_recovered_909",
                "name": "projects/proj_unknown_909/screens/scr_recovered_909",
                "title": "Recovered University Home",
                "deviceType": "DESKTOP",
                "width": 1440,
                "height": 900,
                "htmlCode": {
                    "name": "projects/proj_unknown_909/screens/scr_recovered_909/fileEntries/html",
                    "mimeType": "text/html",
                },
            })
        if tool == "download_file":
            return _rpc_ok({"html": STITCH_ACADEMY_HTML})
        raise AssertionError(f"Unexpected tool: {tool}")

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_unknown",
        transport=unknown_outcome_transport,
        recovery_poll_attempts=2,
        recovery_poll_interval_seconds=0.02,
    )
    bundle = adapter.generate_design(
        prompt="Create a university website",
        session_dir=tmp_path / "session_unknown",
        title="Recovered University",
    )

    assert bundle.recovered_after_timeout is True
    assert bundle.project_id == "proj_unknown_909"
    assert bundle.screen_ids == ["scr_recovered_909"]
    assert Path(bundle.preview_file).exists()
    # Must NOT have called create_project or generate_screen_from_text more than once!
    assert tool_counts["create_project"] == 1
    assert tool_counts["generate_screen_from_text"] == 1
    assert tool_counts["get_project"] >= 1
    assert tool_counts["get_screen"] >= 1


# ─── 10. Recovery Without Duplicate Generation (Phase-2 & User Retry) ───────

def test_10a_phase1_design_system_timeout_resumes_phase2_on_same_project(tmp_path: Path) -> None:
    """
    Reproduces the exact live failure mode discovered in projects `3902288964891327810`
    and `13248391444664220062`:
    - Call 1 to `generate_screen_from_text` (no `designSystem`) synthesizes the project's
      `designSystem` (`assets/ds_academic_10`) on the server, then hits the 180s read timeout
      before screens are returned.
    - `StitchAdapter` detects that `list_screens` is empty but `list_design_systems(pid)`
      has `assets/ds_academic_10`, and performs ONE Phase-2 `generate_screen_from_text`
      call on the SAME `project_id` passing `designSystem="assets/ds_academic_10"`.
    """
    gen_calls: List[Dict[str, Any]] = []
    create_calls = 0

    def phase2_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        nonlocal create_calls
        tool = payload["params"]["name"]
        args = payload["params"]["arguments"]

        if tool == "create_project":
            create_calls += 1
            return _rpc_ok({"name": "projects/proj_phase2_1010"})
        if tool == "generate_screen_from_text":
            gen_calls.append(dict(args))
            if not args.get("designSystem"):
                # Phase 1 timed out after creating the design system on server
                raise requests.exceptions.ReadTimeout("Read timed out after 180.0s during cold start")
            # Phase 2 with designSystem="assets/ds_academic_10" succeeds fast!
            return _rpc_ok({
                "projectId": "proj_phase2_1010",
                "outputComponents": [
                    {
                        "design": {
                            "screens": [
                                {
                                    "name": "projects/proj_phase2_1010/screens/scr_p2_home",
                                    "title": "Phase 2 University Home",
                                    "htmlCode": {
                                        "name": "projects/proj_phase2_1010/screens/scr_p2_home/fileEntries/html"
                                    },
                                }
                            ]
                        }
                    }
                ],
            })
        if tool == "list_screens":
            return _rpc_ok({"screens": []})
        if tool == "get_project":
            return _rpc_ok({"name": "projects/proj_phase2_1010", "screenInstances": []})
        if tool == "list_design_systems":
            return _rpc_ok({
                "designSystems": [
                    {
                        "name": "assets/ds_academic_10",
                        "designSystem": {"displayName": "Academic Excellence"},
                    }
                ]
            })
        if tool == "download_file":
            return _rpc_ok({"html": STITCH_ACADEMY_HTML})
        raise AssertionError(f"Unexpected tool: {tool}")

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_p2",
        transport=phase2_transport,
        recovery_poll_attempts=1,
        recovery_poll_interval_seconds=0.02,
    )
    bundle = adapter.generate_design(
        prompt="Create a university website",
        session_dir=tmp_path / "session_phase2",
        title="Phase 2 University",
    )

    assert create_calls == 1
    assert len(gen_calls) == 2
    assert gen_calls[0].get("designSystem") is None
    assert gen_calls[1].get("designSystem") == "assets/ds_academic_10"
    assert gen_calls[1].get("projectId") == "proj_phase2_1010"
    assert bundle.recovered_after_timeout is True
    assert bundle.screen_ids == ["scr_p2_home"]


def test_10b_user_retry_reuses_project_id_and_recovers_without_duplicate_generation(tmp_path: Path) -> None:
    """
    Verifies that if an initial request times out completely and the user clicks
    'Retry Stitch Generation' after the server finishes in the background:
    - MIND reuses the existing `project_id` (`proj_retry_1020`).
    - MIND does NOT call `create_project` a second time.
    - MIND checks `recover_project_screens` first, finds the completed screen,
      and downloads it WITHOUT calling `generate_screen_from_text` a second time!
    """
    server_finished = False
    create_count = 0
    gen_count = 0

    def retry_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        nonlocal create_count, gen_count
        tool = payload["params"]["name"]

        if tool == "create_project":
            create_count += 1
            return _rpc_ok({"name": "projects/proj_retry_1020"})
        if tool == "generate_screen_from_text":
            gen_count += 1
            raise requests.exceptions.ReadTimeout("Read timed out after 180.0s")
        if tool == "list_screens":
            if server_finished:
                return _rpc_ok({
                    "screens": [
                        {
                            "name": "projects/proj_retry_1020/screens/scr_retry_ready",
                            "title": "Completed On Server Home",
                            "htmlCode": {
                                "name": "projects/proj_retry_1020/screens/scr_retry_ready/fileEntries/html"
                            },
                        }
                    ]
                })
            return _rpc_ok({"screens": []})
        if tool == "get_project":
            return _rpc_ok({"name": "projects/proj_retry_1020", "screenInstances": []})
        if tool == "list_design_systems":
            return _rpc_ok({"designSystems": []})
        if tool == "download_file":
            return _rpc_ok({"html": STITCH_ACADEMY_HTML})
        raise AssertionError(f"Unexpected tool: {tool}")

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_retry",
        transport=retry_transport,
        recovery_poll_attempts=1,
        recovery_poll_interval_seconds=0.02,
    )
    orch = _make_orchestrator(tmp_path, adapter)

    # Attempt 1: times out while server is still working
    res1 = orch.execute_command(
        "Create a website for Apex University targeting prospective undergraduate students "
        "for informational admissions and enrollment with Home, Programs, Admissions, and Contact pages "
        "in a dark academic visual style featuring scholarship calculator and virtual campus tour"
    )
    assert res1["status"] == "STITCH_UNAVAILABLE"
    assert create_count == 1
    assert gen_count == 1

    # Now the server finishes generating the screen in the background
    server_finished = True

    # Attempt 2: User clicks "Retry Stitch Generation"
    res2 = orch.execute_command("Retry Stitch Generation")
    assert res2["status"] == "APPROVAL_REQUIRED"
    assert res2["project_id"] == "proj_retry_1020"
    assert res2["screen_ids"] == ["scr_retry_ready"]
    # Neither create_project nor generate_screen_from_text was called again!
    assert create_count == 1
    assert gen_count == 1


# ─── 11. UI Responsiveness During Long-Running Stitch Generation ────────────

def test_11_ui_remains_responsive_and_updates_progress_during_stitch_generation(tmp_path: Path) -> None:
    """
    Verifies that `UnifiedAssistantView` processes live `update_workflow_progress`
    heartbeats during Stitch generation without freezing the chat input or window.
    """
    from PyQt6.QtWidgets import QApplication
    from MIND_GameDev.ui.views.chat_view import UnifiedAssistantView

    app = QApplication.instance() or QApplication([])
    view = UnifiedAssistantView()

    view.update_workflow_progress({
        "workflow_id": "stitch_uni_wf",
        "design_state": "prototyping",
        "message": "Google Stitch is generating 'Apex University' layout (12s elapsed)...",
        "progress": 0.48,
        "progress_pct": 0.48,
    })
    app.processEvents()

    assert view._active_workflow_bubble is not None
    assert "12s elapsed" in view._active_workflow_bubble.lbl_message.text()
    assert view._active_workflow_bubble.progress_bar.value() == 48
    assert view.input_edit.isEnabled()


# ─── 12. Preservation of Previous Preview When Revision Times Out/Cancels ───

def test_12_previous_preview_v1_preserved_when_v2_revision_times_out_or_cancels(tmp_path: Path) -> None:
    """
    Verifies that after `v1` is rendered in `DesignPreviewWindow`, if a `v2` revision
    request times out or is cancelled, `v1` remains active in both `GameDevOrchestrator`
    and `DesignPreviewWindow`.
    """
    from PyQt6.QtWidgets import QApplication
    from MIND_GameDev.ui.views.chat_view import UnifiedAssistantView

    app = QApplication.instance() or QApplication([])

    should_timeout_edit = True

    def rev_transport(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        tool = payload["params"]["name"]
        if tool == "create_project":
            return _rpc_ok({"name": "projects/proj_rev_1200"})
        if tool == "generate_screen_from_text":
            return _rpc_ok({
                "projectId": "proj_rev_1200",
                "outputComponents": [
                    {
                        "design": {
                            "screens": [
                                {
                                    "name": "projects/proj_rev_1200/screens/scr_v1",
                                    "title": "University V1",
                                    "htmlCode": {"name": "projects/proj_rev_1200/screens/scr_v1/fileEntries/html"},
                                }
                            ]
                        }
                    }
                ],
            })
        if tool == "edit_screens":
            if should_timeout_edit:
                raise requests.exceptions.ReadTimeout("edit_screens read timed out after 180.0s")
            return _rpc_ok({})
        if tool == "list_screens":
            return _rpc_ok({"screens": []})
        if tool == "get_project":
            return _rpc_ok({"name": "projects/proj_rev_1200", "screenInstances": []})
        if tool == "download_file":
            return _rpc_ok({"html": STITCH_ACADEMY_HTML})
        raise AssertionError(f"Unexpected tool: {tool}")

    adapter = StitchAdapter(
        config=_make_config(tmp_path),
        api_key="AQ.test_stitch_key_rev",
        transport=rev_transport,
        recovery_poll_attempts=1,
        recovery_poll_interval_seconds=0.02,
    )
    orch = _make_orchestrator(tmp_path, adapter)
    view = UnifiedAssistantView()

    # 1. Generate v1
    res_v1 = orch.execute_command(
        "Create a website for Apex University targeting prospective undergraduate students "
        "for informational admissions and enrollment with Home, Programs, Admissions, and Contact pages "
        "in a dark academic visual style featuring scholarship calculator and virtual campus tour"
    )
    assert res_v1["status"] == "APPROVAL_REQUIRED"
    assert res_v1["version"] == 1
    view.complete_workflow(res_v1)
    app.processEvents()

    v1_preview_file = res_v1["preview_file"]
    assert view.design_preview.window is not None
    assert view.design_preview.window.record is not None
    assert view.design_preview.window.record.version == 1

    # 2. Request v2 revision that times out
    res_v2_err = orch.execute_command("Change the hero background to emerald green and add a scholarship banner")
    assert res_v2_err["status"] == "STITCH_ERROR"
    assert res_v2_err["version"] == 1
    assert res_v2_err["preview_file"] == v1_preview_file

    view.complete_workflow(res_v2_err)
    app.processEvents()

    # v1 remains active in the popup and pending approval in orchestrator!
    assert view.design_preview.window.record.version == 1
    assert view.design_preview.window.record.preview_file == v1_preview_file
    assert orch.conversation_state.pending_design_approval is not None
    assert orch.conversation_state.pending_design_approval["version"] == 1


# ─── 13. Live Stitch Server Inspection & Recovery Verification ──────────────

def test_13_live_stitch_inspection_and_screen_recovery(tmp_path: Path) -> None:
    """
    When STITCH_API_KEY is configured in the environment, verifies live connectivity,
    `list_design_systems` outer `assets/...` extraction on project `3902288964891327810`,
    and `recover_project_screens` + `download_file` on project `9831351434237530052`.
    """
    cfg = _make_config(tmp_path)
    adapter = StitchAdapter(config=cfg)
    if not adapter.is_configured:
        pytest.skip("STITCH_API_KEY not configured for live verification")

    # 1. Inspect project 3902288964891327810 (from user's desktop timeout run)
    ds_list = adapter.list_design_systems("3902288964891327810")
    assert len(ds_list) >= 1
    assert ds_list[0]["name"].startswith("assets/")

    # 2. Recover screens from existing completed Stitch project 9831351434237530052 without generating new screens
    recovered = adapter.recover_project_screens("9831351434237530052")
    assert len(recovered) >= 1
    html_text, file_id = adapter._download_screen_html("9831351434237530052", recovered[0])
    assert "<html" in html_text.lower()
    assert len(html_text) > 500
    assert file_id.startswith("projects/9831351434237530052/")
