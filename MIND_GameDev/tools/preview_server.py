"""
MIND Universal Development Studio — Workspace Preview Server.
Provides a secured, ephemeral local HTTP server bound to 127.0.0.1 for live website
rendering, responsive testing, and hot preview updates during AI synthesis.
"""

from __future__ import annotations

import functools
import http.server
import logging
import os
import socketserver
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mind.tools.preview_server")


class _SecurePreviewRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP request handler restricted strictly to an approved project directory.
    Rejects directory traversal, blocks sensitive files (.env, keys, git, py),
    and disables client-side caching so live edits immediately reflect.
    """

    server_version = "MIND-Preview/2.5"

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress routine GET logging spam; only log errors
        if args and str(args[0]).startswith(("4", "5")):
            logger.warning("Preview server HTTP error: " + (format % args))

    def end_headers(self) -> None:
        # Prevent browser caching so live development updates are instantly visible
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        """Enforces directory confinement and blocks access to sensitive files."""
        # 1. Block sensitive paths
        clean_path = path.split("?")[0].split("#")[0].strip()
        lower_path = clean_path.lower()

        # Reject hidden files, credentials, source code, and virtualenvs
        blocked_extensions = (".env", ".key", ".pem", ".py", ".pyc", ".db", ".sqlite", ".git")
        blocked_names = (".env", ".git", "venv", "__pycache__", "config.py")

        for part in Path(clean_path).parts:
            if part in blocked_names or any(part.endswith(ext) for ext in blocked_extensions):
                self.send_error(403, "Access to this file type is forbidden by MIND Security Gateway.")
                return ""

        # 2. Translate within directory
        translated = super().translate_path(path)
        base_dir = os.path.abspath(self.directory)

        # 3. Path containment check
        try:
            rel = os.path.relpath(translated, base_dir)
            if rel.startswith("..") or os.path.isabs(rel):
                self.send_error(403, "Path traversal attempt blocked by MIND Security Gateway.")
                return ""
        except Exception:
            self.send_error(403, "Invalid path resolution.")
            return ""

        return translated


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class WorkspacePreviewServer:
    """
    Manages the lifecycle of a secure, local preview server for a specific project.
    """

    _active_servers: List["WorkspacePreviewServer"] = []
    _lock = threading.Lock()

    def __init__(self, project_dir: Path | str, port: int = 0) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.port = port
        self.server: Optional[ThreadedTCPServer] = None
        self.thread: Optional[threading.Thread] = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running and self.server is not None

    def start(self) -> str:
        """Starts the server on 127.0.0.1 and returns the base URL."""
        if self.is_running:
            return self.get_url()

        if not self.project_dir.exists() or not self.project_dir.is_dir():
            raise FileNotFoundError(f"Project directory does not exist: {self.project_dir}")

        handler = functools.partial(_SecurePreviewRequestHandler, directory=str(self.project_dir))

        # Bind to 127.0.0.1 strictly (no external LAN exposure)
        self.server = ThreadedTCPServer(("127.0.0.1", self.port), handler)
        # Retrieve the assigned port if dynamically allocated (port=0)
        self.port = self.server.server_address[1]

        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
            name=f"MIND_PreviewServer_{self.port}",
        )
        self.thread.start()
        self._is_running = True

        with self._lock:
            WorkspacePreviewServer._active_servers.append(self)

        logger.info(f"Workspace preview server started at {self.get_url()} for {self.project_dir}")
        return self.get_url()

    def get_url(self, relative_path: str = "index.html") -> str:
        """Returns the full HTTP preview URL for a given file in the project."""
        rel = relative_path.lstrip("/\\").replace("\\", "/")
        return f"http://127.0.0.1:{self.port}/{rel}"

    def stop(self) -> None:
        """Stops the preview server and releases ports."""
        if not self.is_running:
            return

        self._is_running = False
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
        except Exception as e:
            logger.debug(f"Error shutting down preview server: {e}")
        finally:
            self.server = None
            self.thread = None
            with self._lock:
                if self in WorkspacePreviewServer._active_servers:
                    WorkspacePreviewServer._active_servers.remove(self)
        logger.info(f"Workspace preview server on port {self.port} stopped.")

    def __enter__(self) -> "WorkspacePreviewServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    @classmethod
    def stop_all(cls) -> None:
        """Global cleanup utility to ensure all preview servers terminate on app exit."""
        with cls._lock:
            servers = list(cls._active_servers)
        for s in servers:
            try:
                s.stop()
            except Exception:
                pass
