"""
Comprehensive Automated Tests for MIND Automated Workflow Screenshot Capture
and Visual Evidence System.

Verifies:
1. Centralized WorkflowScreenshotManager lifecycle and directory structure
2. Capture across all 15 workflow stages from Stage 01 (Request) to Stage 15 (Report)
3. Chronological ordering, unique IDs, timestamps, and stage tags
4. Non-overwriting retention when stages repeat
5. Automatic retry mechanism on capture failure
6. Session isolation between concurrent workflows
7. Generation of workflow_manifest.json and interactive workflow_report.html
8. Real desktop/canvas visual capture and evidence viewer integration
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import (
    ProjectSpecification,
    ProjectStatus,
    ProjectType,
    DiagnosticReport,
    VerificationCategory,
)
from MIND_GameDev.tools.screenshot_manager import (
    WorkflowScreenshotManager,
    WorkflowStage,
    ScreenshotMetadata,
    STAGE_DISPLAY_NAMES,
)
from MIND_GameDev.orchestrator import GameDevOrchestrator
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager


class TestWorkflowScreenshotManager(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.evidence_root = Path(self.tmp_dir) / "MIND_EVIDENCE"
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.manager = WorkflowScreenshotManager(
            session_id="test_session_evidence_001",
            evidence_root=self.evidence_root,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_directory_structure_and_all_15_stage_folders(self):
        """Verifies session directory and all 15 stage folders exist."""
        session_dir = self.manager.session_dir
        self.assertTrue(session_dir.exists())

        for stage in WorkflowStage:
            stage_dir = session_dir / stage.value
            self.assertTrue(stage_dir.exists(), f"Stage directory missing: {stage.value}")

        manifest_file = session_dir / "workflow_manifest.json"
        self.assertTrue(manifest_file.exists())

    def test_02_chronological_capture_and_unique_ids(self):
        """Verifies sequential ordering, timestamps, and unique screenshot IDs."""
        meta1 = self.manager.capture(
            stage=WorkflowStage.STAGE_01_USER_REQUEST,
            event_name="request.received",
            description="User prompt submitted: Create a modern fintech portal",
            evidence_data={"prompt": "Create a modern fintech portal"},
        )
        meta2 = self.manager.capture(
            stage=WorkflowStage.STAGE_02_REQUEST_UNDERSTANDING,
            event_name="request.understood",
            description="Requirements parsed: fintech domain, responsive web",
            evidence_data={"domain": "fintech"},
        )

        self.assertEqual(meta1.sequence_number, 1)
        self.assertEqual(meta2.sequence_number, 2)
        self.assertTrue(meta1.timestamp <= meta2.timestamp)
        self.assertNotEqual(meta1.screenshot_id, meta2.screenshot_id)
        self.assertTrue(Path(meta1.file_path).exists())
        self.assertTrue(Path(meta2.file_path).exists())

    def test_03_non_overwriting_retention_when_stage_repeats(self):
        """Repeated captures in the same stage (e.g. repair iterations) must not overwrite earlier evidence."""
        meta_a = self.manager.capture(
            stage=WorkflowStage.STAGE_10_ERROR_DETECTION,
            event_name="error.detected",
            description="Attempt 1: Unclosed div detected",
        )
        time.sleep(0.01)
        meta_b = self.manager.capture(
            stage=WorkflowStage.STAGE_10_ERROR_DETECTION,
            event_name="error.detected",
            description="Attempt 2: Unbalanced brace detected",
        )

        self.assertNotEqual(meta_a.file_path, meta_b.file_path)
        self.assertTrue(Path(meta_a.file_path).exists())
        self.assertTrue(Path(meta_b.file_path).exists())
        self.assertEqual(len(self.manager.captures), 2)

    def test_04_automatic_retry_on_recoverable_failure(self):
        """Failure during initial grab triggers bounded retry and logs recovery status."""
        # Force initial failure then succeed
        call_count = [0]
        orig_render = self.manager._render_evidence_card

        def _flaky_render(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("Transient file lock")
            return orig_render(*args, **kwargs)

        with patch.object(self.manager, "_render_evidence_card", side_effect=_flaky_render):
            meta = self.manager.capture(
                stage=WorkflowStage.STAGE_07_IMPLEMENTATION,
                event_name="implementation.started",
                description="Testing retry logic",
            )
            self.assertTrue(meta.success)
            self.assertEqual(meta.retries_attempted, 1)

    def test_05_concurrent_session_isolation(self):
        """Two concurrent workflow sessions maintain strictly isolated directories and manifests."""
        session_a = WorkflowScreenshotManager("session_alpha", self.evidence_root)
        session_b = WorkflowScreenshotManager("session_beta", self.evidence_root)

        meta_a = session_a.capture(WorkflowStage.STAGE_01_USER_REQUEST, "req", "Prompt Alpha")
        meta_b = session_b.capture(WorkflowStage.STAGE_01_USER_REQUEST, "req", "Prompt Beta")

        self.assertIn("session_alpha", meta_a.file_path)
        self.assertIn("session_beta", meta_b.file_path)
        self.assertEqual(len(session_a.captures), 1)
        self.assertEqual(len(session_b.captures), 1)
        self.assertNotEqual(session_a.session_dir, session_b.session_dir)

    def test_06_manifest_and_interactive_html_report_generation(self):
        """Verifies workflow_manifest.json and workflow_report.html contain all captured stages."""
        self.manager.set_original_request("Build modern AI analytics portal")

        for idx, stage in enumerate(WorkflowStage, start=1):
            self.manager.capture(
                stage=stage,
                event_name=f"event_{stage.value}",
                description=f"Evidence captured for stage {stage.value}",
                evidence_data={"stage_index": idx},
            )

        # Check Manifest
        manifest_path = self.manager.session_dir / "workflow_manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_captures"], 15)
        self.assertEqual(manifest["original_request"], "Build modern AI analytics portal")
        self.assertEqual(len(manifest["stages_recorded"]), 15)

        # Check HTML Report
        report_path = self.manager.session_dir / "workflow_report.html"
        self.assertTrue(report_path.exists())
        html_text = report_path.read_text(encoding="utf-8")
        self.assertIn("MIND // WORKFLOW VISUAL EVIDENCE DOSSIER", html_text)
        self.assertIn("test_session_evidence_001", html_text)
        self.assertIn("Build modern AI analytics portal", html_text)
        self.assertIn("01. User Request", html_text)
        self.assertIn("15. Completion Report", html_text)

    def test_07_real_orchestrator_end_to_end_workflow_evidence(self):
        """
        Executes a real MIND development workflow from user prompt to final delivery,
        verifying that visual evidence is captured across the lifecycle.
        """
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        ws_root = Path(self.tmp_dir) / "workspace"
        ws_root.mkdir(parents=True, exist_ok=True)
        cfg.workspace_root = ws_root

        orch = GameDevOrchestrator(config=cfg, enable_voice=False)
        cmd = "create website for aerospace dynamics lab"
        plan_res = orch.execute_command(cmd)
        self.assertEqual(plan_res["status"], "APPROVAL_REQUIRED")

        result = orch.execute_command("approve")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(result["verification"]["success"])

        # Inspect captured evidence
        mgr = WorkflowScreenshotManager.get_instance()
        self.assertGreater(len(mgr.captures), 5)
        recorded_stages = [c.stage for c in mgr.captures]
        
        # Must include request, understanding, planning, implementation, verification, delivery, and report
        self.assertIn(WorkflowStage.STAGE_01_USER_REQUEST, recorded_stages)
        self.assertIn(WorkflowStage.STAGE_02_REQUEST_UNDERSTANDING, recorded_stages)
        self.assertIn(WorkflowStage.STAGE_03_PLANNING_ARCHITECTURE, recorded_stages)
        self.assertIn(WorkflowStage.STAGE_07_IMPLEMENTATION, recorded_stages)
        self.assertIn(WorkflowStage.STAGE_08_INITIAL_EXECUTION, recorded_stages)
        self.assertIn(WorkflowStage.STAGE_13_FINAL_EXECUTION, recorded_stages)
        self.assertIn(WorkflowStage.STAGE_14_FINAL_DELIVERY, recorded_stages)
        self.assertIn(WorkflowStage.STAGE_15_COMPLETION_REPORT, recorded_stages)

        # Verify all captured image files physically exist on disk
        for c in mgr.captures:
            self.assertTrue(Path(c.file_path).exists(), f"Image missing: {c.file_path}")
            self.assertGreater(Path(c.file_path).stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
