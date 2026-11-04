"""
MIND_GameDev — Asset Workflow Coordinator.
Manages generating 2D concept images and 3D models (character, coin, obstacle),
validating geometries and saving them into project directories.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..config import GameDevConfig
from ..models import AssetMetadata, GameSpecification
from ..tools.workspace_files import SafeWorkspaceManager
from ..adapters.image_adapter import ImageAssetAdapter
from ..adapters.threed_adapter import ThreeDAssetAdapter


class AssetWorkflowCoordinator:
    """Coordinates 2D and 3D asset generation workflows for game projects."""

    def __init__(self, workspace: SafeWorkspaceManager, config: Optional[GameDevConfig] = None) -> None:
        self.workspace = workspace
        self.config = config or GameDevConfig.load()
        self.image_adapter = ImageAssetAdapter(self.config)
        self.threed_adapter = ThreeDAssetAdapter(self.config)

    def generate_game_assets(self, spec: Optional[GameSpecification] = None) -> List[AssetMetadata]:
        """Generates all standard 3D and 2D assets for the game project."""
        assets: List[AssetMetadata] = []

        models_dir = self.workspace.base_directory / "assets" / "models"
        textures_dir = self.workspace.base_directory / "assets" / "textures"
        self.workspace.create_directory("assets/models")
        self.workspace.create_directory("assets/textures")

        # 1. Generate 3D Character Mesh
        char_meta = self.threed_adapter.generate_asset(
            name="character",
            asset_type="character",
            output_dir=models_dir,
            file_format="glb",
        )
        assets.append(char_meta)

        # 2. Generate 3D Coin Mesh
        coin_meta = self.threed_adapter.generate_asset(
            name="coin",
            asset_type="coin",
            output_dir=models_dir,
            file_format="glb",
        )
        assets.append(coin_meta)

        # 3. Generate 3D Obstacle Barrier Mesh
        barrier_meta = self.threed_adapter.generate_asset(
            name="obstacle",
            asset_type="obstacle",
            output_dir=models_dir,
            file_format="glb",
        )
        assets.append(barrier_meta)

        # 4. Generate 2D Concept Art / Splash Banner
        theme = spec.theme if spec else "cyberpunk neon endless runner"
        prompt = f"Futuristic runner character dashing along neon holographic highway in {theme}, highly detailed arcade concept art"
        image_meta = self.image_adapter.generate_concept_image(
            prompt=prompt,
            name="concept_hero",
            output_dir=textures_dir,
        )
        assets.append(image_meta)

        return assets
