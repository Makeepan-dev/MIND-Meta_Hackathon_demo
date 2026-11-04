"""
MIND Centralized Voice Notification & TTS Authority — Contracts & Data Models.
Defines versioned event schemas, task lifecycle states, notification priorities,
and delivery states.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class NotificationEventType(str, enum.Enum):
    """Supported task lifecycle and system notification event types."""
    TASK_ACCEPTED = "TASK_ACCEPTED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_PARTIALLY_COMPLETED = "TASK_PARTIALLY_COMPLETED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    WORKFLOW_PARTIALLY_COMPLETED = "WORKFLOW_PARTIALLY_COMPLETED"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    SYSTEM_WARNING = "SYSTEM_WARNING"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class TaskLifecycleState(str, enum.Enum):
    """Consistent task lifecycle state machine."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"

    @classmethod
    def terminal_states(cls) -> set[TaskLifecycleState]:
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED, cls.PARTIALLY_COMPLETED}


class NotificationPriority(int, enum.Enum):
    """Priority levels for speech and notification delivery (lower number = higher priority)."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


class DeliveryChannel(str, enum.Enum):
    """Target channel for notification delivery."""
    VOICE_PRIMARY = "VOICE_PRIMARY"
    VISUAL_FALLBACK = "VISUAL_FALLBACK"
    SILENT_LOG = "SILENT_LOG"


class DeliveryState(str, enum.Enum):
    """Explicit lifecycle states for notification delivery."""
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    GENERATED = "GENERATED"
    PLAYING = "PLAYING"
    DELIVERED = "DELIVERED"
    RETRY_PENDING = "RETRY_PENDING"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    FALLBACK_DELIVERED = "FALLBACK_DELIVERED"
    SUPPRESSED = "SUPPRESSED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"


class FailureCategory(str, enum.Enum):
    """Classification of notification or audio failure."""
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"


@dataclass
class NotificationEvent:
    """
    Standardized, versioned event contract submitted silently by all agents,
    tools, MCP servers, and background services.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_version: str = "1.0"
    event_type: NotificationEventType = NotificationEventType.TASK_COMPLETED
    task_id: str = ""
    workflow_id: Optional[str] = None
    source_id: str = "unknown_agent"
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sequence_number: int = 1
    status: TaskLifecycleState = TaskLifecycleState.COMPLETED
    priority: NotificationPriority = NotificationPriority.NORMAL
    summary: str = ""
    result_reference: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validates schema conformance and mandatory fields."""
        if not self.event_id:
            raise ValueError("event_id must not be empty.")
        if self.event_version != "1.0":
            raise ValueError(f"Unsupported event_version: {self.event_version}")
        if not self.task_id:
            raise ValueError("task_id must not be empty.")
        if not self.source_id:
            raise ValueError("source_id must not be empty.")
        if not self.summary:
            raise ValueError("summary must not be empty.")
        if not isinstance(self.event_type, NotificationEventType):
            try:
                self.event_type = NotificationEventType(self.event_type)
            except Exception:
                raise ValueError(f"Invalid event_type: {self.event_type}")
        if not isinstance(self.status, TaskLifecycleState):
            try:
                self.status = TaskLifecycleState(self.status)
            except Exception:
                raise ValueError(f"Invalid task status: {self.status}")
        if not isinstance(self.priority, NotificationPriority):
            try:
                self.priority = NotificationPriority(self.priority)
            except Exception:
                raise ValueError(f"Invalid priority: {self.priority}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_version": self.event_version,
            "event_type": self.event_type.value,
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "source_id": self.source_id,
            "occurred_at": self.occurred_at,
            "sequence_number": self.sequence_number,
            "status": self.status.value,
            "priority": self.priority.value,
            "summary": self.summary,
            "result_reference": self.result_reference,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class NotificationDecision:
    """
    Contract representing MIND's centralized decision on what and how to communicate.
    Only the central MIND voice controller may execute user-facing speech.
    """
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    associated_event_ids: List[str] = field(default_factory=list)
    task_id: str = ""
    workflow_id: Optional[str] = None
    priority: NotificationPriority = NotificationPriority.NORMAL
    delivery_channel: DeliveryChannel = DeliveryChannel.VOICE_PRIMARY
    aggregation_decision: str = "SINGLE_TASK"
    intended_message: str = ""
    delivery_state: DeliveryState = DeliveryState.CREATED
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "associated_event_ids": self.associated_event_ids,
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "priority": self.priority.value,
            "delivery_channel": self.delivery_channel.value,
            "aggregation_decision": self.aggregation_decision,
            "intended_message": self.intended_message,
            "delivery_state": self.delivery_state.value,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class DeliveryRecord:
    """
    Comprehensive diagnostic record for tracking delivery attempts and recovery.
    """
    notification_id: str
    original_event_ids: List[str]
    attempt_count: int = 0
    last_attempted_at: float = field(default_factory=time.time)
    failure_classification: Optional[FailureCategory] = None
    error_details: Optional[str] = None
    recovery_action: Optional[str] = None
    final_delivery_state: DeliveryState = DeliveryState.CREATED
    visual_fallback_delivered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "original_event_ids": self.original_event_ids,
            "attempt_count": self.attempt_count,
            "last_attempted_at": self.last_attempted_at,
            "failure_classification": self.failure_classification.value if self.failure_classification else None,
            "error_details": self.error_details,
            "recovery_action": self.recovery_action,
            "final_delivery_state": self.final_delivery_state.value,
            "visual_fallback_delivered": self.visual_fallback_delivered,
        }
