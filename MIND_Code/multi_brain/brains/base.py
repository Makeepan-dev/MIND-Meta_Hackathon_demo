"""Base interface and abstraction for Specialist Brains in MIND."""

from __future__ import annotations

import abc
import time
from typing import Any, Dict, List, Optional

from multi_brain.contracts import (
    Capability,
    PermissionTier,
    Provenance,
    TaskRequest,
    TaskResult,
    TaskStatus,
)


class SpecialistBrain(abc.ABC):
    """
    Common contract for all specialist brains in MIND.
    A brain is a specialized domain agent that uses models, tools, and algorithms.
    """

    def __init__(
        self,
        brain_id: str,
        name: str,
        domain: str,
        description: str = "",
        capabilities: Optional[List[Capability]] = None,
        permission_tier: PermissionTier = PermissionTier.SAFE,
    ) -> None:
        if not brain_id or not brain_id.strip():
            raise ValueError("brain_id must be a non-empty string.")
        if not name or not name.strip():
            raise ValueError("name must be a non-empty string.")
        
        self.brain_id = brain_id.strip()
        self.name = name.strip()
        self.domain = domain.strip()
        self.description = description.strip()
        self.capabilities: List[Capability] = capabilities or []
        self.permission_tier = permission_tier
        self._is_enabled = True

    @property
    def is_available(self) -> bool:
        """Determines if the brain is currently ready and able to execute tasks."""
        if not self._is_enabled:
            return False
        return self.check_availability()

    def check_availability(self) -> bool:
        """Hook for subclasses to verify backend service, model, or hardware availability."""
        return True

    def set_enabled(self, enabled: bool) -> None:
        """Enables or disables this brain instance."""
        self._is_enabled = enabled

    def has_capability(self, capability_name: str) -> bool:
        """Checks if this brain declares support for a specific capability."""
        cap_clean = capability_name.strip().lower()
        return any(c.name.lower() == cap_clean and c.is_available for c in self.capabilities)

    def get_declared_capabilities(self) -> List[Capability]:
        """Returns the list of declared capabilities."""
        return list(self.capabilities)

    def execute(self, request: TaskRequest) -> TaskResult:
        """
        Executes a task request within this specialist domain.
        Wraps domain execution with timing and error isolation.
        """
        start_time = time.time()
        
        if not self.is_available:
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error=f"Specialist brain '{self.name}' ({self.brain_id}) is currently unavailable.",
                provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
                execution_time_seconds=time.time() - start_time,
            )

        try:
            result = self._execute_task(request)
            result.execution_time_seconds = time.time() - start_time
            if result.provenance is None:
                result.provenance = Provenance(brain_id=self.brain_id, confidence=1.0)
            return result
        except Exception as exc:
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error=f"Execution error in {self.brain_id}: {str(exc)}",
                provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
                execution_time_seconds=time.time() - start_time,
            )

    @abc.abstractmethod
    def _execute_task(self, request: TaskRequest) -> TaskResult:
        """Domain-specific task execution logic. Must be implemented by specialist subclasses."""
        pass

    def to_metadata(self) -> Dict[str, Any]:
        """Returns serializable metadata describing this brain's specifications and status."""
        return {
            "brain_id": self.brain_id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "permission_tier": self.permission_tier.value,
            "is_available": self.is_available,
            "is_enabled": self._is_enabled,
            "capabilities": [c.to_dict() for c in self.capabilities],
        }
