"""
MIND Universal Studio — Google Stitch Direct Design-to-Preview Adapter.

Communicates with the official Google Stitch MCP service (`https://stitch.googleapis.com/mcp`)
using JSON-RPC 2.0 `tools/call` requests authenticated via `X-Goog-Api-Key`.

Responsibilities:
1. Create or reuse a Stitch project container (`create_project`, `list_projects`, `get_project`).
2. Generate website UI designs from natural-language prompts (`generate_screen_from_text`).
3. Parse Stitch's nested `outputComponents` (`design.screens`, `designSystem`, `suggestion`, `text`),
   preserving the outer `designSystem.name` (`assets/...`) asset identifier for follow-up calls.
4. Handle long-running generation lifecycles with:
   - Separate TCP connect timeout and MCP response read timeout.
   - Correlation IDs and structured request lifecycle telemetry (without exposing secrets).
   - Streamable HTTP MCP support (`application/json` and `text/event-stream` SSE payloads).
   - MCP session tracking (`Mcp-Session-Id`) and automatic session re-initialization on expiration.
   - Cooperative cancellation (`CancellationToken`) and live heartbeat progress callbacks.
   - Unknown-outcome server-side recovery (`get_project` `screenInstances`, `get_screen`,
     `list_screens`, `list_design_systems`) without duplicate project/screen generation.
5. Retrieve the actual Stitch-generated HTML, CSS, JavaScript, and optional screenshot assets
   using Stitch's `download_file` tool.
6. Apply user-requested design revisions via `edit_screens` and retrieve the updated screens.
7. Persist versioned design artifacts (`v1`, `v2`, ...) inside the session preview directory
   without ever fabricating HTML or exposing `STITCH_API_KEY`.
"""

from __future__ import annotations

import base64
import concurrent.futures
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import requests

from ..config import GameDevConfig, redact_secret

logger = logging.getLogger("mind.gamedev.stitch_adapter")


class StitchError(RuntimeError):
    """Base exception for Google Stitch integration errors."""

    def __init__(
        self,
        message: str,
        *,
        failure_category: str = "stitch_error",
        project_id: Optional[str] = None,
        design_system: Optional[str] = None,
        correlation_id: Optional[str] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.failure_category = failure_category
        self.project_id = project_id
        self.design_system = design_system
        self.correlation_id = correlation_id
        self.retryable = retryable


class StitchUnavailableError(StitchError):
    """Raised when Google Stitch is unconfigured, unreachable, or returns no design output."""

    def __init__(
        self,
        message: str,
        *,
        failure_category: str = "unavailable",
        project_id: Optional[str] = None,
        design_system: Optional[str] = None,
        correlation_id: Optional[str] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            failure_category=failure_category,
            project_id=project_id,
            design_system=design_system,
            correlation_id=correlation_id,
            retryable=retryable,
        )


class StitchAuthenticationError(StitchUnavailableError):
    """Raised on HTTP 401/403 authentication or authorization failure (non-retryable)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_category", "authentication")
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class StitchInvalidRequestError(StitchUnavailableError):
    """Raised on HTTP 400 or JSON-RPC invalid request/params error (non-retryable)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_category", "invalid_request")
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class StitchRateLimitError(StitchUnavailableError):
    """Raised when Google Stitch returns HTTP 429 Too Many Requests."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("failure_category", "rate_limited")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class StitchSessionExpiredError(StitchUnavailableError):
    """Raised when an MCP session (`Mcp-Session-Id`) has expired on the server."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_category", "session_expired")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class StitchConnectionTimeoutError(StitchUnavailableError):
    """Raised when TCP/TLS connection establishment to Google Stitch times out before transmission."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_category", "connection_timeout")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class StitchResponseTimeoutError(StitchUnavailableError):
    """
    Raised when a transmitted Google Stitch MCP request exceeds the read timeout.
    Because generation may still complete server-side, callers must check server state
    (`get_project` / `get_screen` / `list_screens`) before re-sending generation requests.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_category", "response_timeout")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class StitchMalformedResponseError(StitchUnavailableError):
    """Raised when Google Stitch returns malformed JSON, truncated SSE, or invalid JSON-RPC structure."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("failure_category", "malformed_response")
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class StitchCancelledError(StitchError):
    """Raised when a long-running Google Stitch request is cooperatively cancelled by the user."""

    def __init__(
        self,
        message: str = "Google Stitch request was cancelled by the user.",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("failure_category", "cancelled")
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


@dataclass
class StitchScreenArtifact:
    """Represents a single rendered screen retrieved from Google Stitch."""

    screen_id: str
    name: str
    title: str
    device_type: str = "DESKTOP"
    width: int = 1440
    height: int = 900
    html_file_id: str = ""
    html_path: str = ""
    css_path: Optional[str] = None
    js_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    html_size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "name": self.name,
            "title": self.title,
            "device_type": self.device_type,
            "width": self.width,
            "height": self.height,
            "html_file_id": self.html_file_id,
            "html_path": self.html_path,
            "css_path": self.css_path,
            "js_path": self.js_path,
            "screenshot_path": self.screenshot_path,
            "html_size_bytes": self.html_size_bytes,
        }


@dataclass
class StitchDesignBundle:
    """Complete versioned design bundle returned by Google Stitch."""

    provider: str = "stitch"
    project_id: str = ""
    session_id: str = ""
    title: str = "Stitch Design"
    prompt: str = ""
    version: int = 1
    device_type: str = "DESKTOP"
    version_dir: str = ""
    preview_file: str = ""
    preview_url: Optional[str] = None
    screens: List[StitchScreenArtifact] = field(default_factory=list)
    design_system: Optional[Dict[str, Any]] = None
    assistant_text: str = ""
    suggestions: List[str] = field(default_factory=list)
    recovered_after_timeout: bool = False
    timestamp: float = field(default_factory=time.time)

    @property
    def screen_ids(self) -> List[str]:
        return [s.screen_id for s in self.screens if s.screen_id]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "title": self.title,
            "prompt": self.prompt,
            "version": self.version,
            "device_type": self.device_type,
            "version_dir": self.version_dir,
            "preview_file": self.preview_file,
            "preview_url": self.preview_url,
            "screen_ids": self.screen_ids,
            "screens": [s.to_dict() for s in self.screens],
            "design_system": self.design_system,
            "assistant_text": self.assistant_text,
            "suggestions": self.suggestions,
            "recovered_after_timeout": self.recovered_after_timeout,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StitchDesignBundle":
        screens_raw = data.get("screens") or []
        screens = [
            s if isinstance(s, StitchScreenArtifact) else StitchScreenArtifact(
                screen_id=str(s.get("screen_id", "")),
                name=str(s.get("name", "")),
                title=str(s.get("title", "Screen")),
                device_type=str(s.get("device_type", "DESKTOP")),
                width=int(s.get("width", 1440) or 1440),
                height=int(s.get("height", 900) or 900),
                html_file_id=str(s.get("html_file_id", "")),
                html_path=str(s.get("html_path", "")),
                css_path=s.get("css_path"),
                js_path=s.get("js_path"),
                screenshot_path=s.get("screenshot_path"),
                html_size_bytes=int(s.get("html_size_bytes", 0) or 0),
            )
            for s in screens_raw
            if isinstance(s, (dict, StitchScreenArtifact))
        ]
        return cls(
            provider=str(data.get("provider", "stitch")),
            project_id=str(data.get("project_id", "")),
            session_id=str(data.get("session_id", "")),
            title=str(data.get("title", "Stitch Design")),
            prompt=str(data.get("prompt", "")),
            version=int(data.get("version", 1) or 1),
            device_type=str(data.get("device_type", "DESKTOP")),
            version_dir=str(data.get("version_dir", "")),
            preview_file=str(data.get("preview_file", "")),
            preview_url=data.get("preview_url"),
            screens=screens,
            design_system=data.get("design_system"),
            assistant_text=str(data.get("assistant_text", "")),
            suggestions=list(data.get("suggestions") or []),
            recovered_after_timeout=bool(data.get("recovered_after_timeout", False)),
            timestamp=float(data.get("timestamp", time.time())),
        )


TransportFn = Callable[[str, Dict[str, str], Dict[str, Any], float], Any]


class StitchAdapter:
    """
    Official Google Stitch MCP Client for MIND Studio.

    Never fabricates HTML when Stitch is unavailable or fails.
    Never logs or raises raw API key material.
    """

    _global_in_flight_lock = threading.Lock()
    _global_in_flight_projects: Dict[str, float] = {}

    def __init__(
        self,
        config: Optional[GameDevConfig] = None,
        api_key: Optional[str] = None,
        mcp_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        connect_timeout_seconds: Optional[float] = None,
        transport: Optional[TransportFn] = None,
        heartbeat_interval_seconds: float = 1.0,
        recovery_poll_attempts: int = 3,
        recovery_poll_interval_seconds: float = 5.0,
        max_rate_limit_wait_seconds: float = 15.0,
        resume_phase2_on_design_system: bool = True,
    ) -> None:
        self.config = config or GameDevConfig.load()
        self._api_key = (
            api_key
            if api_key is not None
            else (self.config.stitch_api_key or os.getenv("STITCH_API_KEY") or "")
        ).strip()
        self.mcp_url = (
            mcp_url
            or self.config.stitch_mcp_url
            or os.getenv("STITCH_MCP_URL", "https://stitch.googleapis.com/mcp")
        ).strip()
        self.timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(
                getattr(self.config, "stitch_timeout_seconds", 300.0)
                or os.getenv("STITCH_TIMEOUT_SECONDS", "300.0")
            )
        )
        self.connect_timeout_seconds = (
            float(connect_timeout_seconds)
            if connect_timeout_seconds is not None
            else float(os.getenv("STITCH_CONNECT_TIMEOUT_SECONDS", "15.0"))
        )
        self._transport = transport
        self.heartbeat_interval_seconds = max(0.02, float(heartbeat_interval_seconds))
        self.recovery_poll_attempts = max(0, int(recovery_poll_attempts))
        self.recovery_poll_interval_seconds = max(0.02, float(recovery_poll_interval_seconds))
        self.max_rate_limit_wait_seconds = max(0.0, float(max_rate_limit_wait_seconds))
        self.resume_phase2_on_design_system = bool(resume_phase2_on_design_system)

        self._rpc_id = 0
        self._rpc_lock = threading.Lock()
        self._mcp_session_id: Optional[str] = None
        self.call_history: List[Dict[str, Any]] = []
        self.last_timed_out_project_id: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        """Returns True if a non-placeholder Stitch API key is configured."""
        return bool(self._api_key and not self._api_key.startswith("your_"))

    def masked_key(self) -> str:
        """Returns a safely redacted representation of the configured API key."""
        return redact_secret(self._api_key)

    def _sanitize(self, text: str) -> str:
        """Strips any accidental raw API key material from log or exception strings."""
        if not text:
            return ""
        sanitized = str(text)
        if self._api_key and len(self._api_key) >= 6 and self._api_key in sanitized:
            sanitized = sanitized.replace(self._api_key, "[REDACTED_STITCH_KEY]")
        return sanitized

    @staticmethod
    def normalize_project_id(project_id: str) -> str:
        """Strips leading `projects/` prefix if present."""
        pid = str(project_id or "").strip()
        if pid.startswith("projects/"):
            return pid.split("/", 1)[1]
        return pid

    @staticmethod
    def normalize_screen_id(screen_id: str) -> str:
        """Extracts bare screen ID from `projects/{pid}/screens/{sid}` or returns as-is."""
        sid = str(screen_id or "").strip()
        if "/screens/" in sid:
            return sid.rsplit("/screens/", 1)[1]
        if sid.startswith("screens/"):
            return sid.split("/", 1)[1]
        return sid

    def _next_rpc_id(self) -> int:
        with self._rpc_lock:
            self._rpc_id += 1
            return self._rpc_id

    @staticmethod
    def _check_cancelled(cancellation_token: Optional[Any]) -> None:
        if cancellation_token is not None and getattr(cancellation_token, "is_cancelled", False):
            reason = getattr(cancellation_token, "reason", "") or "Google Stitch operation cancelled by user."
            raise StitchCancelledError(str(reason))

    def _sleep_cancellable(self, seconds: float, cancellation_token: Optional[Any] = None) -> None:
        """Sleeps in small slices while checking `cancellation_token`."""
        deadline = time.time() + max(0.0, seconds)
        slice_sec = min(0.1, max(0.01, seconds / 5.0)) if seconds > 0 else 0.0
        while time.time() < deadline:
            self._check_cancelled(cancellation_token)
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(slice_sec, remaining))
        self._check_cancelled(cancellation_token)

    # ─── MCP Session & Streamable HTTP Parsing ──────────────────────────────

    def initialize_session(self, timeout: float = 20.0) -> Optional[str]:
        """
        Performs an optional MCP `initialize` handshake to establish or refresh
        an `Mcp-Session-Id` with the Streamable HTTP MCP endpoint.
        """
        if not self.is_configured:
            raise StitchUnavailableError(
                "Google Stitch API is not configured (STITCH_API_KEY is missing)."
            )
        rpc_id = self._next_rpc_id()
        correlation_id = f"stitch_init_{uuid.uuid4().hex[:8]}"
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "MIND-Universal-Studio",
                    "version": "2.5.0",
                },
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Goog-Api-Key": self._api_key,
            "X-Request-Id": correlation_id,
        }
        start_ts = time.time()
        try:
            if self._transport is not None:
                raw_resp = self._transport(self.mcp_url, headers, payload, timeout)
                if isinstance(raw_resp, dict):
                    resp_headers = raw_resp.get("_headers") if isinstance(raw_resp.get("_headers"), dict) else {}
                    sess_id = (
                        raw_resp.get("_mcp_session_id")
                        or resp_headers.get("Mcp-Session-Id")
                        or resp_headers.get("mcp-session-id")
                        or (
                            raw_resp.get("result", {}).get("sessionId")
                            if isinstance(raw_resp.get("result"), dict)
                            else None
                        )
                    )
                    if sess_id:
                        self._mcp_session_id = str(sess_id).strip()
            else:
                http_resp = requests.post(
                    self.mcp_url,
                    headers=headers,
                    json=payload,
                    timeout=(min(self.connect_timeout_seconds, timeout), timeout),
                )
                sess_hdr = (
                    http_resp.headers.get("Mcp-Session-Id")
                    or http_resp.headers.get("mcp-session-id")
                )
                if sess_hdr:
                    self._mcp_session_id = str(sess_hdr).strip()
            self.call_history.append({
                "tool": "initialize",
                "arguments": {},
                "correlation_id": correlation_id,
                "timestamp": start_ts,
                "elapsed_ms": round((time.time() - start_ts) * 1000.0, 2),
                "status": "ok",
                "mcp_session_id": self._mcp_session_id,
            })
        except Exception as exc:
            logger.debug("MCP initialize notice (%s): %s", correlation_id, self._sanitize(str(exc)))
        return self._mcp_session_id

    @classmethod
    def _parse_sse_or_json_text(cls, body_text: str, content_type: str, tool_name: str, correlation_id: str) -> Dict[str, Any]:
        """
        Parses either a standard `application/json` body or a Streamable HTTP MCP
        `text/event-stream` (SSE) payload into the final JSON-RPC response dict.
        """
        stripped = (body_text or "").strip()
        if not stripped:
            raise StitchMalformedResponseError(
                f"Google Stitch returned an empty HTTP body for '{tool_name}' [{correlation_id}].",
                correlation_id=correlation_id,
            )

        ctype = (content_type or "").lower()
        is_sse = (
            "text/event-stream" in ctype
            or stripped.startswith("event:")
            or stripped.startswith("data:")
            or "\ndata:" in stripped
        )
        if is_sse:
            last_rpc_obj: Optional[Dict[str, Any]] = None
            data_Accumulator: List[str] = []

            def _flush_accumulator() -> None:
                nonlocal last_rpc_obj
                if not data_Accumulator:
                    return
                joined = "\n".join(data_Accumulator).strip()
                data_Accumulator.clear()
                if not joined or joined == "[DONE]":
                    return
                try:
                    parsed_frame = json.loads(joined)
                    if isinstance(parsed_frame, dict):
                        if "result" in parsed_frame or "error" in parsed_frame:
                            last_rpc_obj = parsed_frame
                        elif last_rpc_obj is None:
                            last_rpc_obj = parsed_frame
                except Exception as parse_err:
                    raise StitchMalformedResponseError(
                        f"Google Stitch returned malformed SSE JSON frame for '{tool_name}' [{correlation_id}]: {parse_err}",
                        correlation_id=correlation_id,
                    ) from parse_err

            for raw_line in stripped.splitlines():
                line = raw_line.strip("\r")
                if not line:
                    _flush_accumulator()
                    continue
                if line.startswith(":"):
                    # SSE heartbeat comment
                    continue
                if line.startswith("data:"):
                    data_Accumulator.append(line[5:].lstrip())
                elif line.startswith("{") and not data_Accumulator:
                    data_Accumulator.append(line)
            _flush_accumulator()

            if isinstance(last_rpc_obj, dict):
                return last_rpc_obj

            raise StitchMalformedResponseError(
                f"Google Stitch SSE stream for '{tool_name}' [{correlation_id}] ended without a JSON-RPC result frame.",
                correlation_id=correlation_id,
            )

        try:
            parsed = json.loads(stripped)
        except Exception as json_err:
            raise StitchMalformedResponseError(
                f"Google Stitch returned invalid JSON for '{tool_name}' [{correlation_id}]: {json_err}",
                correlation_id=correlation_id,
            ) from json_err

        if not isinstance(parsed, dict):
            raise StitchMalformedResponseError(
                f"Google Stitch returned non-object JSON ({type(parsed).__name__}) for '{tool_name}' [{correlation_id}].",
                correlation_id=correlation_id,
            )
        return parsed

    @staticmethod
    def _parse_retry_after(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            val = float(str(value).strip())
            return max(0.0, val)
        except (TypeError, ValueError):
            return None

    # ─── Low-Level JSON-RPC 2.0 MCP Transport ───────────────────────────────

    def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        *,
        cancellation_token: Optional[Any] = None,
        retry_on_session_expired: bool = True,
        retry_on_rate_limit: bool = True,
    ) -> Dict[str, Any]:
        """
        Invokes a Stitch MCP tool via JSON-RPC 2.0 `tools/call`.
        Classifies failures into typed `StitchError` subclasses, tracks correlation IDs
        and elapsed timing, handles MCP session expiration (`Mcp-Session-Id`), and
        respects `Retry-After` on HTTP 429 when bounded.
        """
        self._check_cancelled(cancellation_token)

        if not self.is_configured:
            raise StitchUnavailableError(
                "Google Stitch API is not configured (STITCH_API_KEY is missing). "
                "Please configure STITCH_API_KEY in your environment."
            )

        rpc_id = self._next_rpc_id()
        correlation_id = f"stitch_{uuid.uuid4().hex[:10]}"
        args = arguments or {}
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args,
            },
        }
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Goog-Api-Key": self._api_key,
            "X-Request-Id": correlation_id,
        }
        if self._mcp_session_id:
            headers["Mcp-Session-Id"] = self._mcp_session_id

        eff_timeout = float(timeout if timeout is not None else self.timeout_seconds)
        connect_timeout = min(self.connect_timeout_seconds, eff_timeout)
        start_ts = time.time()

        history_entry: Dict[str, Any] = {
            "tool": tool_name,
            "arguments": json.loads(json.dumps(args)),
            "correlation_id": correlation_id,
            "timestamp": start_ts,
            "timeout_seconds": eff_timeout,
            "connect_timeout_seconds": connect_timeout,
            "mcp_session_id": self._mcp_session_id,
            "status": "in_flight",
        }
        self.call_history.append(history_entry)

        logger.info(
            "Stitch MCP request start [%s] tool=%s timeout=%.1fs project=%s",
            correlation_id,
            tool_name,
            eff_timeout,
            args.get("projectId") or args.get("name") or "-",
        )

        try:
            if self._transport is not None:
                raw_resp = self._transport(self.mcp_url, headers, payload, eff_timeout)
                if isinstance(raw_resp, str):
                    raw_resp = self._parse_sse_or_json_text(
                        raw_resp, "text/event-stream" if "data:" in raw_resp else "application/json", tool_name, correlation_id
                    )
                elif isinstance(raw_resp, dict) and "_http_status" in raw_resp:
                    status_code = int(raw_resp.get("_http_status", 200))
                    resp_headers = raw_resp.get("_headers") or {}
                    sess_hdr = resp_headers.get("Mcp-Session-Id") or resp_headers.get("mcp-session-id")
                    if sess_hdr:
                        self._mcp_session_id = str(sess_hdr).strip()
                    if status_code >= 400:
                        self._handle_http_error_status(
                            status_code=status_code,
                            body_text=str(raw_resp.get("_body", "")),
                            resp_headers=resp_headers,
                            tool_name=tool_name,
                            correlation_id=correlation_id,
                        )
                    if "_body" in raw_resp and "result" not in raw_resp and "error" not in raw_resp:
                        raw_resp = self._parse_sse_or_json_text(
                            str(raw_resp.get("_body", "")),
                            str(resp_headers.get("Content-Type", "application/json")),
                            tool_name,
                            correlation_id,
                        )
            else:
                http_resp = requests.post(
                    self.mcp_url,
                    headers=headers,
                    json=payload,
                    timeout=(connect_timeout, eff_timeout),
                )
                sess_hdr = (
                    http_resp.headers.get("Mcp-Session-Id")
                    or http_resp.headers.get("mcp-session-id")
                )
                if sess_hdr:
                    self._mcp_session_id = str(sess_hdr).strip()

                if http_resp.status_code >= 400:
                    self._handle_http_error_status(
                        status_code=http_resp.status_code,
                        body_text=http_resp.text,
                        resp_headers=dict(http_resp.headers),
                        tool_name=tool_name,
                        correlation_id=correlation_id,
                    )

                raw_resp = self._parse_sse_or_json_text(
                    http_resp.text,
                    http_resp.headers.get("Content-Type", "application/json"),
                    tool_name,
                    correlation_id,
                )

        except StitchSessionExpiredError as sess_err:
            history_entry["elapsed_ms"] = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["status"] = "session_expired"
            self._mcp_session_id = None
            if retry_on_session_expired:
                logger.info("Stitch MCP session expired [%s]; re-initializing session and retrying '%s' once.", correlation_id, tool_name)
                self.initialize_session()
                return self.call_tool(
                    tool_name,
                    arguments,
                    timeout=timeout,
                    cancellation_token=cancellation_token,
                    retry_on_session_expired=False,
                    retry_on_rate_limit=retry_on_rate_limit,
                )
            raise sess_err
        except StitchRateLimitError as rl_err:
            history_entry["elapsed_ms"] = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["status"] = "rate_limited"
            wait_sec = rl_err.retry_after if rl_err.retry_after is not None else 2.0
            if retry_on_rate_limit and wait_sec <= self.max_rate_limit_wait_seconds:
                logger.info("Stitch MCP rate-limited [%s]; waiting %.2fs (Retry-After) before single retry.", correlation_id, wait_sec)
                self._sleep_cancellable(wait_sec, cancellation_token)
                return self.call_tool(
                    tool_name,
                    arguments,
                    timeout=timeout,
                    cancellation_token=cancellation_token,
                    retry_on_session_expired=retry_on_session_expired,
                    retry_on_rate_limit=False,
                )
            raise rl_err
        except StitchError as st_err:
            history_entry["elapsed_ms"] = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["status"] = st_err.failure_category
            raise
        except requests.exceptions.ConnectTimeout as e:
            elapsed_ms = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["elapsed_ms"] = elapsed_ms
            history_entry["status"] = "connection_timeout"
            raise StitchConnectionTimeoutError(
                f"Google Stitch connection timed out after {connect_timeout}s while connecting for '{tool_name}' [{correlation_id}].",
                correlation_id=correlation_id,
            ) from e
        except requests.exceptions.ReadTimeout as e:
            elapsed_ms = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["elapsed_ms"] = elapsed_ms
            history_entry["status"] = "response_timeout"
            raise StitchResponseTimeoutError(
                f"Google Stitch request '{tool_name}' timed out after {eff_timeout}s [{correlation_id}].",
                project_id=str(args.get("projectId") or ""),
                correlation_id=correlation_id,
            ) from e
        except requests.Timeout as e:
            elapsed_ms = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["elapsed_ms"] = elapsed_ms
            history_entry["status"] = "response_timeout"
            raise StitchResponseTimeoutError(
                f"Google Stitch request '{tool_name}' timed out after {eff_timeout}s [{correlation_id}].",
                project_id=str(args.get("projectId") or ""),
                correlation_id=correlation_id,
            ) from e
        except requests.RequestException as e:
            elapsed_ms = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["elapsed_ms"] = elapsed_ms
            history_entry["status"] = "network_error"
            raise StitchUnavailableError(
                f"Google Stitch network error during '{tool_name}' [{correlation_id}]: {self._sanitize(str(e))}",
                failure_category="network_error",
                correlation_id=correlation_id,
                retryable=True,
            ) from e
        except Exception as e:
            elapsed_ms = round((time.time() - start_ts) * 1000.0, 2)
            history_entry["elapsed_ms"] = elapsed_ms
            history_entry["status"] = "error"
            raise StitchUnavailableError(
                f"Google Stitch call '{tool_name}' failed [{correlation_id}]: {self._sanitize(str(e))}",
                correlation_id=correlation_id,
            ) from e

        elapsed_ms = round((time.time() - start_ts) * 1000.0, 2)
        history_entry["elapsed_ms"] = elapsed_ms

        if not isinstance(raw_resp, dict):
            history_entry["status"] = "malformed_response"
            raise StitchMalformedResponseError(
                f"Google Stitch returned non-JSON response for '{tool_name}' [{correlation_id}].",
                correlation_id=correlation_id,
            )

        if "error" in raw_resp and raw_resp["error"]:
            err_obj = raw_resp["error"]
            err_code = err_obj.get("code") if isinstance(err_obj, dict) else None
            err_msg = err_obj.get("message", str(err_obj)) if isinstance(err_obj, dict) else str(err_obj)
            clean_msg = self._sanitize(err_msg)
            history_entry["status"] = "rpc_error"

            if "session" in clean_msg.lower() and ("expired" in clean_msg.lower() or "not found" in clean_msg.lower()):
                self._mcp_session_id = None
                if retry_on_session_expired:
                    self.initialize_session()
                    return self.call_tool(
                        tool_name,
                        arguments,
                        timeout=timeout,
                        cancellation_token=cancellation_token,
                        retry_on_session_expired=False,
                        retry_on_rate_limit=retry_on_rate_limit,
                    )
                raise StitchSessionExpiredError(
                    f"Google Stitch MCP session expired in '{tool_name}': {clean_msg}",
                    correlation_id=correlation_id,
                )

            if err_code in (-32600, -32602) or "invalid argument" in clean_msg.lower() or "invalid params" in clean_msg.lower():
                raise StitchInvalidRequestError(
                    f"Google Stitch invalid request in '{tool_name}': {clean_msg}",
                    correlation_id=correlation_id,
                )

            raise StitchUnavailableError(
                f"Google Stitch RPC error in '{tool_name}': {clean_msg}",
                failure_category="rpc_error",
                correlation_id=correlation_id,
            )

        result = raw_resp.get("result")
        if not isinstance(result, dict):
            history_entry["status"] = "malformed_response"
            raise StitchMalformedResponseError(
                f"Google Stitch returned empty or malformed result for '{tool_name}' [{correlation_id}].",
                correlation_id=correlation_id,
            )

        if result.get("isError"):
            history_entry["status"] = "tool_error"
            err_text = self._extract_text_from_content(result.get("content", []))
            clean_err = self._sanitize(err_text or "Unknown tool error")
            if "invalid" in clean_err.lower() and ("argument" in clean_err.lower() or "parameter" in clean_err.lower()):
                raise StitchInvalidRequestError(
                    f"Google Stitch tool '{tool_name}' rejected arguments: {clean_err}",
                    correlation_id=correlation_id,
                )
            raise StitchUnavailableError(
                f"Google Stitch tool '{tool_name}' reported error: {clean_err}",
                failure_category="tool_error",
                correlation_id=correlation_id,
            )

        history_entry["status"] = "ok"
        logger.info(
            "Stitch MCP request completed [%s] tool=%s elapsed_ms=%.1f",
            correlation_id,
            tool_name,
            elapsed_ms,
        )

        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured

        # Fallback: parse JSON text blocks inside `result.content`
        content_list = result.get("content")
        if isinstance(content_list, list):
            for item in content_list:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    txt = item["text"].strip()
                    if txt.startswith("{") or txt.startswith("["):
                        try:
                            parsed = json.loads(txt)
                            if isinstance(parsed, dict):
                                return parsed
                        except Exception:
                            pass
            return {"text": self._extract_text_from_content(content_list)}

        return result

    def _handle_http_error_status(
        self,
        *,
        status_code: int,
        body_text: str,
        resp_headers: Dict[str, Any],
        tool_name: str,
        correlation_id: str,
    ) -> None:
        """Maps HTTP 4xx/5xx responses into typed `StitchError` exceptions."""
        body_preview = self._sanitize((body_text or "")[:300])
        if status_code in (401, 403):
            raise StitchAuthenticationError(
                f"Google Stitch authentication failed (HTTP {status_code}) "
                f"with key {self.masked_key()}.",
                correlation_id=correlation_id,
            )
        if status_code == 429:
            retry_after = self._parse_retry_after(
                resp_headers.get("Retry-After") or resp_headers.get("retry-after")
            )
            raise StitchRateLimitError(
                f"Google Stitch rate limit exceeded (HTTP 429) on '{tool_name}' [{correlation_id}].",
                retry_after=retry_after,
                correlation_id=correlation_id,
            )
        if status_code in (404, 410) and (
            self._mcp_session_id
            or "session" in body_preview.lower()
        ):
            raise StitchSessionExpiredError(
                f"Google Stitch MCP session expired (HTTP {status_code}) on '{tool_name}' [{correlation_id}].",
                correlation_id=correlation_id,
            )
        if status_code == 400:
            raise StitchInvalidRequestError(
                f"Google Stitch HTTP 400 Invalid Request on '{tool_name}': {body_preview}",
                correlation_id=correlation_id,
            )
        raise StitchUnavailableError(
            f"Google Stitch HTTP {status_code} on '{tool_name}': {body_preview}",
            failure_category=f"http_{status_code}",
            correlation_id=correlation_id,
            retryable=status_code >= 500,
        )

    @staticmethod
    def _extract_text_from_content(content_list: Any) -> str:
        if not isinstance(content_list, list):
            return ""
        parts = []
        for item in content_list:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()

    # ─── Documented Stitch Tool Wrappers ────────────────────────────────────

    def list_projects(self, filter_str: Optional[str] = None) -> List[Dict[str, Any]]:
        args: Dict[str, Any] = {}
        if filter_str:
            args["filter"] = filter_str
        res = self.call_tool("list_projects", args, timeout=30.0)
        projects = res.get("projects")
        return projects if isinstance(projects, list) else []

    def create_project(self, title: Optional[str] = None) -> Dict[str, Any]:
        args: Dict[str, Any] = {}
        if title:
            args["title"] = title
        return self.call_tool("create_project", args, timeout=45.0)

    def get_project(self, project_id: str) -> Dict[str, Any]:
        pid = self.normalize_project_id(project_id)
        return self.call_tool("get_project", {"name": f"projects/{pid}"}, timeout=30.0)

    def list_design_systems(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        args: Dict[str, Any] = {}
        if project_id:
            args["projectId"] = self.normalize_project_id(project_id)
        res = self.call_tool("list_design_systems", args, timeout=30.0)
        raw_list = res.get("designSystems")
        if not isinstance(raw_list, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            outer_name = str(item.get("name") or "").strip()
            inner = item.get("designSystem")
            if isinstance(inner, dict):
                merged = dict(inner)
                if outer_name and not merged.get("name"):
                    merged["name"] = outer_name
                normalized.append(merged)
            else:
                normalized.append(dict(item))
        return normalized

    def list_screens(self, project_id: str) -> List[Dict[str, Any]]:
        pid = self.normalize_project_id(project_id)
        res = self.call_tool("list_screens", {"projectId": pid}, timeout=45.0)
        screens = res.get("screens")
        return screens if isinstance(screens, list) else []

    def get_screen(self, project_id: str, screen_id: str) -> Dict[str, Any]:
        pid = self.normalize_project_id(project_id)
        sid = self.normalize_screen_id(screen_id)
        return self.call_tool(
            "get_screen",
            {
                "name": f"projects/{pid}/screens/{sid}",
                "projectId": pid,
                "screenId": sid,
            },
            timeout=45.0,
        )

    def generate_screen_from_text(
        self,
        project_id: str,
        prompt: str,
        device_type: str = "DESKTOP",
        design_system: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        pid = self.normalize_project_id(project_id)
        args: Dict[str, Any] = {
            "projectId": pid,
            "prompt": prompt,
            "deviceType": device_type.upper() if device_type else "DESKTOP",
        }
        if design_system:
            args["designSystem"] = design_system
        if model_id:
            args["modelId"] = model_id
        return self.call_tool("generate_screen_from_text", args, timeout=self.timeout_seconds)

    def edit_screens(
        self,
        project_id: str,
        selected_screen_ids: List[str],
        prompt: str,
        device_type: str = "DESKTOP",
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        pid = self.normalize_project_id(project_id)
        clean_ids = [self.normalize_screen_id(s) for s in selected_screen_ids if s]
        if not clean_ids:
            raise StitchUnavailableError("Cannot call Stitch edit_screens without at least one screen ID.")
        args: Dict[str, Any] = {
            "projectId": pid,
            "selectedScreenIds": clean_ids,
            "prompt": prompt,
            "deviceType": device_type.upper() if device_type else "DESKTOP",
        }
        if model_id:
            args["modelId"] = model_id
        return self.call_tool("edit_screens", args, timeout=self.timeout_seconds)

    def download_file(self, file_name: str) -> Dict[str, Any]:
        if not file_name:
            raise StitchUnavailableError("Empty Stitch file resource name passed to download_file.")
        return self.call_tool("download_file", {"name": file_name}, timeout=60.0)

    # ─── Server-Side Completion Check & Non-Blocking Execution ──────────────

    def recover_project_screens(
        self,
        project_id: str,
        cancellation_token: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Inspects the Stitch server to determine whether screen generation completed
        server-side after a socket read timeout or connection drop.

        Checks:
        1. `list_screens(project_id)`
        2. `get_project(project_id)` -> `screenInstances` -> `get_screen(project_id, screen_id)`
           (per official Stitch MCP `generate_screen_from_text` recovery instructions).
        """
        self._check_cancelled(cancellation_token)
        pid = self.normalize_project_id(project_id)
        if not pid:
            return []

        try:
            screens = self.list_screens(pid)
            if screens:
                return screens
        except StitchCancelledError:
            raise
        except Exception as exc:
            logger.debug("recover_project_screens list_screens notice: %s", self._sanitize(str(exc)))

        self._check_cancelled(cancellation_token)
        try:
            proj = self.get_project(pid)
            instances = proj.get("screenInstances")
            if isinstance(instances, list) and instances:
                recovered: List[Dict[str, Any]] = []
                seen_sids: set[str] = set()
                for inst in instances:
                    self._check_cancelled(cancellation_token)
                    if not isinstance(inst, dict):
                        continue
                    source_screen = str(inst.get("sourceScreen") or inst.get("id") or "").strip()
                    sid = self.normalize_screen_id(source_screen)
                    if not sid or sid in seen_sids:
                        continue
                    seen_sids.add(sid)
                    try:
                        scr = self.get_screen(pid, sid)
                        if isinstance(scr, dict) and (scr.get("name") or scr.get("htmlCode") or scr.get("id")):
                            recovered.append(scr)
                    except StitchCancelledError:
                        raise
                    except Exception as scr_exc:
                        logger.debug("recover_project_screens get_screen(%s) notice: %s", sid, self._sanitize(str(scr_exc)))
                if recovered:
                    return recovered
        except StitchCancelledError:
            raise
        except Exception as proj_exc:
            logger.debug("recover_project_screens get_project notice: %s", self._sanitize(str(proj_exc)))

        return []

    def _poll_for_server_completion(
        self,
        project_id: str,
        *,
        stage_label: str = "generation",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Polls `recover_project_screens(project_id)` up to `self.recovery_poll_attempts` times
        following a read timeout to recover screens that finished generating on the server.
        """
        pid = self.normalize_project_id(project_id)
        if not pid or self.recovery_poll_attempts <= 0:
            return []

        for attempt in range(1, self.recovery_poll_attempts + 1):
            self._check_cancelled(cancellation_token)
            if progress_callback:
                try:
                    progress_callback({
                        "design_state": "recovering",
                        "message": (
                            f"Google Stitch {stage_label} is taking longer than expected — "
                            f"checking server completion (check {attempt}/{self.recovery_poll_attempts})..."
                        ),
                        "progress": min(0.88, 0.78 + attempt * 0.03),
                        "progress_pct": min(0.88, 0.78 + attempt * 0.03),
                    })
                except Exception:
                    pass

            # First check immediately on attempt 1 before sleeping, then sleep between checks
            if attempt > 1:
                self._sleep_cancellable(self.recovery_poll_interval_seconds, cancellation_token)

            recovered = self.recover_project_screens(pid, cancellation_token=cancellation_token)
            if recovered:
                logger.info(
                    "Recovered %d screen(s) from Stitch project %s on recovery poll %d.",
                    len(recovered),
                    pid,
                    attempt,
                )
                return recovered

        return []

    def _run_with_heartbeat(
        self,
        fn: Callable[[], Dict[str, Any]],
        *,
        status_prefix: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancellation_token: Optional[Any] = None,
        base_progress: float = 0.40,
        max_progress: float = 0.80,
    ) -> Dict[str, Any]:
        """
        Executes a blocking MCP tool call inside a background thread while emitting
        non-blocking heartbeat progress updates and checking `cancellation_token`
        every `self.heartbeat_interval_seconds`.
        """
        self._check_cancelled(cancellation_token)
        start_ts = time.time()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(fn)
        try:
            while True:
                try:
                    return future.result(timeout=self.heartbeat_interval_seconds)
                except concurrent.futures.TimeoutError:
                    self._check_cancelled(cancellation_token)
                    elapsed = time.time() - start_ts
                    if progress_callback:
                        ratio = min(1.0, elapsed / max(10.0, self.timeout_seconds))
                        pct = round(base_progress + (max_progress - base_progress) * ratio, 3)
                        try:
                            progress_callback({
                                "design_state": "prototyping",
                                "message": f"{status_prefix} ({int(elapsed)}s elapsed)...",
                                "progress": pct,
                                "progress_pct": pct,
                                "elapsed_seconds": round(elapsed, 1),
                            })
                        except Exception:
                            pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    # ─── Response Parsing & Artifact Extraction ─────────────────────────────

    @classmethod
    def parse_generation_response(cls, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts screens, designSystem, assistant text, and suggestions from a
        `generate_screen_from_text` or `edit_screens` response.

        Supports both nested `outputComponents` (live Stitch MCP format) and
        top-level `screens` / single-screen objects.
        Preserves the outer `designSystem.name` (`assets/...`) resource identifier
        so follow-up `generate_screen_from_text` calls can reuse the synthesized design system.
        """
        screens: List[Dict[str, Any]] = []
        design_system: Optional[Dict[str, Any]] = None
        texts: List[str] = []
        suggestions: List[str] = []

        output_components = response.get("outputComponents")
        if isinstance(output_components, list):
            for comp in output_components:
                if not isinstance(comp, dict):
                    continue
                if "design" in comp and isinstance(comp["design"], dict):
                    comp_screens = comp["design"].get("screens")
                    if isinstance(comp_screens, list):
                        for s in comp_screens:
                            if isinstance(s, dict):
                                screens.append(s)
                if "designSystem" in comp and isinstance(comp["designSystem"], dict):
                    raw_ds = comp["designSystem"]
                    outer_name = str(raw_ds.get("name") or "").strip()
                    inner_ds = raw_ds.get("designSystem")
                    if isinstance(inner_ds, dict):
                        design_system = dict(inner_ds)
                        if outer_name and not design_system.get("name"):
                            design_system["name"] = outer_name
                    else:
                        design_system = dict(raw_ds)
                if comp.get("text"):
                    texts.append(str(comp["text"]))
                if comp.get("suggestion"):
                    suggestions.append(str(comp["suggestion"]))

        # Also support top-level `screens` array
        if not screens and isinstance(response.get("screens"), list):
            for s in response["screens"]:
                if isinstance(s, dict):
                    screens.append(s)

        # Also support single screen object at top level
        if not screens and isinstance(response.get("htmlCode"), dict):
            screens.append(response)

        return {
            "screens": screens,
            "design_system": design_system,
            "assistant_text": "\n\n".join(texts).strip(),
            "suggestions": suggestions,
            "project_id": cls.normalize_project_id(str(response.get("projectId", ""))),
            "session_id": str(response.get("sessionId", "")),
        }

    @staticmethod
    def extract_css_and_js_from_html(html_text: str) -> Tuple[str, str]:
        """
        Extracts inline `<style>` and non-external `<script>` blocks from Stitch HTML
        so they can be saved alongside `index.html` as inspectable `.css` and `.js` assets.
        """
        style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", html_text, flags=re.IGNORECASE | re.DOTALL)
        css_content = "\n\n/* --- Stitch Extracted Style Block --- */\n\n".join(
            b.strip() for b in style_blocks if b.strip()
        )

        script_blocks: List[str] = []
        for match in re.finditer(r"<script([^>]*)>(.*?)</script>", html_text, flags=re.IGNORECASE | re.DOTALL):
            attrs, body = match.group(1), match.group(2)
            if "src=" in attrs.lower():
                continue
            if body.strip():
                script_blocks.append(body.strip())
        js_content = "\n\n// --- Stitch Extracted Script Block ---\n\n".join(script_blocks)
        return css_content, js_content

    def _download_screen_html(self, project_id: str, screen_dict: Dict[str, Any]) -> Tuple[str, str]:
        """
        Retrieves the actual HTML string for a Stitch screen descriptor using `download_file`.
        Returns `(html_text, html_file_resource_name)`.
        Raises `StitchUnavailableError` if no HTML can be retrieved.
        """
        pid = self.normalize_project_id(project_id)
        screen_name = str(screen_dict.get("name", ""))
        sid = self.normalize_screen_id(screen_name or str(screen_dict.get("id", "")))

        html_code_info = screen_dict.get("htmlCode") if isinstance(screen_dict.get("htmlCode"), dict) else {}
        file_resource_name = str(html_code_info.get("name", "")).strip()

        # If screen descriptor from list_screens omitted htmlCode, call get_screen first
        if not file_resource_name and pid and sid:
            try:
                detailed = self.get_screen(pid, sid)
                if isinstance(detailed.get("htmlCode"), dict):
                    html_code_info = detailed["htmlCode"]
                    file_resource_name = str(html_code_info.get("name", "")).strip()
            except Exception as e:
                logger.debug("get_screen fallback notice: %s", self._sanitize(str(e)))

        if not file_resource_name and pid and sid:
            file_resource_name = f"projects/{pid}/screens/{sid}/fileEntries/html"

        html_text = ""
        if file_resource_name:
            dl_res = self.download_file(file_resource_name)
            html_text = str(dl_res.get("html") or dl_res.get("content") or dl_res.get("text") or "").strip()

        if not html_text:
            raise StitchUnavailableError(
                f"Google Stitch did not return HTML content for screen '{sid or screen_name}'."
            )

        return html_text, file_resource_name

    def _materialize_screens(
        self,
        project_id: str,
        screens_raw: List[Dict[str, Any]],
        version_dir: Path,
    ) -> List[StitchScreenArtifact]:
        """
        Downloads HTML (and optional screenshots) for every Stitch screen and writes
        them into `version_dir`.
        """
        version_dir.mkdir(parents=True, exist_ok=True)
        artifacts: List[StitchScreenArtifact] = []

        for idx, s_dict in enumerate(screens_raw):
            s_name = str(s_dict.get("name", f"projects/{project_id}/screens/screen_{idx+1}"))
            sid = self.normalize_screen_id(s_name)
            s_title = str(s_dict.get("title") or f"Screen {idx + 1}").strip()
            dev_type = str(s_dict.get("deviceType") or "DESKTOP")
            try:
                width = int(s_dict.get("width", 1440) or 1440)
            except (TypeError, ValueError):
                width = 1440
            try:
                height = int(s_dict.get("height", 900) or 900)
            except (TypeError, ValueError):
                height = 900

            html_text, html_file_id = self._download_screen_html(project_id, s_dict)

            slug = re.sub(r"[^a-z0-9]+", "_", s_title.lower()).strip("_") or f"screen_{idx+1}"
            screen_filename = f"screen_{idx+1}_{slug}.html"
            screen_html_path = version_dir / screen_filename
            screen_html_path.write_text(html_text, encoding="utf-8")

            # Primary screen is also written to index.html for standard preview server routing
            if idx == 0:
                index_path = version_dir / "index.html"
                index_path.write_text(html_text, encoding="utf-8")
                primary_html_path = index_path
            else:
                primary_html_path = screen_html_path

            # Extract inline CSS and JS into companion files if present
            css_text, js_text = self.extract_css_and_js_from_html(html_text)
            css_path_str: Optional[str] = None
            js_path_str: Optional[str] = None
            if css_text:
                css_file = version_dir / ("stitch_extracted.css" if idx == 0 else f"screen_{idx+1}_extracted.css")
                css_file.write_text(css_text, encoding="utf-8")
                css_path_str = str(css_file.resolve())
            if js_text:
                js_file = version_dir / ("stitch_extracted.js" if idx == 0 else f"screen_{idx+1}_extracted.js")
                js_file.write_text(js_text, encoding="utf-8")
                js_path_str = str(js_file.resolve())

            # Optional screenshot download via download_file
            screenshot_path_str: Optional[str] = None
            ss_info = s_dict.get("screenshot") if isinstance(s_dict.get("screenshot"), dict) else {}
            ss_name = str(ss_info.get("name", "")).strip()
            if ss_name:
                try:
                    ss_res = self.download_file(ss_name)
                    b64_img = ss_res.get("image")
                    if isinstance(b64_img, str) and b64_img:
                        img_bytes = base64.b64decode(b64_img)
                        ss_file = version_dir / f"screen_{idx+1}_{slug}.png"
                        ss_file.write_bytes(img_bytes)
                        screenshot_path_str = str(ss_file.resolve())
                except Exception as ss_err:
                    logger.debug("Optional Stitch screenshot download skipped: %s", self._sanitize(str(ss_err)))

            artifacts.append(
                StitchScreenArtifact(
                    screen_id=sid,
                    name=s_name,
                    title=s_title,
                    device_type=dev_type,
                    width=width,
                    height=height,
                    html_file_id=html_file_id,
                    html_path=str(primary_html_path.resolve()),
                    css_path=css_path_str,
                    js_path=js_path_str,
                    screenshot_path=screenshot_path_str,
                    html_size_bytes=len(html_text.encode("utf-8")),
                )
            )

        if not artifacts:
            raise StitchUnavailableError("Google Stitch returned no downloadable screen artifacts.")

        return artifacts

    # ─── High-Level Design & Revision Workflows ─────────────────────────────

    def ensure_project(self, project_id: Optional[str] = None, title: Optional[str] = None) -> str:
        """Returns a normalized Stitch `projectId`, creating a new Stitch project if needed."""
        if project_id:
            return self.normalize_project_id(project_id)

        proj_res = self.create_project(title=title or "MIND Website Design")
        name = str(proj_res.get("name") or proj_res.get("projectId") or "").strip()
        pid = self.normalize_project_id(name)
        if not pid:
            raise StitchUnavailableError("Google Stitch create_project did not return a valid project ID.")
        return pid

    @staticmethod
    def _load_in_flight_state(session_path: Path) -> Optional[Dict[str, Any]]:
        state_file = session_path / "stitch_in_flight.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return None

    @staticmethod
    def _save_in_flight_state(session_path: Path, state: Dict[str, Any]) -> None:
        try:
            session_path.mkdir(parents=True, exist_ok=True)
            state_file = session_path / "stitch_in_flight.json"
            state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass

    def generate_design(
        self,
        prompt: str,
        session_dir: Union[Path, str],
        project_id: Optional[str] = None,
        title: Optional[str] = None,
        device_type: str = "DESKTOP",
        version: int = 1,
        design_system: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> StitchDesignBundle:
        """
        Generates a website design via Google Stitch, downloads the actual HTML/CSS/JS
        and screenshot artifacts into `session_dir / f"v{version}"`, and returns a
        `StitchDesignBundle`.

        Safeguards against timeouts and duplicate generation:
        1. Reuses an existing `project_id` (or persisted `stitch_in_flight.json` in `session_dir`)
           instead of creating duplicate Stitch projects.
        2. When resuming an existing `project_id`, checks `recover_project_screens(pid)` first —
           if Stitch already completed screen generation server-side, downloads and renders
           the screens immediately without calling `generate_screen_from_text` again.
        3. If Stitch already synthesized a `designSystem` (`assets/...`) for `pid`, passes
           that `designSystem` asset ID into `generate_screen_from_text` to skip redundant
           Phase-1 design-system generation.
        4. Emits live heartbeat progress updates and checks `cancellation_token` while waiting.
        """
        self._check_cancelled(cancellation_token)
        session_path = Path(session_dir).resolve()

        # Check if a prior attempt in this session directory already created a Stitch project
        prior_state = self._load_in_flight_state(session_path)
        reused_existing_project = bool(project_id)
        if not project_id and isinstance(prior_state, dict) and prior_state.get("project_id"):
            project_id = str(prior_state["project_id"])
            reused_existing_project = True
            if not design_system and prior_state.get("design_system"):
                design_system = str(prior_state["design_system"])

        pid = self.ensure_project(project_id=project_id, title=title)
        self._check_cancelled(cancellation_token)

        # Prevent duplicate concurrent in-flight generations for the same Stitch project
        with self._global_in_flight_lock:
            if pid in self._global_in_flight_projects:
                raise StitchUnavailableError(
                    f"Google Stitch generation is already in progress for project '{pid}'. "
                    "Please wait for the active request to finish.",
                    failure_category="concurrent_in_flight",
                    project_id=pid,
                )
            self._global_in_flight_projects[pid] = time.time()

        try:
            self._save_in_flight_state(
                session_path,
                {
                    "project_id": pid,
                    "title": title or "MIND Website Design",
                    "prompt": prompt,
                    "design_system": design_system,
                    "status": "in_flight",
                    "updated_at": time.time(),
                },
            )

            recovered_after_timeout = False
            parsed: Optional[Dict[str, Any]] = None

            # If reusing a project from a prior timeout/retry, check server state BEFORE generating!
            if reused_existing_project:
                existing_screens = self.recover_project_screens(pid, cancellation_token=cancellation_token)
                if existing_screens:
                    logger.info(
                        "Found %d existing screen(s) on Stitch project %s; recovering without re-generating.",
                        len(existing_screens),
                        pid,
                    )
                    recovered_after_timeout = True
                    parsed = {
                        "screens": existing_screens,
                        "design_system": {"name": design_system} if design_system else None,
                        "assistant_text": "Recovered completed Google Stitch design from existing project.",
                        "suggestions": [],
                        "project_id": pid,
                        "session_id": f"stitch_{pid}",
                    }
                elif not design_system:
                    try:
                        ds_list = self.list_design_systems(pid)
                        if ds_list and ds_list[0].get("name"):
                            design_system = str(ds_list[0]["name"])
                    except Exception:
                        pass

            if parsed is None:
                try:
                    gen_res = self._run_with_heartbeat(
                        lambda: self.generate_screen_from_text(
                            project_id=pid,
                            prompt=prompt,
                            device_type=device_type,
                            design_system=design_system,
                        ),
                        status_prefix=f"Google Stitch is generating '{title or 'website'}' layout",
                        progress_callback=progress_callback,
                        cancellation_token=cancellation_token,
                    )
                    parsed = self.parse_generation_response(gen_res)
                except StitchCancelledError:
                    self._save_in_flight_state(
                        session_path,
                        {
                            "project_id": pid,
                            "title": title or "MIND Website Design",
                            "prompt": prompt,
                            "design_system": design_system,
                            "status": "cancelled",
                            "updated_at": time.time(),
                        },
                    )
                    raise
                except StitchUnavailableError as gen_err:
                    self._check_cancelled(cancellation_token)
                    is_timeout_or_drop = (
                        isinstance(gen_err, StitchResponseTimeoutError)
                        or "timed out" in str(gen_err).lower()
                        or gen_err.failure_category == "network_error"
                    )
                    if is_timeout_or_drop and not isinstance(gen_err, StitchConnectionTimeoutError):
                        self.last_timed_out_project_id = pid
                        recovered_screens = self._poll_for_server_completion(
                            pid,
                            stage_label="screen generation",
                            progress_callback=progress_callback,
                            cancellation_token=cancellation_token,
                        )
                        if recovered_screens:
                            recovered_after_timeout = True
                            parsed = {
                                "screens": recovered_screens,
                                "design_system": {"name": design_system} if design_system else None,
                                "assistant_text": "Recovered Stitch design screens after long upstream generation.",
                                "suggestions": [],
                                "project_id": pid,
                                "session_id": f"stitch_{pid}",
                            }
                        else:
                            # Check if Phase 1 (designSystem synthesis) completed on the server before the read timeout
                            synthesized_ds: Optional[Dict[str, Any]] = None
                            synthesized_ds_name: Optional[str] = design_system
                            if not synthesized_ds_name:
                                try:
                                    ds_list = self.list_design_systems(pid)
                                    if ds_list and ds_list[0].get("name"):
                                        synthesized_ds = ds_list[0]
                                        synthesized_ds_name = str(ds_list[0]["name"])
                                except Exception:
                                    pass

                            if synthesized_ds_name and self.resume_phase2_on_design_system and not design_system:
                                self._check_cancelled(cancellation_token)
                                self._save_in_flight_state(
                                    session_path,
                                    {
                                        "project_id": pid,
                                        "title": title or "MIND Website Design",
                                        "prompt": prompt,
                                        "design_system": synthesized_ds_name,
                                        "status": "phase2_in_flight",
                                        "updated_at": time.time(),
                                    },
                                )
                                logger.info(
                                    "Stitch project %s completed Phase 1 designSystem (%s); resuming Phase 2 screen synthesis.",
                                    pid,
                                    synthesized_ds_name,
                                )
                                try:
                                    gen_res_p2 = self._run_with_heartbeat(
                                        lambda: self.generate_screen_from_text(
                                            project_id=pid,
                                            prompt=prompt,
                                            device_type=device_type,
                                            design_system=synthesized_ds_name,
                                        ),
                                        status_prefix=f"Google Stitch design system ready; synthesizing '{title or 'website'}' screens",
                                        progress_callback=progress_callback,
                                        cancellation_token=cancellation_token,
                                        base_progress=0.65,
                                        max_progress=0.90,
                                    )
                                    parsed = self.parse_generation_response(gen_res_p2)
                                    if synthesized_ds and not parsed.get("design_system"):
                                        parsed["design_system"] = synthesized_ds
                                    recovered_after_timeout = True
                                except StitchCancelledError:
                                    raise
                                except StitchUnavailableError as p2_err:
                                    p2_screens = self._poll_for_server_completion(
                                        pid,
                                        stage_label="Phase-2 screen synthesis",
                                        progress_callback=progress_callback,
                                        cancellation_token=cancellation_token,
                                    )
                                    if p2_screens:
                                        recovered_after_timeout = True
                                        parsed = {
                                            "screens": p2_screens,
                                            "design_system": synthesized_ds or {"name": synthesized_ds_name},
                                            "assistant_text": "Recovered Stitch design screens after Phase-2 completion.",
                                            "suggestions": [],
                                            "project_id": pid,
                                            "session_id": f"stitch_{pid}",
                                        }
                                    else:
                                        p2_err.project_id = pid
                                        p2_err.design_system = synthesized_ds_name
                                        raise p2_err
                            else:
                                gen_err.project_id = pid
                                gen_err.design_system = synthesized_ds_name
                                raise
                    else:
                        gen_err.project_id = pid
                        raise

            screens_raw = parsed["screens"]
            ds_obj = parsed["design_system"]
            ds_name = ds_obj.get("name") if isinstance(ds_obj, dict) else design_system
            if not ds_name and isinstance(ds_obj, dict):
                # Fallback: query list_design_systems on the project to retrieve the outer `assets/...` ID
                try:
                    ds_list = self.list_design_systems(pid)
                    if ds_list and ds_list[0].get("name"):
                        ds_name = str(ds_list[0]["name"])
                        ds_obj["name"] = ds_name
                except Exception:
                    pass

            # Per Stitch MCP documentation: if the first call returned a suggestion/designSystem
            # before generating the screens, follow up once with the suggestion to materialize screens.
            if not screens_raw and parsed["suggestions"]:
                self._check_cancelled(cancellation_token)
                follow_prompt = parsed["suggestions"][0]
                gen_res2 = self._run_with_heartbeat(
                    lambda: self.generate_screen_from_text(
                        project_id=pid,
                        prompt=follow_prompt,
                        device_type=device_type,
                        design_system=ds_name,
                    ),
                    status_prefix=f"Google Stitch is materializing screens for '{title or 'website'}'",
                    progress_callback=progress_callback,
                    cancellation_token=cancellation_token,
                    base_progress=0.65,
                    max_progress=0.90,
                )
                parsed2 = self.parse_generation_response(gen_res2)
                screens_raw = parsed2["screens"]
                if parsed2["design_system"]:
                    ds_obj = parsed2["design_system"]
                    if ds_name and isinstance(ds_obj, dict) and not ds_obj.get("name"):
                        ds_obj["name"] = ds_name
                if parsed2["assistant_text"]:
                    parsed["assistant_text"] = (
                        f"{parsed['assistant_text']}\n\n{parsed2['assistant_text']}".strip()
                    )

            # If screens are still empty, check `recover_project_screens` (`list_screens` + `get_project`)
            if not screens_raw:
                screens_raw = self.recover_project_screens(pid, cancellation_token=cancellation_token)

            if not screens_raw:
                err = StitchUnavailableError(
                    "Google Stitch completed without returning any generated screens.",
                    project_id=pid,
                    design_system=ds_name,
                )
                raise err

            self._check_cancelled(cancellation_token)
            if progress_callback:
                try:
                    progress_callback({
                        "design_state": "downloading",
                        "message": f"Downloading {len(screens_raw)} generated screen(s) from Google Stitch...",
                        "progress": 0.90,
                        "progress_pct": 0.90,
                    })
                except Exception:
                    pass

            version_dir = session_path / f"v{version}"
            artifacts = self._materialize_screens(pid, screens_raw, version_dir)

            resolved_title = (
                title
                or artifacts[0].title
                or (ds_obj.get("displayName") if isinstance(ds_obj, dict) else None)
                or "Stitch Website Design"
            )
            session_id = parsed["session_id"] or f"stitch_{pid}"

            bundle = StitchDesignBundle(
                provider="stitch",
                project_id=pid,
                session_id=session_id,
                title=resolved_title,
                prompt=prompt,
                version=version,
                device_type=device_type,
                version_dir=str(version_dir),
                preview_file=artifacts[0].html_path,
                screens=artifacts,
                design_system=ds_obj,
                assistant_text=parsed["assistant_text"],
                suggestions=parsed["suggestions"],
                recovered_after_timeout=recovered_after_timeout,
            )

            manifest_path = version_dir / "stitch_manifest.json"
            manifest_path.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")
            self._save_in_flight_state(
                session_path,
                {
                    "project_id": pid,
                    "title": resolved_title,
                    "prompt": prompt,
                    "design_system": ds_name,
                    "status": "completed",
                    "version": version,
                    "updated_at": time.time(),
                },
            )
            return bundle
        finally:
            with self._global_in_flight_lock:
                self._global_in_flight_projects.pop(pid, None)

    def revise_design(
        self,
        previous_bundle: Union[StitchDesignBundle, Dict[str, Any]],
        revision_prompt: str,
        session_dir: Optional[Union[Path, str]] = None,
        device_type: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> StitchDesignBundle:
        """
        Sends a user revision request to Google Stitch (`edit_screens`), retrieves the
        updated screens, stores them in `v{previous_version + 1}` while preserving all
        earlier versions on disk, and returns the updated `StitchDesignBundle`.
        """
        self._check_cancelled(cancellation_token)
        prev = (
            previous_bundle
            if isinstance(previous_bundle, StitchDesignBundle)
            else StitchDesignBundle.from_dict(previous_bundle)
        )
        pid = self.normalize_project_id(prev.project_id)
        if not pid:
            raise StitchUnavailableError("Cannot revise Stitch design: missing Stitch project_id.")

        target_screen_ids = prev.screen_ids
        if not target_screen_ids:
            existing_screens = self.recover_project_screens(pid, cancellation_token=cancellation_token)
            target_screen_ids = [
                self.normalize_screen_id(str(s.get("name", "")))
                for s in existing_screens
                if isinstance(s, dict) and s.get("name")
            ]

        if not target_screen_ids:
            raise StitchUnavailableError("Cannot revise Stitch design: no existing screen IDs found.")

        dev_type = device_type or prev.device_type or "DESKTOP"
        recovered_after_timeout = False
        try:
            edit_res = self._run_with_heartbeat(
                lambda: self.edit_screens(
                    project_id=pid,
                    selected_screen_ids=target_screen_ids,
                    prompt=revision_prompt,
                    device_type=dev_type,
                ),
                status_prefix=f"Google Stitch is revising '{prev.title or 'website'}'",
                progress_callback=progress_callback,
                cancellation_token=cancellation_token,
            )
            parsed = self.parse_generation_response(edit_res)
        except StitchCancelledError:
            raise
        except StitchUnavailableError as edit_err:
            self._check_cancelled(cancellation_token)
            is_timeout_or_drop = (
                isinstance(edit_err, StitchResponseTimeoutError)
                or "timed out" in str(edit_err).lower()
                or edit_err.failure_category == "network_error"
            )
            if is_timeout_or_drop and not isinstance(edit_err, StitchConnectionTimeoutError):
                recovered_screens = self._poll_for_server_completion(
                    pid,
                    stage_label="design revision",
                    progress_callback=progress_callback,
                    cancellation_token=cancellation_token,
                )
                if recovered_screens:
                    recovered_after_timeout = True
                    parsed = {
                        "screens": recovered_screens,
                        "design_system": prev.design_system,
                        "assistant_text": "Recovered revised Stitch screens after long upstream edit.",
                        "suggestions": [],
                        "project_id": pid,
                        "session_id": prev.session_id or f"stitch_{pid}",
                    }
                else:
                    edit_err.project_id = pid
                    raise
            else:
                edit_err.project_id = pid
                raise

        screens_raw = parsed["screens"]

        if not screens_raw:
            screens_raw = self.recover_project_screens(pid, cancellation_token=cancellation_token)

        if not screens_raw:
            raise StitchUnavailableError(
                "Google Stitch edit_screens did not return any revised screens.",
                project_id=pid,
            )

        self._check_cancelled(cancellation_token)
        new_version = prev.version + 1
        if session_dir is not None:
            base_session_dir = Path(session_dir).resolve()
        elif prev.version_dir:
            base_session_dir = Path(prev.version_dir).resolve().parent
        else:
            base_session_dir = self.config.workspace_root / "stitch_previews" / f"stitch_{pid}"

        version_dir = base_session_dir / f"v{new_version}"
        artifacts = self._materialize_screens(pid, screens_raw, version_dir)

        bundle = StitchDesignBundle(
            provider="stitch",
            project_id=pid,
            session_id=prev.session_id or parsed["session_id"] or f"stitch_{pid}",
            title=prev.title or artifacts[0].title,
            prompt=revision_prompt,
            version=new_version,
            device_type=dev_type,
            version_dir=str(version_dir),
            preview_file=artifacts[0].html_path,
            screens=artifacts,
            design_system=parsed["design_system"] or prev.design_system,
            assistant_text=parsed["assistant_text"],
            suggestions=parsed["suggestions"],
            recovered_after_timeout=recovered_after_timeout,
        )

        manifest_path = version_dir / "stitch_manifest.json"
        manifest_path.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")
        return bundle
