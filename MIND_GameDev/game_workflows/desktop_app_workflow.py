"""
MIND Universal Development Studio — Desktop App Workflow.
Generates Windows desktop utilities with Python & Tkinter,
diagnostic monitors, clean card layouts, and automated headless smoke tests.
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


class DesktopAppWorkflow(BaseProjectWorkflow):
    """Workflow for native Windows desktop applications and utilities."""

    project_type = ProjectType.DESKTOP_APP

    def build(self, spec: ProjectSpecification, workspace: SafeWorkspaceManager) -> Dict[str, Any]:
        title = spec.title or "SysPulse: System Diagnostics Utility"
        desc = spec.description or "Desktop hardware telemetry, process monitoring, and disk diagnostics"

        workspace.create_directory("app")
        workspace.create_directory("tests")

        self._write_main_py(workspace, title)
        self._write_diagnostics_py(workspace)
        self._write_test_desktop_py(workspace)
        self._write_manifest(workspace, title, desc)

        return {
            "status": "SUCCESS",
            "project_type": "desktop_app",
            "title": title,
            "entry_point": "app/main.py",
        }

    def _write_main_py(self, ws: SafeWorkspaceManager, title: str) -> None:
        code = f"""\"\"\"
{title} — Windows Desktop GUI Application.
Built with Python Tkinter and native platform diagnostics.
\"\"\"

import tkinter as tk
from tkinter import ttk, messagebox
import platform
import os
import time

from .diagnostics import SystemDiagnostics


class DesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("{title}")
        self.root.geometry("640x480")
        self.root.configure(bg="#0b1020")

        self.diag = SystemDiagnostics()
        self.build_ui()
        self.refresh_stats()

    def build_ui(self):
        # Header Frame
        header = tk.Frame(self.root, bg="#12182b", padx=16, pady=12)
        header.pack(fill=tk.X)

        title_lbl = tk.Label(
            header,
            text="⚡ {title.upper()}",
            font=("Segoe UI", 12, "bold"),
            fg="#00f3ff",
            bg="#12182b",
        )
        title_lbl.pack(side=tk.LEFT)

        refresh_btn = tk.Button(
            header,
            text="Refresh ⟳",
            command=self.refresh_stats,
            bg="#00f3ff",
            fg="#05070e",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
        )
        refresh_btn.pack(side=tk.RIGHT)

        # Content Card
        card = tk.Frame(self.root, bg="#162038", padx=20, pady=20)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        self.info_text = tk.Text(
            card,
            bg="#0a0f1d",
            fg="#e2e8f0",
            font=("Consolas", 10),
            relief=tk.FLAT,
            padx=12,
            pady=12,
        )
        self.info_text.pack(fill=tk.BOTH, expand=True)

    def refresh_stats(self):
        stats = self.diag.collect()
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert(tk.END, f"=== SYSTEM TELEMETRY AUDIT ===\\n")
        self.info_text.insert(tk.END, f"Timestamp: {{time.ctime()}}\\n\\n")
        for k, v in stats.items():
            self.info_text.insert(tk.END, f"{{k.upper():<22}}: {{v}}\\n")


def launch():
    root = tk.Tk()
    app = DesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
"""
        ws.write_file("app/main.py", code, overwrite=True)

    def _write_diagnostics_py(self, ws: SafeWorkspaceManager) -> None:
        code = """\"\"\"System Diagnostics Collector.\"\"\"

import os
import platform
import sys


class SystemDiagnostics:
    def collect(self) -> dict:
        uname = platform.uname()
        return {
            "os_system": uname.system,
            "os_release": uname.release,
            "os_version": uname.version,
            "architecture": uname.machine,
            "processor": uname.processor or "Standard x86_64",
            "python_runtime": platform.python_version(),
            "cpu_count": str(os.cpu_count() or "Unknown"),
            "working_directory": str(os.getcwd()),
        }
"""
        ws.write_file("app/diagnostics.py", code, overwrite=True)

    def _write_test_desktop_py(self, ws: SafeWorkspaceManager) -> None:
        code = """\"\"\"Automated Smoke Tests for Desktop Application.\"\"\"

from app.diagnostics import SystemDiagnostics


def test_diagnostics_collector():
    diag = SystemDiagnostics()
    data = diag.collect()
    assert isinstance(data, dict)
    assert "os_system" in data
    assert "architecture" in data
    assert "python_runtime" in data
    assert len(data) >= 5
"""
        ws.write_file("tests/test_desktop.py", code, overwrite=True)

    def _write_manifest(self, ws: SafeWorkspaceManager, title: str, desc: str) -> None:
        manifest = {
            "name": title.lower().replace(" ", "_"),
            "title": title,
            "type": "desktop_app",
            "framework": "python_tkinter",
            "entry_point": "app/main.py",
            "run_command": "python -m app.main",
            "test_command": "pytest tests/ -v",
        }
        ws.write_file("project.json", json.dumps(manifest, indent=2), overwrite=True)

    def verify(self, project_dir: Path) -> ExecutionReport:
        start_time = time.time()
        test_file = project_dir / "tests" / "test_desktop.py"

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
            target_engine="Python Tkinter",
            project_type="desktop_app",
            project_path=str(project_dir),
            entry_point="app/main.py",
            files_created=[f.name for f in project_dir.rglob("*.py")],
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            elapsed_seconds=elapsed,
            summary=f"Desktop app verification completed with {tests_passed} tests passed.",
            errors=errors,
        )

    def get_run_instructions(self, project_dir: Path) -> Dict[str, Any]:
        return {
            "run_command": f"python {project_dir / 'app' / 'main.py'}",
            "instructions": "Execute with python app/main.py to open the native Tkinter window.",
        }
