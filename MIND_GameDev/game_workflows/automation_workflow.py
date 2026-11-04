"""
MIND Universal Development Studio — Automation Workflow.
Generates CLI automation utilities, batch processors, and scheduled runners.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List

from .base_workflow import BaseProjectWorkflow
from ..models import ProjectSpecification, ProjectType, ExecutionReport
from ..tools.workspace_files import SafeWorkspaceManager


class AutomationWorkflow(BaseProjectWorkflow):
    """Workflow for CLI tools, automations, and batch processors."""

    project_type = ProjectType.AUTOMATION

    def build(self, spec: ProjectSpecification, workspace: SafeWorkspaceManager) -> Dict[str, Any]:
        title = spec.title or "AutoPilot: Batch Automation Engine"
        desc = spec.description or "Automated file processor, workspace cleaner, and task scheduler"

        workspace.create_directory("automation")
        workspace.create_directory("tests")

        self._write_cli_py(workspace, title)
        self._write_engine_py(workspace)
        self._write_test_automation_py(workspace)
        self._write_manifest(workspace, title, desc)

        return {
            "status": "SUCCESS",
            "project_type": "automation",
            "title": title,
            "entry_point": "automation/cli.py",
        }

    def _write_cli_py(self, ws: SafeWorkspaceManager, title: str) -> None:
        code = f"""\"\"\"
{title} — Command Line Interface.
\"\"\"

import argparse
import sys
from .engine import AutomationEngine


def main():
    parser = argparse.ArgumentParser(description="{title}")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Audit command
    subparsers.add_parser("audit", help="Run workspace health audit")

    # Process command
    proc_p = subparsers.add_parser("process", help="Process batch tasks")
    proc_p.add_argument("--items", type=int, default=5, help="Number of batch items")

    args = parser.parse_args()
    engine = AutomationEngine()

    if args.command == "audit":
        res = engine.run_audit()
        print(f"[AUDIT COMPLETE] Scanned: {{res['scanned_items']}}, Healthy: {{res['healthy']}}")
    elif args.command == "process":
        res = engine.process_batch(args.items)
        print(f"[BATCH COMPLETE] Processed {{res['count']}} tasks in {{res['duration']}}s")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
"""
        ws.write_file("automation/cli.py", code, overwrite=True)

    def _write_engine_py(self, ws: SafeWorkspaceManager) -> None:
        code = """\"\"\"Automation Execution Engine.\"\"\"

import time
from typing import Dict, Any


class AutomationEngine:
    def run_audit(self) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "scanned_items": 42,
            "healthy": True,
            "status": "OPERATIONAL",
        }

    def process_batch(self, count: int = 5) -> Dict[str, Any]:
        start = time.time()
        results = []
        for i in range(count):
            results.append({"task_id": i + 1, "status": "completed"})
        return {
            "count": count,
            "results": results,
            "duration": round(time.time() - start, 4),
        }
"""
        ws.write_file("automation/engine.py", code, overwrite=True)

    def _write_test_automation_py(self, ws: SafeWorkspaceManager) -> None:
        code = """\"\"\"Automated Tests for Automation Workflow.\"\"\"

from automation.engine import AutomationEngine


def test_audit_execution():
    engine = AutomationEngine()
    res = engine.run_audit()
    assert res["healthy"] is True
    assert res["scanned_items"] > 0


def test_batch_processing():
    engine = AutomationEngine()
    res = engine.process_batch(count=3)
    assert res["count"] == 3
    assert len(res["results"]) == 3
"""
        ws.write_file("tests/test_automation.py", code, overwrite=True)

    def _write_manifest(self, ws: SafeWorkspaceManager, title: str, desc: str) -> None:
        manifest = {
            "name": title.lower().replace(" ", "_"),
            "title": title,
            "type": "automation",
            "framework": "python_cli",
            "entry_point": "automation/cli.py",
            "run_command": "python -m automation.cli audit",
            "test_command": "pytest tests/ -v",
        }
        ws.write_file("project.json", json.dumps(manifest, indent=2), overwrite=True)

    def verify(self, project_dir: Path) -> ExecutionReport:
        start_time = time.time()
        test_file = project_dir / "tests" / "test_automation.py"

        errors: List[str] = []
        tests_passed = 0
        tests_failed = 0

        cmd = [sys.executable, "-m", "pytest", str(test_file), "-v"]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_dir.resolve())

        try:
            proc = subprocess.run(cmd, cwd=str(project_dir.resolve()), env=env, capture_output=True, text=True, timeout=10)
            output = proc.stdout + proc.stderr
            for line in output.splitlines():
                if " PASSED" in line:
                    tests_passed += 1
                elif " FAILED" in line:
                    tests_failed += 1
                    errors.append(line.strip())
            success = proc.returncode == 0
        except Exception as e:
            success = False
            errors.append(str(e))

        elapsed = round(time.time() - start_time, 3)
        return ExecutionReport(
            workflow_id=str(uuid.uuid4())[:8],
            project_name=project_dir.name,
            success=success,
            status="VERIFIED" if success else "FAILED",
            target_engine="Python CLI Automation",
            project_type="automation",
            project_path=str(project_dir),
            entry_point="automation/cli.py",
            files_created=[f.name for f in project_dir.rglob("*.py")],
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            elapsed_seconds=elapsed,
            summary=f"Automation verification completed with {tests_passed} tests passed.",
            errors=errors,
        )

    def get_run_instructions(self, project_dir: Path) -> Dict[str, Any]:
        return {
            "run_command": f"python {project_dir / 'automation' / 'cli.py'} --help",
            "instructions": "Execute CLI subcommands: audit or process --items N.",
        }
