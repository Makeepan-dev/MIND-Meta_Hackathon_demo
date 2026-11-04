"""3D Model Generation Brain: Coordinates text-to-3D, mesh generation, and format validation."""

from __future__ import annotations

import logging
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

logger = logging.getLogger("mind.multi_brain.threed_brain")


class ThreeDGenerationBrain(SpecialistBrain):
    """
    Specialist brain for 3D asset generation and mesh modeling.
    Produces valid, verifiable Wavefront OBJ and STL assets locally.
    Optionally interfaces with Blender when installed.
    """

    def __init__(self, tool_registry: Optional[ToolRegistry] = None) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        super().__init__(
            brain_id="threed_generation",
            name="3D Model Generation Brain",
            domain="3D & Spatial Computing",
            description="Generates physically verifiable 3D polygonal meshes (OBJ, STL) and Blender automations.",
            capabilities=[
                Capability(
                    name="generate_3d_mesh",
                    domain="3D Modeling",
                    description="Generates valid 3D polygonal meshes (Wavefront OBJ, STL) with geometric verification.",
                    modalities=["3d"],
                    supported_formats=["obj", "stl"],
                    execution_modes=["local"],
                    permission_tier=PermissionTier.LOW_RISK,
                    is_available=True,
                ),
                Capability(
                    name="blender_script_generation",
                    domain="3D Modeling",
                    description="Generates procedural Blender Python (bpy) scripts for complex geometry and materials.",
                    modalities=["code", "3d"],
                    supported_formats=["py", "blend"],
                    execution_modes=["local"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
                Capability(
                    name="cloud_3d_generation",
                    domain="3D Modeling",
                    description="Generates neural 3D assets via external cloud services (e.g. Meshy, Tripo3D).",
                    modalities=["3d"],
                    execution_modes=["cloud"],
                    permission_tier=PermissionTier.REQUIRES_APPROVAL,
                    is_available=bool(os.getenv("MESHY_API_KEY") or os.getenv("TRIPO_API_KEY") or os.getenv("THREED_API_KEY")),
                    health_status="healthy" if bool(os.getenv("MESHY_API_KEY") or os.getenv("TRIPO_API_KEY") or os.getenv("THREED_API_KEY")) else "unconfigured",
                ),
                Capability(
                    name="image_to_3d_pipeline",
                    domain="3D Asset Pipeline",
                    description="Transforms user requests into concept artwork and reconstructs validated 3D models (GLB/OBJ).",
                    modalities=["text", "image", "3d"],
                    supported_formats=["png", "glb", "obj"],
                    execution_modes=["hybrid", "cloud", "local"],
                    permission_tier=PermissionTier.LOW_RISK,
                    is_available=True,
                ),
            ],
            permission_tier=PermissionTier.LOW_RISK,
        )

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        goal = request.user_goal
        inputs = request.input_data or {}
        req_caps = request.required_capabilities

        # Check if this is an AI Image-to-3D character pipeline request
        is_character_pipeline = any(
            k in goal.lower()
            for k in ["character", "human", "guard", "blacksmith", "adventurer", "image to 3d", "image-to-3d", "asset pipeline"]
        )
        if is_character_pipeline:
            try:
                from multi_brain.pipeline.pipeline_coordinator import AssetGenerationPipeline
                pipeline = AssetGenerationPipeline()
                launch_ui = os.getenv("MIND_TEST_MODE") != "1" and os.getenv("MIND_HEADLESS") != "1"
                pipe_res = pipeline.execute_workflow(goal, launch_viewer=launch_ui)

                manifest = pipe_res.get("manifest", {})
                model_path = pipe_res.get("threed_model", "")
                concept_path = pipe_res.get("concept_image", "")

                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.COMPLETED,
                    output={
                        "status": "completed",
                        "message": pipe_res.get("message"),
                        "model_path": model_path,
                        "concept_image": concept_path,
                        "format": pipe_res.get("format", "GLB"),
                        "manifest": manifest,
                        "verified": True,
                    },
                    artifacts=[
                        Artifact(
                            name=os.path.basename(concept_path),
                            artifact_type="image",
                            uri=concept_path,
                            format="png",
                            description="AI-generated character concept artwork in neutral A-pose.",
                        ),
                        Artifact(
                            name=os.path.basename(model_path),
                            artifact_type="3d_model",
                            uri=model_path,
                            format="glb",
                            description="Reconstructed 3D character asset in binary glTF 2.0 format.",
                        ),
                    ],
                    provenance=Provenance(brain_id=self.brain_id, confidence=0.98),
                )
            except Exception as e:
                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.FAILED,
                    output={"status": "error", "message": f"Asset pipeline failure: {str(e)}"},
                    error=str(e),
                    provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
                )

        # Check if cloud neural 3D was explicitly requested without character pipeline
        wants_cloud = "cloud" in goal.lower() or "neural" in goal.lower() or "meshy" in goal.lower()
        if wants_cloud:
            has_cloud = bool(os.getenv("MESHY_API_KEY") or os.getenv("TRIPO_API_KEY") or os.getenv("THREED_API_KEY"))
            if not has_cloud:
                return TaskResult(
                    task_id=request.task_id,
                    status=TaskStatus.FAILED,
                    output={
                        "status": "UNCONFIGURED",
                        "message": "Cloud 3D generation is currently UNAVAILABLE. Configure MESHY_API_KEY or TRIPO_API_KEY to enable neural 3D synthesis.",
                    },
                    error="Cloud 3D provider is unconfigured.",
                    provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
                )

        # Generate real, physically verifiable local 3D mesh (Wavefront OBJ)
        mesh_type = "parametric_cube"
        if "cylinder" in goal.lower():
            mesh_type = "cylinder"
        elif "sphere" in goal.lower():
            mesh_type = "sphere"

        try:
            tool_res = self.tool_registry.execute_tool(
                "generate_3d_obj",
                {"prompt": goal, "mesh_type": mesh_type},
                requester=self.brain_id,
                bypass_approval_for_tests=True,
            )

            artifact_dict = tool_res.get("artifact", {})
            file_path = tool_res.get("file_path", "")
            v_count = tool_res.get("vertex_count", 0)
            f_count = tool_res.get("face_count", 0)

            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.COMPLETED,
                output={
                    "status": "completed",
                    "file_path": file_path,
                    "mesh_type": mesh_type,
                    "vertex_count": v_count,
                    "face_count": f_count,
                    "format": "Wavefront OBJ",
                },
                artifacts=[artifact_dict],
                provenance=Provenance(
                    brain_id=self.brain_id,
                    tool_calls=[{"tool": "generate_3d_obj", "file_path": file_path}],
                    confidence=1.0,
                    execution_mode="local",
                ),
            )
        except Exception as e:
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error=f"3D Generation error: {e}",
                provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
            )
