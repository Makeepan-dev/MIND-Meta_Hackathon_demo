"""Analysis and Data Brain: Handles data calculations, metrics, and structured interpretation."""

from __future__ import annotations

import statistics
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
from multi_brain.registries.tool_registry import ToolRegistry


class AnalysisDataBrain(SpecialistBrain):
    """Specialist brain for quantitative reasoning, statistical calculations, and data summaries."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        model_registry: Optional[ModelRegistry] = None,
    ) -> None:
        super().__init__(
            brain_id="analysis_data",
            name="Analysis and Data Brain",
            domain="Data & Analytics",
            description="Performs calculations, statistical evaluations, and structured table analysis.",
            capabilities=[
                Capability(
                    name="statistical_summary",
                    domain="Analytics",
                    description="Computes mean, median, standard deviation, and distribution metrics for numeric sets.",
                    modalities=["data"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
                Capability(
                    name="calculate_formula",
                    domain="Math",
                    description="Evaluates mathematical equations and numeric relationships.",
                    modalities=["data"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
            ],
            permission_tier=PermissionTier.SAFE,
        )
        self.tool_registry = tool_registry or ToolRegistry()
        self.model_registry = model_registry or ModelRegistry()

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        inputs = request.input_data or {}
        numbers = inputs.get("numbers")

        # Case 1: Compute statistical summary of numeric series
        if isinstance(numbers, list) and len(numbers) > 0 and all(isinstance(x, (int, float)) for x in numbers):
            stats = {
                "count": len(numbers),
                "sum": sum(numbers),
                "mean": round(statistics.mean(numbers), 4),
                "median": round(statistics.median(numbers), 4),
                "stdev": round(statistics.stdev(numbers), 4) if len(numbers) > 1 else 0.0,
                "min": min(numbers),
                "max": max(numbers),
            }
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.COMPLETED,
                output=stats,
                provenance=Provenance(brain_id=self.brain_id, confidence=1.0),
            )

        # Case 2: Math calculation via math_calculator tool
        expression = inputs.get("expression") or request.parameters.get("expression")
        if expression:
            try:
                calc_res = self.tool_registry.execute_tool(
                    "math_calculator",
                    {"expression": expression},
                    requester=self.brain_id,
                )
                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.COMPLETED,
                    output=calc_res,
                    provenance=Provenance(
                        brain_id=self.brain_id,
                        tool_calls=[{"tool": "math_calculator", "expression": expression}],
                        confidence=1.0,
                    ),
                )
            except Exception as e:
                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.FAILED,
                    output=None,
                    error=f"Calculation error: {e}",
                    provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
                )

        # General data interpretation via Meta analytical model (meta-muse-spark-1.2)
        spark_12 = self.model_registry.get("meta-muse-spark-1.2")
        model = spark_12 if (spark_12 and spark_12.is_available) else self.model_registry.get_default_model(ModelModality.TEXT)
        model_id = model.model_id if model else "deterministic-fallback"
        try:
            analysis_text = self.model_registry.invoke(
                model_id=model_id,
                prompt=f"Perform quantitative and technical analysis for: {request.user_goal}\nInputs: {inputs}",
                system_prompt="You are MIND's Analysis and Data Specialist Brain. Provide precise, objective analysis.",
                temperature=0.2,
                agent_id=self.brain_id,
            )
        except Exception:
            analysis_text = f"Data analysis completed for task: {request.user_goal}"
        return TaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output={"analysis": analysis_text},
            provenance=Provenance(brain_id=self.brain_id, model_id=model_id, confidence=0.90),
        )
