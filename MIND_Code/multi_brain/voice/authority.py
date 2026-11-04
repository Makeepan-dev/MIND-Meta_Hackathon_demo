"""
MIND Centralized Voice Notification & TTS Authority — System Coordinator.
Acts as the central authority unifying event collection, validation, aggregation,
priority voice queuing, and delivery failure recovery.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from multi_brain.voice.contracts import (
    DeliveryChannel,
    DeliveryState,
    NotificationDecision,
    NotificationEvent,
    NotificationEventType,
    NotificationPriority,
    TaskLifecycleState,
)
from multi_brain.voice.controller import CentralVoiceController
from multi_brain.voice.event_manager import NotificationEventManager
from multi_brain.voice.recovery_manager import DeliveryRecoveryManager
from multi_brain.voice.synthesizer import BaseVoiceSynthesizer, PowerShellVoiceSynthesizer

logger = logging.getLogger("mind.voice.authority")


class CentralVoiceNotificationAuthority:
    """
    The Single Central Voice Notification & TTS Authority for MIND.
    Ensures that AI agents perform work and report silently, while MIND
    is the sole entity authorized to communicate with the user through voice.
    """

    _instance: Optional[CentralVoiceNotificationAuthority] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> CentralVoiceNotificationAuthority:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def set_instance(cls, authority: CentralVoiceNotificationAuthority) -> None:
        with cls._instance_lock:
            cls._instance = authority

    def __init__(
        self,
        synthesizer: Optional[BaseVoiceSynthesizer] = None,
        aggregation_window_seconds: float = 0.35,
        visual_fallback_callback: Optional[Callable[[NotificationDecision], None]] = None,
        enabled: bool = True,
    ) -> None:
        self.recovery_manager = DeliveryRecoveryManager(
            visual_fallback_callback=visual_fallback_callback
        )
        self.event_manager = NotificationEventManager(
            aggregation_window_seconds=aggregation_window_seconds
        )
        self.controller = CentralVoiceController(
            synthesizer=synthesizer,
            recovery_manager=self.recovery_manager,
            enabled=enabled,
        )

        self._shutdown_event = threading.Event()
        self._flusher_thread = threading.Thread(
            target=self._aggregation_flush_loop,
            daemon=True,
            name="MIND_VoiceAuthorityFlusher",
        )
        self._flusher_thread.start()

    def post_event(self, event: NotificationEvent) -> Tuple[bool, Optional[str]]:
        """
        Primary silent entry point for all AI agents, tools, MCP servers,
        and background tasks to report lifecycle events.
        Agents do NOT speak; they submit events silently here.
        """
        accepted, reason, immediate_decision = self.event_manager.ingest_event(event)
        if not accepted:
            return False, reason

        if immediate_decision:
            self.controller.enqueue_decision(immediate_decision)

        return True, None

    def report_task_completion(
        self,
        task_id: str,
        source_id: str,
        summary: str,
        workflow_id: Optional[str] = None,
        result_reference: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Convenience method for silent task completion reporting."""
        ev = NotificationEvent(
            event_type=NotificationEventType.TASK_COMPLETED,
            task_id=task_id,
            workflow_id=workflow_id,
            source_id=source_id,
            status=TaskLifecycleState.COMPLETED,
            priority=priority,
            summary=summary,
            result_reference=result_reference,
            metadata=metadata or {},
        )
        return self.post_event(ev)

    def report_task_failure(
        self,
        task_id: str,
        source_id: str,
        summary: str,
        error_details: Dict[str, Any],
        workflow_id: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> Tuple[bool, Optional[str]]:
        """Convenience method for silent task failure reporting."""
        ev = NotificationEvent(
            event_type=NotificationEventType.TASK_FAILED,
            task_id=task_id,
            workflow_id=workflow_id,
            source_id=source_id,
            status=TaskLifecycleState.FAILED,
            priority=priority,
            summary=summary,
            error=error_details,
        )
        return self.post_event(ev)

    def report_workflow_completion(
        self,
        workflow_id: str,
        summary: str = "Development workflow completed successfully.",
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> None:
        """
        Flushes pending child task events and emits an authoritative
        workflow completion voice announcement.
        """
        # First flush any remaining buffered tasks
        decisions = self.event_manager.flush_pending_events()
        for d in decisions:
            self.controller.enqueue_decision(d)

        # Emit overarching workflow announcement
        wf_decision = NotificationDecision(
            associated_event_ids=[],
            task_id=workflow_id,
            workflow_id=workflow_id,
            priority=priority,
            delivery_channel=DeliveryChannel.VOICE_PRIMARY,
            aggregation_decision="WORKFLOW_COMPLETE",
            intended_message=summary,
        )
        self.controller.enqueue_decision(wf_decision)

    def speak(
        self,
        text: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        source_id: str = "mind_core",
    ) -> NotificationDecision:
        """
        Official central voice output channel for MIND conversational responses.
        Only MIND core is authorized to invoke this.
        """
        return self.controller.speak_direct(text, priority=priority, source_id=source_id)

    def _aggregation_flush_loop(self) -> None:
        """Background ticker checking and flushing aggregated task announcements."""
        while not self._shutdown_event.is_set():
            time.sleep(0.05)
            # If aggregation window has passed, flush buffered events
            now = time.time()
            if (
                self.event_manager._pending_aggregation_events
                and (now - self.event_manager._last_aggregation_time) >= self.event_manager.aggregation_window_seconds
            ):
                decisions = self.event_manager.flush_pending_events()
                for d in decisions:
                    self.controller.enqueue_decision(d)

    def flush_immediately(self) -> None:
        """Forces immediate aggregation and queueing without waiting for timer."""
        decisions = self.event_manager.flush_pending_events()
        for d in decisions:
            self.controller.enqueue_decision(d)

    def stop(self) -> None:
        """Safely terminates all background threads and flushes queues."""
        self._shutdown_event.set()
        self.controller.stop()
