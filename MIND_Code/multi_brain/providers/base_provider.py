"""Base interface and normalization layer for all AI and tool providers in MIND."""

from __future__ import annotations

import abc
import logging
import time
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger("mind.multi_brain.providers")


class BaseProviderAdapter(abc.ABC):
    """
    Common abstraction for inference and generation providers.
    Normalizes input preparation, execution, streaming, errors, and metadata.
    Ensures credentials and sensitive tokens are never leaked into logs.
    """

    def __init__(
        self,
        provider_id: str,
        name: str,
        execution_mode: str = "local",
        supported_modalities: Optional[List[str]] = None,
        is_cloud: bool = False,
    ) -> None:
        if not provider_id or not provider_id.strip():
            raise ValueError("provider_id must be non-empty.")
        self.provider_id = provider_id.strip()
        self.name = name.strip()
        self.execution_mode = execution_mode
        self.supported_modalities = supported_modalities or ["text"]
        self.is_cloud = is_cloud
        self._is_enabled = True

    @property
    def is_available(self) -> bool:
        """Checks if the provider is enabled and structurally ready."""
        if not self._is_enabled:
            return False
        health = self.check_health()
        return health.get("status") in ("healthy", "ready", "degraded")

    def set_enabled(self, enabled: bool) -> None:
        self._is_enabled = enabled

    @abc.abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Verifies connection to backend daemon, API, or hardware."""
        pass

    @abc.abstractmethod
    def prepare_input(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes task parameters into provider-specific request format."""
        pass

    @abc.abstractmethod
    def execute(self, prepared_input: Dict[str, Any]) -> Dict[str, Any]:
        """Executes task synchronously and returns standardized output payload."""
        pass

    def execute_stream(self, prepared_input: Dict[str, Any]) -> Generator[str, None, None]:
        """Optional streaming execution hook."""
        res = self.execute(prepared_input)
        yield str(res.get("output", ""))

    def cancel(self, task_id: str) -> bool:
        """Attempts to cancel in-flight task."""
        return False

    def normalize_error(self, error: Exception) -> str:
        """Converts raw provider errors into sanitized, actionable error strings."""
        raw_msg = str(error)
        # Redact any accidental API key patterns
        clean_msg = raw_msg
        for prefix in ["LLM_", "sk-", "gsk_", "AIza"]:
            if prefix in clean_msg:
                import re
                clean_msg = re.sub(rf"{prefix}[A-Za-z0-9_-]+", "[REDACTED_KEY]", clean_msg)
        return f"{self.name} Provider Error: {clean_msg}"

    def get_metadata(self) -> Dict[str, Any]:
        """Returns serializable provider descriptor."""
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "execution_mode": self.execution_mode,
            "is_cloud": self.is_cloud,
            "is_available": self.is_available,
            "is_enabled": self._is_enabled,
            "supported_modalities": self.supported_modalities,
        }
