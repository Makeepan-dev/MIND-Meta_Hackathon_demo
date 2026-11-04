"""
MIND Universal Development Studio — Closed-Loop Automated Repair Engine.
Enforces MIND's core development principle:
"Every generated output is a candidate implementation that must pass MIND-controlled,
independent verification before it can be finalized."

Workflow Cycle:
GENERATE -> VERIFY -> DIAGNOSE -> ASSIGN REPAIR -> APPLY CORRECTION -> VERIFY AGAIN
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..config import GameDevConfig
from ..models import (
    AgentTask,
    DiagnosticReport,
    ExecutionReport,
    ProjectStatus,
    ProjectType,
    RepairAttempt,
    VerificationCategory,
)
from ..tools.workspace_files import SafeWorkspaceManager
from ..tools.independent_verifier import IndependentVerifier
from ..agents.specialized_agents import (
    AgentRegistry,
    CodingAgent,
    DesignAgent,
    ImageAssetAgent,
    ThreeDAssetAgent,
)

logger = logging.getLogger("mind.gamedev.repair_engine")


class ClosedLoopRepairEngine:
    """
    Coordinates candidate verification, diagnostic generation, agent repair assignments,
    safe checkpoints, recurring-error detection, and bounded retry loops.
    """

    def __init__(
        self,
        config: Optional[GameDevConfig] = None,
        agent_registry: Optional[AgentRegistry] = None,
    ) -> None:
        self.config = config or GameDevConfig.load()
        self.registry = agent_registry or AgentRegistry(self.config)
        self.max_retries = self.config.max_repair_retries
        self.timeout_seconds = self.config.repair_timeout_seconds

    def run_closed_loop(
        self,
        workspace: SafeWorkspaceManager,
        project_type: ProjectType,
        project_name: str,
        entry_point: str = "index.html",
        functional_requirements: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ExecutionReport:
        """
        Executes independent verification and bounded automated repair iterations
        until all criteria pass or recovery limits are reached.
        """
        start_time = time.time()
        workflow_id = f"wf_{uuid.uuid4().hex[:8]}"
        verifier = IndependentVerifier(workspace)

        def _notify(stage: str, msg: str, pct: float, status: ProjectStatus) -> None:
            if progress_callback:
                progress_callback({
                    "workflow_id": workflow_id,
                    "stage": stage,
                    "message": msg,
                    "progress": pct,
                    "status": status.value,
                    "project_name": project_name,
                })

        # Stage: Initial Candidate Verification
        _notify("verifying", f"Initiating independent multi-layer verification for '{project_name}'...", 0.50, ProjectStatus.VERIFYING)

        current_attempt = 0
        repair_history: List[RepairAttempt] = []
        seen_failure_signatures: Set[str] = set()
        recurring_error_detected = False
        limitations: List[str] = []

        # Initial checkpoint of candidate implementation
        workspace.create_checkpoint("initial_candidate")

        while current_attempt <= self.max_retries:
            from ..tools.screenshot_manager import WorkflowScreenshotManager, WorkflowStage
            screenshot_mgr = WorkflowScreenshotManager.get_instance()

            # STAGE 09: Automated Testing Capture
            screenshot_mgr.capture(
                stage=WorkflowStage.STAGE_09_AUTOMATED_TESTING,
                event_name="tests.started",
                description=f"Automated verification suite executing for '{project_name}' (Attempt #{current_attempt + 1}).",
                evidence_data={"attempt": current_attempt + 1, "project": project_name},
            )

            # 1. INDEPENDENT VERIFICATION
            passed, diagnostics = self._execute_verification(
                verifier=verifier,
                project_type=project_type,
                entry_point=entry_point,
                task_id=f"{workflow_id}_attempt_{current_attempt}",
                project_id=project_name,
                functional_requirements=functional_requirements,
            )

            # Filter diagnostics
            critical_errors = [d for d in diagnostics if d.error_severity in ("ERROR", "CRITICAL")]
            warnings = [d for d in diagnostics if d.error_severity == "WARNING"]

            if not critical_errors:
                # All critical checks passed!
                for att in repair_history:
                    att.verification_passed = True
                    att.verification_after = {"status": "PASSED"}

                final_status = ProjectStatus.PASSED if not warnings else ProjectStatus.NEEDS_ATTENTION
                elapsed = round(time.time() - start_time, 3)
                
                # STAGE 12: Independent Verification Passed Capture
                screenshot_mgr.capture(
                    stage=WorkflowStage.STAGE_12_INDEPENDENT_VERIFICATION,
                    event_name="verification.completed",
                    description=f"Independent multi-layer verification PASSED for '{project_name}'. Mandatory checks passed.",
                    evidence_data={"passed": True, "diagnostics_count": len(diagnostics), "status": final_status.value},
                )

                if warnings:
                    limitations.extend([f"Non-critical notice: {w.error_message}" for w in warnings])

                summary_msg = f"Project '{project_name}' verified and passed all mandatory criteria."
                if current_attempt > 0:
                    summary_msg += f" (Resolved through {current_attempt} automated repair cycle{'s' if current_attempt > 1 else ''})."

                _notify("passed", summary_msg, 1.0, final_status)

                return ExecutionReport(
                    workflow_id=workflow_id,
                    project_name=project_name,
                    success=True,
                    status=final_status.value,
                    project_type=project_type.value if hasattr(project_type, "value") else str(project_type),
                    project_path=str(workspace.workspace_root),
                    entry_point=entry_point,
                    files_created=[f.name for f in workspace.workspace_root.rglob("*") if f.is_file() and ".mind_checkpoints" not in f.parts],
                    verification_results={"passed": True, "diagnostics_count": len(diagnostics)},
                    tests_passed=1,
                    tests_failed=0,
                    elapsed_seconds=elapsed,
                    summary=summary_msg,
                    limitations=limitations,
                    errors=[],
                    warnings=[w.error_message for w in warnings],
                    diagnostics=[d.to_dict() for d in diagnostics],
                    repair_attempts=[r.to_dict() for r in repair_history],
                    is_candidate=False,
                )

            # Check if timeout exceeded
            if (time.time() - start_time) > self.timeout_seconds:
                limitations.append(f"Repair timeout of {self.timeout_seconds}s exceeded.")
                break

            # Check if max retries reached
            if current_attempt >= self.max_retries:
                limitations.append(f"Exhausted maximum configured repair attempts ({self.max_retries}).")
                break

            # 2. DIAGNOSTIC SIGNATURE ANALYSIS & RECURRING ERROR DETECTION
            # STAGE 10: Error Detection Capture
            screenshot_mgr.capture(
                stage=WorkflowStage.STAGE_10_ERROR_DETECTION,
                event_name="error.detected",
                description=f"Detected {len(critical_errors)} verification failure(s): {critical_errors[0].error_message}",
                evidence_data={
                    "total_errors": len(critical_errors),
                    "primary_error": critical_errors[0].error_message,
                    "primary_file": critical_errors[0].file_path,
                    "diagnostics": [d.to_dict() for d in critical_errors],
                },
                evidence_type="internal_evidence",
            )

            current_signature = "|".join(
                f"{d.verification_category.value}:{d.file_path}:{d.line_number or 0}:{d.error_message}"
                for d in critical_errors
            )
            if current_signature in seen_failure_signatures:
                recurring_error_detected = True
                logger.warning(f"Recurring error signature detected in attempt {current_attempt + 1}. Escalating repair strategy.")
            seen_failure_signatures.add(current_signature)

            # 3. ASSIGN REPAIR TO SPECIALIZED AGENT
            current_attempt += 1
            _notify(
                "repairing",
                f"Verification detected {len(critical_errors)} issue(s). Initiating repair cycle {current_attempt}/{self.max_retries}...",
                0.50 + (current_attempt * 0.10),
                ProjectStatus.REPAIRING,
            )

            # Save checkpoint before applying repair
            workspace.create_checkpoint(f"pre_repair_attempt_{current_attempt}")

            # Group critical diagnostics by file to repair all diagnosed files in this iteration
            files_to_fix: Dict[str, List[DiagnosticReport]] = {}
            for diag in critical_errors:
                files_to_fix.setdefault(diag.file_path, []).append(diag)

            for f_path, f_diags in files_to_fix.items():
                for diag in f_diags:
                    repair_result = self._apply_repair(
                        workspace=workspace,
                        diagnostic=diag,
                        recurring_escalation=recurring_error_detected,
                    )
                    repair_attempt = RepairAttempt(
                        attempt_number=current_attempt,
                        diagnostic=diag,
                        patch_applied=repair_result.get("changes_made", ["Applied code patch"])[0] if repair_result.get("changes_made") else "Patch",
                        explanation=repair_result.get("explanation", "Automated correction applied."),
                        verification_passed=False,
                        agent_identity=repair_result.get("agent_responsible", "coding_agent"),
                        relevant_context={
                            "target_file": diag.file_path,
                            "recurring_escalation": recurring_error_detected,
                            "diagnostic_category": diag.verification_category.value,
                        },
                        repair_response=repair_result,
                        files_changed=[diag.file_path] if repair_result.get("success") else [],
                        verification_before={"status": "FAILED", "error": diag.error_message, "category": diag.verification_category.value},
                        verification_after={"status": "PENDING_REVERIFICATION"},
                    )
                    repair_history.append(repair_attempt)

            # STAGE 11: Automated Correction Capture
            screenshot_mgr.capture(
                stage=WorkflowStage.STAGE_11_AUTOMATED_CORRECTION,
                event_name="correction.completed",
                description=f"Applied language-aware code corrections across {len(files_to_fix)} file(s).",
                evidence_data={
                    "files_repaired": list(files_to_fix.keys()),
                    "repair_attempts_count": len(repair_history),
                    "latest_explanation": repair_history[-1].explanation if repair_history else "",
                },
                evidence_type="internal_evidence",
            )

            _notify("reverifying", f"Applied corrections for {len(files_to_fix)} file(s). Re-verifying candidate implementation...", 0.60 + (current_attempt * 0.10), ProjectStatus.REVERIFYING)

        # 4. RECOVERY FAILED OR EXHAUSTED
        elapsed = round(time.time() - start_time, 3)
        failure_msg = f"Project '{project_name}' could not be fully finalized. Unresolved verification failures remain."
        _notify("failed", failure_msg, 1.0, ProjectStatus.FAILED)

        return ExecutionReport(
            workflow_id=workflow_id,
            project_name=project_name,
            success=False,
            status=ProjectStatus.FAILED.value,
            project_type=project_type.value if hasattr(project_type, "value") else str(project_type),
            project_path=str(workspace.workspace_root),
            entry_point=entry_point,
            files_created=[f.name for f in workspace.workspace_root.rglob("*") if f.is_file() and ".mind_checkpoints" not in f.parts],
            verification_results={"passed": False, "remaining_errors": len(critical_errors)},
            tests_passed=0,
            tests_failed=len(critical_errors),
            elapsed_seconds=elapsed,
            summary=failure_msg,
            limitations=limitations,
            errors=[d.error_message for d in critical_errors],
            warnings=[w.error_message for w in warnings],
            diagnostics=[d.to_dict() for d in diagnostics],
            repair_attempts=[r.to_dict() for r in repair_history],
            is_candidate=True,  # Kept as candidate, not finalized product
        )

    def _execute_verification(
        self,
        verifier: IndependentVerifier,
        project_type: ProjectType,
        entry_point: str,
        task_id: str,
        project_id: str,
        functional_requirements: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """Dispatches verification according to project type."""
        p_val = project_type.value if hasattr(project_type, "value") else str(project_type).lower()

        if p_val in ("website", "web_app"):
            return verifier.verify_web_deliverable(
                task_id=task_id,
                project_id=project_id,
                required_pages=[entry_point] if entry_point else ["index.html"],
                functional_requirements=functional_requirements,
            )
        elif p_val in ("desktop_app", "backend_api", "custom"):
            return verifier.verify_python_deliverable(
                entry_file=entry_point or "app/main.py",
                task_id=task_id,
                project_id=project_id,
                run_entry=False,
            )
        elif p_val == "game":
            # Games check HTML5 canvas, JS, and GLB models
            passed_web, diags_web = verifier.verify_web_deliverable(
                task_id=task_id,
                project_id=project_id,
                required_pages=["index.html"],
            )
            # Check GLB assets
            for glb in verifier.root.rglob("*.glb"):
                if ".mind_checkpoints" in glb.parts:
                    continue
                passed_3d, diags_3d = verifier.verify_3d_asset(
                    glb_file_path=glb.relative_to(verifier.root),
                    task_id=task_id,
                    project_id=project_id,
                )
                diags_web.extend(diags_3d)
                if not passed_3d:
                    passed_web = False
            return passed_web, diags_web
        else:
            # General fallback check
            return verifier.verify_web_deliverable(task_id=task_id, project_id=project_id)

    def _apply_repair(
        self,
        workspace: SafeWorkspaceManager,
        diagnostic: DiagnosticReport,
        recurring_escalation: bool = False,
    ) -> Dict[str, Any]:
        """Routes diagnostic report to the responsible specialist agent and writes correction."""
        target_file = workspace.workspace_root / diagnostic.file_path
        if not target_file.exists():
            return {"success": False, "explanation": f"Target file '{diagnostic.file_path}' does not exist."}

        # Route 3D assets to ThreeDAssetAgent
        if target_file.suffix.lower() == ".glb" or diagnostic.agent_responsible == "threed_agent":
            asset_type = target_file.stem
            meta = self.registry.threed_agent.adapter.generate_asset(
                name=asset_type,
                asset_type=asset_type,
                output_dir=target_file.parent,
                file_format="glb",
            )
            return {
                "success": target_file.exists() and target_file.stat().st_size > 50,
                "code": None,
                "explanation": f"Regenerated 3D binary model geometry for '{diagnostic.file_path}'.",
                "changes_made": [f"Regenerated GLB {diagnostic.file_path}"],
                "agent_responsible": "threed_agent",
            }

        current_code = target_file.read_text(encoding="utf-8", errors="replace")

        # Select language from extension
        ext = target_file.suffix.lower()
        lang = "python"
        if ext in (".html", ".htm"):
            lang = "html"
        elif ext == ".css":
            lang = "css"
        elif ext in (".js", ".jsx", ".mjs"):
            lang = "javascript"
        elif ext in (".ts", ".tsx"):
            lang = "typescript"
        elif ext in (".c", ".cpp", ".h"):
            lang = "c"

        # Construct workspace and architectural context for agent
        context = {
            "workspace_files": [
                str(p.relative_to(workspace.workspace_root)).replace("\\", "/")
                for p in workspace.workspace_root.rglob("*")
                if p.is_file() and ".mind_checkpoints" not in p.parts
            ],
            "related_files": {},
            "recurring_escalation": recurring_escalation,
        }
        for p in workspace.workspace_root.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".py", ".js", ".ts", ".c", ".h", ".html", ".css", ".json") and ".mind_checkpoints" not in p.parts:
                rel = str(p.relative_to(workspace.workspace_root)).replace("\\", "/")
                if rel != diagnostic.file_path.replace("\\", "/"):
                    try:
                        context["related_files"][rel] = p.read_text(encoding="utf-8", errors="replace")[:4000]
                    except Exception:
                        pass

        # Route to CodingAgent
        repair_res = self.registry.coding_agent.repair_code(
            diagnostic=diagnostic,
            current_code=current_code,
            language=lang,
            context=context,
        )

        if repair_res.get("success") and repair_res.get("code"):
            # Write corrected code safely to workspace
            workspace.write_file(diagnostic.file_path, repair_res["code"], overwrite=True)

        return repair_res
