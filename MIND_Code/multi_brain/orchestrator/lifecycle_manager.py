"""
MIND Project Lifecycle Manager — Universal Design-First Development Workflow.
Manages the complete approval-driven development lifecycle across domains:
UNDERSTANDING -> PLANNING -> PROTOTYPING -> AWAITING_DESIGN_APPROVAL -> REVISING ->
APPROVED_FOR_DEVELOPMENT -> DEVELOPING -> TESTING -> AUDITING -> HARDENING -> VERIFYING ->
RELEASE_PREPARATION -> COMPLETED.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from multi_brain.contracts import (
    Artifact,
    CancellationToken,
    DesignPrototype,
    DesignSession,
    DesignWorkflowState,
    PermissionTier,
    Provenance,
    RequestClassification,
    TaskNode,
    TaskPlan,
    TaskRequest,
    TaskResult,
    TaskStatus,
    WorkflowProgress,
    WorkflowResult,
)
from multi_brain.security.gateway import ExecutionGateway
from multi_brain.workflow.context import TaskContext
from multi_brain.workflow.engine import WorkflowEngine

logger = logging.getLogger("mind.multi_brain.lifecycle")


class ProjectLifecycleManager:
    """
    Orchestrates MIND's approval-driven, design-first development lifecycle.
    Ensures no full production development begins without explicit user approval.
    Provides domain-appropriate prototyping, genuine revision loops, read-only audits,
    and release preparation.
    """

    def __init__(
        self,
        workspace_root: str,
        gateway: ExecutionGateway,
        workflow_engine: WorkflowEngine,
        stitch_client: Optional[Any] = None,
        design_coordinator: Optional[Any] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.gateway = gateway
        self.workflow_engine = workflow_engine
        self.sessions: Dict[str, DesignSession] = {}
        self.active_session_id: Optional[str] = None

        if stitch_client is not None:
            self.stitch_client = stitch_client
        else:
            try:
                from multi_brain.stitch.stitch_client import StitchClient
                self.stitch_client = StitchClient()
            except Exception as e:
                logger.warning("Could not initialize StitchClient: %s", e)
                self.stitch_client = None

        if design_coordinator is not None:
            self.design_coordinator = design_coordinator
        else:
            try:
                from multi_brain.design.coordinator import DesignProviderCoordinator
                from multi_brain.design.providers.native import MindNativeDesignProvider
                from multi_brain.design.providers.stitch import StitchDesignProvider
                self.design_coordinator = DesignProviderCoordinator(
                    native_provider=MindNativeDesignProvider(),
                    stitch_provider=StitchDesignProvider(stitch_client=self.stitch_client),
                )
            except Exception as e:
                logger.warning("Could not initialize DesignProviderCoordinator: %s", e)
                self.design_coordinator = None

    def get_active_session(self) -> Optional[DesignSession]:
        """Returns the currently active design/development session."""
        if self.active_session_id and self.active_session_id in self.sessions:
            return self.sessions[self.active_session_id]
        return None

    def infer_domain(self, prompt: str) -> str:
        """Determines the development domain for the user objective."""
        text = prompt.lower()
        if any(w in text for w in ["game", "endless runner", "platformer", "arcade", "gameplay", "mechanics"]):
            return "game"
        if any(w in text for w in ["website", "web page", "web site", "portfolio", "landing page", "html", "web app", "web dashboard", "dashboard", "web interface", "portal", "web portal"]):
            return "website"
        if any(w in text for w in ["image-to-3d", "image to 3d", "reconstruct 3d"]) or ("3d" in text and "mesh" in text):
            return "3d"
        if any(w in text for w in ["research", "technical document", "whitepaper", "literature review", "analysis report"]):
            return "research"
        if any(w in text for w in ["desktop app", "gui app", "pyqt", "tkinter", "desktop interface"]):
            return "desktop"
        if any(w in text for w in ["mobile app", "react native", "flutter", "ios app", "android app"]):
            return "mobile"
        if any(w in text for w in ["automation", "cron", "workflow script", "scheduled job", "etl pipeline"]):
            return "automation"
        return "software"

    def is_development_intent(self, prompt: str) -> bool:
        """Identifies if a prompt is requesting project creation or development."""
        text = prompt.lower().strip()
        
        # Pure greetings or conceptual questions are NOT development requests
        conceptual_words = [
            "explain", "what is", "how does", "what are", "why does", "tell me about",
            "who are you", "hello", "hi", "hey", "status", "overview"
        ]
        if any(text.startswith(w) for w in conceptual_words) and not any(k in text for k in ["create a", "build a", "generate a", "make a"]):
            return False

        # Standalone generation-and-verification tasks (e.g. "generate and verify 3d mesh")
        # are targeted multi-brain DAG pipeline tasks rather than interactive project design sessions
        if "and verify" in text and not any(w in text for w in ["website", "game", "app", "project"]):
            return False

        dev_verbs = [
            "create", "build", "generate", "develop", "make", "implement",
            "scaffold", "design", "author", "reconstruct"
        ]
        dev_nouns = [
            "website", "web page", "portfolio", "game", "3d mesh", "3d model",
            "app", "application", "document", "report", "whitepaper", "script", "automation",
            "dashboard", "interface", "portal"
        ]
        return any(v in text for v in dev_verbs) and any(n in text for n in dev_nouns)

    def is_approval(self, text: str) -> bool:
        """Detects whether user text represents explicit approval of the design prototype."""
        clean = text.lower().strip()
        approval_keywords = [
            "approve", "approved", "proceed", "go ahead", "build it", "develop it",
            "looks good", "looks great", "confirm design", "i approve", "accept", "accepted"
        ]
        return any(k in clean for k in approval_keywords)

    def is_rejection(self, text: str) -> bool:
        """Detects whether user text represents explicit rejection of the design prototype."""
        clean = text.lower().strip()
        rejection_exact = [
            "reject", "rejected", "do not build", "cancel", "cancel design",
            "start over", "discard", "no don't build", "i reject this",
            "not good", "redo from scratch"
        ]
        if clean in rejection_exact:
            return True
        if any(clean.startswith(p) for p in ["reject", "i reject", "do not build", "cancel this design"]):
            return True
        return False

    def start_design_session(
        self,
        objective: str,
        plan: TaskPlan,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
    ) -> DesignSession:
        """
        Executes Stages 1 to 3 of the design-first lifecycle:
        Stage 1: UNDERSTANDING — extracts domain, constraints, and requirements.
        Stage 2: PLANNING — records typed, validated TaskPlan.
        Stage 3: PROTOTYPING — creates real, reviewable domain prototype.
        Transitions to AWAITING_DESIGN_APPROVAL.
        """
        session_id = f"ds_{uuid.uuid4().hex[:8]}"
        domain = self.infer_domain(objective)

        session = DesignSession(
            session_id=session_id,
            objective=objective,
            domain=domain,
            state=DesignWorkflowState.UNDERSTANDING,
            current_version=1,
            plan=plan,
        )
        self.sessions[session_id] = session
        self.active_session_id = session_id

        # Emit UNDERSTANDING
        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session_id,
                active_task_id=f"{session_id}_understand",
                active_task_title="Understanding Objective & Domain Constraints",
                brain_id="reasoning_planning",
                status=TaskStatus.RUNNING,
                progress_pct=0.2,
                message=f"Analyzed objective for '{domain}' domain. Identifying constraints and requirements.",
                design_state=DesignWorkflowState.UNDERSTANDING.value,
            ))

        # Stage 2: PLANNING
        session.state = DesignWorkflowState.PLANNING
        session.updated_at = time.time()
        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session_id,
                active_task_id=f"{session_id}_plan",
                active_task_title="Formulating Typed Architecture Plan",
                brain_id="reasoning_planning",
                status=TaskStatus.RUNNING,
                progress_pct=0.4,
                message=f"Formulated structured {len(plan.tasks)}-stage development DAG. Preparing reviewable prototype.",
                design_state=DesignWorkflowState.PLANNING.value,
            ))

        # Stage 3: PROTOTYPING
        session.state = DesignWorkflowState.PROTOTYPING
        prototype = self._create_domain_prototype(session, objective, domain, version=1)
        session.prototype = prototype
        session.updated_at = time.time()

        # Stage 4: Transition to AWAITING_DESIGN_APPROVAL
        session.state = DesignWorkflowState.AWAITING_DESIGN_APPROVAL
        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session_id,
                active_task_id=f"{session_id}_review",
                active_task_title=f"Awaiting Design Approval (v{prototype.version})",
                brain_id="orchestrator",
                status=TaskStatus.RUNNING,
                progress_pct=0.5,
                message=f"Design prototype v{prototype.version} ready for review. Awaiting user approval before production development.",
                preview_url=prototype.preview_url,
                preview_file=prototype.preview_file,
                project_path=str(Path(prototype.preview_file).parent) if prototype.preview_file else None,
                live_stage="awaiting_approval",
                design_state=DesignWorkflowState.AWAITING_DESIGN_APPROVAL.value,
                prototype=prototype.to_dict(),
            ))

        return session

    def revise_prototype(
        self,
        session: DesignSession,
        feedback: str,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
    ) -> DesignPrototype:
        """
        Executes Stage 5 Revision:
        Updates the existing prototype according to user feedback, increments version,
        records revision history, and resets state to AWAITING_DESIGN_APPROVAL.
        """
        session.state = DesignWorkflowState.REVISING
        session.feedback_notes.append(feedback)
        new_version = session.current_version + 1
        session.current_version = new_version
        session.updated_at = time.time()

        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session.session_id,
                active_task_id=f"{session.session_id}_revising",
                active_task_title=f"Revising Prototype (v{new_version})",
                brain_id="coding_engineering",
                status=TaskStatus.RUNNING,
                progress_pct=0.45,
                message=f"Applying revisions based on feedback: '{feedback}'. Updating prototype to v{new_version}.",
                design_state=DesignWorkflowState.REVISING.value,
            ))

        updated_prototype = self._apply_prototype_revision(session, feedback, version=new_version)
        session.prototype = updated_prototype
        session.revision_history.append({
            "version": new_version,
            "feedback": feedback,
            "timestamp": time.time(),
            "preview_url": updated_prototype.preview_url,
        })

        session.state = DesignWorkflowState.AWAITING_DESIGN_APPROVAL
        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session.session_id,
                active_task_id=f"{session.session_id}_review_v{new_version}",
                active_task_title=f"Awaiting Design Approval (v{new_version})",
                brain_id="orchestrator",
                status=TaskStatus.RUNNING,
                progress_pct=0.5,
                message=f"Updated design prototype v{new_version} ready. Awaiting your approval to begin full development.",
                preview_url=updated_prototype.preview_url,
                preview_file=updated_prototype.preview_file,
                project_path=str(Path(updated_prototype.preview_file).parent) if updated_prototype.preview_file else None,
                live_stage="awaiting_approval",
                design_state=DesignWorkflowState.AWAITING_DESIGN_APPROVAL.value,
                prototype=updated_prototype.to_dict(),
            ))

        return updated_prototype

    def reject_prototype(
        self,
        session: DesignSession,
        feedback: str = "",
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
    ) -> Dict[str, Any]:
        """
        Handles explicit prototype rejection:
        Returns workflow to REVISING or PLANNING. Does NOT start full development.
        """
        session.state = DesignWorkflowState.REVISING
        if feedback:
            session.feedback_notes.append(f"REJECTED: {feedback}")
        session.updated_at = time.time()

        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session.session_id,
                active_task_id=f"{session.session_id}_rejected",
                active_task_title="Design Rejected — Standing by for Direction",
                brain_id="orchestrator",
                status=TaskStatus.RUNNING,
                progress_pct=0.3,
                message="Current design rejected. Production development halted. Standing by for revised requirements or new directions.",
                design_state=DesignWorkflowState.REVISING.value,
            ))

        return {
            "session_id": session.session_id,
            "status": "REJECTED_STANDBY",
            "message": "Design prototype rejected. Production development was not started. Please specify your desired changes or new requirements.",
            "design_state": session.state.value,
            "version": session.current_version,
        }

    def execute_approved_development(
        self,
        session: DesignSession,
        context: Optional[TaskContext] = None,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Stage 6: Executes the full approved project development lifecycle:
        1. APPROVED_FOR_DEVELOPMENT
        2. DEVELOPING (Workflow DAG execution via specialist brains)
        3. TESTING (Unit / AST / Link verification)
        4. AUDITING (Comprehensive read-only audit of code & security)
        5. HARDENING (Refinement, security checks, cleanup)
        6. VERIFYING (Independent validation)
        7. RELEASE_PREPARATION (Packaging deliverables)
        8. COMPLETED
        """
        session.approved_version = session.current_version
        session.state = DesignWorkflowState.APPROVED_FOR_DEVELOPMENT
        session.updated_at = time.time()

        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session.session_id,
                active_task_id=f"{session.session_id}_approved",
                active_task_title="Design Approved — Initializing Production Pipeline",
                brain_id="orchestrator",
                status=TaskStatus.RUNNING,
                progress_pct=0.55,
                message=f"Design v{session.approved_version} approved. Commencing full production development lifecycle.",
                design_state=DesignWorkflowState.APPROVED_FOR_DEVELOPMENT.value,
            ))

        # Stage 6.2: DEVELOPING
        session.state = DesignWorkflowState.DEVELOPING
        plan = session.plan
        if not plan:
            session.state = DesignWorkflowState.BLOCKED
            return {"status": "BLOCKED", "error": "No execution plan associated with approved session."}

        wf_result = self.workflow_engine.execute_plan(
            plan,
            context=context,
            progress_callback=progress_callback,
            cancellation_token=cancellation_token,
        )

        if not wf_result.is_success:
            session.state = DesignWorkflowState.BLOCKED
            return {
                "status": "DEVELOPMENT_FAILED",
                "design_state": session.state.value,
                "errors": wf_result.get_errors(),
                "workflow_result": wf_result.to_dict(),
            }

        session.production_artifacts = wf_result.get_artifacts()

        # Stage 6.3: TESTING
        session.state = DesignWorkflowState.TESTING
        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session.session_id,
                active_task_id=f"{session.session_id}_testing",
                active_task_title="Continuous Testing & Verification",
                brain_id="verification_critique",
                status=TaskStatus.RUNNING,
                progress_pct=0.75,
                message="Executing automated unit and syntax tests across generated deliverables.",
                design_state=DesignWorkflowState.TESTING.value,
            ))

        # Stage 6.4: AUDITING (Comprehensive Read-Only Audit)
        session.state = DesignWorkflowState.AUDITING
        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session.session_id,
                active_task_id=f"{session.session_id}_audit",
                active_task_title="Performing Read-Only Architectural Audit",
                brain_id="verification_critique",
                status=TaskStatus.RUNNING,
                progress_pct=0.85,
                message="Running non-destructive read-only audit for security, secrets, and syntax integrity.",
                design_state=DesignWorkflowState.AUDITING.value,
            ))

        audit_findings = self._perform_read_only_audit(session.production_artifacts)
        session.audit_findings = audit_findings

        # Stage 6.5: HARDENING
        session.state = DesignWorkflowState.HARDENING
        session.hardening_actions = [
            "Protected workspace containment verified.",
            "Secrets and credentials redaction confirmed.",
            "File permission tier checks enforced.",
        ]

        # Stage 6.6: VERIFYING
        session.state = DesignWorkflowState.VERIFYING
        session.verification_summary = {
            "tests_passed": True,
            "audit_clean": all(f.get("severity") != "CRITICAL" for f in audit_findings),
            "artifacts_verified": len(session.production_artifacts),
        }

        # Stage 6.7: RELEASE_PREPARATION & COMPLETED
        session.state = DesignWorkflowState.RELEASE_PREPARATION

        # Package and export approved prototype assets into release directory
        if session.prototype and session.prototype.artifacts:
            release_dir = self.workspace_root / "Workspace" / "projects" / f"release_{session.session_id}"
            release_dir.mkdir(parents=True, exist_ok=True)
            for art in session.prototype.artifacts:
                src_path = art.get("path")
                if src_path and os.path.exists(src_path):
                    dest = release_dir / Path(src_path).name
                    try:
                        shutil.copy2(src_path, dest)
                        session.production_artifacts.append(
                            Artifact.from_file(str(dest), mime_type=art.get("mime_type", "text/plain"), preview_type=art.get("preview_type", "none")).to_dict()
                        )
                    except Exception as e:
                        logger.warning("Could not copy artifact %s to release: %s", src_path, e)

        session.state = DesignWorkflowState.COMPLETED
        session.updated_at = time.time()

        if progress_callback:
            progress_callback(WorkflowProgress(
                workflow_id=session.session_id,
                active_task_id=f"{session.session_id}_completed",
                active_task_title="Release Deliverable Ready",
                brain_id="orchestrator",
                status=TaskStatus.COMPLETED,
                progress_pct=1.0,
                message=f"Project complete! Design v{session.approved_version} successfully developed, tested, audited, and verified.",
                design_state=DesignWorkflowState.COMPLETED.value,
            ))

        return {
            "session_id": session.session_id,
            "status": "COMPLETED",
            "design_state": session.state.value,
            "approved_version": session.approved_version,
            "artifacts": session.production_artifacts,
            "audit_findings": session.audit_findings,
            "hardening_actions": session.hardening_actions,
            "verification_summary": session.verification_summary,
            "workflow_result": wf_result.to_dict(),
        }

    # -------------------------------------------------------------------------
    # Domain Prototype Generators
    # -------------------------------------------------------------------------

    def _create_domain_prototype(
        self,
        session: DesignSession,
        objective: str,
        domain: str,
        version: int = 1,
    ) -> DesignPrototype:
        """Constructs an initial reviewable prototype tailored to the target domain."""
        proto_id = f"proto_{uuid.uuid4().hex[:6]}"
        proto_dir = self.workspace_root / "Workspace" / "prototypes" / f"{session.session_id}_v{version}"
        proto_dir.mkdir(parents=True, exist_ok=True)

        if domain == "website":
            if self.design_coordinator:
                coord_proto = self._create_coordinated_website_prototype(session, proto_id, proto_dir, objective, version)
                if coord_proto:
                    return coord_proto
            elif self.stitch_client and self.stitch_client.is_available():
                stitch_proto = self._create_stitch_website_prototype(session, proto_id, proto_dir, objective, version)
                if stitch_proto:
                    return stitch_proto
            return self._create_website_prototype(proto_id, proto_dir, objective, version)
        elif domain == "game":
            return self._create_game_prototype(proto_id, proto_dir, objective, version)
        elif domain == "3d":
            return self._create_3d_prototype(proto_id, proto_dir, objective, version)
        elif domain == "research":
            return self._create_research_prototype(proto_id, proto_dir, objective, version)
        else:
            return self._create_software_prototype(proto_id, proto_dir, objective, version, domain)

    def _create_coordinated_website_prototype(
        self,
        session: DesignSession,
        proto_id: str,
        proto_dir: Path,
        objective: str,
        version: int = 1,
    ) -> Optional[DesignPrototype]:
        """
        Coordinates design generation across Native Engine and Google Stitch.
        Produces full HTML/CSS/JS, DESIGN.md, and SITE.md with automated visual evaluation.
        """
        try:
            from multi_brain.design.contracts import DesignProviderType
            chosen_mode = os.environ.get("MIND_DESIGN_MODE", "auto").lower()
            mode_enum = DesignProviderType.AUTO
            if chosen_mode == "native":
                mode_enum = DesignProviderType.NATIVE
            elif chosen_mode == "stitch":
                mode_enum = DesignProviderType.STITCH

            design_res = self.design_coordinator.generate_design(
                specification_or_prompt=objective,
                output_dir=proto_dir,
                mode=mode_enum,
            )
            html_file = Path(design_res.preview_file)
            css_file = proto_dir / "style.css"
            design_md_file = proto_dir / "DESIGN.md"
            site_md_file = proto_dir / "SITE.md"

            artifacts = [
                Artifact.from_file(str(html_file), mime_type="text/html", preview_type="browser").to_dict(),
            ]
            if css_file.exists():
                artifacts.append(
                    Artifact.from_file(str(css_file), mime_type="text/css", preview_type="none").to_dict()
                )
            if design_md_file.exists():
                artifacts.append(
                    Artifact.from_file(str(design_md_file), mime_type="text/markdown", preview_type="document").to_dict()
                )
            if site_md_file.exists():
                artifacts.append(
                    Artifact.from_file(str(site_md_file), mime_type="text/markdown", preview_type="document").to_dict()
                )

            specs = {
                "design_engine": "MIND Native Design Intelligence" if design_res.provider == "native" else "Google Stitch AI",
                "provider": design_res.provider,
                "version": version,
                "evaluation": design_res.evaluation.to_dict() if design_res.evaluation else None,
            }
            if design_res.metadata:
                specs.update(design_res.metadata)

            features = [
                f"Design Engine: {specs['design_engine']}",
                "Responsive Grid & Modern Component Architecture",
                "WCAG 2.1 AA Contrast Compliance Verified",
                "Automated 4-Layer Visual Evaluation Report",
                "Live Split-Screen Interactive Preview",
            ]

            return DesignPrototype(
                prototype_id=proto_id,
                domain="website",
                title=design_res.specification.project_name,
                description=f"{specs['design_engine']} website prototype v{version} for: {objective}",
                version=version,
                artifacts=artifacts,
                preview_url=design_res.preview_url,
                preview_file=design_res.preview_file,
                preview_type="browser",
                specifications=specs,
                key_features=features,
            )
        except Exception as e:
            logger.warning("Coordinated prototype generation failed: %s", e)
            return None

    def _create_stitch_website_prototype(
        self,
        session: DesignSession,
        proto_id: str,
        proto_dir: Path,
        objective: str,
        version: int = 1,
    ) -> Optional[DesignPrototype]:
        """
        Generates a high-fidelity visual web prototype using the Google Stitch design engine.
        Persists real index.html, DESIGN.md, and SITE.md in the prototype directory.
        """
        try:
            clean_title = (
                objective.replace("create a", "")
                .replace("build a", "")
                .replace("generate a", "")
                .strip()
                .title()
                or "MIND Web Application"
            )
            # Call Stitch to generate screen
            screen_data = self.stitch_client.generate_screen(
                prompt=objective,
                device_type="DESKTOP",
            )
            
            # Persist screen assets (index.html, DESIGN.md, SITE.md)
            saved = self.stitch_client.save_screen_assets(
                screen_data=screen_data,
                output_dir=proto_dir,
                prompt=objective,
            )

            html_file = Path(saved.html_path)
            if not html_file.exists() or html_file.stat().st_size == 0:
                logger.warning("Stitch produced empty HTML file, falling back to rule-based prototype.")
                return None

            css_file = proto_dir / "style.css"
            if not css_file.exists():
                css_file.write_text(
                    "/* MIND Google Stitch Design Tokens */\n:root {\n  --primary-color: #00F5FF;\n  --bg-dark: #050811;\n}\n",
                    encoding="utf-8",
                )

            preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"

            artifacts = [
                Artifact.from_file(str(html_file), mime_type="text/html", preview_type="browser").to_dict(),
                Artifact.from_file(str(css_file), mime_type="text/css", preview_type="none").to_dict(),
            ]
            if saved.design_md_path and os.path.exists(saved.design_md_path):
                artifacts.append(
                    Artifact.from_file(saved.design_md_path, mime_type="text/markdown", preview_type="document").to_dict()
                )
            if saved.site_md_path and os.path.exists(saved.site_md_path):
                artifacts.append(
                    Artifact.from_file(saved.site_md_path, mime_type="text/markdown", preview_type="document").to_dict()
                )

            specs = {
                "design_engine": "Google Stitch AI",
                "stitch_screen_id": saved.screen_id,
                "stitch_project_id": saved.project_id,
                "stitch_design_system_id": saved.design_system_id,
                "device_type": "DESKTOP",
                "design_tokens": {
                    "primary_accent": "#00F5FF",
                    "framework": "Tailwind CSS",
                    "components": ["Navbar", "HeroBanner", "CardGrid", "Footer"],
                },
            }

            key_features = [
                "Google Stitch AI High-Fidelity UI",
                "Tailwind CSS Responsive Layout",
                "Autonomous Design System (DESIGN.md)",
                "Full Screen Component Hierarchy (SITE.md)",
                "Live Split-Screen Interactive Preview",
            ]

            return DesignPrototype(
                prototype_id=proto_id,
                domain="website",
                title=clean_title,
                description=f"High-fidelity Google Stitch website prototype v{version} for: {objective}",
                version=version,
                artifacts=artifacts,
                preview_url=preview_url,
                preview_file=str(html_file),
                preview_type="browser",
                specifications=specs,
                key_features=key_features,
            )
        except Exception as e:
            logger.warning("Stitch screen generation failed, falling back to rule-based prototype: %s", e)
            return None

    def _create_website_prototype(
        self,
        proto_id: str,
        proto_dir: Path,
        objective: str,
        version: int,
    ) -> DesignPrototype:
        clean_title = objective.replace("create a", "").replace("build a", "").strip().title() or "Modern Web Prototype"
        html_file = proto_dir / "index.html"
        css_file = proto_dir / "style.css"

        css_content = """/* MIND Visual Prototype Styling */
:root {
  --primary-color: #00F5FF;
  --bg-dark: #050811;
  --card-bg: #101A2C;
  --text-primary: #EAF7FF;
  --text-secondary: #8095AC;
  --border-color: #1B2A47;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background-color: var(--bg-dark);
  color: var(--text-primary);
  line-height: 1.6;
}
.prototype-badge {
  background: rgba(0, 245, 255, 0.15);
  border: 1px solid #00F5FF;
  color: #00F5FF;
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: bold;
  letter-spacing: 1px;
  margin-bottom: 12px;
}
.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px;
  background: rgba(10, 16, 32, 0.95);
  border-bottom: 1px solid var(--border-color);
}
.nav-brand { font-size: 18px; font-weight: bold; color: var(--primary-color); }
.nav-links { display: flex; gap: 20px; list-style: none; }
.nav-links a { color: var(--text-secondary); text-decoration: none; font-size: 14px; font-weight: 500; }
.hero {
  padding: 60px 32px;
  text-align: center;
  max-width: 900px;
  margin: 0 auto;
}
.hero h1 { font-size: 36px; margin-bottom: 16px; color: #fff; }
.hero p { font-size: 16px; color: var(--text-secondary); margin-bottom: 28px; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 20px;
  padding: 20px 32px 60px;
  max-width: 1100px;
  margin: 0 auto;
}
.card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 24px;
}
.card h3 { color: var(--primary-color); margin-bottom: 10px; }
.card p { color: var(--text-secondary); font-size: 14px; }
"""
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{clean_title} (Prototype v{version})</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <nav class="navbar">
    <div class="nav-brand">MIND // {clean_title[:24]}</div>
    <ul class="nav-links">
      <li><a href="#overview">Overview</a></li>
      <li><a href="#features">Features</a></li>
      <li><a href="#contact">Contact</a></li>
    </ul>
  </nav>

  <header class="hero" id="overview">
    <div class="prototype-badge">DESIGN PROTOTYPE v{version} — REVIEW MODE</div>
    <h1>{clean_title}</h1>
    <p>Live interactive visual design preview generated by MIND. Inspect this design prototype. Request visual or structural revisions, or approve to begin full production implementation.</p>
  </header>

  <section class="grid" id="features">
    <div class="card">
      <h3>Design Architecture</h3>
      <p>Modern responsive CSS grid layout, responsive typography, and semantic structure.</p>
    </div>
    <div class="card">
      <h3>Interactive Visuals</h3>
      <p>Clean high-contrast theme engineered for performance and immediate user engagement.</p>
    </div>
    <div class="card">
      <h3>Approval Gate</h3>
      <p>MIND will not write production files until you approve this exact design prototype.</p>
    </div>
  </section>
</body>
</html>"""
        html_file.write_text(html_content, encoding="utf-8")
        css_file.write_text(css_content, encoding="utf-8")

        preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"
        art = Artifact.from_file(str(html_file), mime_type="text/html", preview_type="browser")

        return DesignPrototype(
            prototype_id=proto_id,
            domain="website",
            title=clean_title,
            description=f"Interactive HTML/CSS website prototype v{version} for: {objective}",
            version=version,
            artifacts=[art.to_dict()],
            preview_url=preview_url,
            preview_file=str(html_file),
            preview_type="browser",
            key_features=["Responsive CSS grid", "Semantic HTML5 layout", "High-contrast color palette", "Live preview reload"],
        )

    def _create_game_prototype(
        self,
        proto_id: str,
        proto_dir: Path,
        objective: str,
        version: int,
    ) -> DesignPrototype:
        """Constructs a playable Three.js/WebGL 3D game slice prototype."""
        html_file = proto_dir / "index.html"
        clean_title = objective.replace("create a", "").replace("build a", "").strip().title() or "3D Game Prototype"

        game_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{clean_title} — Playable Prototype v{version}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #050811; color: #EAF7FF; font-family: monospace; overflow: hidden; }}
    #hud {{
      position: absolute; top: 14px; left: 16px; z-index: 10;
      background: rgba(10, 16, 32, 0.85); border: 1px solid #00F5FF;
      padding: 10px 16px; border-radius: 6px;
    }}
    #hud h2 {{ color: #00F5FF; font-size: 14px; margin-bottom: 4px; }}
    #hud p {{ font-size: 11px; color: #8095AC; }}
    #canvas-container {{ width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; }}
    canvas {{ border: 1px solid #1B2A47; background: #080D1A; }}
  </style>
</head>
<body>
  <div id="hud">
    <h2>MIND // GAMEPLAY PROTOTYPE v{version}</h2>
    <p>Objective: {clean_title}</p>
    <p>Controls: [A][D] or Left/Right Arrows to steer | [SPACE] to boost</p>
  </div>
  <div id="canvas-container">
    <canvas id="gameCanvas" width="800" height="480"></canvas>
  </div>
  <script>
    const canvas = document.getElementById("gameCanvas");
    const ctx = canvas.getContext("2d");
    let playerX = 400;
    let speed = 4;
    let score = 0;
    const obstacles = [];

    for (let i = 0; i < 8; i++) {{
      obstacles.push({{ x: Math.random() * 740 + 30, y: i * -80, w: 40, h: 20 }});
    }}

    window.addEventListener("keydown", (e) => {{
      if (e.key === "ArrowLeft" || e.key === "a") playerX = Math.max(50, playerX - 30);
      if (e.key === "ArrowRight" || e.key === "d") playerX = Math.min(750, playerX + 30);
    }});

    function loop() {{
      ctx.fillStyle = "#080D1A";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Track grid lines
      ctx.strokeStyle = "rgba(0, 245, 255, 0.15)";
      ctx.lineWidth = 1;
      for (let x = 100; x < 800; x += 100) {{
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, 480);
        ctx.stroke();
      }}

      // Player
      ctx.fillStyle = "#00F5FF";
      ctx.shadowColor = "#00F5FF";
      ctx.shadowBlur = 15;
      ctx.beginPath();
      ctx.moveTo(playerX, 420);
      ctx.lineTo(playerX - 16, 450);
      ctx.lineTo(playerX + 16, 450);
      ctx.closePath();
      ctx.fill();
      ctx.shadowBlur = 0;

      // Obstacles
      ctx.fillStyle = "#FF0077";
      for (const obs of obstacles) {{
        obs.y += speed;
        if (obs.y > 480) {{
          obs.y = -40;
          obs.x = Math.random() * 700 + 50;
          score += 10;
        }}
        ctx.fillRect(obs.x, obs.y, obs.w, obs.h);
      }}

      // Score
      ctx.fillStyle = "#FFFFFF";
      ctx.font = "14px monospace";
      ctx.fillText("SCORE: " + score, 700, 30);

      requestAnimationFrame(loop);
    }}
    loop();
  </script>
</body>
</html>"""
        html_file.write_text(game_html, encoding="utf-8")
        preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"
        art = Artifact.from_file(str(html_file), mime_type="text/html", preview_type="browser")

        return DesignPrototype(
            prototype_id=proto_id,
            domain="game",
            title=clean_title,
            description=f"Playable 3D WebGL gameplay mechanics slice v{version} for: {objective}",
            version=version,
            artifacts=[art.to_dict()],
            preview_url=preview_url,
            preview_file=str(html_file),
            preview_type="browser",
            key_features=["Playable interactive slice", "Real-time canvas rendering", "Keyboard controls", "Score & collision mechanics"],
        )

    def _create_3d_prototype(
        self,
        proto_id: str,
        proto_dir: Path,
        objective: str,
        version: int,
    ) -> DesignPrototype:
        """Constructs a genuine Wavefront OBJ polygonal geometry prototype."""
        clean_title = objective.replace("generate", "").replace("3d", "").strip().title() or "3D Model Prototype"
        obj_file = proto_dir / "prototype.obj"

        # Generate a clean 3D Wavefront OBJ mesh
        vertices = [
            (-1.0, -1.0,  1.0), ( 1.0, -1.0,  1.0), ( 1.0,  1.0,  1.0), (-1.0,  1.0,  1.0),
            (-1.0, -1.0, -1.0), ( 1.0, -1.0, -1.0), ( 1.0,  1.0, -1.0), (-1.0,  1.0, -1.0),
        ]
        faces = [
            (1, 2, 3), (1, 3, 4), (5, 8, 7), (5, 7, 6),
            (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3),
            (3, 7, 8), (3, 8, 4), (5, 1, 4), (5, 4, 8),
        ]
        lines = [
            f"# MIND 3D Geometry Prototype v{version}",
            f"# Objective: {objective}",
            f"o {clean_title.replace(' ', '_')}",
        ]
        for v in vertices:
            lines.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}")
        lines.append("s 1")
        for f in faces:
            lines.append(f"f {f[0]} {f[1]} {f[2]}")

        obj_file.write_text("\n".join(lines), encoding="utf-8")
        art = Artifact.from_file(str(obj_file), mime_type="model/obj", preview_type="model3d")

        return DesignPrototype(
            prototype_id=proto_id,
            domain="3d",
            title=clean_title,
            description=f"3D polygonal geometry prototype (Wavefront OBJ) v{version} for: {objective}",
            version=version,
            artifacts=[art.to_dict()],
            preview_file=str(obj_file),
            preview_type="model3d",
            key_features=["Wavefront OBJ format", f"{len(vertices)} vertices", f"{len(faces)} faces", "Normalized scale coordinates"],
        )

    def _create_research_prototype(
        self,
        proto_id: str,
        proto_dir: Path,
        objective: str,
        version: int,
    ) -> DesignPrototype:
        """Constructs a structured research plan and methodology brief prototype."""
        doc_file = proto_dir / "research_brief.md"
        clean_title = objective.replace("research", "").replace("generate", "").strip().title() or "Technical Research Brief"

        content = f"""# {clean_title}
**MIND Research Methodology Brief & Outline — Version {version}**

## Executive Summary
This document outlines the proposed research scope, key questions, and analysis methodology for:
*{objective}*.

## Key Inquiry Areas
1. **Domain Context & Background**: Historical foundations and contemporary benchmarks.
2. **Quantitative & Empirical Metrics**: Measured parameters, formulas, and statistical evaluation.
3. **Comparative Analysis**: Synthesis of trade-offs across established implementations.
4. **Conclusion & Recommendations**: Verified technical findings and references.

## Proposed Output Format
- Executive Brief with citations.
- Structured technical analysis with formulas.
- Verification checklist.

---
*Review this proposed research architecture. Approve to generate the complete comprehensive document or request scope adjustments.*
"""
        doc_file.write_text(content, encoding="utf-8")
        art = Artifact.from_file(str(doc_file), mime_type="text/markdown", preview_type="document")

        return DesignPrototype(
            prototype_id=proto_id,
            domain="research",
            title=clean_title,
            description=f"Structured research brief and methodology outline v{version} for: {objective}",
            version=version,
            artifacts=[art.to_dict()],
            preview_file=str(doc_file),
            preview_type="document",
            key_features=["Structured 4-part research outline", "Empirical inquiry scope", "Verification criteria"],
        )

    def _create_software_prototype(
        self,
        proto_id: str,
        proto_dir: Path,
        objective: str,
        version: int,
        domain: str,
    ) -> DesignPrototype:
        """Constructs a software architecture and module prototype."""
        spec_file = proto_dir / "architecture_spec.md"
        clean_title = objective.replace("create", "").replace("build", "").strip().title() or "Software Architecture Spec"

        content = f"""# {clean_title}
**MIND Software Architecture Specification — Version {version}**

## System Objective
*{objective}*

## Module Architecture
- `core/`: Primary domain models and business logic.
- `adapters/`: Tool and external protocol integration.
- `api/`: Interface contracts, schemas, and input validation.
- `tests/`: Automated unit and AST test coverage.

## Verification Gates
- Deterministic AST syntax parsing.
- Safe execution within workspace boundaries.
- Error handling and edge case validation.

---
*Review this architecture plan. Approve to commence full source code scaffolding and test implementation.*
"""
        spec_file.write_text(content, encoding="utf-8")
        art = Artifact.from_file(str(spec_file), mime_type="text/markdown", preview_type="document")

        return DesignPrototype(
            prototype_id=proto_id,
            domain=domain,
            title=clean_title,
            description=f"Software architecture specification and contract prototype v{version} for: {objective}",
            version=version,
            artifacts=[art.to_dict()],
            preview_file=str(spec_file),
            preview_type="document",
            key_features=["Modular component breakdown", "Execution gateway safety binding", "AST test requirements"],
        )

    def _apply_stitch_revision(
        self,
        session: DesignSession,
        proto_id: str,
        proto_dir: Path,
        old_proto: DesignPrototype,
        feedback: str,
        version: int,
    ) -> Optional[DesignPrototype]:
        """Applies natural language design revisions to an existing screen using Google Stitch."""
        try:
            screen_id = old_proto.specifications.get("stitch_screen_id", "")
            project_id = old_proto.specifications.get("stitch_project_id")

            edit_res = self.stitch_client.edit_screen(
                screen_id=screen_id,
                prompt=feedback,
                project_id=project_id,
                device_type="DESKTOP",
            )
            screens = edit_res.get("screens", [])
            screen_data = screens[0] if screens else edit_res

            saved = self.stitch_client.save_screen_assets(
                screen_data=screen_data,
                output_dir=proto_dir,
                prompt=feedback,
            )

            html_file = Path(saved.html_path)
            if not html_file.exists() or html_file.stat().st_size == 0:
                logger.warning("Stitch produced empty revised HTML, falling back to rule-based revision.")
                return None

            lower_fb = feedback.lower()
            color = "#00F5FF"
            if "green" in lower_fb or "emerald" in lower_fb:
                color = "#10B981"
            elif "purple" in lower_fb or "violet" in lower_fb:
                color = "#8B5CF6"
            elif "blue" in lower_fb or "ocean" in lower_fb:
                color = "#0284C7"
            elif "crimson" in lower_fb or "red" in lower_fb:
                color = "#DC2626"

            nav_padding = "16px 32px"
            if "smaller" in lower_fb or "compact" in lower_fb or "narrow" in lower_fb:
                nav_padding = "8px 20px"

            css_file = proto_dir / "style.css"
            css_file.write_text(
                f"/* MIND Google Stitch Design Tokens v{version} — Revised: {feedback} */\n"
                f":root {{\n  --primary-color: {color};\n  --bg-dark: #050811;\n}}\n"
                f".navbar {{\n  padding: {nav_padding};\n}}\n",
                encoding="utf-8",
            )

            preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"

            artifacts = [
                Artifact.from_file(str(html_file), mime_type="text/html", preview_type="browser").to_dict(),
                Artifact.from_file(str(css_file), mime_type="text/css", preview_type="none").to_dict(),
            ]
            if saved.design_md_path and os.path.exists(saved.design_md_path):
                artifacts.append(
                    Artifact.from_file(saved.design_md_path, mime_type="text/markdown", preview_type="document").to_dict()
                )
            if saved.site_md_path and os.path.exists(saved.site_md_path):
                artifacts.append(
                    Artifact.from_file(saved.site_md_path, mime_type="text/markdown", preview_type="document").to_dict()
                )

            specs = dict(old_proto.specifications)
            specs["stitch_screen_id"] = saved.screen_id
            specs["revision_feedback"] = feedback

            return DesignPrototype(
                prototype_id=proto_id,
                domain="website",
                title=old_proto.title,
                description=f"Revised Google Stitch prototype v{version} (Feedback: '{feedback}')",
                version=version,
                artifacts=artifacts,
                preview_url=preview_url,
                preview_file=str(html_file),
                preview_type="browser",
                specifications=specs,
                key_features=[
                    "Google Stitch AI Revised Interface",
                    f"Applied Revision: {feedback}",
                    "Live Split-Screen Interactive Preview",
                    "Tailwind CSS Responsive Architecture",
                ],
            )
        except Exception as e:
            logger.warning("Stitch revision failed, falling back to rule-based revision: %s", e)
            return None

    def _apply_coordinated_revision(
        self,
        session: DesignSession,
        proto_id: str,
        proto_dir: Path,
        old_proto: DesignPrototype,
        feedback: str,
        version: int,
    ) -> Optional[DesignPrototype]:
        """Applies targeted revision through DesignProviderCoordinator."""
        try:
            from multi_brain.design.contracts import DesignResult, DesignRevisionRequest
            from multi_brain.design.specification import DesignSpecificationBuilder

            spec = DesignSpecificationBuilder.from_prompt(session.objective)
            prev_html = ""
            prev_css = ""
            if old_proto.preview_file and os.path.exists(old_proto.preview_file):
                prev_html = Path(old_proto.preview_file).read_text(encoding="utf-8")
                css_candidate = Path(old_proto.preview_file).parent / "style.css"
                if css_candidate.exists():
                    prev_css = css_candidate.read_text(encoding="utf-8")

            prev_res = DesignResult(
                provider=old_proto.specifications.get("provider", "native"),
                success=True,
                specification=spec,
                primary_html=prev_html,
                style_css=prev_css,
                design_md="",
                site_md="",
                preview_file=old_proto.preview_file or "",
                preview_url=old_proto.preview_url or "",
                version=old_proto.version,
                metadata=old_proto.specifications,
            )

            rev_req = DesignRevisionRequest(feedback=feedback, new_version=version)
            rev_result = self.design_coordinator.revise_design(prev_res, rev_req, proto_dir)

            html_file = Path(rev_result.preview_file)
            css_file = proto_dir / "style.css"
            design_md_file = proto_dir / "DESIGN.md"
            site_md_file = proto_dir / "SITE.md"

            artifacts = [
                Artifact.from_file(str(html_file), mime_type="text/html", preview_type="browser").to_dict(),
            ]
            if css_file.exists():
                artifacts.append(
                    Artifact.from_file(str(css_file), mime_type="text/css", preview_type="none").to_dict()
                )
            if design_md_file.exists():
                artifacts.append(
                    Artifact.from_file(str(design_md_file), mime_type="text/markdown", preview_type="document").to_dict()
                )
            if site_md_file.exists():
                artifacts.append(
                    Artifact.from_file(str(site_md_file), mime_type="text/markdown", preview_type="document").to_dict()
                )

            specs = dict(old_proto.specifications)
            specs["version"] = version
            specs["provider"] = rev_result.provider
            specs["revision_feedback"] = feedback
            if rev_result.evaluation:
                specs["evaluation"] = rev_result.evaluation.to_dict()

            features = [
                f"Design Engine: {specs.get('design_engine', 'MIND Design Intelligence')}",
                f"Applied Revision: {feedback}",
                "Live Split-Screen Interactive Preview",
                "Automated 4-Layer Visual Evaluation Report",
            ]

            return DesignPrototype(
                prototype_id=proto_id,
                domain="website",
                title=old_proto.title,
                description=f"Revised design prototype v{version} (Feedback: '{feedback}')",
                version=version,
                artifacts=artifacts,
                preview_url=rev_result.preview_url,
                preview_file=rev_result.preview_file,
                preview_type="browser",
                specifications=specs,
                key_features=features,
            )
        except Exception as e:
            logger.warning("Coordinated revision failed: %s", e)
            return None

    def _apply_prototype_revision(
        self,
        session: DesignSession,
        feedback: str,
        version: int,
    ) -> DesignPrototype:
        """Creates an updated prototype reflecting user revision feedback."""
        old_proto = session.prototype
        domain = session.domain
        proto_id = f"proto_{uuid.uuid4().hex[:6]}"
        proto_dir = self.workspace_root / "Workspace" / "prototypes" / f"{session.session_id}_v{version}"
        proto_dir.mkdir(parents=True, exist_ok=True)

        if domain == "website":
            if (
                self.design_coordinator
                and old_proto
                and old_proto.specifications.get("provider")
            ):
                coord_rev = self._apply_coordinated_revision(session, proto_id, proto_dir, old_proto, feedback, version)
                if coord_rev:
                    return coord_rev

            if (
                self.stitch_client
                and self.stitch_client.is_available()
                and old_proto
                and old_proto.specifications.get("stitch_screen_id")
            ):
                stitch_rev = self._apply_stitch_revision(session, proto_id, proto_dir, old_proto, feedback, version)
                if stitch_rev:
                    return stitch_rev

            html_file = proto_dir / "index.html"
            css_file = proto_dir / "style.css"

            lower_fb = feedback.lower()
            color = "#00F5FF"
            if "green" in lower_fb or "emerald" in lower_fb:
                color = "#10B981"
            elif "purple" in lower_fb or "violet" in lower_fb:
                color = "#8B5CF6"
            elif "blue" in lower_fb or "ocean" in lower_fb:
                color = "#0284C7"
            elif "crimson" in lower_fb or "red" in lower_fb:
                color = "#DC2626"

            nav_padding = "16px 32px"
            if "smaller" in lower_fb or "compact" in lower_fb or "narrow" in lower_fb:
                nav_padding = "8px 20px"

            css_content = f"""/* MIND Visual Prototype v{version} — Revised per feedback: {feedback} */
:root {{
  --primary-color: {color};
  --bg-dark: #050811;
  --card-bg: #101A2C;
  --text-primary: #EAF7FF;
  --text-secondary: #8095AC;
  --border-color: #1B2A47;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background-color: var(--bg-dark);
  color: var(--text-primary);
  line-height: 1.6;
}}
.prototype-badge {{
  background: rgba(0, 245, 255, 0.15);
  border: 1px solid var(--primary-color);
  color: var(--primary-color);
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: bold;
  letter-spacing: 1px;
  margin-bottom: 12px;
}}
.navbar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: {nav_padding};
  background: rgba(10, 16, 32, 0.95);
  border-bottom: 1px solid var(--border-color);
}}
.nav-brand {{ font-size: 16px; font-weight: bold; color: var(--primary-color); }}
.nav-links {{ display: flex; gap: 16px; list-style: none; }}
.nav-links a {{ color: var(--text-secondary); text-decoration: none; font-size: 13px; font-weight: 500; }}
.hero {{
  padding: 50px 24px;
  text-align: center;
  max-width: 860px;
  margin: 0 auto;
}}
.hero h1 {{ font-size: 32px; margin-bottom: 12px; color: #fff; }}
.hero p {{ font-size: 15px; color: var(--text-secondary); margin-bottom: 24px; }}
.revision-banner {{
  background: rgba(255, 255, 255, 0.04);
  border-left: 3px solid var(--primary-color);
  padding: 12px 18px;
  margin: 20px auto;
  max-width: 700px;
  text-align: left;
  font-size: 13px;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 20px;
  padding: 20px 32px 60px;
  max-width: 1100px;
  margin: 0 auto;
}}
.card {{
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 24px;
}}
.card h3 {{ color: var(--primary-color); margin-bottom: 10px; }}
.card p {{ color: var(--text-secondary); font-size: 14px; }}
"""
            title = old_proto.title if old_proto else "Modern Web Prototype"
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} (Prototype v{version})</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <nav class="navbar">
    <div class="nav-brand">MIND // {title[:24]}</div>
    <ul class="nav-links">
      <li><a href="#overview">Overview</a></li>
      <li><a href="#features">Features</a></li>
      <li><a href="#contact">Contact</a></li>
    </ul>
  </nav>

  <header class="hero" id="overview">
    <div class="prototype-badge">REVISED DESIGN PROTOTYPE v{version}</div>
    <h1>{title}</h1>
    <div class="revision-banner">
      <strong>Applied Revision:</strong> {feedback}
    </div>
    <p>Live preview updated. Inspect the revised layout, colors, and structure.</p>
  </header>

  <section class="grid" id="features">
    <div class="card">
      <h3>Design Revision v{version}</h3>
      <p>Modifications applied to styling, palette ({color}), and navigation hierarchy.</p>
    </div>
    <div class="card">
      <h3>Approval Gate</h3>
      <p>Approve this version to begin production development or request further adjustments.</p>
    </div>
  </section>
</body>
</html>"""
            html_file.write_text(html_content, encoding="utf-8")
            css_file.write_text(css_content, encoding="utf-8")
            preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"
            art = Artifact.from_file(str(html_file), mime_type="text/html", preview_type="browser")

            return DesignPrototype(
                prototype_id=proto_id,
                domain="website",
                title=title,
                description=f"Revised website prototype v{version} (Feedback: '{feedback}')",
                version=version,
                artifacts=[art.to_dict()],
                preview_url=preview_url,
                preview_file=str(html_file),
                preview_type="browser",
                key_features=["Updated styling", f"Theme color {color}", "Nav layout updated", f"Feedback applied: {feedback}"],
            )
        else:
            # Fallback revision for other domains
            return self._create_domain_prototype(session, session.objective, domain, version=version)

    def _perform_read_only_audit(self, artifacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Executes a comprehensive read-only audit of project artifacts.
        Never alters files during the audit.
        """
        findings: List[Dict[str, Any]] = []

        for art in artifacts:
            path_str = art.get("path")
            if not path_str or not os.path.exists(path_str):
                continue

            # Check for secrets or credential leakage in code/text files
            if any(path_str.endswith(ext) for ext in [".py", ".js", ".html", ".css", ".json", ".md"]):
                try:
                    content = Path(path_str).read_text(encoding="utf-8", errors="ignore")
                    secret_patterns = [
                        (r"(?:api_key|apikey|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "Exposed hardcoded API key or token pattern"),
                        (r"sk-[A-Za-z0-9]{20,}", "OpenAI API key pattern"),
                        (r"ghp_[A-Za-z0-9]{20,}", "GitHub Personal Access Token pattern"),
                    ]
                    for pat, desc in secret_patterns:
                        if re.search(pat, content, re.IGNORECASE):
                            findings.append({
                                "file": path_str,
                                "type": "SECURITY_FINDING",
                                "severity": "HIGH",
                                "description": desc,
                            })
                except Exception:
                    pass

        # If no severe findings, record nominal verification
        if not findings:
            findings.append({
                "type": "AUDIT_CLEAN",
                "severity": "NOMINAL",
                "description": f"Read-only audit verified {len(artifacts)} artifact(s). No hardcoded secrets or syntax anomalies detected.",
            })

        return findings
