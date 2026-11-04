"""Shared Task Context and Provenance Tracking for Workflows."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from multi_brain.contracts import TaskResult


@dataclass
class TaskContext:
    """
    Context container maintaining original goal, constraints, intermediate outputs,
    and provenance across task boundaries.
    Enforces data minimization: slices context for specific brains.
    """
    original_goal: str
    workflow_id: str
    constraints: Dict[str, Any] = field(default_factory=dict)
    intermediate_outputs: Dict[str, Any] = field(default_factory=dict)
    task_results: Dict[str, TaskResult] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance_ledger: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def store_result(self, task_id: str, result: TaskResult) -> None:
        """Stores a task result, extracts intermediate output and artifacts, and updates ledger."""
        self.task_results[task_id] = result
        if result.output is not None:
            self.intermediate_outputs[task_id] = result.output

        if result.artifacts:
            for art in result.artifacts:
                art_copy = dict(art)
                art_copy["source_task_id"] = task_id
                self.artifacts.append(art_copy)

        self.provenance_ledger.append({
            "task_id": task_id,
            "status": result.status.value,
            "provenance": result.provenance.to_dict() if result.provenance else None,
            "timestamp": time.time(),
        })

    def get_slice_for_task(self, task_id: str, dependency_ids: List[str]) -> Dict[str, Any]:
        """
        Extracts a scoped context slice containing only the data from specified dependencies
        plus the original goal and constraints. Prevents unrestricted data leakage.
        """
        scoped_inputs: Dict[str, Any] = {}
        for dep_id in dependency_ids:
            if dep_id in self.intermediate_outputs:
                scoped_inputs[dep_id] = self.intermediate_outputs[dep_id]

        return {
            "workflow_id": self.workflow_id,
            "original_goal": self.original_goal,
            "constraints": dict(self.constraints),
            "dependency_outputs": scoped_inputs,
            "relevant_artifacts": [
                art for art in self.artifacts if art.get("source_task_id") in dependency_ids
            ],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "original_goal": self.original_goal,
            "constraints": self.constraints,
            "intermediate_outputs": self.intermediate_outputs,
            "artifacts": self.artifacts,
            "provenance_ledger": self.provenance_ledger,
            "created_at": self.created_at,
        }
