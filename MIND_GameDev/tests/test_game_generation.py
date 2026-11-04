"""
Unit tests for Game Project Creation:
Validates that EndlessRunnerGenerator, AssetWorkflowCoordinator, and GameProjectCreator
produce a fully scaffolded project containing all modules, libraries, HUD elements, and 3D assets.
"""

import json
import tempfile
from pathlib import Path

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import GameSpecification
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager
from MIND_GameDev.game_workflows.endless_runner import EndlessRunnerGenerator
from MIND_GameDev.game_workflows.asset_generation import AssetWorkflowCoordinator
from MIND_GameDev.game_workflows.project_creator import GameProjectCreator


def test_endless_runner_scaffolding():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        gen = EndlessRunnerGenerator(ws)
        spec = GameSpecification(title="NeonRunner 3D", theme="cyberpunk neon")

        res = gen.build_project(spec)
        assert res["status"] == "SUCCESS"

        # Verify critical files exist
        assert (ws.base_directory / "index.html").exists()
        assert (ws.base_directory / "style.css").exists()
        assert (ws.base_directory / "js" / "game.js").exists()
        assert (ws.base_directory / "js" / "player.js").exists()
        assert (ws.base_directory / "js" / "track.js").exists()
        assert (ws.base_directory / "js" / "obstacles.js").exists()
        assert (ws.base_directory / "js" / "collectibles.js").exists()
        assert (ws.base_directory / "js" / "audio.js").exists()
        assert (ws.base_directory / "libs" / "three.module.min.js").exists()
        assert (ws.base_directory / "project.json").exists()

        # Check library bundle is valid
        lib_size = (ws.base_directory / "libs" / "three.module.min.js").stat().st_size
        assert lib_size > 10000

        # Check project manifest
        manifest = json.loads((ws.base_directory / "project.json").read_text(encoding="utf-8"))
        assert manifest["title"] == "NeonRunner 3D"
        assert manifest["type"] == "endless_runner_3d"


def test_asset_coordinator_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        ws = SafeWorkspaceManager(Path(tmpdir))
        coord = AssetWorkflowCoordinator(ws, cfg)

        assets = coord.generate_game_assets()
        assert len(assets) >= 4  # character, coin, obstacle, concept image

        for a in assets:
            assert a.verified is True
            assert Path(a.file_path).exists()


def test_project_creator_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.workspace_root = Path(tmpdir)

        creator = GameProjectCreator(cfg)
        spec = GameSpecification(project_name="test_runner_game", title="Test Runner")

        project = creator.create_project(spec)
        assert project.name == "test_runner_game"
        assert Path(project.root_path).exists()
        assert len(project.assets) >= 4
