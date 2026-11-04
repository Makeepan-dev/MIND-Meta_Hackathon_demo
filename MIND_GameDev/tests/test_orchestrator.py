"""
Unit tests for GameDev Orchestrator:
Tests command parsing, workflow dispatching, and execution reporting.
"""

import tempfile
from pathlib import Path

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.orchestrator import GameDevOrchestrator


def test_orchestrator_create_command():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.require_design_approval = False
        cfg.workspace_root = Path(tmpdir)

        orch = GameDevOrchestrator(config=cfg, enable_voice=False)
        result = orch.execute_command("Create 3d endless runner with synthwave theme")

        assert result["status"] == "SUCCESS"
        assert "cyberdash_3d" in result["project"]["name"]
        assert Path(result["entry_point"]).exists()
        assert result["verification"]["success"] is True


def test_orchestrator_verify_command():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.require_design_approval = False
        cfg.workspace_root = Path(tmpdir)

        orch = GameDevOrchestrator(config=cfg, enable_voice=False)
        # Create first
        orch.execute_command("Create 3d runner")

        # Now verify
        verify_result = orch.execute_command("verify")
        assert verify_result["status"] == "SUCCESS"
        assert verify_result["report"]["success"] is True


def test_orchestrator_serve_command():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.require_design_approval = False
        cfg.workspace_root = Path(tmpdir)

        orch = GameDevOrchestrator(config=cfg, enable_voice=False)
        orch.execute_command("Create runner")

        serve_res = orch.serve_project(port=9090, open_browser=False)
        assert serve_res["status"] == "SERVING"
        assert "http://127.0.0.1:9090" in serve_res["url"]
