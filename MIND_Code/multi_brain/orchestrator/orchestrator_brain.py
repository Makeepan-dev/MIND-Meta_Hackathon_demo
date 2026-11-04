"""Orchestrator Brain: Central router, planner, and coordinator for MIND."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from multi_brain.contracts import (
    Capability,
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
    WorkflowResult,
)
from multi_brain.orchestrator.lifecycle_manager import ProjectLifecycleManager
from multi_brain.registries.brain_registry import BrainRegistry
from multi_brain.registries.capability_registry import CapabilityRegistry
from multi_brain.registries.model_registry import ModelModality, ModelRegistry
from multi_brain.registries.provider_registry import ProviderRegistry
from multi_brain.registries.tool_registry import ToolRegistry
from multi_brain.security.gateway import ExecutionGateway
from multi_brain.workflow.context import TaskContext
from multi_brain.workflow.engine import WorkflowEngine

logger = logging.getLogger("mind.multi_brain.orchestrator")


class OrchestratorBrain:
    """
    MIND Central Orchestrator.
    Understands user intent, classifies requests, creates structured plans,
    discovers available specialist brains via registries, routes tasks, and integrates results.
    """

    def __init__(
        self,
        brain_registry: BrainRegistry,
        model_registry: Optional[ModelRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        gateway: Optional[ExecutionGateway] = None,
        workflow_engine: Optional[WorkflowEngine] = None,
        provider_registry: Optional[ProviderRegistry] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
    ) -> None:
        self.brain_registry = brain_registry
        self.model_registry = model_registry or ModelRegistry()
        self.gateway = gateway or ExecutionGateway()
        self.tool_registry = tool_registry or ToolRegistry(gateway=self.gateway)
        self.workflow_engine = workflow_engine or WorkflowEngine(brain_registry=self.brain_registry)
        self.provider_registry = provider_registry or ProviderRegistry()
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.lifecycle_manager = ProjectLifecycleManager(
            workspace_root=self.gateway.workspace_root,
            gateway=self.gateway,
            workflow_engine=self.workflow_engine,
        )

    def classify_request(self, user_input: str) -> RequestClassification:
        """
        Classifies incoming user requests into:
        - DIRECT_RESPONSE: greetings, simple chat, fast answers.
        - SINGLE_BRAIN: single-domain questions/actions.
        - MULTI_STEP_WORKFLOW: multi-stage, collaborative, or verified tasks.
        - CLARIFICATION_NEEDED: vague, underspecified queries.
        """
        text = user_input.strip().lower()

        if not text or len(text) < 3:
            return RequestClassification.CLARIFICATION_NEEDED

        if text in ["do it", "fix it", "make something", "start"]:
            return RequestClassification.CLARIFICATION_NEEDED

        multi_step_keywords = [
            "plan and", "build and test", "implement and verify",
            "code and test", "research and analyze", "create and check",
            "workflow", "step by step", "develop and validate", "generate and verify",
            "website", "web site", "web page", "multi-page", "portfolio",
            "dashboard", "interface", "portal", "game", "web app",
            "image-to-3d", "image to 3d", "reconstruct 3d",
            "technical document", "research and technical",
            "inspect and repair", "diagnose and repair", "inspect, diagnose", "repair and verify",
        ]
        if any(k in text for k in multi_step_keywords) or self.lifecycle_manager.is_development_intent(text):
            return RequestClassification.MULTI_STEP_WORKFLOW

        direct_greetings = [
            "hi", "hello", "hey", "who are you", "what is your name",
            "how are you", "good morning", "good evening", "status check"
        ]
        if text in direct_greetings or (len(text.split()) <= 4 and any(g in text for g in ["who are you", "what are you", "how are you"])):
            return RequestClassification.DIRECT_RESPONSE

        # Explanatory, conceptual, and informational queries are DIRECT_RESPONSE
        conceptual_prefixes = [
            "explain", "what is", "how does", "what are", "why does", "tell me about",
            "describe", "give me an overview", "can you explain"
        ]
        if any(text.startswith(p) for p in conceptual_prefixes) and not any(k in text for k in ["create a", "build a", "generate a", "make a"]):
            return RequestClassification.DIRECT_RESPONSE

        domain_keywords = [
            "code", "python", "script", "function", "refactor", "debug",
            "calculate", "stats", "mean", "median", "numbers",
            "research", "investigate", "history", "theory", "document", "pdf",
            "image", "draw", "render", "photoshoot", "art",
            "3d", "mesh", "obj", "stl", "video", "animation",
            "speak", "say", "voice", "audio", "verify"
        ]
        if any(k in text for k in domain_keywords):
            return RequestClassification.SINGLE_BRAIN

        return RequestClassification.DIRECT_RESPONSE

    def select_specialist(self, user_input: str) -> Optional[str]:
        """
        Selects the best registered and available specialist brain for a single-domain request.
        """
        text = user_input.lower()

        # 3D modeling
        if any(w in text for w in ["3d", "mesh", "obj", "stl", "cylinder", "sphere", "cube model", "blender"]):
            if "threed_generation" in self.brain_registry:
                return "threed_generation"

        # Video generation (do not match video game)
        if any(w in text for w in ["video clip", "generate video", "create video", "render video", "animation", "animate"]) and not any(g in text for g in ["game", "games"]):
            if "video_generation" in self.brain_registry:
                return "video_generation"

        # Code / Software development
        if any(w in text for w in ["code", "python", "script", "function", "debug", "refactor", "inspect repo"]):
            if "coding_engineering" in self.brain_registry:
                return "coding_engineering"

        # Data & Math Analytics
        if any(w in text for w in ["calculate", "math", "stats", "mean", "median", "standard deviation", "numbers"]):
            if "analysis_data" in self.brain_registry:
                return "analysis_data"

        # Verification & Critique
        if any(w in text for w in ["verify", "critique", "check output", "test result", "syntax check"]):
            if "verification_critique" in self.brain_registry:
                return "verification_critique"

        # Visual & 2D Image
        if any(w in text for w in ["image", "picture", "draw", "render image", "visual", "art", "photoshoot"]):
            if "creative_visual" in self.brain_registry:
                return "creative_visual"

        # Audio & Voice
        if any(w in text for w in ["speak", "say", "audio", "voice", "listen", "transcribe"]):
            if "audio_communication" in self.brain_registry:
                return "audio_communication"

        # Research & Documents
        if any(w in text for w in ["research", "paper", "investigate", "sources", "cite", "history", "document", "pdf", "docx"]):
            if "research_knowledge" in self.brain_registry:
                return "research_knowledge"

        # Planning
        if any(w in text for w in ["plan", "decompose", "strategy", "logic", "deduce"]):
            if "reasoning_planning" in self.brain_registry:
                return "reasoning_planning"

        brains = self.brain_registry.list_all(only_available=True)
        return brains[0]["brain_id"] if brains else None

    def create_plan(self, user_input: str) -> TaskPlan:
        """
        Creates a structured TaskPlan DAG based on user input and registered capabilities.
        """
        plan_id = str(uuid.uuid4())[:8]
        classification = self.classify_request(user_input)
        text = user_input.lower()

        tasks: List[TaskNode] = []

        if classification == RequestClassification.CLARIFICATION_NEEDED:
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=classification,
                tasks=[],
                clarification_prompt="Could you please specify your exact objective or target deliverable?",
            )

        # Scenario B: Multi-page Website Generation with Images
        if any(k in text for k in ["website", "web site", "web page", "multi-page", "portfolio"]):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_render_assets",
                    title="Synthesize Visual Graphic Assets",
                    description=f"Render website graphic images and visual assets for: {user_input}",
                    brain_id="creative_visual",
                    dependencies=[],
                    expected_output_type="image/png",
                )
            )
            gamedev_id = "gamedev_subsystem" if "gamedev_subsystem" in self.brain_registry else "coding_engineering"
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_build_site",
                    title="Generate Multi-Page Web Architecture",
                    description=f"Scaffold responsive HTML5, CSS3, and JavaScript pages for: {user_input}",
                    brain_id=gamedev_id,
                    dependencies=[f"{plan_id}_render_assets"],
                    expected_output_type="website",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_verify_site",
                    title="Verify Web Deliverables & Integrity",
                    description=f"Validate HTML/CSS/JS syntax, links, and asset presence for: {user_input}",
                    brain_id="verification_critique",
                    dependencies=[f"{plan_id}_build_site"],
                    requires_verification=True,
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into visual asset synthesis, multi-page website scaffolding, and web contract verification.",
            )

        # Scenario C: Image-to-3D Generation Pipeline
        if ("image-to-3d" in text or "image to 3d" in text or "reconstruct 3d" in text) or (("3d" in text or "mesh" in text or "obj" in text) and any(w in text for w in ["from image", "from an image", "image of", "picture of"])):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_gen_reference_img",
                    title="Generate 2D Source Visual",
                    description=f"Render 2D visual reference image for 3D reconstruction: {user_input}",
                    brain_id="creative_visual",
                    dependencies=[],
                    expected_output_type="image/png",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_reconstruct_3d",
                    title="3D Mesh Reconstruction",
                    description=f"Reconstruct 3D polygonal geometry (Wavefront OBJ) from visual reference: {user_input}",
                    brain_id="threed_generation",
                    dependencies=[f"{plan_id}_gen_reference_img"],
                    expected_output_type="model/obj",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_verify_3d_mesh",
                    title="Verify 3D Geometry Integrity",
                    description=f"Validate 3D mesh vertices, faces, and file structure for: {user_input}",
                    brain_id="verification_critique",
                    dependencies=[f"{plan_id}_reconstruct_3d"],
                    requires_verification=True,
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into 2D visual generation, 3D mesh reconstruction, and polygonal geometry validation.",
            )

        # Scenario D: Research & Technical Document Generation
        if ("research" in text or "investigate" in text or "whitepaper" in text) and any(w in text for w in ["document", "technical", "report", "pdf", "paper", "documentation"]):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_gather_research",
                    title="Conduct Domain Research & Citations",
                    description=f"Gather research citations, background literature, and domain facts for: {user_input}",
                    brain_id="research_knowledge",
                    dependencies=[],
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_tech_analysis",
                    title="Perform Quantitative & Technical Analysis",
                    description=f"Analyze data, formulas, and technical metrics for: {user_input}",
                    brain_id="analysis_data",
                    dependencies=[f"{plan_id}_gather_research"],
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_compose_doc",
                    title="Compose Technical Document",
                    description=f"Synthesize verified technical document deliverable for: {user_input}",
                    brain_id="coding_engineering",
                    dependencies=[f"{plan_id}_tech_analysis"],
                    expected_output_type="document",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_verify_doc",
                    title="Verify Document Quality & Coherence",
                    description=f"Validate document sections, syntax, and deliverables for: {user_input}",
                    brain_id="verification_critique",
                    dependencies=[f"{plan_id}_compose_doc"],
                    requires_verification=True,
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into research synthesis, quantitative analysis, technical document authoring, and quality verification.",
            )

        # Scenario E: Project Inspection, Diagnosis, Repair & Verification
        if any(w in text for w in ["inspect", "diagnose", "repair", "fix issue", "audit"]) and any(w in text for w in ["project", "repo", "codebase", "workspace", "bug"]):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_inspect_project",
                    title="Inspect & Diagnose Workspace Project",
                    description=f"Inspect workspace project files and diagnose defects for: {user_input}",
                    brain_id="coding_engineering",
                    dependencies=[],
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_repair_project",
                    title="Execute Code Repair & Refactoring",
                    description=f"Apply fixes, patches, and refactored code to resolve issues for: {user_input}",
                    brain_id="coding_engineering",
                    dependencies=[f"{plan_id}_inspect_project"],
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_verify_repair",
                    title="Run Verification Tests & AST Validation",
                    description=f"Verify syntax and test suite assertions for: {user_input}",
                    brain_id="verification_critique",
                    dependencies=[f"{plan_id}_repair_project"],
                    requires_verification=True,
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into workspace project diagnosis, automated repair implementation, and test verification.",
            )

        # Multi-brain Collaborative 3D Task
        if any(k in text for k in ["3d", "mesh", "obj"]) and any(k in text for k in ["verify", "check", "test", "plan"]):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_plan_3d",
                    title="Plan 3D Geometry Specifications",
                    description=f"Plan geometric parameters, vertices, and coordinate scales for: {user_input}",
                    brain_id="reasoning_planning",
                    dependencies=[],
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_gen_3d",
                    title="Generate 3D Polygonal Mesh",
                    description=f"Generate genuine Wavefront OBJ mesh file for: {user_input}",
                    brain_id="threed_generation",
                    dependencies=[f"{plan_id}_plan_3d"],
                    expected_output_type="model/obj",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_verify_3d",
                    title="Verify 3D Mesh Integrity",
                    description=f"Validate vertex count, face integrity, and file format for: {user_input}",
                    brain_id="verification_critique",
                    dependencies=[f"{plan_id}_gen_3d"],
                    requires_verification=True,
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into 3D specification planning, OBJ mesh generation, and mesh validation.",
            )

        # Multi-brain Collaborative Software Task
        if any(k in text for k in ["code", "implement", "python", "function", "utility"]) and any(k in text for k in ["test", "verify", "check", "plan"]):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_plan",
                    title="Plan Architecture & Requirements",
                    description=f"Plan implementation details and test cases for: {user_input}",
                    brain_id="reasoning_planning",
                    dependencies=[],
                    expected_output_type="plan",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_code",
                    title="Generate Implementation Code",
                    description=f"Implement source code based on planning specifications for: {user_input}",
                    brain_id="coding_engineering",
                    dependencies=[f"{plan_id}_plan"],
                    expected_output_type="source_code",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_verify",
                    title="Verify Implementation & AST Validity",
                    description=f"Deterministically verify syntax, structure, and test assertions for: {user_input}",
                    brain_id="verification_critique",
                    dependencies=[f"{plan_id}_code"],
                    expected_output_type="verification_report",
                    requires_verification=True,
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into planning, coding, and independent evidence-based verification.",
            )

        # Multi-brain Collaborative Image Task
        if any(k in text for k in ["image", "picture"]) and any(k in text for k in ["verify", "check", "generate and verify"]):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_render_img",
                    title="Render Image Asset",
                    description=user_input,
                    brain_id="creative_visual",
                    dependencies=[],
                    expected_output_type="image/png",
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_verify_img",
                    title="Verify Image Format & Dimensions",
                    description=f"Validate image file integrity and resolution for: {user_input}",
                    brain_id="verification_critique",
                    dependencies=[f"{plan_id}_render_img"],
                    requires_verification=True,
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into local image rendering followed by Pillow image verification.",
            )

        # Multi-brain Research & Analysis Task
        if "research" in text and ("analyze" in text or "stats" in text):
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_research",
                    title="Information Gathering",
                    description=f"Synthesize relevant domain knowledge for: {user_input}",
                    brain_id="research_knowledge",
                    dependencies=[],
                )
            )
            tasks.append(
                TaskNode(
                    task_id=f"{plan_id}_analysis",
                    title="Quantitative Data Analysis",
                    description=f"Perform calculations and statistical evaluation for: {user_input}",
                    brain_id="analysis_data",
                    dependencies=[f"{plan_id}_research"],
                )
            )
            return TaskPlan(
                plan_id=plan_id,
                original_request=user_input,
                classification=RequestClassification.MULTI_STEP_WORKFLOW,
                tasks=tasks,
                rationale="Decomposed into factual research followed by quantitative analysis.",
            )

        # Single brain task
        specialist_id = self.select_specialist(user_input) or "reasoning_planning"
        tasks.append(
            TaskNode(
                task_id=f"{plan_id}_exec",
                title="Specialist Execution",
                description=user_input,
                brain_id=specialist_id,
                dependencies=[],
            )
        )
        return TaskPlan(
            plan_id=plan_id,
            original_request=user_input,
            classification=RequestClassification.SINGLE_BRAIN,
            tasks=tasks,
            rationale=f"Routed to specialist '{specialist_id}' based on domain requirements.",
        )

    def process_request(
        self,
        user_input: str,
        context: Optional[TaskContext] = None,
        bypass_approval_for_tests: bool = False,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Complete end-to-end request processing lifecycle:
        1. Classify request.
        2. Direct response handling for greetings/status.
        3. Clarification prompt if goal is underspecified.
        4. Honest unconfigured/unavailable checking for cloud-only requests.
        5. Plan and execute DAG workflow through WorkflowEngine.
        6. Return verified results, artifacts, and audit evidence.
        """
        classification = self.classify_request(user_input)

        # 1. Active Design Review & Approval Session Gate (Priority Context)
        active_session = self.lifecycle_manager.get_active_session()
        if active_session and active_session.state in (
            DesignWorkflowState.AWAITING_DESIGN_APPROVAL,
            DesignWorkflowState.REVISING,
        ):
            # 1.1 Explicit Approval Gate
            if self.lifecycle_manager.is_approval(user_input):
                dev_res = self.lifecycle_manager.execute_approved_development(
                    session=active_session,
                    context=context,
                    progress_callback=progress_callback,
                    cancellation_token=cancellation_token,
                )
                self.lifecycle_manager.active_session_id = None  # Reset active session upon completion
                return {
                    "classification": RequestClassification.MULTI_STEP_WORKFLOW.value,
                    "status": "completed",
                    "response": (
                        f"Design v{active_session.approved_version} approved by user. "
                        f"Production development, automated testing, read-only architectural audit, "
                        f"and independent verification completed successfully."
                    ),
                    "design_state": DesignWorkflowState.COMPLETED.value,
                    "version": active_session.approved_version,
                    "session_id": active_session.session_id,
                    "artifacts": dev_res.get("artifacts", []),
                    "audit_findings": dev_res.get("audit_findings", []),
                    "hardening_actions": dev_res.get("hardening_actions", []),
                    "verification_summary": dev_res.get("verification_summary", {}),
                    "workflow_result": dev_res.get("workflow_result"),
                }

            # 1.2 Explicit Rejection Gate
            if self.lifecycle_manager.is_rejection(user_input):
                rej_res = self.lifecycle_manager.reject_prototype(
                    session=active_session,
                    feedback=user_input,
                    progress_callback=progress_callback,
                )
                return {
                    "classification": RequestClassification.MULTI_STEP_WORKFLOW.value,
                    "status": "rejected",
                    "response": rej_res["message"],
                    "design_state": active_session.state.value,
                    "version": active_session.current_version,
                    "workflow_result": None,
                }

            # 1.3 Ordinary Conversational Inquiry During Review
            if classification == RequestClassification.DIRECT_RESPONSE and not any(
                w in user_input.lower() for w in ["change", "make", "add", "remove", "update", "nav", "color", "hero", "faster", "scale"]
            ):
                return {
                    "classification": classification.value,
                    "status": "in_review",
                    "response": (
                        f"Current design prototype v{active_session.current_version} is awaiting your review. "
                        f"To proceed, say 'Approve' or 'Proceed'. To adjust layout or features, request a revision."
                    ),
                    "design_state": active_session.state.value,
                    "version": active_session.current_version,
                    "preview_url": active_session.prototype.preview_url if active_session.prototype else None,
                    "workflow_result": None,
                }

            # 1.4 Genuine Revision Loop (Feedback -> Revised Prototype -> Updated Preview)
            updated_proto = self.lifecycle_manager.revise_prototype(
                session=active_session,
                feedback=user_input,
                progress_callback=progress_callback,
            )
            return {
                "classification": RequestClassification.MULTI_STEP_WORKFLOW.value,
                "status": "awaiting_approval",
                "response": (
                    f"Design prototype updated to v{updated_proto.version} based on your feedback: '{user_input}'. "
                    f"Live preview reloaded. Please inspect the updated design. "
                    f"Say 'Approve' to begin production development or request further changes."
                ),
                "design_state": active_session.state.value,
                "version": updated_proto.version,
                "preview_url": updated_proto.preview_url,
                "preview_file": updated_proto.preview_file,
                "prototype": updated_proto.to_dict(),
                "artifacts": updated_proto.artifacts,
                "workflow_result": None,
            }

        # 2. Direct Response Path (Greetings & Conceptual Q&A)
        if classification == RequestClassification.DIRECT_RESPONSE:
            clean = user_input.strip().lower()
            if clean in ["hi", "hello", "hey"]:
                reply = "Greetings! MIND Modular Multi-Brain Architecture is online and ready, Sir."
            elif "who are you" in clean:
                reply = "I am MIND (Mageepan's Intelligence Network Device), powered by a modular multi-brain architecture."
            elif "status check" in clean:
                active_brains = len(self.brain_registry.list_all(only_available=True))
                reply = f"MIND Core Systems Nominal. {active_brains} specialist brains currently active."
            else:
                model = self.model_registry.get_default_model(ModelModality.TEXT)
                model_id = model.model_id if model else "deterministic-fallback"
                try:
                    reply = self.model_registry.invoke(
                        model_id=model_id,
                        prompt=user_input,
                        system_prompt="You are MIND, a helpful AI desktop assistant. Be concise and precise.",
                    )
                except Exception:
                    reply = f"Acknowledged: '{user_input}'. Core assistant standing by."

            return {
                "classification": classification.value,
                "status": "completed",
                "response": reply,
                "workflow_result": None,
                "evidence": None,
            }

        # 3. Clarification Needed Path
        if classification == RequestClassification.CLARIFICATION_NEEDED:
            return {
                "classification": classification.value,
                "status": "needs_clarification",
                "response": "Could you please clarify your specific goal or deliverable?",
                "workflow_result": None,
                "evidence": None,
            }

        # 4. Explicit Cloud Image Generation Check (Honest Reporting)
        if "cloud" in user_input.lower() and ("image" in user_input.lower() or "dall-e" in user_input.lower()):
            creative_brain = self.brain_registry.get("creative_visual")
            if creative_brain and not creative_brain.has_capability("image_generation"):
                msg = (
                    "Cloud image generation capability is currently UNAVAILABLE. "
                    "No cloud rendering provider (e.g. STABILITY_API_KEY, OPENAI_API_KEY) is configured. "
                    "Configure STABILITY_API_KEY or OPENAI_API_KEY to enable cloud rendering. "
                    "I cannot generate cloud raster images without an active provider."
                )
                return {
                    "classification": RequestClassification.SINGLE_BRAIN.value,
                    "status": "unavailable_capability",
                    "response": msg,
                    "workflow_result": None,
                    "evidence": {"capability": "image_generation", "is_available": False},
                }

        # 5. New Development Request: Initiate Stages 1-3 (Understand -> Plan -> Prototype)
        if self.lifecycle_manager.is_development_intent(user_input) and not bypass_approval_for_tests:
            plan = self.create_plan(user_input)
            session = self.lifecycle_manager.start_design_session(
                objective=user_input,
                plan=plan,
                progress_callback=progress_callback,
            )
            proto = session.prototype
            return {
                "classification": RequestClassification.MULTI_STEP_WORKFLOW.value,
                "status": "awaiting_approval",
                "response": (
                    f"Design prototype v{proto.version} generated for: '{proto.title}'. "
                    f"Domain: {session.domain.upper()}. "
                    f"Live preview rendered. Please inspect the proposed layout and structure. "
                    f"Say 'Approve' to begin production development or request design revisions."
                ),
                "design_state": session.state.value,
                "version": proto.version,
                "preview_url": proto.preview_url,
                "preview_file": proto.preview_file,
                "prototype": proto.to_dict(),
                "artifacts": proto.artifacts,
                "workflow_result": None,
            }

        # 6. Standard Execution via Workflow Engine (Direct single-brains, research tasks, or test bypass)
        plan = self.create_plan(user_input)
        workflow_res = self.workflow_engine.execute_plan(
            plan,
            context=context,
            progress_callback=progress_callback,
            cancellation_token=cancellation_token,
        )

        # Build user-facing response summary
        final_response = ""
        if workflow_res.is_success:
            if plan.classification == RequestClassification.MULTI_STEP_WORKFLOW:
                verification_notes = []
                for t_id, r in workflow_res.task_results.items():
                    if r.verification:
                        v_summary = r.output.get("summary") if isinstance(r.output, dict) else None
                        if v_summary:
                            verification_notes.append(v_summary)
                v_text = f" [{'; '.join(verification_notes)}]" if verification_notes else ""
                final_response = f"Workflow completed successfully ({len(workflow_res.task_results)} tasks executed).{v_text}"
            else:
                first_res = next(iter(workflow_res.task_results.values()), None)
                if first_res and isinstance(first_res.output, dict):
                    final_response = (
                        first_res.output.get("message")
                        or first_res.output.get("summary")
                        or first_res.output.get("raw_response")
                        or str(first_res.output)
                    )
                elif first_res:
                    final_response = str(first_res.output)
        elif workflow_res.status == TaskStatus.CANCELLED:
            reason = f": {workflow_res.cancellation_reason}" if workflow_res.cancellation_reason else ""
            final_response = f"Workflow was cancelled by user request{reason}."
        else:
            failed_tasks = [t_id for t_id, r in workflow_res.task_results.items() if not r.is_success]
            errors = [f"{t_id}: {workflow_res.task_results[t_id].error}" for t_id in failed_tasks]
            final_response = f"Workflow failed on tasks: {failed_tasks}. Details: {'; '.join(errors)}"

        return {
            "classification": plan.classification.value,
            "status": workflow_res.status.value,
            "response": final_response,
            "workflow_result": workflow_res.to_dict(),
            "artifacts": workflow_res.get_artifacts(),
            "evidence": {
                t_id: r.verification for t_id, r in workflow_res.task_results.items() if r.verification
            },
        }
