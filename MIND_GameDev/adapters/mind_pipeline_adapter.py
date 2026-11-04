"""
MIND_GameDev — MIND Pipeline Adapter.
Bridges to MIND's existing multi_brain.pipeline.pipeline_coordinator.AssetGenerationPipeline
for Stage A-F asset synthesis without mutating any existing files.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from ..config import GameDevConfig
from ..models import AssetMetadata


class MindPipelineAdapter:
    """
    Adapter that interfaces with MIND's existing Multi-Brain Asset Generation Pipeline.
    Ensures safe execution in standalone mode without GUI locks or global config dependencies.
    """

    def __init__(self, config: Optional[GameDevConfig] = None) -> None:
        self.config = config or GameDevConfig.load()
        self._ensure_mind_code_in_syspath()

    def _ensure_mind_code_in_syspath(self) -> None:
        mind_code_path = str(self.config.mind_code_root.resolve())
        if mind_code_path not in sys.path:
            sys.path.insert(0, mind_code_path)

    def generate_asset_via_pipeline(
        self,
        user_request: str,
        launch_viewer: bool = False,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes MIND's Stage A-F asset pipeline safely.
        Returns asset dictionary containing paths to concept art, 3D model, and manifest.
        """
        self._ensure_mind_code_in_syspath()

        # Set headless environment flag to prevent blocking GUI
        old_headless = os.environ.get("MIND_HEADLESS")
        os.environ["MIND_HEADLESS"] = "1"

        try:
            from multi_brain.pipeline.pipeline_coordinator import AssetGenerationPipeline

            pipeline = AssetGenerationPipeline(workspace_root=str(self.config.workspace_root.parent.resolve()))
            result = pipeline.execute_workflow(
                user_request=user_request,
                launch_viewer=launch_viewer,
                progress_callback=progress_callback,
            )
            return result
        except Exception as e:
            # Fallback to local generation if pipeline coordination encounters an error
            return {
                "status": "FALLBACK",
                "message": f"MIND pipeline encountered error ({e}); using direct local generator",
                "user_request": user_request,
                "verified": False,
                "error": str(e),
            }
        finally:
            if old_headless is None:
                os.environ.pop("MIND_HEADLESS", None)
            else:
                os.environ["MIND_HEADLESS"] = old_headless
