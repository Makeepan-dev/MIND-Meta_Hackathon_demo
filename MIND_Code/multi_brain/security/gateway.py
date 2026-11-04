"""Security and Execution Gateway for MIND Multi-Brain Architecture.

Enforces role-based permissions, Sentinel integrity, approval boundaries,
and audit logging across all tool invocations and brain actions.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from multi_brain.contracts import PermissionTier

logger = logging.getLogger("mind.multi_brain.gateway")


@dataclass
class AuditRecord:
    timestamp: float
    requesting_component: str
    action_type: str
    target: str
    permission_tier: PermissionTier
    status: str
    details: Dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "requesting_component": self.requesting_component,
            "action_type": self.action_type,
            "target": self.target,
            "permission_tier": self.permission_tier.value,
            "status": self.status,
            "details": self._redact_secrets(self.details),
            "error": self.error,
        }

    @staticmethod
    def _redact_secrets(data: Any) -> Any:
        """Redacts sensitive credentials, tokens, or passwords from logs."""
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                if any(sec in k.lower() for sec in ["key", "token", "password", "secret", "auth"]):
                    clean[k] = "[REDACTED]"
                else:
                    clean[k] = AuditRecord._redact_secrets(v)
            return clean
        elif isinstance(data, list):
            return [AuditRecord._redact_secrets(item) for item in data]
        elif isinstance(data, str):
            # Check for generic API key patterns
            if len(data) > 20 and any(prefix in data for prefix in ["sk-", "gsk_", "AIza", "LLM_", "AQ."]):
                return "[REDACTED_API_KEY]"
            return data
        return data


_DEFAULT_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class ExecutionGateway:
    """Central policy enforcement point preventing unauthorized or unsafe operations."""

    def __init__(self, workspace_root: Optional[str] = None) -> None:
        self.workspace_root = os.path.abspath(workspace_root or _DEFAULT_REPO_ROOT)
        self.audit_log: List[AuditRecord] = []
        self._approval_handler: Optional[Callable[[str, str, Dict[str, Any]], bool]] = None
        self._sentinel = self._load_sentinel()

    def _load_sentinel(self) -> Optional[Any]:
        """Optionally binds to existing Sentinel module if available."""
        try:
            from modules.sentinel import Sentinel
            return Sentinel()
        except Exception:
            return None

    def set_approval_handler(self, handler: Callable[[str, str, Dict[str, Any]], bool]) -> None:
        """Sets callback for interactive user approval on consequential actions."""
        self._approval_handler = handler

    def sanitize_input(self, raw_text: str) -> str:
        """Sanitizes text strings using Sentinel rules to prevent shell injection."""
        if self._sentinel and hasattr(self._sentinel, "sanitize_input"):
            return self._sentinel.sanitize_input(raw_text)
        
        # Fallback sanitization
        dangerous = [";", "|", "&&", "$", "`", ">", "<"]
        clean = raw_text
        for char in dangerous:
            clean = clean.replace(char, "")
        return clean

    def validate_path_safety(self, file_path: str) -> bool:
        """Ensures file access stays within allowed directory boundaries."""
        abs_target = os.path.abspath(file_path)
        # Check that it resides inside workspace_root or allowed paths
        return abs_target.startswith(self.workspace_root)

    def authorize_action(
        self,
        action_type: str,
        target_path: str = "",
        tier: PermissionTier = PermissionTier.SAFE,
        bypass_approval_for_tests: bool = False,
    ) -> Any:
        """Convenience method checking path boundary and permission tier authorization."""
        if target_path and not self.validate_path_safety(target_path):
            return type("AuthResult", (), {"is_authorized": False, "reason": f"Path outside workspace boundary: CRITICAL security denial for '{target_path}'"})()
        if tier in (PermissionTier.REQUIRES_APPROVAL, PermissionTier.CRITICAL):
            if bypass_approval_for_tests:
                return type("AuthResult", (), {"is_authorized": True, "reason": "Authorized via test bypass"})()
            return type("AuthResult", (), {"is_authorized": False, "reason": f"Action '{action_type}' requires explicit security approval (tier: {tier.value})"})()
        return type("AuthResult", (), {"is_authorized": True, "reason": "Safe tier permitted"})()

    def authorize_and_execute(
        self,
        requester: str,
        action_name: str,
        permission_tier: PermissionTier,
        func: Callable[[], Any],
        details: Optional[Dict[str, Any]] = None,
        bypass_approval_for_tests: bool = False,
    ) -> Any:
        """
        Validates authorization for an action, records audit trace, and executes.
        Raises PermissionError if unauthorized or rejected.
        """
        details = details or {}
        timestamp = time.time()

        # Step 1: Input sanitization check for string inputs
        for k, v in details.items():
            if isinstance(v, str):
                details[k] = self.sanitize_input(v)

        # Step 2: Check Permission Tier
        if permission_tier in (PermissionTier.REQUIRES_APPROVAL, PermissionTier.CRITICAL):
            approved = False
            if bypass_approval_for_tests:
                approved = True
            elif self._approval_handler:
                approved = self._approval_handler(requester, action_name, details)
            else:
                # Default behavior: Unattended execution of consequential actions is blocked
                approved = False

            if not approved:
                record = AuditRecord(
                    timestamp=timestamp,
                    requesting_component=requester,
                    action_type=action_name,
                    target=details.get("target", "system"),
                    permission_tier=permission_tier,
                    status="DENIED",
                    details=details,
                    error="Action requires approval, but approval was denied or not provided.",
                )
                self.audit_log.append(record)
                logger.warning(f"Gateway DENIED consequential action '{action_name}' requested by '{requester}'")
                raise PermissionError(f"Action '{action_name}' requires explicit approval which was not granted.")

        # Step 3: Execute Action
        try:
            result = func()
            record = AuditRecord(
                timestamp=timestamp,
                requesting_component=requester,
                action_type=action_name,
                target=str(details.get("target", "execution")),
                permission_tier=permission_tier,
                status="SUCCESS",
                details=details,
            )
            self.audit_log.append(record)
            return result
        except Exception as exc:
            record = AuditRecord(
                timestamp=timestamp,
                requesting_component=requester,
                action_type=action_name,
                target=str(details.get("target", "execution")),
                permission_tier=permission_tier,
                status="ERROR",
                details=details,
                error=str(exc),
            )
            self.audit_log.append(record)
            raise

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Returns redacted audit trail."""
        return [record.to_dict() for record in self.audit_log]
