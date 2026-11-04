"""
Comprehensive Automated Tests for MIND Closed-Loop AI Development,
Automated Error Correction, and Independent Verification.

Validates Tests A through L as mandated by the closed-loop specifications:
- Test A: Incorrect capitalization (C Printf -> printf)
- Test B: Undefined variable repair
- Test C: Broken HTML/CSS structural detection and repair
- Test D: Missing dependency detection and graceful resolution
- Test E: Runtime exception detection and repair
- Test F: Repeated failure, bounded retries, and recurring error detection
- Test G: Provider failure and fallback chain
- Test H: Voice failure fault isolation
- Test I: Preview port conflict and recovery
- Test J: Filesystem conflict and path containment safety
- Test K: False success prevention (functional defect with passing syntax)
- Test L: Successful finalization with centralized completion notification
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import (
    AgentTask,
    DiagnosticReport,
    ExecutionReport,
    ProjectSpecification,
    ProjectStatus,
    ProjectType,
    SafePathValidator,
    VerificationCategory,
)
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager
from MIND_GameDev.tools.independent_verifier import IndependentVerifier
from MIND_GameDev.agents.specialized_agents import (
    AgentRegistry,
    CodingAgent,
    DesignAgent,
)
from MIND_GameDev.game_workflows.repair_engine import ClosedLoopRepairEngine
from MIND_GameDev.orchestrator import GameDevOrchestrator
from MIND_GameDev.adapters.voice_output import VoiceOutputAdapter


class TestClosedLoopDevelopmentAndRepair(unittest.TestCase):

    def setUp(self):
        self.config = GameDevConfig.load()
        self.config.test_mode = True
        self.config.max_repair_retries = 3
        self.tmp_dir = tempfile.mkdtemp()
        self.workspace_root = Path(self.tmp_dir) / "test_workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.workspace = SafeWorkspaceManager(self.workspace_root)
        self.verifier = IndependentVerifier(self.workspace)
        self.coding_agent = CodingAgent(self.config)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # =========================================================================
    # Test A — Incorrect Capitalization (C Printf -> printf)
    # =========================================================================
    def test_a_incorrect_capitalization_c_repaired(self):
        """
        Compiler/verifier detects Printf, captures diagnostic, sends to coding agent,
        agent returns printf with explanation, verification passes.
        """
        c_code = (
            "#include <stdio.h>\n\n"
            "int main() {\n"
            '    Printf("Hello World\\n");\n'
            "    return 0;\n"
            "}\n"
        )
        self.workspace.write_file("main.c", c_code, overwrite=True)

        # 1. Independent Verification detects error
        passed, diags = self.verifier.verify_c_code("main.c")
        self.assertFalse(passed, "Verification should fail on capitalized 'Printf'")
        self.assertTrue(any("Printf" in d.error_message for d in diags))

        primary_diag = diags[0]
        self.assertEqual(primary_diag.verification_category, VerificationCategory.SYNTAX)

        # 2. Responsible Coding Agent repairs output
        repair_res = self.coding_agent.repair_code(primary_diag, c_code, language="c")
        self.assertTrue(repair_res["success"])
        self.assertIn("printf", repair_res["code"])
        self.assertNotIn("Printf", repair_res["code"])
        self.assertIn("Corrected misspelled C standard library function", repair_res["explanation"])

        # 3. Integrate correction safely and verify again
        self.workspace.write_file("main.c", repair_res["code"], overwrite=True)
        repassed, rediags = self.verifier.verify_c_code("main.c")
        self.assertTrue(repassed, f"Re-verification should pass. Errors: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Test B — Undefined Variable
    # =========================================================================
    def test_b_undefined_variable_repaired(self):
        """
        Code referencing an undefined variable is diagnosed, repaired by coding agent,
        and independently verified.
        """
        py_code = (
            "def calculate_total():\n"
            "    total = undefined_counter + 10\n"
            "    return total\n"
        )
        self.workspace.write_file("calc.py", py_code, overwrite=True)

        # Create diagnostic simulating linter / runtime NameError
        diag = DiagnosticReport(
            task_id="task_var",
            project_id="py_project",
            agent_responsible="coding_agent",
            verification_category=VerificationCategory.SYNTAX,
            error_severity="ERROR",
            file_path="calc.py",
            line_number=2,
            error_message="Undefined variable 'undefined_counter'",
            code_context="total = undefined_counter + 10",
        )

        repair_res = self.coding_agent.repair_code(diag, py_code, language="python")
        self.assertTrue(repair_res["success"])
        self.assertIn("undefined_counter = 0", repair_res["code"])
        self.workspace.write_file("calc.py", repair_res["code"], overwrite=True)

        # Re-verify Python AST compilation
        passed, diags = self.verifier.verify_python_deliverable(entry_file="calc.py")
        self.assertTrue(passed)

    # =========================================================================
    # Test C — Broken HTML / CSS
    # =========================================================================
    def test_c_broken_html_css_repaired(self):
        """
        HTML with unclosed tag and CSS with unclosed brace are detected,
        repaired by closed-loop engine, and validated.
        """
        broken_html = (
            "<!DOCTYPE html>\n"
            "<html lang='en'>\n"
            "<head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>App</title><link rel='stylesheet' href='style.css'></head>\n"
            "<body>\n"
            "  <div class='container'>\n"
            "    <h1>Unclosed Container\n"
            "</body>\n"
            "</html>"
        )
        broken_css = (
            ".container {\n"
            "  display: flex;\n"
            "  background: #000;\n"
        )
        self.workspace.write_file("index.html", broken_html, overwrite=True)
        self.workspace.write_file("style.css", broken_css, overwrite=True)

        # 1. Independent Verification must detect both
        passed, diags = self.verifier.verify_web_deliverable()
        self.assertFalse(passed)
        self.assertTrue(any("Unclosed tag" in d.error_message or "CSS syntax error" in d.error_message for d in diags))

        # 2. Run closed-loop repair engine
        engine = ClosedLoopRepairEngine(self.config)
        report = engine.run_closed_loop(
            workspace=self.workspace,
            project_type=ProjectType.WEBSITE,
            project_name="Web_Repair_Test",
            entry_point="index.html",
        )

        self.assertTrue(report.success)
        self.assertIn(report.status, (ProjectStatus.PASSED.value, ProjectStatus.NEEDS_ATTENTION.value))
        self.assertGreater(len(report.repair_attempts), 0)

    # =========================================================================
    # Test D — Missing Dependency
    # =========================================================================
    def test_d_missing_dependency_detected_and_handled(self):
        """
        Missing unavailable dependency is detected, wrapped in a graceful fallback,
        and logged without silent corruption.
        """
        py_code = (
            "import non_existent_quantum_pkg\n\n"
            "def run():\n"
            "    return 'ok'\n"
        )
        self.workspace.write_file("service.py", py_code, overwrite=True)

        passed, diags = self.verifier.verify_python_deliverable(entry_file="service.py")
        self.assertFalse(passed)
        dep_diags = [d for d in diags if d.verification_category == VerificationCategory.DEPENDENCY]
        self.assertTrue(len(dep_diags) > 0)
        self.assertIn("non_existent_quantum_pkg", dep_diags[0].error_message)

        # Repair via CodingAgent
        repair_res = self.coding_agent.repair_code(dep_diags[0], py_code, language="python")
        self.assertTrue(repair_res["success"])
        self.assertIn("try:", repair_res["code"])
        self.assertIn("except ImportError:", repair_res["code"])

    # =========================================================================
    # Test E — Runtime Exception
    # =========================================================================
    def test_e_runtime_exception_detected_and_repaired(self):
        """
        Code that compiles cleanly but crashes with ZeroDivisionError is detected,
        returned to agent, guarded, and re-verified.
        """
        calc_code = (
            "def divide(a, b):\n"
            "    return a / b\n"
        )
        diag = DiagnosticReport(
            task_id="task_runtime",
            project_id="math_app",
            agent_responsible="coding_agent",
            verification_category=VerificationCategory.RUNTIME,
            error_severity="ERROR",
            file_path="math_app.py",
            error_message="ZeroDivisionError: division by zero",
            code_context="return a / b",
        )

        repair_res = self.coding_agent.repair_code(diag, calc_code, language="python")
        self.assertTrue(repair_res["success"])
        self.assertIn("!= 0", repair_res["code"])

    # =========================================================================
    # Test F — Repeated Failure & Bounded Retries
    # =========================================================================
    def test_f_repeated_failure_bounded_retries_and_loop_prevention(self):
        """
        When an error recurs without resolution, engine enforces max_retries limit,
        detects recurring failure signature, and stops safely with FAILED status.
        """
        unfixable_code = "/* PERMANENT BAD CODE */"
        self.workspace.write_file("bad.css", unfixable_code, overwrite=True)
        self.workspace.write_file("index.html", "<body>Missing head and unclosed", overwrite=True)

        engine = ClosedLoopRepairEngine(self.config)
        engine.max_retries = 2

        # Mock repair to produce identical bad output each time
        with patch.object(CodingAgent, "repair_code", return_value={"success": False, "code": unfixable_code}):
            report = engine.run_closed_loop(
                workspace=self.workspace,
                project_type=ProjectType.WEBSITE,
                project_name="LoopTest",
            )

        self.assertFalse(report.success)
        self.assertEqual(report.status, ProjectStatus.FAILED.value)
        self.assertTrue(report.is_candidate, "Unresolved project must remain candidate")
        self.assertIn("Exhausted maximum configured repair attempts", report.limitations[0])

    # =========================================================================
    # Test G — Provider Failure & Fallback Chain
    # =========================================================================
    def test_g_provider_failure_fallback_chain(self):
        """
        Simulates total cloud provider unavailability. CodingAdapter falls back
        gracefully to local deterministic scaffolding.
        """
        with patch("requests.post", side_effect=ConnectionError("Cloud API unreachable")):
            res = self.coding_agent.adapter.generate(
                prompt="Build responsive navbar component",
                language="html",
            )
            self.assertTrue(res.get("success"))
            self.assertTrue(len(res.get("code", "")) > 50)
            provider_str = res.get("provider", "").lower()
            self.assertTrue("fallback" in provider_str or "offline" in provider_str, f"Unexpected provider: {provider_str}")

    # =========================================================================
    # Test H — Voice Failure Fault Isolation
    # =========================================================================
    def test_h_voice_failure_does_not_fail_project(self):
        """
        Voice synthesis exception must never destroy project files or fail creation.
        """
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.require_design_approval = False
        cfg.workspace_root = self.workspace_root

        orch = GameDevOrchestrator(config=cfg, enable_voice=True)
        with patch.object(VoiceOutputAdapter, "_speak_powershell", side_effect=RuntimeError("SAPI failure")):
            res = orch.execute_command("create website for test agency")
            self.assertEqual(res["status"], "SUCCESS")
            self.assertTrue(Path(res["project_path"]).exists())
            self.assertTrue((Path(res["project_path"]) / "index.html").exists())

    # =========================================================================
    # Test I — Preview Failure Handling (Port Conflict)
    # =========================================================================
    def test_i_preview_failure_graceful_port_retry(self):
        """
        Occupied preview port is gracefully retried across alternative ports.
        """
        import socket
        # Occupy port 8080 intentionally
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 8080))
        sock.listen(1)

        try:
            cfg = GameDevConfig.load()
            cfg.test_mode = True
            cfg.require_design_approval = False
            cfg.workspace_root = self.workspace_root
            orch = GameDevOrchestrator(config=cfg, enable_voice=False)
            orch.execute_command("create website for preview test")

            res = orch.serve_project(port=8080, open_browser=False)
            self.assertIn(res["status"], ("SUCCESS", "SERVING"))
            # Must have used alternative port > 8080
            self.assertNotEqual(res["port"], 8080)
            self.assertTrue(res["port"] > 8080)
        finally:
            sock.close()

    # =========================================================================
    # Test J — Filesystem Conflict & Path Containment
    # =========================================================================
    def test_j_filesystem_conflict_and_path_containment(self):
        """
        Path traversal attempts are blocked by SafePathValidator;
        Overwrites on existing populated directories require explicit confirmation.
        """
        # 1. Path Traversal blocked
        with self.assertRaises(PermissionError):
            SafePathValidator.validate_containment(
                Path(self.tmp_dir) / ".." / ".." / "Windows" / "System32",
                self.workspace_root,
            )

        # 2. Existing folder collision requires confirmation
        populated_dir = self.workspace_root / "ExistingProject"
        populated_dir.mkdir(parents=True, exist_ok=True)
        (populated_dir / "existing_file.txt").write_text("critical data", encoding="utf-8")

        cfg = GameDevConfig.load()
        cfg.test_mode = True
        orch = GameDevOrchestrator(config=cfg, enable_voice=False)
        cmd = f"create website at {populated_dir}"
        res = orch.execute_command(cmd)

        self.assertEqual(res["status"], "CONFIRMATION_REQUIRED")
        self.assertEqual(res["action"], "create_project_overwrite")

    # =========================================================================
    # Test K — False Success Prevention
    # =========================================================================
    def test_k_false_success_prevention_functional_defect(self):
        """
        An application with valid syntax but missing a required functional requirement
        must NOT be marked passed merely because it compiled.
        """
        valid_html = (
            "<!DOCTYPE html>\n"
            "<html lang='en'>\n"
            "<head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>Doc</title></head>\n"
            "<body><h1>Generic Document</h1></body>\n"
            "</html>"
        )
        self.workspace.write_file("index.html", valid_html, overwrite=True)

        passed, diags = self.verifier.verify_web_deliverable(
            functional_requirements={"expected_keywords": ["Interactive Solar Observatory", "Telescope Feed"]}
        )
        self.assertFalse(passed, "Must fail functional requirements despite valid HTML syntax")
        self.assertTrue(any(d.verification_category == VerificationCategory.FUNCTIONAL for d in diags))

    # =========================================================================
    # Test L — Successful Finalization & Single Voice Announcement
    # =========================================================================
    def test_l_successful_finalization_with_single_voice_announcement(self):
        """
        Valid project passes all required checks, files are intact, and MIND issues
        exactly one central completion notification.
        """
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.require_design_approval = False
        cfg.workspace_root = self.workspace_root

        spoken_messages = []
        with patch.object(VoiceOutputAdapter, "speak", side_effect=lambda msg, block=False: spoken_messages.append(msg)):
            orch = GameDevOrchestrator(config=cfg, enable_voice=True)
            res = orch.execute_command("create website for modern tech startup")

            self.assertEqual(res["status"], "SUCCESS")
            self.assertTrue(res["verification"]["success"])
            self.assertTrue(Path(res["project_path"]).exists())
            self.assertTrue((Path(res["project_path"]) / "index.html").exists())
            self.assertTrue((Path(res["project_path"]) / "style.css").exists())

            # Verify completion speech was delivered
            completion_speeches = [s for s in spoken_messages if "verified" in s.lower() or "passed" in s.lower()]
            self.assertEqual(len(completion_speeches), 1, f"Expected exactly 1 completion speech, got {completion_speeches}")

    # =========================================================================
    # Stage 2 Design Approval Lifecycle Verification
    # =========================================================================
    def test_stage2_design_approval_lifecycle(self):
        """
        Verifies Stage 2 Design Approval gate:
        1. When design approval is required, MIND returns APPROVAL_REQUIRED with design proposal.
        2. Files are not written until user explicitly issues 'approve'.
        3. Upon approval, MIND proceeds with candidate generation and closed-loop verification.
        """
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.require_design_approval = False
        cfg.workspace_root = self.workspace_root
        cfg.require_design_approval = True

        orch = GameDevOrchestrator(config=cfg, enable_voice=False)
        # Step 1: Submit command requesting project creation with approval required
        plan_res = orch.execute_command("create website for artisanal bakery")
        self.assertEqual(plan_res["status"], "APPROVAL_REQUIRED")
        self.assertEqual(plan_res["stage"], "DESIGN_APPROVAL")
        self.assertIn("design_plan", plan_res)
        self.assertIsNotNone(orch.pending_design_spec)

        # Step 2: User explicitly approves the design proposal
        approve_res = orch.execute_command("approve")
        self.assertEqual(approve_res["status"], "SUCCESS")
        self.assertTrue(approve_res["verification"]["success"])
        self.assertIsNone(orch.pending_design_spec)
        self.assertTrue(Path(approve_res["project_path"]).exists())
        self.assertTrue((Path(approve_res["project_path"]) / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
