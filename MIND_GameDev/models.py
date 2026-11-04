"""Data models and contracts for MIND Universal Development Studio."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SafePathValidator:
    """Validates that all file and path operations remain strictly enclosed in a base directory."""

    @staticmethod
    def validate_containment(target_path: Path, base_dir: Path) -> Path:
        """
        Ensures target_path resolves strictly within base_dir.
        Blocks path traversal attacks ('../'), prefix collisions, and absolute path escapes.
        Raises PermissionError if target is outside base_dir.
        """
        try:
            base_resolved = base_dir.resolve()
            target_resolved = target_path.resolve()

            # Prevent prefix collision (e.g. /workspace_evil vs /workspace)
            target_resolved.relative_to(base_resolved)
            return target_resolved
        except (ValueError, RuntimeError) as e:
            raise PermissionError(
                f"Path traversal detected! Attempted to access path '{target_path}' "
                f"outside authorized root '{base_dir}'"
            ) from e

    @staticmethod
    def is_system_protected_path(path: Path | str) -> bool:
        """
        Detects whether a path refers to a critical operating system directory,
        drive root, or repository-critical metadata (.git) that must not be modified or deleted.
        """
        try:
            p = Path(path).resolve()
        except Exception:
            return True

        # Drive roots (e.g., C:\ or /)
        if p == p.parent or len(p.parts) <= 1:
            return True

        p_str = str(p).lower().replace("/", "\\")

        # Windows system paths
        windows_protected = [
            "c:\\windows",
            "c:\\program files",
            "c:\\program files (x86)",
            "c:\\system32",
            "c:\\recovery",
            "c:\\boot",
            "c:\\msocache",
        ]
        for wp in windows_protected:
            if p_str == wp or p_str.startswith(wp + "\\"):
                return True

        # Unix/Linux protected paths
        unix_protected = [
            "/bin", "/boot", "/dev", "/etc", "/lib", "/proc",
            "/root", "/sbin", "/sys", "/usr", "/var"
        ]
        p_unix = str(p).replace("\\", "/").lower()
        for up in unix_protected:
            if p_unix == up or p_unix.startswith(up + "/"):
                return True

        # Critical repository files/folders
        if ".git" in p.parts:
            return True

        return False


class DecisionStatus(str, Enum):
    """Execution gateway and conversational decision statuses."""
    READY = "READY"
    CLARIFY = "CLARIFY"
    CONFIRM = "CONFIRM"
    EXECUTE = "EXECUTE"
    FAILED = "FAILED"


class ActionType(str, Enum):
    """Types of natural-language user project and file operations."""
    CREATE_PROJECT = "create_project"
    APPROVE_DESIGN = "approve_design"
    REVISE_DESIGN = "revise_design"
    CANCEL = "cancel"
    LIST_FILES = "list_files"
    READ_FILE = "read_file"
    UPDATE_FILE = "update_file"
    ADD_PAGE = "add_page"
    RENAME_PATH = "rename_path"
    MOVE_PATH = "move_path"
    DELETE_PATH = "delete_path"
    INSPECT_PROJECT = "inspect_project"
    VERIFY_PROJECT = "verify_project"
    SERVE_PROJECT = "serve_project"
    GENERATE_IMAGE = "generate_image"
    RECONSTRUCT_3D = "reconstruct_3d"
    COMPOUND_WORKFLOW = "compound_workflow"
    UNKNOWN = "unknown"


class ProjectStatus(str, Enum):
    INITIALIZED = "initialized"
    PLANNING = "planning"
    PROPOSING_DESIGN = "proposing_design"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    GENERATING_CODE = "generating_code"
    GENERATING_ASSETS = "generating_assets"
    GENERATING = "generating"
    INTEGRATING = "integrating"
    GENERATED = "generated"
    TESTING = "testing"
    VERIFYING = "verifying"
    REPAIR_REQUIRED = "repair_required"
    REPAIRING = "repairing"
    REVERIFYING = "reverifying"
    PASSED = "passed"
    VERIFIED = "verified"
    NEEDS_ATTENTION = "needs_attention"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VerificationCategory(str, Enum):
    SYNTAX = "syntax"
    STRUCTURE = "structure"
    DEPENDENCY = "dependency"
    RUNTIME = "runtime"
    INTEGRITY = "integrity"
    FUNCTIONAL = "functional"
    SECURITY = "security"
    TYPE_CHECK = "type_check"


@dataclass
class DiagnosticReport:
    """Actionable diagnostic report sent to responsible specialized agent for repair."""
    task_id: str
    project_id: str
    agent_responsible: str
    verification_category: VerificationCategory
    error_severity: str  # "ERROR", "WARNING", "CRITICAL"
    file_path: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    error_message: str = ""
    diagnostic_output: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""
    code_context: str = ""
    suggested_correction: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "agent_responsible": self.agent_responsible,
            "verification_category": self.verification_category.value if hasattr(self.verification_category, "value") else str(self.verification_category),
            "error_severity": self.error_severity,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column_number": self.column_number,
            "error_message": self.error_message,
            "diagnostic_output": self.diagnostic_output,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "code_context": self.code_context,
            "suggested_correction": self.suggested_correction,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentTask:
    """Formal contract for an agent task assignment with dependencies and repair history."""
    task_id: str
    assigned_agent: str
    input_requirements: Dict[str, Any]
    expected_output_format: str
    project_context: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    completion_state: str = "PENDING"
    verification_state: str = "UNVERIFIED"
    repair_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "assigned_agent": self.assigned_agent,
            "input_requirements": self.input_requirements,
            "expected_output_format": self.expected_output_format,
            "project_context": self.project_context,
            "dependencies": self.dependencies,
            "completion_state": self.completion_state,
            "verification_state": self.verification_state,
            "repair_history": self.repair_history,
        }


@dataclass
class RepairAttempt:
    """Record of an automated repair cycle iteration."""
    attempt_number: int
    diagnostic: DiagnosticReport
    patch_applied: str
    explanation: str
    verification_passed: bool
    agent_identity: str = "coding_agent"
    relevant_context: Dict[str, Any] = field(default_factory=dict)
    repair_response: str = ""
    files_changed: List[str] = field(default_factory=list)
    verification_before: Dict[str, Any] = field(default_factory=dict)
    verification_after: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "diagnostic": self.diagnostic.to_dict(),
            "patch_applied": self.patch_applied,
            "explanation": self.explanation,
            "verification_passed": self.verification_passed,
            "agent_identity": self.agent_identity,
            "relevant_context": self.relevant_context,
            "repair_response": self.repair_response,
            "files_changed": self.files_changed,
            "verification_before": self.verification_before,
            "verification_after": self.verification_after,
            "timestamp": self.timestamp,
        }


class ProjectType(str, Enum):
    WEBSITE = "website"
    WEB_APP = "web_app"
    BACKEND_API = "backend_api"
    MOBILE_APP = "mobile_app"
    DESKTOP_APP = "desktop_app"
    GAME = "game"
    IMAGE = "image"
    AUTOMATION = "automation"
    CUSTOM = "custom"


@dataclass
class GameSpecification:
    """Detailed game and universal project design specification."""
    title: str = "CyberDash 3D: Endless Runner"
    genre: str = "3D Endless Runner"
    target_engine: str = "Three.js WebGL"
    game_type: str = "endless_runner_3d"
    project_type: ProjectType = ProjectType.GAME
    theme: str = "cyberpunk neon arcade"
    project_name: str = "cyberdash_3d"
    description: str = ""
    art_style: str = "stylized low-poly neon"
    target_framework: str = "threejs"
    lanes_count: int = 3
    player_character: str = "Runner Hero"
    controls: Dict[str, str] = field(default_factory=lambda: {
        "ArrowLeft / KeyA": "Switch to left lane",
        "ArrowRight / KeyD": "Switch to right lane",
        "ArrowUp / KeyW / Space": "Jump over obstacles",
        "ArrowDown / KeyS": "Slide under barriers",
        "KeyR": "Restart game",
        "KeyP": "Pause / resume",
    })
    obstacles: List[str] = field(default_factory=lambda: ["hurdle", "laser_gate", "barrier"])
    collectibles: List[str] = field(default_factory=lambda: ["gold_coin", "shield", "magnet"])
    track_segment_length: float = 30.0
    initial_speed: float = 16.0
    max_speed: float = 38.0
    speed_increase_rate: float = 0.25
    fog_color: str = "#05060f"
    pages: List[str] = field(default_factory=list)
    endpoints: List[str] = field(default_factory=list)
    destination_dir: Optional[str] = None
    features: List[str] = field(default_factory=lambda: [
        "Dynamic procedural infinite track extension",
        "Real-time collision detection (AABB bounding boxes)",
        "Coins pickup with rotating animation and score increment",
        "Increasing difficulty curve over survival distance",
        "Jump arc physics and slide crouch physics",
        "Start screen, HUD score/coins overlay, and Game Over screen",
        "Local high score persistence via localStorage",
        "Fallback procedural 3D geometry + GLB mesh asset integration",
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "genre": self.genre,
            "target_engine": self.target_engine,
            "game_type": self.game_type,
            "project_type": self.project_type.value if hasattr(self.project_type, "value") else str(self.project_type),
            "theme": self.theme,
            "project_name": self.project_name,
            "description": self.description,
            "art_style": self.art_style,
            "target_framework": self.target_framework,
            "lanes_count": self.lanes_count,
            "player_character": self.player_character,
            "controls": self.controls,
            "obstacles": self.obstacles,
            "collectibles": self.collectibles,
            "track_segment_length": self.track_segment_length,
            "initial_speed": self.initial_speed,
            "max_speed": self.max_speed,
            "speed_increase_rate": self.speed_increase_rate,
            "fog_color": self.fog_color,
            "pages": self.pages,
            "endpoints": self.endpoints,
            "destination_dir": self.destination_dir,
            "features": self.features,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameSpecification":
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            return cls()
        pt_raw = data.get("project_type", ProjectType.GAME)
        if isinstance(pt_raw, ProjectType):
            p_type = pt_raw
        else:
            try:
                p_type = ProjectType(str(pt_raw).lower())
            except ValueError:
                p_type = ProjectType.GAME
        return cls(
            title=str(data.get("title", "CyberDash 3D: Endless Runner")),
            genre=str(data.get("genre", "3D Endless Runner")),
            target_engine=str(data.get("target_engine", "Three.js WebGL")),
            game_type=str(data.get("game_type", "endless_runner_3d")),
            project_type=p_type,
            theme=str(data.get("theme", "cyberpunk neon arcade")),
            project_name=str(data.get("project_name", "cyberdash_3d")),
            description=str(data.get("description", "")),
            art_style=str(data.get("art_style", "stylized low-poly neon")),
            target_framework=str(data.get("target_framework", "threejs")),
            lanes_count=int(data.get("lanes_count", 3)),
            player_character=str(data.get("player_character", "Runner Hero")),
            controls=dict(data.get("controls")) if isinstance(data.get("controls"), dict) else cls().controls,
            obstacles=list(data.get("obstacles")) if isinstance(data.get("obstacles"), list) else cls().obstacles,
            collectibles=list(data.get("collectibles")) if isinstance(data.get("collectibles"), list) else cls().collectibles,
            track_segment_length=float(data.get("track_segment_length", 30.0)),
            initial_speed=float(data.get("initial_speed", 16.0)),
            max_speed=float(data.get("max_speed", 38.0)),
            speed_increase_rate=float(data.get("speed_increase_rate", 0.25)),
            fog_color=str(data.get("fog_color", "#05060f")),
            pages=list(data.get("pages") or []),
            endpoints=list(data.get("endpoints") or []),
            destination_dir=data.get("destination_dir"),
            features=list(data.get("features")) if isinstance(data.get("features"), list) else cls().features,
        )


# Universal alias for GameSpecification
ProjectSpecification = GameSpecification


@dataclass
class AssetMetadata:
    """Metadata for a generated or imported 2D/3D game asset."""
    name: str
    asset_type: str  # "image_concept", "3d_model", "sound_sfx", "data_schema"
    format: str
    file_path: str
    file_size_bytes: int = 0
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    asset_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "asset_type": self.asset_type,
            "format": self.format,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "verified": self.verified,
            "metadata": self.metadata,
        }


@dataclass
class GameProject:
    """Representation of an active development project."""
    name: str
    root_path: str
    specification: GameSpecification
    status: ProjectStatus = ProjectStatus.INITIALIZED
    project_type: ProjectType = ProjectType.GAME
    project_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    files: List[str] = field(default_factory=list)
    assets: List[AssetMetadata] = field(default_factory=list)
    manifest_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    run_command: str = ""
    test_command: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "root_path": self.root_path,
            "specification": self.specification.to_dict(),
            "status": self.status.value,
            "project_type": self.project_type.value if hasattr(self.project_type, "value") else str(self.project_type),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": self.files,
            "assets": [a.to_dict() for a in self.assets],
            "manifest_path": self.manifest_path,
            "metadata": self.metadata,
            "run_command": self.run_command,
            "test_command": self.test_command,
        }


# Universal alias for GameProject
DevProject = GameProject


@dataclass
class ExecutionReport:
    """Final outcome report of a generation and verification workflow."""
    workflow_id: str
    project_name: str
    success: bool
    status: str
    target_engine: str = "Standard"
    project_type: str = "game"
    project_path: str = ""
    index_html_path: str = ""
    entry_point: str = ""
    files_created: List[str] = field(default_factory=list)
    assets_created: List[Dict[str, Any]] = field(default_factory=list)
    verification_results: Dict[str, Any] = field(default_factory=dict)
    playability_verified: bool = False
    tests_passed: int = 0
    tests_failed: int = 0
    elapsed_seconds: float = 0.0
    summary: str = ""
    limitations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    repair_attempts: List[Dict[str, Any]] = field(default_factory=list)
    is_candidate: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "project_name": self.project_name,
            "success": self.success,
            "status": self.status,
            "target_engine": self.target_engine,
            "project_type": self.project_type,
            "project_path": self.project_path,
            "index_html_path": self.index_html_path,
            "entry_point": self.entry_point,
            "files_created": self.files_created,
            "assets_created": self.assets_created,
            "verification_results": self.verification_results,
            "playability_verified": self.playability_verified,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "elapsed_seconds": self.elapsed_seconds,
            "summary": self.summary,
            "limitations": self.limitations,
            "errors": self.errors,
            "warnings": self.warnings,
            "diagnostics": self.diagnostics,
            "repair_attempts": self.repair_attempts,
            "is_candidate": self.is_candidate,
            "details": self.details,
        }
