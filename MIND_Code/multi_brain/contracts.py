"""Foundational contracts and shared data models for the MIND Modular Multi-Brain Architecture."""

from __future__ import annotations

import hashlib
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class CancellationToken:
    """Thread-safe cooperative cancellation token for long-running workflows."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: Optional[str] = None

    def cancel(self, reason: str = "Execution cancelled by user request.") -> None:
        self._reason = reason
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def is_set(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise WorkflowCancelledError(self._reason or "Execution cancelled.")


class WorkflowCancelledError(Exception):
    """Raised when a workflow or task execution is cancelled cooperatively."""
    pass


class WorkflowExecutionError(Exception):
    """Raised when an unrecoverable failure occurs during workflow execution."""
    pass


class TaskStatus(str, Enum):
    """Lifecycle states of a task or workflow."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class DesignWorkflowState(str, Enum):
    """Lifecycle states for MIND's approval-driven, design-first development workflow."""
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    PROTOTYPING = "prototyping"
    AWAITING_DESIGN_APPROVAL = "awaiting_design_approval"
    REVISING = "revising"
    APPROVED_FOR_DEVELOPMENT = "approved_for_development"
    DEVELOPING = "developing"
    TESTING = "testing"
    AUDITING = "auditing"
    HARDENING = "hardening"
    VERIFYING = "verifying"
    RELEASE_PREPARATION = "release_preparation"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass
class DesignPrototype:
    """A domain-specific reviewable prototype presented to the user prior to full development."""
    prototype_id: str
    domain: str
    title: str
    description: str
    version: int = 1
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    preview_url: Optional[str] = None
    preview_file: Optional[str] = None
    preview_type: str = "none"  # "browser", "model3d", "image", "document", "spec"
    specifications: Dict[str, Any] = field(default_factory=dict)
    key_features: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prototype_id": self.prototype_id,
            "domain": self.domain,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "artifacts": self.artifacts,
            "preview_url": self.preview_url,
            "preview_file": self.preview_file,
            "preview_type": self.preview_type,
            "specifications": self.specifications,
            "key_features": self.key_features,
            "created_at": self.created_at,
        }


@dataclass
class DesignSession:
    """Maintains active project design lifecycle context, revisions, and approval gate."""
    session_id: str
    objective: str
    domain: str
    state: DesignWorkflowState = DesignWorkflowState.UNDERSTANDING
    current_version: int = 1
    approved_version: Optional[int] = None
    prototype: Optional[DesignPrototype] = None
    plan: Optional[TaskPlan] = None
    revision_history: List[Dict[str, Any]] = field(default_factory=list)
    feedback_notes: List[str] = field(default_factory=list)
    production_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    audit_findings: List[Dict[str, Any]] = field(default_factory=list)
    hardening_actions: List[str] = field(default_factory=list)
    verification_summary: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_approved(self) -> bool:
        return self.state in (
            DesignWorkflowState.APPROVED_FOR_DEVELOPMENT,
            DesignWorkflowState.DEVELOPING,
            DesignWorkflowState.TESTING,
            DesignWorkflowState.AUDITING,
            DesignWorkflowState.HARDENING,
            DesignWorkflowState.VERIFYING,
            DesignWorkflowState.RELEASE_PREPARATION,
            DesignWorkflowState.COMPLETED,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "objective": self.objective,
            "domain": self.domain,
            "state": self.state.value,
            "current_version": self.current_version,
            "approved_version": self.approved_version,
            "is_approved": self.is_approved,
            "prototype": self.prototype.to_dict() if self.prototype else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "revision_history": self.revision_history,
            "feedback_notes": self.feedback_notes,
            "production_artifacts": self.production_artifacts,
            "audit_findings": self.audit_findings,
            "hardening_actions": self.hardening_actions,
            "verification_summary": self.verification_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RequestClassification(str, Enum):
    """Orchestrator routing decision classifications."""
    DIRECT_RESPONSE = "direct_response"
    SINGLE_BRAIN = "single_brain"
    MULTI_STEP_WORKFLOW = "multi_step_workflow"
    CLARIFICATION_NEEDED = "clarification_needed"


class PermissionTier(str, Enum):
    """Security tier for tools and actions."""
    SAFE = "safe"                            # Read-only, deterministic, in-memory computations
    LOW_RISK = "low_risk"                    # Safe filesystem read, non-invasive metrics
    REQUIRES_APPROVAL = "requires_approval"  # Filesystem write, code execution, network operations
    CRITICAL = "critical"                    # System settings, secret management, file deletion


class ExecutionMode(str, Enum):
    """Execution mode of a capability or provider."""
    LOCAL = "local"
    CLOUD = "cloud"
    EXTERNAL_TOOL = "external_tool"
    HYBRID = "hybrid"


@dataclass
class Capability:
    """
    Comprehensive capability contract representing a domain or functional service in MIND.
    Adheres to Phase 2 specification for dynamic registries and discovery.
    """
    name: str
    domain: str
    description: str = ""
    capability_id: str = ""
    supported_operations: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    accepted_mime_types: List[str] = field(default_factory=list)
    supported_formats: List[str] = field(default_factory=list)
    execution_modes: List[str] = field(default_factory=lambda: ["local"])
    compatible_providers: List[str] = field(default_factory=list)
    compatible_models: List[str] = field(default_factory=list)
    hardware_requirements: Dict[str, Any] = field(default_factory=dict)
    required_credentials: List[str] = field(default_factory=list)
    modalities: List[str] = field(default_factory=lambda: ["text"])
    permission_tier: PermissionTier = PermissionTier.SAFE
    safety_constraints: List[str] = field(default_factory=list)
    timeout_seconds: float = 60.0
    cancellation_supported: bool = True
    max_retries: int = 1
    is_available: bool = True
    health_status: str = "healthy"  # "healthy", "degraded", "unconfigured", "unavailable"
    artifact_locations: List[str] = field(default_factory=list)
    verification_requirements: List[str] = field(default_factory=list)
    provider_limitations: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.capability_id:
            # Derive stable ID from name and domain if omitted
            clean_name = self.name.lower().replace(" ", "_").replace("-", "_")
            self.capability_id = clean_name
        if not self.supported_operations:
            self.supported_operations = [self.name]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "supported_operations": self.supported_operations,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "accepted_mime_types": self.accepted_mime_types,
            "supported_formats": self.supported_formats,
            "execution_modes": self.execution_modes,
            "compatible_providers": self.compatible_providers,
            "compatible_models": self.compatible_models,
            "hardware_requirements": self.hardware_requirements,
            "required_credentials": self.required_credentials,
            "modalities": self.modalities,
            "permission_tier": self.permission_tier.value,
            "safety_constraints": self.safety_constraints,
            "timeout_seconds": self.timeout_seconds,
            "cancellation_supported": self.cancellation_supported,
            "max_retries": self.max_retries,
            "is_available": self.is_available,
            "health_status": self.health_status,
            "artifact_locations": self.artifact_locations,
            "verification_requirements": self.verification_requirements,
            "provider_limitations": self.provider_limitations,
        }


@dataclass
class Artifact:
    """A tangible deliverable produced by a brain or tool (code file, image, 3D model, report)."""
    artifact_id: str
    path: str
    mime_type: str
    size_bytes: int = 0
    checksum: str = ""
    source_brain: str = ""
    source_task: str = ""
    created_at: float = field(default_factory=time.time)
    is_verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    preview_type: str = "none"
    is_partial: bool = False
    provenance: Optional[Provenance] = None

    @staticmethod
    def infer_preview_type(path: str, mime_type: str = "") -> str:
        """Determines the appropriate UI preview capability for an artifact."""
        p_lower = path.lower()
        m_lower = mime_type.lower()
        if os.path.isdir(path) or p_lower.endswith(("/", "\\")):
            return "folder"
        if m_lower.startswith("image/") or p_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp")):
            return "image"
        if "html" in m_lower or p_lower.endswith((".html", ".htm")):
            return "browser"
        if m_lower in ("model/obj", "model/stl", "model/gltf-binary", "model/gltf+json") or p_lower.endswith((".obj", ".stl", ".glb", ".gltf")):
            return "model3d"
        if m_lower.startswith("text/") or p_lower.endswith((".py", ".js", ".css", ".json", ".md", ".txt", ".csv", ".yml", ".yaml")):
            return "text"
        return "none"

    def exists(self) -> bool:
        """Returns True if the file or directory physically exists on disk."""
        return os.path.exists(self.path)

    @classmethod
    def from_file(
        cls,
        path: str,
        mime_type: str,
        source_brain: str = "",
        source_task: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        preview_type: Optional[str] = None,
        is_partial: bool = False,
        provenance: Optional[Provenance] = None,
    ) -> Artifact:
        size = 0
        sha256 = ""
        if os.path.exists(path):
            try:
                size = os.path.getsize(path)
                with open(path, "rb") as f:
                    sha256 = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                pass

        inferred_preview = preview_type or cls.infer_preview_type(path, mime_type)
        return cls(
            artifact_id=str(uuid.uuid4())[:8],
            path=os.path.abspath(path),
            mime_type=mime_type,
            size_bytes=size,
            checksum=sha256,
            source_brain=source_brain,
            source_task=source_task,
            metadata=metadata or {},
            preview_type=inferred_preview,
            is_partial=is_partial,
            provenance=provenance,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "source_brain": self.source_brain,
            "source_task": self.source_task,
            "created_at": self.created_at,
            "is_verified": self.is_verified,
            "metadata": self.metadata,
            "preview_type": self.preview_type,
            "is_partial": self.is_partial,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "exists": self.exists(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Artifact:
        prov_dict = data.get("provenance")
        prov = Provenance.from_dict(prov_dict) if isinstance(prov_dict, dict) else None
        return cls(
            artifact_id=data.get("artifact_id", str(uuid.uuid4())[:8]),
            path=data.get("path", ""),
            mime_type=data.get("mime_type", "application/octet-stream"),
            size_bytes=data.get("size_bytes", 0),
            checksum=data.get("checksum", ""),
            source_brain=data.get("source_brain", ""),
            source_task=data.get("source_task", ""),
            created_at=data.get("created_at", time.time()),
            is_verified=data.get("is_verified", False),
            metadata=data.get("metadata", {}),
            preview_type=data.get("preview_type", "none"),
            is_partial=data.get("is_partial", False),
            provenance=prov,
        )


@dataclass
class Provenance:
    """Audit and provenance metadata tracking which component produced an output."""
    brain_id: str
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    execution_mode: str = "local"
    verified_by: Optional[str] = None
    is_fallback: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brain_id": self.brain_id,
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "tool_calls": self.tool_calls,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "execution_mode": self.execution_mode,
            "verified_by": self.verified_by,
            "is_fallback": self.is_fallback,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Provenance:
        return cls(
            brain_id=data.get("brain_id", "unknown"),
            model_id=data.get("model_id"),
            provider_id=data.get("provider_id"),
            tool_calls=data.get("tool_calls", []),
            timestamp=data.get("timestamp", time.time()),
            confidence=data.get("confidence", 1.0),
            execution_mode=data.get("execution_mode", "local"),
            verified_by=data.get("verified_by"),
            is_fallback=data.get("is_fallback", False),
        )


@dataclass
class TaskRequest:
    """Input payload dispatched to a specialist brain or workflow task."""
    user_goal: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    input_data: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    context_slice: Dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[str] = field(default_factory=list)
    preferred_execution_mode: Optional[str] = None
    timeout_seconds: float = 60.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_goal": self.user_goal,
            "input_data": self.input_data,
            "parameters": self.parameters,
            "context_slice": self.context_slice,
            "required_capabilities": self.required_capabilities,
            "preferred_execution_mode": self.preferred_execution_mode,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class TaskResult:
    """Standardized output produced by a specialist brain or tool execution."""
    task_id: str
    status: TaskStatus
    output: Any
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None
    provenance: Optional[Provenance] = None
    error: Optional[str] = None
    execution_time_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == TaskStatus.COMPLETED and self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "artifacts": self.artifacts,
            "verification": self.verification,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "error": self.error,
            "execution_time_seconds": self.execution_time_seconds,
            "is_success": self.is_success,
        }


@dataclass
class TaskNode:
    """A node in a structured workflow execution plan DAG."""
    task_id: str
    title: str
    description: str
    brain_id: str
    dependencies: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_output_type: str = "text"
    required_capabilities: List[str] = field(default_factory=list)
    requires_verification: bool = False
    timeout_seconds: float = 60.0
    max_retries: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "brain_id": self.brain_id,
            "dependencies": self.dependencies,
            "inputs": self.inputs,
            "expected_output_type": self.expected_output_type,
            "required_capabilities": self.required_capabilities,
            "requires_verification": self.requires_verification,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


@dataclass
class TaskPlan:
    """A structured execution plan generated by the Orchestrator."""
    plan_id: str
    original_request: str
    classification: RequestClassification
    tasks: List[TaskNode] = field(default_factory=list)
    rationale: str = ""
    clarification_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "original_request": self.original_request,
            "classification": self.classification.value,
            "tasks": [t.to_dict() for t in self.tasks],
            "rationale": self.rationale,
            "clarification_prompt": self.clarification_prompt,
        }


@dataclass
class WorkflowProgress:
    """Live progress update emitted during workflow execution."""
    workflow_id: str
    active_task_id: str
    active_task_title: str
    brain_id: str
    status: TaskStatus
    progress_pct: float          # 0.0 to 1.0
    message: str
    completed_tasks: int = 0
    total_tasks: int = 0
    current_artifact: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    task_statuses: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    is_cancelled: bool = False
    cancellation_reason: Optional[str] = None
    preview_url: Optional[str] = None
    preview_file: Optional[str] = None
    project_path: Optional[str] = None
    live_stage: Optional[str] = None
    design_state: Optional[str] = None
    prototype: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "active_task_id": self.active_task_id,
            "active_task_title": self.active_task_title,
            "brain_id": self.brain_id,
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "message": self.message,
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.total_tasks,
            "current_artifact": self.current_artifact,
            "error": self.error,
            "timestamp": self.timestamp,
            "task_statuses": self.task_statuses,
            "is_cancelled": self.is_cancelled,
            "cancellation_reason": self.cancellation_reason,
            "preview_url": self.preview_url,
            "preview_file": self.preview_file,
            "project_path": self.project_path,
            "live_stage": self.live_stage,
            "design_state": self.design_state,
            "prototype": self.prototype,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowProgress:
        raw_status = data.get("status", TaskStatus.RUNNING.value)
        try:
            status = TaskStatus(raw_status)
        except ValueError:
            status = TaskStatus.RUNNING
        return cls(
            workflow_id=data.get("workflow_id", ""),
            active_task_id=data.get("active_task_id", ""),
            active_task_title=data.get("active_task_title", ""),
            brain_id=data.get("brain_id", ""),
            status=status,
            progress_pct=data.get("progress_pct", 0.0),
            message=data.get("message", ""),
            completed_tasks=data.get("completed_tasks", 0),
            total_tasks=data.get("total_tasks", 0),
            current_artifact=data.get("current_artifact"),
            error=data.get("error"),
            timestamp=data.get("timestamp", time.time()),
            task_statuses=data.get("task_statuses", {}),
            is_cancelled=data.get("is_cancelled", False),
            cancellation_reason=data.get("cancellation_reason"),
            preview_url=data.get("preview_url"),
            preview_file=data.get("preview_file"),
            project_path=data.get("project_path"),
            live_stage=data.get("live_stage"),
            design_state=data.get("design_state"),
            prototype=data.get("prototype"),
        )


@dataclass
class WorkflowResult:
    """The aggregate result of an executed workflow plan."""
    workflow_id: str
    status: TaskStatus
    plan: TaskPlan
    task_results: Dict[str, TaskResult] = field(default_factory=dict)
    final_output: Any = None
    execution_duration: float = 0.0
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    cancellation_reason: Optional[str] = None
    partial_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    verification_summary: Optional[Dict[str, Any]] = None

    @property
    def is_success(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    @property
    def is_cancelled(self) -> bool:
        return self.status == TaskStatus.CANCELLED

    def get_artifacts(self) -> List[Dict[str, Any]]:
        """Collects all tangible artifacts produced by any task in the workflow."""
        artifacts: List[Dict[str, Any]] = []
        for res in self.task_results.values():
            if res.artifacts:
                artifacts.extend(res.artifacts)
        if isinstance(self.final_output, dict) and "artifacts" in self.final_output:
            for a in self.final_output["artifacts"]:
                if a not in artifacts:
                    artifacts.append(a)
        return artifacts

    def get_partial_artifacts(self) -> List[Dict[str, Any]]:
        """Collects all partial artifacts produced prior to interruption or failure."""
        partials: List[Dict[str, Any]] = list(self.partial_artifacts)
        for res in self.task_results.values():
            for art in res.artifacts:
                if isinstance(art, dict) and art.get("is_partial") and art not in partials:
                    partials.append(art)
        return partials

    def get_task_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Returns snapshot of task execution statuses across the plan."""
        statuses: Dict[str, Dict[str, Any]] = {}
        for t in self.plan.tasks:
            res = self.task_results.get(t.task_id)
            statuses[t.task_id] = {
                "title": t.title,
                "brain_id": t.brain_id,
                "status": res.status.value if res else "pending",
                "is_success": res.is_success if res else False,
                "error": res.error if res else None,
                "execution_time_seconds": res.execution_time_seconds if res else 0.0,
            }
        return statuses

    def get_provenance_summary(self) -> List[Dict[str, Any]]:
        """Returns list of distinct provenances contributing to this result."""
        provenance_list: List[Dict[str, Any]] = []
        seen = set()
        for res in self.task_results.values():
            if res.provenance:
                key = (res.provenance.brain_id, res.provenance.model_id, res.provenance.provider_id)
                if key not in seen:
                    seen.add(key)
                    provenance_list.append(res.provenance.to_dict())
        return provenance_list

    def get_errors(self) -> List[str]:
        """Collects all failure reasons across tasks."""
        errors: List[str] = []
        for t_id, res in self.task_results.items():
            if res.error:
                errors.append(f"[{t_id}] {res.error}")
        return errors

    def get_summary(self) -> str:
        """Returns a user-facing concise completion summary."""
        if self.is_success:
            count = len(self.task_results)
            artifacts = self.get_artifacts()
            art_str = f" ({len(artifacts)} artifact(s) generated)" if artifacts else ""
            return f"Workflow completed successfully: {count} task(s) verified.{art_str}"
        elif self.status == TaskStatus.CANCELLED:
            reason = f": {self.cancellation_reason}" if self.cancellation_reason else "."
            return f"Workflow was cancelled by user request{reason}"
        else:
            errors = self.get_errors()
            err_str = f": {'; '.join(errors)}" if errors else "."
            return f"Workflow halted with failure{err_str}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "plan": self.plan.to_dict(),
            "task_results": {k: v.to_dict() for k, v in self.task_results.items()},
            "final_output": self.final_output,
            "artifacts": self.get_artifacts(),
            "partial_artifacts": self.get_partial_artifacts(),
            "task_statuses": self.get_task_statuses(),
            "provenance_summary": self.get_provenance_summary(),
            "verification_summary": self.verification_summary,
            "summary": self.get_summary(),
            "execution_duration": self.execution_duration,
            "audit_trail": self.audit_trail,
            "is_success": self.is_success,
            "is_cancelled": self.is_cancelled,
            "cancellation_reason": self.cancellation_reason,
        }
