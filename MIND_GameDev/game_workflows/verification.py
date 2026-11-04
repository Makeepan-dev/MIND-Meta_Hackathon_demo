"""
MIND Universal Development Studio — Universal Workflow Verifier.
Executes specialized verification across websites, web applications, backend APIs,
games, desktop utilities, automations, and mobile apps.
Integrates independent verification and automated closed-loop error correction.
"""

from pathlib import Path
from typing import Any, Callable, Optional

from ..config import GameDevConfig
from ..models import GameProject, DevProject, ExecutionReport, ProjectStatus, ProjectType
from ..tools.workspace_files import SafeWorkspaceManager
from .workflow_registry import WorkflowRegistry


class WorkflowVerifier:
    """Verifies project integrity, executes automated unit/endpoint tests, and checks live loadability."""

    def __init__(self, config: Optional[GameDevConfig] = None) -> None:
        self.config = config or GameDevConfig.load()

    def verify_project(
        self,
        project: DevProject,
        auto_repair: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ExecutionReport:
        """Runs specialized verification tests appropriate for the project type with closed-loop repair."""
        project_dir = Path(project.root_path)
        ws = SafeWorkspaceManager(project_dir)

        p_type = getattr(project, "project_type", ProjectType.GAME)
        if isinstance(p_type, str):
            try:
                p_type = ProjectType(p_type)
            except ValueError:
                p_type = ProjectType.GAME

        # 1. Run baseline workflow verification
        workflow = WorkflowRegistry.get_workflow(p_type, config=self.config)
        report = workflow.verify(project_dir)

        # 2. Run multi-layer Independent Verification
        from ..tools.independent_verifier import IndependentVerifier
        from .repair_engine import ClosedLoopRepairEngine

        repair_engine = ClosedLoopRepairEngine(self.config)
        verifier = IndependentVerifier(ws)
        entry_file = getattr(report, "entry_point", "index.html") or "index.html"

        passed, diags = repair_engine._execute_verification(
            verifier=verifier,
            project_type=p_type,
            entry_point=entry_file,
            task_id=f"verify_{project.name}",
            project_id=project.name,
        )

        critical_diags = [d for d in diags if d.error_severity in ("ERROR", "CRITICAL")]

        # 3. If baseline test or independent verifier failed and auto_repair enabled, initiate repair cycle!
        if (not report.success or critical_diags) and auto_repair:
            repair_report = repair_engine.run_closed_loop(
                workspace=ws,
                project_type=p_type,
                project_name=project.name,
                entry_point=entry_file,
                progress_callback=progress_callback,
            )
            report = repair_report
        elif critical_diags:
            report.success = False
            report.status = ProjectStatus.FAILED.value
            report.errors.extend([d.error_message for d in critical_diags])

        if report.success:
            project.status = ProjectStatus.PASSED
        else:
            project.status = ProjectStatus.FAILED

        return report
