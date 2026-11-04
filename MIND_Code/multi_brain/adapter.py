"""Compatibility Adapters for MIND Legacy Components & Subsystems.

Bridges existing MindBrain, GameDevOrchestrator, and UI workers
to the Unified Modular Multi-Brain Architecture.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from multi_brain.brains.base import SpecialistBrain
from multi_brain.contracts import (
    Artifact,
    Capability,
    CancellationToken,
    PermissionTier,
    Provenance,
    TaskNode,
    TaskPlan,
    TaskRequest,
    TaskResult,
    TaskStatus,
    WorkflowProgress,
    WorkflowResult,
)

logger = logging.getLogger("mind.multi_brain.adapter")


class GameDevSubsystemBrain(SpecialistBrain):
    """
    Adapter integrating the specialized GameDevOrchestrator into the
    MIND Multi-Brain Architecture as a recognized SpecialistBrain.
    Owns autonomous web building, game development, project scaffolding,
    and 3D reconstruction pipeline.
    """

    def __init__(
        self,
        orchestrator: Optional[Any] = None,
        workspace_root: Optional[str] = None,
    ) -> None:
        capabilities = [
            Capability(
                name="autonomous_web_builder",
                domain="Software Engineering",
                description="Scaffolds and builds complete multi-page responsive websites with HTML/CSS/JS and media.",
                supported_operations=["create_website", "build_web_project", "add_page"],
                modalities=["text", "code", "image"],
                permission_tier=PermissionTier.REQUIRES_APPROVAL,
            ),
            Capability(
                name="game_development",
                domain="Game Engineering",
                description="Scaffolds and generates playable 2D/3D procedural games (Pygame, Three.js, Canvas).",
                supported_operations=["create_game", "build_game"],
                modalities=["text", "code"],
                permission_tier=PermissionTier.REQUIRES_APPROVAL,
            ),
            Capability(
                name="workspace_file_operations",
                domain="Workspace Management",
                description="Inspects, reads, updates, repairs, and verifies files in the project workspace.",
                supported_operations=["list_files", "read_file", "update_file", "repair_project"],
                modalities=["text", "code"],
                permission_tier=PermissionTier.REQUIRES_APPROVAL,
            ),
            Capability(
                name="image_to_3d_pipeline",
                domain="3D Asset Engineering",
                description="Reconstructs 3D assets (OBJ/GLB) from 2D images via Blender or procedural pipelines.",
                supported_operations=["reconstruct_3d", "image_to_3d"],
                modalities=["image", "model3d"],
                permission_tier=PermissionTier.REQUIRES_APPROVAL,
            ),
        ]
        super().__init__(
            brain_id="gamedev_subsystem",
            name="GameDev & Web Execution Subsystem",
            domain="Software & Game Engineering",
            description="Specialized execution subsystem for autonomous web applications, games, and project files.",
            capabilities=capabilities,
            permission_tier=PermissionTier.REQUIRES_APPROVAL,
        )
        self._orchestrator = orchestrator
        default_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.workspace_root = workspace_root or default_root

    @property
    def gamedev_orchestrator(self) -> Any:
        if self._orchestrator is None:
            try:
                from MIND_GameDev.orchestrator import GameDevOrchestrator
                self._orchestrator = GameDevOrchestrator()
            except Exception as e:
                logger.error(f"Failed to instantiate GameDevOrchestrator: {e}")
        return self._orchestrator

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        orch = self.gamedev_orchestrator
        if not orch:
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error="GameDevOrchestrator execution subsystem unavailable.",
                provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
            )

        cmd = request.user_goal
        live_cb = request.parameters.get("progress_callback") or request.context_slice.get("progress_callback")
        try:
            res = orch.execute_command(cmd, progress_callback=live_cb)
        except TypeError:
            res = orch.execute_command(cmd)
        except Exception as e:
            logger.error(f"GameDev subsystem error on command '{cmd}': {e}", exc_info=True)
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error=f"GameDev subsystem error: {e}",
                provenance=Provenance(brain_id=self.brain_id, confidence=0.0),
            )

        # Evaluate execution status
        status = TaskStatus.COMPLETED
        err = None
        if not res.get("success", True) and res.get("status") in (
            "VALIDATION_FAILED", "BLENDER_EXECUTION_FAILED", "GLB_VERIFICATION_FAILED", "FAILED", "ERROR"
        ):
            status = TaskStatus.FAILED
            err = res.get("error") or res.get("message") or "Subsystem execution failed."

        # Collect artifacts
        artifacts: List[Dict[str, Any]] = []
        proj_path = res.get("project_path") or res.get("destination_dir")
        if proj_path and os.path.exists(proj_path):
            index_file = os.path.join(proj_path, "index.html")
            if os.path.exists(index_file):
                art_html = Artifact.from_file(
                    index_file,
                    mime_type="text/html",
                    source_brain=self.brain_id,
                    source_task=request.task_id,
                    preview_type="browser",
                    metadata={"title": res.get("title", "Generated Website"), "is_root_page": True},
                )
                artifacts.append(art_html.to_dict())

            art_folder = Artifact(
                artifact_id=f"dir_{request.task_id[:6]}",
                path=os.path.abspath(proj_path),
                mime_type="inode/directory",
                source_brain=self.brain_id,
                source_task=request.task_id,
                preview_type="folder",
                metadata={"title": res.get("title", os.path.basename(proj_path))},
            )
            artifacts.append(art_folder.to_dict())

        for f in res.get("files_written", []):
            if os.path.exists(f):
                mime = "text/plain"
                if f.endswith(".html"):
                    mime = "text/html"
                elif f.endswith(".css"):
                    mime = "text/css"
                elif f.endswith(".js"):
                    mime = "application/javascript"
                elif f.endswith((".obj", ".stl", ".glb")):
                    mime = "model/obj" if f.endswith(".obj") else "model/gltf-binary"
                art = Artifact.from_file(
                    f,
                    mime_type=mime,
                    source_brain=self.brain_id,
                    source_task=request.task_id,
                )
                if art.to_dict() not in artifacts:
                    artifacts.append(art.to_dict())

        model_path = res.get("model_path") or res.get("glb_path") or res.get("obj_path")
        if model_path and os.path.exists(model_path):
            art_3d = Artifact.from_file(
                model_path,
                mime_type="model/obj" if model_path.endswith(".obj") else "model/gltf-binary",
                source_brain=self.brain_id,
                source_task=request.task_id,
                preview_type="model3d",
                metadata={"vertex_count": res.get("vertex_count", 0), "face_count": res.get("face_count", 0)},
            )
            artifacts.append(art_3d.to_dict())

        # Provenance tracking
        prov = Provenance(
            brain_id=self.brain_id,
            model_id=res.get("model", "qwen2.5-coder-32b"),
            provider_id=res.get("provider", "gamedev_subsystem"),
            confidence=1.0 if status == TaskStatus.COMPLETED else 0.0,
        )

        return TaskResult(
            task_id=request.task_id,
            status=status,
            output=res,
            artifacts=artifacts,
            verification=res.get("verification") or res.get("verification_report"),
            provenance=prov,
            error=err,
        )


class LegacyBrainAdapter(SpecialistBrain):
    """
    Adapter wrapping a legacy named model (e.g. MANAGER, CODER, THEORIST, ANALYST, CEREBRAS)
    from MindBrain. Guarantees that when a user selects a manual brain, that exact model/provider
    is invoked without silent substitution.
    """

    def __init__(
        self,
        brain_key: str,
        name: str,
        model_id: str,
        provider_id: str,
        desc: str = "",
    ) -> None:
        super().__init__(
            brain_id=brain_key.lower(),
            name=name,
            domain="General Intelligence",
            description=desc,
            capabilities=[
                Capability(
                    name=f"{brain_key.lower()}_inference",
                    domain="General",
                    description=desc,
                )
            ],
            permission_tier=PermissionTier.SAFE,
        )
        self.brain_key = brain_key
        self.target_model_id = model_id
        self.target_provider_id = provider_id

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        try:
            from mind_brain import MindBrain
            brain = MindBrain()
            if self.brain_key in brain.brains:
                response = brain.query_specific_brain(self.brain_key, request.user_goal)
            else:
                response = brain.think(request.user_goal)

            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.COMPLETED,
                output={"response": response, "model_tag": self.name},
                provenance=Provenance(
                    brain_id=self.brain_id,
                    model_id=self.target_model_id,
                    provider_id=self.target_provider_id,
                    confidence=1.0,
                ),
            )
        except Exception as e:
            logger.error(f"Manual brain '{self.brain_key}' execution failed: {e}")
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error=f"Selected Brain '{self.brain_key}' failed: {e}",
                provenance=Provenance(
                    brain_id=self.brain_id,
                    model_id=self.target_model_id,
                    provider_id=self.target_provider_id,
                    confidence=0.0,
                ),
            )


class MultiBrainAdapter:
    """
    Singleton or reusable adapter connecting legacy MIND components
    to the new modular multi-brain system.
    """

    _instance: Optional[MultiBrainAdapter] = None

    def __init__(self, orchestrator: Optional[Any] = None) -> None:
        if orchestrator is None:
            from multi_brain import create_multi_brain_system
            self.orchestrator = create_multi_brain_system()
        else:
            self.orchestrator = orchestrator

    @classmethod
    def get_instance(cls) -> MultiBrainAdapter:
        if cls._instance is None:
            cls._instance = MultiBrainAdapter()
        return cls._instance

    def process(self, text: str) -> str:
        """Processes request via Orchestrator and returns a text reply for backward compatibility."""
        try:
            result = self.orchestrator.process_request(text)
            return result.get("response", "Task processed.")
        except Exception as e:
            logger.error(f"Error in multi-brain adapter processing: {e}")
            return f"Neural coordination encountered an error: {e}"

    def process_detailed(
        self,
        text: str,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Returns the full execution dictionary including workflow results and evidence."""
        return self.orchestrator.process_request(
            text,
            progress_callback=progress_callback,
            cancellation_token=cancellation_token,
        )

    def process_workflow(
        self,
        plan: TaskPlan,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> WorkflowResult:
        """Executes a validated TaskPlan DAG through the WorkflowEngine."""
        return self.orchestrator.workflow_engine.execute_plan(
            plan,
            progress_callback=progress_callback,
            cancellation_token=cancellation_token,
        )

    def execute_single_brain(self, brain_key: str, prompt: str) -> TaskResult:
        """Executes a user request against a specifically designated brain without substitution."""
        clean_key = brain_key.strip().lower()
        aliases = {
            "coder": "coding_engineering",
            "theorist": "reasoning_planning",
            "analyst": "analysis_data",
            "cerebras": "reasoning_planning",
            "manager": "reasoning_planning",
            "vision": "creative_visual",
            "3d": "threed_generation",
            "video": "video_generation",
            "audio": "audio_communication",
            "research": "research_knowledge",
        }
        target_id = aliases.get(clean_key, clean_key)
        brain = self.orchestrator.brain_registry.get(target_id)
        if brain:
            req = TaskRequest(user_goal=prompt)
            res = brain.execute(req)
            if res.provenance:
                res.provenance.brain_id = clean_key
            return res

        # Fallback to MindBrain specific brain
        legacy = LegacyBrainAdapter(
            brain_key=brain_key.strip().upper(),
            name=f"MIND // {brain_key.strip().upper()}",
            model_id=clean_key,
            provider_id="mind_brain_legacy",
        )
        req = TaskRequest(user_goal=prompt)
        return legacy.execute(req)
