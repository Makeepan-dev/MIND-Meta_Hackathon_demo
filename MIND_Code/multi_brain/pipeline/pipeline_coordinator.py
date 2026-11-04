"""
MIND — Asset Generation Pipeline Coordinator
End-to-end coordinator managing Stages A through F:
User Request -> Prompt Synthesis -> Image Generation -> Image-to-3D Conversion -> Manifest Persistence -> Interactive UI
"""

import os
import time
from typing import Dict, Any, Optional, Callable

from multi_brain.pipeline.prompt_synthesizer import PromptSynthesizer
from multi_brain.pipeline.image_client import ImageGenerationClient
from multi_brain.pipeline.threed_client import ThreeDGenerationClient
from multi_brain.pipeline.asset_manager import AssetStorageManager
from multi_brain.pipeline.asset_viewer_ui import AssetViewerWindow


_DEFAULT_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class AssetGenerationPipeline:
    """Coordinates the full AI Image-to-3D generation workflow."""

    def __init__(self, workspace_root: str = _DEFAULT_REPO_ROOT) -> None:
        self.workspace_root = workspace_root
        self.synthesizer = PromptSynthesizer()
        self.image_client = ImageGenerationClient()
        self.threed_client = ThreeDGenerationClient()
        self.storage = AssetStorageManager(workspace_root=workspace_root)

    def execute_workflow(
        self,
        user_request: str,
        launch_viewer: bool = True,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the complete asset generation pipeline:
        Stage A & B: Local LLM interpretation & 3D prompt synthesis
        Stage C: Concept Image generation & validation
        Stage D: Image-to-3D model conversion & task tracking
        Stage E: Asset download, storage, and manifest registration
        Stage F: Interactive UI rendering & voice notification
        """
        start_time = time.time()

        # Send HUD / Speech update if config exists
        self._send_status_update(f"AI ASSET: INTERPRETING '{user_request}'", "Interpreting your 3D character request...")
        if progress_callback:
            progress_callback(f"Interpreting request: {user_request}", 10)

        # Stage A & B: Prompt Synthesis
        prompt_data = self.synthesizer.synthesize_prompt(user_request)

        # Stage C: Concept Image Generation
        self._send_status_update("AI ASSET: GENERATING CONCEPT IMAGE", "Generating character concept artwork...")
        if progress_callback:
            progress_callback("Generating concept image...", 35)

        image_result = self.image_client.generate_concept_image(prompt_data, user_request)
        concept_path = image_result["image_path"]

        # Stage D: Convert Image into 3D Model
        self._send_status_update("AI ASSET: 3D RECONSTRUCTION", "Reconstructing 3D polygonal mesh from concept image...")
        if progress_callback:
            progress_callback("Initiating 3D mesh reconstruction...", 60)

        threed_result = self.threed_client.convert_image_to_3d(
            image_path=concept_path,
            user_goal=user_request,
            progress_callback=progress_callback,
        )

        # Stage E: Asset Registration & Manifest Persistence
        manifest = self.storage.register_asset(
            user_request=user_request,
            prompt_data=prompt_data,
            image_result=image_result,
            threed_result=threed_result,
        )

        elapsed = round(time.time() - start_time, 2)
        model_path = threed_result.get("model_path")

        success_message = (
            f"I've generated your character concept and converted it into a 3D model in {elapsed}s. "
            f"The model is saved locally and ready to preview or export."
        )

        self._send_status_update("AI ASSET: COMPLETED", success_message)
        if progress_callback:
            progress_callback(success_message, 100)

        # Stage F: Return Model and Launch UI
        if launch_viewer and os.getenv("MIND_HEADLESS") != "1":
            try:
                viewer = AssetViewerWindow(manifest)
                viewer.show_async()
            except Exception:
                pass

        return {
            "status": "COMPLETED",
            "message": success_message,
            "elapsed_seconds": elapsed,
            "user_request": user_request,
            "prompt": prompt_data.get("prompt"),
            "concept_image": concept_path,
            "threed_model": model_path,
            "format": threed_result.get("format", "glb").upper(),
            "manifest": manifest,
            "verified": True,
        }

    def _send_status_update(self, hud_msg: str, speech_msg: str) -> None:
        """Helper to post non-blocking updates to MIND global nervous system if active."""
        try:
            import config
            if hasattr(config, "hud_queue"):
                config.hud_queue.put(hud_msg)
            if hasattr(config, "speech_queue"):
                config.speech_queue.put(speech_msg)
        except Exception:
            pass
