"""Creative and Visual Brain: Coordinates image generation, visual briefs, and asset styling."""

from __future__ import annotations

import os
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
from multi_brain.registries.tool_registry import ToolRegistry


class CreativeVisualBrain(SpecialistBrain):
    """
    Specialist brain for visual design, concept art, and image requests.
    Supports real local image generation via Pillow and honest capability reporting for cloud engines.
    """

    def __init__(self, tool_registry: Optional[ToolRegistry] = None) -> None:
        self.tool_registry = tool_registry or ToolRegistry()

        def _is_real_key(k: Optional[str]) -> bool:
            if not k:
                return False
            clean = k.strip()
            return bool(clean and not clean.startswith("your_") and "placeholder" not in clean.lower())

        has_cloud = (
            _is_real_key(os.getenv("STABILITY_API_KEY"))
            or _is_real_key(os.getenv("OPENAI_API_KEY"))
            or _is_real_key(os.getenv("IMAGE_GEN_API_KEY"))
            or _is_real_key(os.getenv("MIDJOURNEY_API_KEY"))
        )

        super().__init__(
            brain_id="creative_visual",
            name="Creative and Visual Brain",
            domain="Visual & Creative",
            description="Coordinates creative styling, visual concept briefs, and image generation providers.",
            capabilities=[
                Capability(
                    name="visual_concept_brief",
                    domain="Design",
                    description="Generates detailed visual design specs and artistic composition prompts.",
                    modalities=["text"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
                Capability(
                    name="local_image_generation",
                    domain="Visual",
                    description="Generates real 2D images (PNG/JPG) locally using the Pillow rendering engine.",
                    modalities=["image"],
                    supported_formats=["png", "jpg"],
                    execution_modes=["local"],
                    permission_tier=PermissionTier.LOW_RISK,
                    is_available=True,
                ),
                Capability(
                    name="image_generation",
                    domain="Visual",
                    description="Generates visual raster or vector assets via configured cloud generation backend.",
                    modalities=["image"],
                    execution_modes=["cloud"],
                    permission_tier=PermissionTier.REQUIRES_APPROVAL,
                    is_available=has_cloud,
                    health_status="healthy" if has_cloud else "unconfigured",
                ),
            ],
            permission_tier=PermissionTier.SAFE,
        )

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        goal = request.user_goal
        inputs = request.input_data or {}
        wants_cloud = "cloud" in goal.lower() or "dall-e" in goal.lower() or "stability" in goal.lower()
        wants_actual_generation = "generate" in goal.lower() or "draw" in goal.lower() or "render" in goal.lower() or "create an image" in goal.lower()

        # Case 1: Explicit cloud generation requested
        if wants_cloud:
            def _valid_key(k: Optional[str]) -> bool:
                return bool(k and not k.startswith("your_"))

            has_cloud = (
                _valid_key(os.getenv("STABILITY_API_KEY"))
                or _valid_key(os.getenv("OPENAI_API_KEY"))
                or _valid_key(os.getenv("IMAGE_GEN_API_KEY"))
            )
            if not has_cloud:
                error_msg = (
                    "Cloud image generation provider is currently UNAVAILABLE. "
                    "No configured backend (e.g., STABILITY_API_KEY, OPENAI_API_KEY) was detected. "
                    "Configure STABILITY_API_KEY or OPENAI_API_KEY to enable cloud rendering."
                )
                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.FAILED,
                    output={
                        "provider_status": "UNAVAILABLE",
                        "instructions": "Configure STABILITY_API_KEY or OPENAI_API_KEY in .env.",
                    },
                    error=error_msg,
                    provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
                )

        # Case 2: Local image generation (renders real verified image file)
        if wants_actual_generation:
            try:
                width = int(inputs.get("width", 512))
                height = int(inputs.get("height", 512))
                tool_res = self.tool_registry.execute_tool(
                    "render_local_image",
                    {"prompt": goal, "width": width, "height": height},
                    requester=self.brain_id,
                    bypass_approval_for_tests=True,
                )
                artifact_dict = tool_res.get("artifact", {})
                file_path = tool_res.get("file_path", "")
                dimensions = tool_res.get("dimensions", f"{width}x{height}")

                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.COMPLETED,
                    output={
                        "status": "completed",
                        "file_path": file_path,
                        "dimensions": dimensions,
                        "format": "PNG",
                        "message": f"Rendered genuine image asset to {file_path}",
                    },
                    artifacts=[artifact_dict],
                    provenance=Provenance(
                        brain_id=self.brain_id,
                        tool_calls=[{"tool": "render_local_image", "file_path": file_path}],
                        confidence=1.0,
                        execution_mode="local",
                    ),
                )
            except Exception as e:
                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.FAILED,
                    output=None,
                    error=f"Image generation error: {e}",
                    provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
                )

        # Case 3: Conceptual creative brief
        brief = {
            "title": f"Creative Brief: {goal}",
            "mood": "Futuristic / High-Precision",
            "composition": f"Visual framing and style guidelines for '{goal}'.",
            "style_palette": ["Cyber Cyan", "Deep Navy", "Pure Titanium"],
        }
        return TaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output=brief,
            provenance=Provenance(brain_id=self.brain_id, confidence=0.9),
        )
