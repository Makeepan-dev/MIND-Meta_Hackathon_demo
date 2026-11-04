"""
Comprehensive Automated Tests for MIND General-Purpose Intelligent Error Detection,
AI-Driven Repair & Verification Audit.

Demonstrates that MIND detects and corrects unfamiliar/previously unseen programming
errors through its assigned AI coding agent (CodingAgent) via structured diagnostics,
rather than relying on hardcoded correction rules.

Validates:
- Test A: Python incorrect function arguments (missing required positional argument)
- Test B: JavaScript undefined function call (Node.js runtime execution & repair)
- Test C: TypeScript type mismatch (string passed to number parameter)
- Test D: C incorrect function arguments (too few arguments in call site)
- Test E: Cross-file missing export (math_utils.js export imported by main.js)
- Test F: Logic error despite successful compilation (functional test failure)
- Test G: Unfamiliar error with no hardcoded rule (KeyError / custom domain exception)
- Agent Verification: Proves the AI agent receives diagnostics and context, generates code,
  and that independent verification records the full audit contract.
- Design Approval Defaults: Proves require_design_approval is True by default, supports
  AWAITING_APPROVAL, design revisions (version increment), cancellation, and safety isolation.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import (
    ActionType,
    AgentTask,
    DiagnosticReport,
    ExecutionReport,
    ProjectSpecification,
    ProjectStatus,
    ProjectType,
    RepairAttempt,
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
from MIND_GameDev.tools.conversation_state import ConversationState
from MIND_GameDev.tools.session_memory import SessionMemory


class TestGeneralPurposeAIRepair(unittest.TestCase):

    def setUp(self):
        self.config = GameDevConfig.load()
        self.config.test_mode = True
        self.config.max_repair_retries = 3
        self.config.require_design_approval = True
        self.tmp_dir = tempfile.mkdtemp()
        self.workspace_root = Path(self.tmp_dir) / "test_workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.workspace = SafeWorkspaceManager(self.workspace_root)
        self.verifier = IndependentVerifier(self.workspace)
        self.registry = AgentRegistry(self.config)
        self.repair_engine = ClosedLoopRepairEngine(
            agent_registry=self.registry,
            config=self.config,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # =========================================================================
    # Test A: Python incorrect function arguments (missing required positional arg)
    # =========================================================================
    def test_a_python_incorrect_function_arguments(self):
        """
        Detects missing required positional argument at runtime in Python.
        Diagnostic is captured, dispatched to CodingAgent reasoning,
        corrected code passes independent re-verification.
        """
        py_code = (
            "def calculate_tax(amount, rate):\n"
            "    return amount * rate\n\n"
            "if __name__ == '__main__':\n"
            "    # Missing required argument 'rate'\n"
            "    result = calculate_tax(100)\n"
            "    print(f'Tax: {result}')\n"
        )
        self.workspace.write_file("main.py", py_code, overwrite=True)

        # 1. Independent Verification executes code and detects runtime failure
        passed, diags = self.verifier.verify_python_deliverable(
            entry_file="main.py",
            run_entry=True,
        )
        self.assertFalse(passed, "Verification must fail due to missing required positional argument.")
        self.assertTrue(any("missing 1 required positional argument" in d.error_message for d in diags))
        diag = diags[0]
        self.assertEqual(diag.verification_category, VerificationCategory.RUNTIME)

        # 2. Mock AI Coding Agent reasoning (simulating provider API)
        def mock_ai_fix(**kwargs):
            return {
                "code": (
                    "def calculate_tax(amount, rate=0.15):\n"
                    "    return amount * rate\n\n"
                    "if __name__ == '__main__':\n"
                    "    result = calculate_tax(100, 0.15)\n"
                    "    print(f'Tax: {result}')\n"
                ),
                "explanation": "Added default rate and supplied required argument at call site.",
                "provider": "mock_llama_coding_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_ai_fix)

        # 3. Apply repair via ClosedLoopRepairEngine
        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])
        self.assertEqual(res["repair_pathway"], "ai_agent_reasoning")

        # 4. Independent re-verification passes cleanly
        repassed, rediags = self.verifier.verify_python_deliverable(
            entry_file="main.py",
            run_entry=True,
        )
        self.assertTrue(repassed, f"Re-verification must pass. Remaining diagnostics: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Test B: JavaScript undefined function call (Node.js runtime execution & repair)
    # =========================================================================
    def test_b_javascript_undefined_function_call(self):
        """
        Detects unhandled ReferenceError in JavaScript via Node.js runtime check.
        Dispatches diagnostic to CodingAgent reasoning to define missing function.
        Re-verification via Node.js runtime passes cleanly.
        """
        js_code = (
            "function greetUser(name) {\n"
            "    return formatGreeting(name);\n"
            "}\n"
            "console.log(greetUser('Developer'));\n"
        )
        self.workspace.write_file("app.js", js_code, overwrite=True)

        # 1. Verification detects undefined function (ReferenceError)
        passed, diags = self.verifier.verify_js_code("app.js", run_execution=True)
        self.assertFalse(passed, "Verification must fail on undefined function call formatGreeting().")
        self.assertTrue(any("ReferenceError" in d.error_message or "formatGreeting" in d.error_message for d in diags))
        diag = diags[0]

        # 2. AI agent reasoning repair
        def mock_js_fix(**kwargs):
            return {
                "code": (
                    "function formatGreeting(name) {\n"
                    "    return 'Welcome, ' + name + '!';\n"
                    "}\n"
                    "function greetUser(name) {\n"
                    "    return formatGreeting(name);\n"
                    "}\n"
                    "console.log(greetUser('Developer'));\n"
                ),
                "explanation": "Implemented missing formatGreeting() utility function.",
                "provider": "mock_llama_coding_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_js_fix)
        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])

        # 3. Re-verification passes cleanly
        repassed, rediags = self.verifier.verify_js_code("app.js", run_execution=True)
        self.assertTrue(repassed, f"JavaScript re-verification should pass: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Test C: TypeScript type mismatch (string passed to number parameter)
    # =========================================================================
    def test_c_typescript_type_mismatch(self):
        """
        Detects parameter/argument type mismatch in TypeScript.
        CodingAgent reasons about types and adjusts argument literal to number.
        """
        ts_code = (
            "function calculateDiscount(price: number): number {\n"
            "    return price * 0.90;\n"
            "}\n"
            "const total = calculateDiscount(\"fifty\");\n"
        )
        self.workspace.write_file("discount.ts", ts_code, overwrite=True)

        # 1. Independent Verification detects type mismatch
        passed, diags = self.verifier.verify_typescript_code("discount.ts")
        self.assertFalse(passed, "Verification must fail due to TypeScript type mismatch.")
        self.assertTrue(any("Argument of type 'string' is not assignable to parameter of type 'number'" in d.error_message for d in diags))
        diag = diags[0]
        self.assertEqual(diag.verification_category, VerificationCategory.TYPE_CHECK)

        # 2. AI agent reasoning repair
        def mock_ts_fix(**kwargs):
            return {
                "code": (
                    "function calculateDiscount(price: number): number {\n"
                    "    return price * 0.90;\n"
                    "}\n"
                    "const total = calculateDiscount(50);\n"
                ),
                "explanation": "Corrected argument literal from string 'fifty' to numeric 50 matching signature.",
                "provider": "mock_llama_coding_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_ts_fix)
        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])

        # 3. Re-verification passes
        repassed, rediags = self.verifier.verify_typescript_code("discount.ts")
        self.assertTrue(repassed, f"TypeScript re-verification should pass: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Test D: C incorrect function arguments (too few arguments in call site)
    # =========================================================================
    def test_d_c_incorrect_function_arguments(self):
        """
        Detects argument count mismatch in C source code (too few arguments).
        CodingAgent supplies missing argument to call site. Re-verification passes.
        """
        c_code = (
            "#include <stdio.h>\n\n"
            "int add_numbers(int a, int b) {\n"
            "    return a + b;\n"
            "}\n\n"
            "int main() {\n"
            "    int sum = add_numbers(10);\n"
            "    printf(\"Sum: %d\\n\", sum);\n"
            "    return 0;\n"
            "}\n"
        )
        self.workspace.write_file("calc.c", c_code, overwrite=True)

        # 1. Independent Verification detects argument count mismatch
        passed, diags = self.verifier.verify_c_code("calc.c")
        self.assertFalse(passed, "Verification must fail due to argument count mismatch in C call site.")
        self.assertTrue(any("too few arguments to function 'add_numbers'" in d.error_message for d in diags))
        diag = diags[0]

        # 2. AI agent reasoning repair
        def mock_c_fix(**kwargs):
            return {
                "code": (
                    "#include <stdio.h>\n\n"
                    "int add_numbers(int a, int b) {\n"
                    "    return a + b;\n"
                    "}\n\n"
                    "int main() {\n"
                    "    int sum = add_numbers(10, 20);\n"
                    "    printf(\"Sum: %d\\n\", sum);\n"
                    "    return 0;\n"
                    "}\n"
                ),
                "explanation": "Added missing second argument (20) to add_numbers() invocation.",
                "provider": "mock_llama_coding_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_c_fix)
        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])

        # 3. Re-verification passes
        repassed, rediags = self.verifier.verify_c_code("calc.c")
        self.assertTrue(repassed, f"C re-verification should pass: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Test E: Cross-file missing export (math_utils.js export imported by main.js)
    # =========================================================================
    def test_e_cross_file_missing_export(self):
        """
        Detects missing export across project files.
        CodingAgent receives context of both files and exports the missing member.
        Re-verification passes.
        """
        math_utils_code = (
            "function square(x) {\n"
            "    return x * x;\n"
            "}\n"
            "// Missing module.exports\n"
        )
        main_code = (
            "const { square } = require('./math_utils');\n"
            "console.log('Square of 4 is:', square(4));\n"
        )
        self.workspace.write_file("math_utils.js", math_utils_code, overwrite=True)
        self.workspace.write_file("main.js", main_code, overwrite=True)

        # 1. Independent Verification detects missing export
        passed, diags = self.verifier.verify_module_exports()
        self.assertFalse(passed, "Verification must fail when imported symbol is not exported.")
        self.assertTrue(any("has no exported member 'square'" in d.error_message for d in diags))
        diag = diags[0]

        # 2. AI agent receives context and updates math_utils.js
        def mock_export_fix(diagnostic, current_code, context, **kwargs):
            # Target is math_utils.js
            return {
                "code": (
                    "function square(x) {\n"
                    "    return x * x;\n"
                    "}\n"
                    "module.exports = { square };\n"
                ),
                "explanation": "Exported square function via module.exports.",
                "provider": "mock_llama_coding_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_export_fix)
        # Note: target file to fix is math_utils.js
        diag.file_path = "math_utils.js"
        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])

        # 3. Re-verification passes
        repassed, rediags = self.verifier.verify_module_exports()
        self.assertTrue(repassed, f"Cross-file module exports should pass: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Test F: Logic error despite successful compilation (functional test failure)
    # =========================================================================
    def test_f_logic_error_despite_successful_compilation(self):
        """
        Syntax is 100% valid, but functional test fails due to inverted logic.
        Verifier captures functional failure with expected vs actual output.
        CodingAgent corrects logic and functional test passes.
        """
        code = (
            "def is_even(number: int) -> bool:\n"
            "    # Bug: Inverted logic\n"
            "    return number % 2 != 0\n\n"
            "if __name__ == '__main__':\n"
            "    print(is_even(4))\n"
        )
        self.workspace.write_file("logic.py", code, overwrite=True)

        # Acceptance test
        def functional_acceptance_test(root_dir):
            import importlib.util
            spec = importlib.util.spec_from_file_location("logic", root_dir / "logic.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if mod.is_even(4) is not True:
                return False, "is_even(4) returned False; expected True."
            if mod.is_even(7) is not False:
                return False, "is_even(7) returned True; expected False."
            return True, ""

        # 1. Verification fails on functional criteria despite zero syntax errors
        passed, diags = self.verifier.verify_python_deliverable(
            entry_file="logic.py",
            run_entry=True,
            functional_test=functional_acceptance_test,
        )
        self.assertFalse(passed, "Verification must reject candidate due to functional logic error.")
        self.assertTrue(any(d.verification_category == VerificationCategory.FUNCTIONAL for d in diags))
        diag = diags[0]

        # 2. AI agent reasoning repair
        def mock_logic_fix(**kwargs):
            return {
                "code": (
                    "def is_even(number: int) -> bool:\n"
                    "    return number % 2 == 0\n\n"
                    "if __name__ == '__main__':\n"
                    "    print(is_even(4))\n"
                ),
                "explanation": "Corrected inverted boolean predicate from != to ==.",
                "provider": "mock_llama_coding_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_logic_fix)
        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])

        # 3. Re-verification passes
        repassed, rediags = self.verifier.verify_python_deliverable(
            entry_file="logic.py",
            run_entry=True,
            functional_test=functional_acceptance_test,
        )
        self.assertTrue(repassed, f"Functional acceptance test should pass: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Test G: Unfamiliar error (KeyError with no hardcoded rule in MIND)
    # =========================================================================
    def test_g_unfamiliar_error_no_hardcoded_rule(self):
        """
        Unfamiliar runtime exception (KeyError: 'auth_token').
        MIND has no predefined rule or regex for this specific domain error.
        CodingAgent receives the raw runtime diagnostic and resolves it dynamically.
        """
        code = (
            "def authenticate(headers: dict):\n"
            "    token = headers['auth_token']\n"
            "    return f'Bearer {token}'\n\n"
            "if __name__ == '__main__':\n"
            "    # Missing 'auth_token' in headers\n"
            "    print(authenticate({'user_id': 101}))\n"
        )
        self.workspace.write_file("auth.py", code, overwrite=True)

        # 1. Independent Verification executes code and catches KeyError
        passed, diags = self.verifier.verify_python_deliverable(
            entry_file="auth.py",
            run_entry=True,
        )
        self.assertFalse(passed)
        self.assertTrue(any("KeyError" in d.error_message or "KeyError" in (d.diagnostic_output or "") for d in diags))
        diag = diags[0]

        # 2. AI agent reasoning repair (no hardcoded rule exists)
        def mock_auth_fix(**kwargs):
            return {
                "code": (
                    "def authenticate(headers: dict):\n"
                    "    token = headers.get('auth_token', 'default_guest_token')\n"
                    "    return f'Bearer {token}'\n\n"
                    "if __name__ == '__main__':\n"
                    "    print(authenticate({'user_id': 101}))\n"
                ),
                "explanation": "Guarded dictionary access with .get() fallback to prevent unhandled KeyError.",
                "provider": "mock_llama_coding_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_auth_fix)
        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])
        self.assertEqual(res["repair_pathway"], "ai_agent_reasoning")

        # 3. Re-verification passes
        repassed, rediags = self.verifier.verify_python_deliverable(
            entry_file="auth.py",
            run_entry=True,
        )
        self.assertTrue(repassed, f"Re-verification should pass without KeyError: {[d.error_message for d in rediags]}")

    # =========================================================================
    # Agent Verification: Diagnostic Received & Full Audit Contract Recorded
    # =========================================================================
    def test_agent_receives_complete_diagnostic_and_context(self):
        """
        Verifies that CodingAgent receives full structured diagnostic information:
        category, file_path, line_number, diagnostic_output, expected/actual behavior,
        and workspace architectural context.
        """
        received_args = {}

        def mock_spy_agent(**kwargs):
            received_args.update(kwargs)
            return {
                "code": "print('Fixed')\n",
                "explanation": "Mock fix",
                "provider": "test_spy",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_spy_agent)

        self.workspace.write_file("dummy.py", "x = 1 / 0\n", overwrite=True)
        self.workspace.write_file("helper.py", "# Helper module\n", overwrite=True)

        diag = DiagnosticReport(
            task_id="task_audit",
            project_id="proj_audit",
            agent_responsible="coding_agent",
            verification_category=VerificationCategory.RUNTIME,
            error_severity="ERROR",
            file_path="dummy.py",
            line_number=1,
            error_message="ZeroDivisionError: division by zero",
            expected_behavior="Valid arithmetic",
            actual_behavior="ZeroDivisionError",
        )

        res = self.repair_engine._apply_repair(self.workspace, diag)
        self.assertTrue(res["success"])

        # Validate structured diagnostic was delivered to agent
        self.assertIn("diagnostic", received_args)
        passed_diag = received_args["diagnostic"]
        self.assertEqual(passed_diag.verification_category, VerificationCategory.RUNTIME)
        self.assertEqual(passed_diag.file_path, "dummy.py")

        # Validate architectural context was delivered to agent
        self.assertIn("context", received_args)
        ctx = received_args["context"]
        self.assertIn("workspace_files", ctx)
        self.assertIn("helper.py", ctx["workspace_files"])

    def test_repair_engine_records_full_audit_contract(self):
        """
        Verifies that ClosedLoopRepairEngine records agent_identity, relevant_context,
        repair_response, files_changed, verification_before, and verification_after
        in RepairAttempt objects.
        """
        broken_code = "print('hello'"  # Syntax error: unclosed parenthesis
        self.workspace.write_file("index.html", "<html><body><h1>Hello</h1></body></html>", overwrite=True)
        self.workspace.write_file("app.py", broken_code, overwrite=True)

        def mock_fix(**kwargs):
            return {
                "code": "print('hello')\n",
                "explanation": "Closed parenthesis.",
                "provider": "mock_brain",
            }

        self.registry.coding_agent.set_mock_ai_agent(mock_fix)

        report = self.repair_engine.run_closed_loop(
            workspace=self.workspace,
            project_type=ProjectType.BACKEND_API,
            entry_point="app.py",
            project_name="Contract_Test",
        )

        self.assertTrue(report.success)
        self.assertEqual(report.status, ProjectStatus.PASSED.value)
        self.assertGreater(len(report.repair_attempts), 0)

        attempt = report.repair_attempts[0]
        self.assertEqual(attempt["agent_identity"], "coding_agent")
        self.assertIn("target_file", attempt["relevant_context"])
        self.assertIn("app.py", attempt["files_changed"])
        self.assertEqual(attempt["verification_before"]["status"], "FAILED")
        self.assertEqual(attempt["verification_after"]["status"], "PASSED")
        self.assertTrue(attempt["verification_passed"])

    # =========================================================================
    # Design Approval Defaults & Lifecycle Tests
    # =========================================================================
    def test_design_approval_enabled_by_default(self):
        """
        Verifies require_design_approval is True by default.
        """
        cfg = GameDevConfig.load()
        self.assertTrue(cfg.require_design_approval, "require_design_approval must be True by default.")

    def test_initial_generation_stops_at_awaiting_approval(self):
        """
        Verifies that project creation pauses at AWAITING_APPROVAL and does not
        generate final code assets until user explicitly approves.
        """
        db = SessionMemory(Path(self.tmp_dir) / "test_session.db")
        conv = ConversationState(db)
        spec = ProjectSpecification(project_name="ShopWebsite", title="ShopWebsite", description="Shop", project_type=ProjectType.WEBSITE)
        conv.set_pending_design(
            spec=spec,
            plan={"title": "Shop", "theme": "dark"},
            version=1,
        )

        pending = conv.pending_design_approval
        self.assertIsNotNone(pending)
        self.assertEqual(pending["status"], "awaiting_approval")
        self.assertEqual(pending["version"], 1)

    def test_design_revision_cycle_increments_version(self):
        """
        Verifies that requesting design revisions updates the proposal,
        increments the version number, and preserves AWAITING_APPROVAL state.
        """
        db = SessionMemory(Path(self.tmp_dir) / "test_session.db")
        conv = ConversationState(db)
        spec = ProjectSpecification(project_name="ECommerce", title="ECommerce", description="ECommerce", project_type=ProjectType.WEBSITE)
        conv.set_pending_design(
            spec=spec,
            plan={"title": "ECommerce", "theme": "light", "pages": ["index.html"], "palette": {"primary": "#0284c7"}},
            version=1,
        )

        # Apply revision instruction
        design_agent = DesignAgent(self.config)
        current = conv.pending_design_approval
        revised_plan = design_agent.revise_design_plan(current["plan"], "change theme to emerald motif and add pricing.html")

        conv.update_pending_design(revised_plan)

        updated = conv.pending_design_approval
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["status"], "awaiting_approval")
        self.assertEqual(updated["plan"]["palette"]["primary"], "#10b981")
        self.assertIn("pricing.html", updated["plan"]["pages"])

    def test_design_cancellation_cleans_up_state(self):
        """
        Verifies that user saying 'cancel' clears pending proposal and sets state to CANCELLED.
        """
        db = SessionMemory(Path(self.tmp_dir) / "test_session.db")
        conv = ConversationState(db)
        spec = ProjectSpecification(project_name="CancelledProject", title="Cancelled", description="Cancelled", project_type=ProjectType.WEBSITE)
        conv.set_pending_design(
            spec=spec,
            plan={"title": "Cancelled"},
            version=1,
        )

        res = conv.cancel_pending_design()
        self.assertIsNotNone(res)
        self.assertIsNone(conv.pending_design_approval)

    def test_destructive_confirmation_does_not_approve_design(self):
        """
        Ensures confirmation of destructive operations (like delete) does not
        inadvertently trigger design approval or code generation.
        """
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        cfg.workspace_root = self.workspace_root
        orch = GameDevOrchestrator(config=cfg, enable_voice=False)

        # Create a pending design
        spec = ProjectSpecification(project_name="PendingApp", title="PendingApp", description="App", project_type=ProjectType.WEBSITE)
        orch.conversation_state.set_pending_design(
            spec=spec,
            plan={"title": "PendingApp", "theme": "modern"},
            version=1,
        )

        # Create a dummy file to delete
        (self.workspace_root / "temp.txt").write_text("temporary", encoding="utf-8")

        # Action: User asks to delete file without force
        del_res = orch.execute_command("delete temp.txt")
        self.assertEqual(del_res["status"], "CONFIRMATION_REQUIRED")

        # Pending design must remain pending
        self.assertIsNotNone(orch.conversation_state.pending_design_approval)
        self.assertEqual(orch.conversation_state.pending_design_approval["status"], "awaiting_approval")

        # User confirms deletion of the file
        del_confirm_res = orch.execute_command("confirm delete temp.txt")
        self.assertEqual(del_confirm_res["status"], "SUCCESS")
        self.assertFalse((self.workspace_root / "temp.txt").exists())

        # Pending design MUST still be pending and unapproved!
        self.assertIsNotNone(orch.conversation_state.pending_design_approval)
        self.assertEqual(orch.conversation_state.pending_design_approval["status"], "awaiting_approval")


if __name__ == "__main__":
    unittest.main()
