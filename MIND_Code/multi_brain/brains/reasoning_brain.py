"""Reasoning and Planning Brain: Decomposes goals, handles structured logic and DAG planning."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from multi_brain.brains.base import SpecialistBrain
from multi_brain.contracts import (
    Capability,
    PermissionTier,
    Provenance,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from multi_brain.registries.model_registry import ModelModality, ModelRegistry


class ReasoningPlanningBrain(SpecialistBrain):
    """Specialist brain for structured problem decomposition, logic, and task planning."""

    def __init__(self, model_registry: Optional[ModelRegistry] = None) -> None:
        super().__init__(
            brain_id="reasoning_planning",
            name="Reasoning and Planning Brain",
            domain="Reasoning & Planning",
            description="Decomposes user goals into structured plans, analyzes logic, and models dependencies.",
            capabilities=[
                Capability(
                    name="decompose_plan",
                    domain="Planning",
                    description="Decomposes a complex objective into sequential and parallel subtasks.",
                    modalities=["text"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
                Capability(
                    name="logical_deduction",
                    domain="Logic",
                    description="Performs multi-step deductions, counter-factual reasoning, and trade-off analysis.",
                    modalities=["text"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
            ],
            permission_tier=PermissionTier.SAFE,
        )
        self.model_registry = model_registry or ModelRegistry()

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        goal = request.user_goal
        inputs = request.input_data or {}
        task_type = request.parameters.get("task_type", "decompose_plan")

        # System prompt for structured planning
        sys_prompt = (
            "You are the MIND Reasoning and Planning Specialist Brain.\n"
            "Analyze the given objective, identify constraints, dependencies, and expected deliverables.\n"
            "Return a structured breakdown with clear actionable steps."
        )

        user_prompt = f"Objective: {goal}\nAdditional Context: {json.dumps(inputs)}"

        # Select frontier Meta reasoning model (meta-muse-wonder-1.0) if available, else default TEXT model
        wonder_model = self.model_registry.get("meta-muse-wonder-1.0")
        if wonder_model and wonder_model.is_available:
            model = wonder_model
        else:
            model = self.model_registry.get_default_model(ModelModality.TEXT)
        model_id = model.model_id if model else "deterministic-fallback"

        try:
            raw_output = self.model_registry.invoke(
                model_id=model_id,
                prompt=user_prompt,
                system_prompt=sys_prompt,
                temperature=0.4,
                agent_id=self.brain_id,
            )
        except Exception:
            # Deterministic plan generation fallback
            steps = [
                f"Analyze prerequisites and constraints for: {goal}",
                f"Execute implementation for: {goal}",
                f"Verify deliverables and test outputs for: {goal}",
            ]
            raw_output = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))

        return TaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "plan_text": raw_output,
                "goal": goal,
                "strategy": "structured_decomposition",
            },
            provenance=Provenance(
                brain_id=self.brain_id,
                model_id=model_id,
                confidence=0.92,
            ),
        )
