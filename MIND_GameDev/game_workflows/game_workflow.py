"""
MIND Universal Development Studio — 3D Game Workflow.
Adapts the Three.js 3D Endless Runner generator to the BaseProjectWorkflow interface.
"""

from pathlib import Path
from typing import Dict, Any

from .base_workflow import BaseProjectWorkflow
from .endless_runner import EndlessRunnerGenerator
from ..models import ProjectSpecification, ProjectType, ExecutionReport
from ..tools.workspace_files import SafeWorkspaceManager
from ..tools.test_runner import GameTestRunner


class GameWorkflow(BaseProjectWorkflow):
    """Workflow for playable 3D games (Three.js WebGL)."""

    project_type = ProjectType.GAME

    def build(self, spec: ProjectSpecification, workspace: SafeWorkspaceManager) -> Dict[str, Any]:
        generator = EndlessRunnerGenerator(workspace)
        return generator.build_project(spec)

    def verify(self, project_dir: Path) -> ExecutionReport:
        runner = GameTestRunner(project_dir)
        report = runner.run_all_tests()
        report.project_type = "game"
        report.entry_point = "index.html"
        return report

    def get_run_instructions(self, project_dir: Path) -> Dict[str, Any]:
        return {
            "run_command": f"python -m http.server 8080 --directory {project_dir}",
            "url": "http://127.0.0.1:8080/index.html",
            "instructions": "Host with python -m http.server or open index.html directly in a modern WebGL browser.",
        }
