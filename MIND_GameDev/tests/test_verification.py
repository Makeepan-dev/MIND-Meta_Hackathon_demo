"""
Unit tests for Verification and Static Quality Audits:
Tests syntax checking, asset validation, and ephemeral HTTP serving tests.
"""

import tempfile
from pathlib import Path

from MIND_GameDev.models import GameSpecification
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager
from MIND_GameDev.tools.test_runner import GameTestRunner
from MIND_GameDev.game_workflows.endless_runner import EndlessRunnerGenerator
from MIND_GameDev.game_workflows.asset_generation import AssetWorkflowCoordinator


def test_game_test_runner_on_valid_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        gen = EndlessRunnerGenerator(ws)
        coord = AssetWorkflowCoordinator(ws)

        gen.build_project()
        coord.generate_game_assets()

        runner = GameTestRunner(ws.base_directory)
        report = runner.run_all_tests()

        assert report.success is True
        assert len(report.errors) == 0
        assert "index.html" in report.details["files_checked"]
        assert report.details["http_serving_test"]["status"] == "SUCCESS"


def test_game_test_runner_detects_missing_entrypoint():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        runner = GameTestRunner(p)
        report = runner.run_all_tests()

        assert report.success is False
        assert any("index.html" in err for err in report.errors)


def test_game_test_runner_detects_corrupt_asset():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        gen = EndlessRunnerGenerator(ws)
        gen.build_project()

        # Add corrupt .glb file
        ws.create_directory("assets/models")
        ws.write_file("assets/models/fake.glb", "NOT_A_VALID_GLTF_BINARY", overwrite=True)

        runner = GameTestRunner(ws.base_directory)
        report = runner.run_all_tests()

        assert report.success is False
        assert any("fake.glb" in err for err in report.errors)
