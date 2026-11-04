"""
MIND Universal Development Studio — Persistent SQLite Session Memory.
Maintains cross-process continuity for active projects, requirements,
conversation turns, pending clarifications, and tool verification history.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import GameDevConfig

CURRENT_SCHEMA_VERSION = 1


@dataclass
class SessionRecord:
    """Snapshot of an active project session."""
    project_name: str
    project_path: str
    domain: str = "website"
    updated_at: float = field(default_factory=time.time)
    requirements: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "project_path": self.project_path,
            "domain": self.domain,
            "updated_at": self.updated_at,
            "requirements": self.requirements,
            "metadata": self.metadata,
        }


class SessionMemory:
    """
    Persistent SQLite database manager with WAL mode for storing and recovering
    project context, conversation history, and tool execution evidence across sessions.
    """

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            # Default to a safe user application directory
            base_app_dir = Path.home() / ".mind"
            base_app_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_app_dir / "session_memory.db"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Creates a SQLite connection with timeout and WAL journal mode."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

    def _init_db(self) -> None:
        """Initializes tables and migrates schema safely."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Schema versioning table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            if not row:
                cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (CURRENT_SCHEMA_VERSION,))

            # Active project session table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS active_session (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    project_name TEXT NOT NULL,
                    project_path TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    requirements_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
            """)

            # Conversation history turns table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    resolved_text TEXT NOT NULL,
                    intent TEXT NOT NULL DEFAULT '',
                    target TEXT DEFAULT NULL,
                    workspace TEXT DEFAULT NULL,
                    entities_json TEXT NOT NULL DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
            """)

            # Pending clarifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_clarifications (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    slot_name TEXT NOT NULL,
                    question TEXT NOT NULL,
                    original_intent TEXT NOT NULL,
                    partial_goal TEXT NOT NULL,
                    options_json TEXT NOT NULL DEFAULT '[]',
                    answers_json TEXT NOT NULL DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
            """)

            # Tool execution and verification history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tool_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    target_path TEXT DEFAULT NULL,
                    status TEXT NOT NULL,
                    output TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    verified INTEGER NOT NULL DEFAULT 0,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
            """)

            # Pending design proposals table (persists design approval state across turns/restarts)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_design_proposals (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    project_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'awaiting_approval',
                    spec_json TEXT NOT NULL DEFAULT '{}',
                    plan_json TEXT NOT NULL DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()

    # ─── Active Project Management ──────────────────────────────────────────

    def save_active_project(
        self,
        project_name: str,
        project_path: str,
        domain: str = "website",
        requirements: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Stores or updates the single active project record."""
        req_json = json.dumps(requirements or {})
        meta_json = json.dumps(metadata or {})
        now = time.time()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO active_session (id, project_name, project_path, domain, updated_at, requirements_json, metadata_json)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_name = excluded.project_name,
                    project_path = excluded.project_path,
                    domain = excluded.domain,
                    updated_at = excluded.updated_at,
                    requirements_json = excluded.requirements_json,
                    metadata_json = excluded.metadata_json
            """, (project_name, str(Path(project_path).resolve()), domain, now, req_json, meta_json))
            conn.commit()

    def get_active_project(self, verify_exists: bool = True) -> Optional[SessionRecord]:
        """
        Retrieves the persisted active project.
        If verify_exists is True, checks that the directory actually exists on disk.
        If the directory no longer exists, clears the stale session and returns None.
        """
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM active_session WHERE id = 1").fetchone()
            if not row:
                return None

            p_path = Path(row["project_path"])
            if verify_exists and not p_path.exists():
                # Directory has been deleted or moved externally; invalidate stale memory
                conn.execute("DELETE FROM active_session WHERE id = 1")
                conn.commit()
                return None

            try:
                reqs = json.loads(row["requirements_json"])
            except Exception:
                reqs = {}
            try:
                meta = json.loads(row["metadata_json"])
            except Exception:
                meta = {}

            return SessionRecord(
                project_name=row["project_name"],
                project_path=row["project_path"],
                domain=row["domain"],
                updated_at=row["updated_at"],
                requirements=reqs,
                metadata=meta,
            )

    def clear_active_project(self) -> None:
        """Clears the active project session."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM active_session WHERE id = 1")
            conn.commit()

    # ─── Conversation Turn Storage ──────────────────────────────────────────

    def record_turn(
        self,
        turn_id: int,
        role: str,
        raw_text: str,
        resolved_text: str,
        intent: str = "",
        target: Optional[str] = None,
        workspace: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Persists a single conversation turn."""
        now = timestamp or time.time()
        ent_json = json.dumps(entities or {})
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO conversation_turns
                (turn_id, role, raw_text, resolved_text, intent, target, workspace, entities_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (turn_id, role, raw_text, resolved_text, intent, target, workspace, ent_json, now))
            conn.commit()

    def get_recent_turns(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves the last N conversation turns in chronological order."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM conversation_turns
                ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()

            turns = []
            for r in reversed(rows):
                try:
                    ent = json.loads(r["entities_json"])
                except Exception:
                    ent = {}
                turns.append({
                    "turn_id": r["turn_id"],
                    "role": r["role"],
                    "raw_text": r["raw_text"],
                    "resolved_text": r["resolved_text"],
                    "intent": r["intent"],
                    "target": r["target"],
                    "workspace": r["workspace"],
                    "entities": ent,
                    "timestamp": r["timestamp"],
                })
            return turns

    # ─── Pending Clarification Management ───────────────────────────────────

    def save_pending_clarification(
        self,
        slot_name: str,
        question: str,
        original_intent: str,
        partial_goal: str,
        options: Optional[List[str]] = None,
        answers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Stores outstanding clarification state."""
        opt_json = json.dumps(options or [])
        ans_json = json.dumps(answers or {})
        now = time.time()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO pending_clarifications
                (id, slot_name, question, original_intent, partial_goal, options_json, answers_json, timestamp)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    slot_name = excluded.slot_name,
                    question = excluded.question,
                    original_intent = excluded.original_intent,
                    partial_goal = excluded.partial_goal,
                    options_json = excluded.options_json,
                    answers_json = excluded.answers_json,
                    timestamp = excluded.timestamp
            """, (slot_name, question, original_intent, partial_goal, opt_json, ans_json, now))
            conn.commit()

    def get_pending_clarification(self) -> Optional[Dict[str, Any]]:
        """Retrieves outstanding clarification state if present."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM pending_clarifications WHERE id = 1").fetchone()
            if not row:
                return None
            try:
                opts = json.loads(row["options_json"])
            except Exception:
                opts = []
            try:
                ans = json.loads(row["answers_json"])
            except Exception:
                ans = {}
            return {
                "slot_name": row["slot_name"],
                "question": row["question"],
                "original_intent": row["original_intent"],
                "partial_goal": row["partial_goal"],
                "options": opts,
                "answers": ans,
                "timestamp": row["timestamp"],
            }

    def clear_pending_clarification(self) -> None:
        """Clears outstanding clarification record."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM pending_clarifications WHERE id = 1")
            conn.commit()

    # ─── Pending Design Approval Management ──────────────────────────────────

    def save_pending_design(
        self,
        project_name: str,
        title: str,
        spec_dict: Dict[str, Any],
        plan_dict: Dict[str, Any],
        version: int = 1,
        status: str = "awaiting_approval",
    ) -> None:
        """Stores pending design proposal requiring explicit user approval."""
        spec_json = json.dumps(spec_dict)
        plan_json = json.dumps(plan_dict)
        now = time.time()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO pending_design_proposals
                (id, project_name, title, version, status, spec_json, plan_json, timestamp)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_name = excluded.project_name,
                    title = excluded.title,
                    version = excluded.version,
                    status = excluded.status,
                    spec_json = excluded.spec_json,
                    plan_json = excluded.plan_json,
                    timestamp = excluded.timestamp
            """, (project_name, title, version, status, spec_json, plan_json, now))
            conn.commit()

    def get_pending_design(self) -> Optional[Dict[str, Any]]:
        """Retrieves pending design proposal if one is awaiting approval."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM pending_design_proposals WHERE id = 1").fetchone()
            if not row:
                return None
            try:
                spec = json.loads(row["spec_json"])
            except Exception:
                spec = {}
            try:
                plan = json.loads(row["plan_json"])
            except Exception:
                plan = {}
            return {
                "project_name": row["project_name"],
                "title": row["title"],
                "version": row["version"],
                "status": row["status"],
                "spec": spec,
                "plan": plan,
                "timestamp": row["timestamp"],
            }

    def clear_pending_design(self) -> None:
        """Clears pending design proposal upon user approval or cancellation."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM pending_design_proposals WHERE id = 1")
            conn.commit()

    # ─── Tool Executions & Evidence ─────────────────────────────────────────

    def record_tool_execution(
        self,
        action: str,
        target_path: Optional[str],
        status: str,
        output: str = "",
        error: str = "",
        verified: bool = False,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Records a tool operation outcome and verification evidence."""
        data_json = json.dumps(data or {})
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO tool_executions
                (action, target_path, status, output, error, verified, data_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (action, target_path, status, output, error, 1 if verified else 0, data_json, time.time()))
            conn.commit()

    def get_recent_tool_executions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves recent tool executions for diagnostic reference."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM tool_executions ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
            results = []
            for r in rows:
                try:
                    dj = json.loads(r["data_json"])
                except Exception:
                    dj = {}
                results.append({
                    "action": r["action"],
                    "target_path": r["target_path"],
                    "status": r["status"],
                    "output": r["output"],
                    "error": r["error"],
                    "verified": bool(r["verified"]),
                    "data": dj,
                    "timestamp": r["timestamp"],
                })
            return results
