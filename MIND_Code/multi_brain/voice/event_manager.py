"""
MIND Centralized Voice Notification & TTS Authority — Event Manager.
Handles event ingestion, validation, task lifecycle state transitions,
idempotency, deduplication, and intelligent aggregation.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from multi_brain.voice.contracts import (
    DeliveryChannel,
    DeliveryState,
    NotificationDecision,
    NotificationEvent,
    NotificationEventType,
    NotificationPriority,
    TaskLifecycleState,
)

logger = logging.getLogger("mind.voice.event_manager")


class NotificationEventManager:
    """
    Central collector and evaluator of task events across the entire MIND ecosystem.
    Ensures silent agent reporting, validates state transitions, prevents duplicate
    notifications, and intelligently aggregates multiple events into unified announcements.
    """

    # Allowed state machine transitions
    VALID_TRANSITIONS: Dict[TaskLifecycleState, Set[TaskLifecycleState]] = {
        TaskLifecycleState.PENDING: {
            TaskLifecycleState.ACCEPTED,
            TaskLifecycleState.RUNNING,
            TaskLifecycleState.COMPLETED,
            TaskLifecycleState.CANCELLED,
            TaskLifecycleState.FAILED,
            TaskLifecycleState.PARTIALLY_COMPLETED,
        },
        TaskLifecycleState.ACCEPTED: {
            TaskLifecycleState.RUNNING,
            TaskLifecycleState.COMPLETED,
            TaskLifecycleState.CANCELLED,
            TaskLifecycleState.FAILED,
            TaskLifecycleState.PARTIALLY_COMPLETED,
        },
        TaskLifecycleState.RUNNING: {
            TaskLifecycleState.COMPLETED,
            TaskLifecycleState.FAILED,
            TaskLifecycleState.CANCELLED,
            TaskLifecycleState.PARTIALLY_COMPLETED,
        },
        TaskLifecycleState.COMPLETED: set(),  # Terminal
        TaskLifecycleState.FAILED: set(),     # Terminal
        TaskLifecycleState.CANCELLED: set(),  # Terminal
        TaskLifecycleState.PARTIALLY_COMPLETED: {
            TaskLifecycleState.COMPLETED,
            TaskLifecycleState.FAILED,
        },
    }

    def __init__(self, aggregation_window_seconds: float = 0.35) -> None:
        self.aggregation_window_seconds = aggregation_window_seconds
        self._lock = threading.RLock()

        # Deduplication & idempotency records
        self._processed_event_ids: Set[str] = set()
        self._rejected_event_log: List[Dict[str, Any]] = []

        # Task and workflow tracking
        self._task_states: Dict[str, TaskLifecycleState] = {}
        self._task_sequences: Dict[str, int] = {}
        self._workflow_tasks: Dict[str, Set[str]] = {}  # workflow_id -> set of task_ids
        self._task_to_workflow: Dict[str, str] = {}    # task_id -> workflow_id
        self._task_summaries: Dict[str, str] = {}      # task_id -> summary

        # Buffered events awaiting aggregation
        self._pending_aggregation_events: List[NotificationEvent] = []
        self._last_aggregation_time: float = 0.0

    def ingest_event(
        self, event: NotificationEvent
    ) -> Tuple[bool, Optional[str], Optional[NotificationDecision]]:
        """
        Validates, deduplicates, and ingests an incoming event.
        Returns: (accepted, rejection_reason, immediate_decision_if_any)
        """
        with self._lock:
            # 1. Schema and contract validation
            try:
                event.validate()
            except ValueError as e:
                err_msg = f"Schema validation error: {e}"
                self._record_rejection(event, err_msg)
                return False, err_msg, None

            # 2. Idempotency Check (Duplicate event_id prevention)
            if event.event_id in self._processed_event_ids:
                msg = f"Duplicate event_id ignored: {event.event_id}"
                logger.debug(msg)
                return False, "DUPLICATE_EVENT", None

            # 3. Sequence Number Ordering Check
            last_seq = self._task_sequences.get(event.task_id, 0)
            if event.sequence_number < last_seq:
                err_msg = f"Out-of-order event sequence: {event.sequence_number} < {last_seq}"
                self._record_rejection(event, err_msg)
                return False, err_msg, None

            # 4. Task State Machine Consistency Check
            current_state = self._task_states.get(event.task_id, TaskLifecycleState.PENDING)
            if current_state in TaskLifecycleState.terminal_states():
                # Cannot transition from terminal state to another terminal state
                err_msg = (
                    f"Illegal state transition: Task '{event.task_id}' is already in terminal state "
                    f"'{current_state.value}', cannot transition to '{event.status.value}'."
                )
                self._record_rejection(event, err_msg)
                return False, err_msg, None

            # Check valid transition path
            allowed = self.VALID_TRANSITIONS.get(current_state, set())
            if event.status != current_state and event.status not in allowed:
                err_msg = f"Invalid transition for task '{event.task_id}': '{current_state.value}' -> '{event.status.value}'"
                self._record_rejection(event, err_msg)
                return False, err_msg, None

            # 5. Commit state update
            self._processed_event_ids.add(event.event_id)
            self._task_states[event.task_id] = event.status
            self._task_sequences[event.task_id] = event.sequence_number
            self._task_summaries[event.task_id] = event.summary

            if event.workflow_id:
                self._workflow_tasks.setdefault(event.workflow_id, set()).add(event.task_id)
                self._task_to_workflow[event.task_id] = event.workflow_id

            logger.info(
                f"Accepted silent event: type={event.event_type.value}, "
                f"task={event.task_id}, source={event.source_id}, status={event.status.value}"
            )

            # 6. Evaluation for immediate or aggregated decision
            decision = self._evaluate_event(event)
            return True, None, decision

    def _evaluate_event(self, event: NotificationEvent) -> Optional[NotificationDecision]:
        """
        Evaluates whether an event requires immediate speech, buffering for aggregation,
        or silent logging. Progress events remain silent unless high priority.
        """
        # Progress and intermediate events remain silent
        if event.event_type in (
            NotificationEventType.TASK_ACCEPTED,
            NotificationEventType.TASK_STARTED,
            NotificationEventType.TASK_PROGRESS,
        ):
            return None

        # Critical / Emergency events bypass aggregation window immediately
        if event.priority == NotificationPriority.CRITICAL or event.event_type in (
            NotificationEventType.SYSTEM_ERROR,
            NotificationEventType.ACTION_REQUIRED,
        ):
            return self._build_single_task_decision(
                event,
                priority=NotificationPriority.CRITICAL,
                summary=event.summary or f"Critical system action required for task {event.task_id}.",
            )

        # Buffer terminal events for aggregation
        self._pending_aggregation_events.append(event)
        self._last_aggregation_time = time.time()
        return None

    def flush_pending_events(self) -> List[NotificationDecision]:
        """
        Flushes all buffered events into cohesive, intelligent NotificationDecisions.
        Called when aggregation window expires or upon workflow finalization.
        """
        with self._lock:
            if not self._pending_aggregation_events:
                return []

            events = list(self._pending_aggregation_events)
            self._pending_aggregation_events.clear()

            # Group events by workflow_id
            workflow_groups: Dict[Optional[str], List[NotificationEvent]] = {}
            for ev in events:
                wf_id = ev.workflow_id or self._task_to_workflow.get(ev.task_id)
                workflow_groups.setdefault(wf_id, []).append(ev)

            decisions: List[NotificationDecision] = []
            for wf_id, ev_list in workflow_groups.items():
                if len(ev_list) == 1:
                    dec = self._build_single_task_decision(ev_list[0])
                    decisions.append(dec)
                else:
                    dec = self._build_aggregated_decision(wf_id, ev_list)
                    decisions.append(dec)

            return decisions

    def _build_single_task_decision(
        self,
        event: NotificationEvent,
        priority: Optional[NotificationPriority] = None,
        summary: Optional[str] = None,
    ) -> NotificationDecision:
        """Constructs an intelligent single-task notification speech decision."""
        clean_summary = summary or event.summary
        task_noun = self._extract_task_noun(clean_summary, event.source_id)

        if event.status == TaskLifecycleState.COMPLETED:
            msg = f"Your {task_noun} has been completed successfully."
        elif event.status == TaskLifecycleState.FAILED:
            err_detail = event.error.get("message", "an unexpected error") if event.error else "an error"
            msg = f"The {task_noun} encountered {err_detail}. I've logged the diagnostics."
        elif event.status == TaskLifecycleState.CANCELLED:
            msg = f"The {task_noun} has been cancelled per user request."
        elif event.status == TaskLifecycleState.PARTIALLY_COMPLETED:
            msg = f"The {task_noun} was partially completed."
        else:
            msg = clean_summary

        return NotificationDecision(
            associated_event_ids=[event.event_id],
            task_id=event.task_id,
            workflow_id=event.workflow_id,
            priority=priority or event.priority,
            delivery_channel=DeliveryChannel.VOICE_PRIMARY,
            aggregation_decision="SINGLE_TASK",
            intended_message=msg,
            delivery_state=DeliveryState.CREATED,
            metadata={"source_id": event.source_id, "status": event.status.value},
        )

    def _build_aggregated_decision(
        self,
        workflow_id: Optional[str],
        events: List[NotificationEvent],
    ) -> NotificationDecision:
        """
        Consolidates multiple simultaneous task completion events into a single,
        fluent natural-language voice announcement.
        """
        event_ids = [e.event_id for e in events]
        highest_priority = min((e.priority for e in events), default=NotificationPriority.NORMAL)

        successes = [e for e in events if e.status == TaskLifecycleState.COMPLETED]
        failures = [e for e in events if e.status == TaskLifecycleState.FAILED]
        cancelled = [e for e in events if e.status == TaskLifecycleState.CANCELLED]

        # Extract friendly nouns
        success_nouns = [self._extract_task_noun(e.summary, e.source_id) for e in successes]
        failure_nouns = [self._extract_task_noun(e.summary, e.source_id) for e in failures]

        # Formulate consolidated speech
        if len(failures) == 0 and len(cancelled) == 0:
            # 100% Success
            items_str = self._format_items_list(success_nouns)
            msg = f"Your {items_str} have all been completed successfully."
            agg_type = "ALL_COMPLETED"
        elif len(successes) > 0 and len(failures) > 0:
            # Partial success / failure mix
            succ_str = self._format_items_list(success_nouns)
            fail_str = self._format_items_list(failure_nouns)
            msg = f"{len(successes)} tasks completed including {succ_str}, but {fail_str} encountered an error."
            agg_type = "PARTIAL_SUCCESS_FAILURE"
        elif len(successes) == 0 and len(failures) > 0:
            # All failed
            fail_str = self._format_items_list(failure_nouns)
            msg = f"The {fail_str} tasks failed to complete. Diagnostics have been recorded."
            agg_type = "ALL_FAILED"
        else:
            msg = f"{len(events)} tasks have finalized in the active workflow."
            agg_type = "MIXED"

        return NotificationDecision(
            associated_event_ids=event_ids,
            task_id=events[0].task_id,
            workflow_id=workflow_id,
            priority=highest_priority,
            delivery_channel=DeliveryChannel.VOICE_PRIMARY,
            aggregation_decision=agg_type,
            intended_message=msg,
            delivery_state=DeliveryState.CREATED,
            metadata={
                "event_count": len(events),
                "success_count": len(successes),
                "failure_count": len(failures),
            },
        )

    def _extract_task_noun(self, summary: str, source_id: str) -> str:
        """Extracts a short, natural item noun from a task description."""
        text = (summary or "").lower()
        if "website" in text or "web page" in text:
            return "website"
        if "image" in text or "visual" in text or "creative" in source_id:
            return "image generation"
        if "3d" in text or "mesh" in text or "threed" in source_id:
            return "3D model"
        if "code" in text or "python" in text or "engineering" in source_id:
            return "code development"
        if "research" in text or "literature" in text or "knowledge" in source_id:
            return "research report"
        if "verify" in text or "audit" in text or "critique" in source_id:
            return "verification audit"
        if "analysis" in text or "data" in text:
            return "data analysis"
        return summary.strip()[:40] or "task"

    def _format_items_list(self, items: List[str]) -> str:
        """Formats list of nouns cleanly: 'website', 'website and images', 'website, images, and 3D model'."""
        unique_items = []
        for it in items:
            if it not in unique_items:
                unique_items.append(it)

        if not unique_items:
            return "tasks"
        if len(unique_items) == 1:
            return unique_items[0]
        if len(unique_items) == 2:
            return f"{unique_items[0]} and {unique_items[1]}"
        return ", ".join(unique_items[:-1]) + f", and {unique_items[-1]}"

    def _record_rejection(self, event: NotificationEvent, reason: str) -> None:
        self._rejected_event_log.append({
            "event_id": event.event_id,
            "task_id": event.task_id,
            "source_id": event.source_id,
            "reason": reason,
            "timestamp": time.time(),
        })
        logger.warning(f"Rejected event {event.event_id}: {reason}")

    def get_rejected_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._rejected_event_log)

    def get_task_state(self, task_id: str) -> TaskLifecycleState:
        with self._lock:
            return self._task_states.get(task_id, TaskLifecycleState.PENDING)
