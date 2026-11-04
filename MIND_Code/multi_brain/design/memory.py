"""
MIND Design Memory.
Persists project design specifications, token history, evaluation reports, and user preferences.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from multi_brain.design.contracts import DesignResult, DesignSpecification

logger = logging.getLogger("mind.multi_brain.design.memory")


class DesignMemory:
    """Stores design system tokens and session context across iterations."""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = storage_dir or (Path.cwd() / "Workspace" / "design_memory")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def save_session_design(self, session_id: str, design_result: DesignResult) -> Path:
        """Persists the design result and tokens for a given session."""
        session_file = self.storage_dir / f"{session_id}_design.json"
        payload = {
            "session_id": session_id,
            "provider": design_result.provider,
            "version": design_result.version,
            "specification": design_result.specification.to_dict(),
            "preview_file": design_result.preview_file,
            "preview_url": design_result.preview_url,
            "evaluation": design_result.evaluation.to_dict() if design_result.evaluation else None,
        }
        session_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._cache[session_id] = payload
        return session_file

    def get_session_design(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves design context for an active or previous session."""
        if session_id in self._cache:
            return self._cache[session_id]
        
        session_file = self.storage_dir / f"{session_id}_design.json"
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                self._cache[session_id] = data
                return data
            except Exception as e:
                logger.warning("Could not read design memory for %s: %s", session_id, e)
        return None
