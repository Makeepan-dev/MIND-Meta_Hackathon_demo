"""
MIND Centralized Voice Notification & TTS Authority — Central Voice Controller.
Enforces single-speaker authority, priority queuing, audio serialization,
and non-blocking asynchronous delivery.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from multi_brain.voice.contracts import (
    DeliveryChannel,
    DeliveryState,
    FailureCategory,
    NotificationDecision,
    NotificationPriority,
)
from multi_brain.voice.recovery_manager import DeliveryRecoveryManager
from multi_brain.voice.synthesizer import BaseVoiceSynthesizer, PowerShellVoiceSynthesizer

logger = logging.getLogger("mind.voice.controller")


class CentralVoiceController:
    """
    The SOLE entity in MIND authorized to generate user-facing speech.
    All agents, tools, MCP servers, and background services are strictly forbidden
    from calling speech directly.
    """

    def __init__(
        self,
        synthesizer: Optional[BaseVoiceSynthesizer] = None,
        recovery_manager: Optional[DeliveryRecoveryManager] = None,
        enabled: bool = True,
    ) -> None:
        self.synthesizer = synthesizer or PowerShellVoiceSynthesizer(enabled=enabled)
        self.recovery_manager = recovery_manager or DeliveryRecoveryManager()
        self.enabled = enabled

        # Priority speech queue: entries are tuples: (priority_int, timestamp, NotificationDecision)
        self._speech_queue: queue.PriorityQueue[Tuple[int, float, NotificationDecision]] = queue.PriorityQueue()

        # Audio playback lock and status tracking
        self.is_speaking = threading.Event()
        self._speech_mutex = threading.Lock()
        self._shutdown_event = threading.Event()

        # Diagnostic history of spoken decisions
        self._history: List[NotificationDecision] = []
        self._history_lock = threading.Lock()

        # Background worker thread
        self._worker_thread: Optional[threading.Thread] = None
        self._start_worker()

    def _start_worker(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_thread = threading.Thread(
            target=self._speech_processing_loop,
            daemon=True,
            name="MIND_CentralVoiceController",
        )
        self._worker_thread.start()

    def enqueue_decision(self, decision: NotificationDecision) -> None:
        """
        Enqueues an authoritative notification decision for prioritized speech delivery.
        Non-blocking: immediately buffers and notifies background speaker.
        """
        if not self.enabled:
            decision.delivery_state = DeliveryState.SUPPRESSED
            logger.info(f"[MIND Voice Muted] Suppressed: {decision.intended_message}")
            return

        self.recovery_manager.register_decision(decision)

        p_val = decision.priority.value if isinstance(decision.priority, NotificationPriority) else int(decision.priority)
        self._speech_queue.put((p_val, time.time(), decision))
        logger.debug(f"Enqueued speech (priority={p_val}): {decision.intended_message}")

    def speak_direct(
        self,
        text: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        source_id: str = "mind_core",
    ) -> NotificationDecision:
        """
        Authoritative direct speech path reserved exclusively for MIND's core assistant.
        """
        decision = NotificationDecision(
            associated_event_ids=[],
            task_id=f"direct_{int(time.time()*1000)}",
            priority=priority,
            delivery_channel=DeliveryChannel.VOICE_PRIMARY,
            aggregation_decision="DIRECT_ASSISTANT",
            intended_message=text,
            metadata={"source_id": source_id},
        )
        self.enqueue_decision(decision)
        return decision

    def _speech_processing_loop(self) -> None:
        """
        Continuous worker loop processing priority speech queue items serially.
        Guarantees that overlapping speech NEVER occurs.
        """
        while not self._shutdown_event.is_set():
            try:
                p_val, enqueued_at, decision = self._speech_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            with self._speech_mutex:
                self._deliver_decision_with_recovery(decision)
                self._speech_queue.task_done()

    def _deliver_decision_with_recovery(self, decision: NotificationDecision) -> None:
        """
        Executes synthesis and playback under speech lock with automatic retries.
        """
        self.is_speaking.set()
        try:
            decision.delivery_state = DeliveryState.PROCESSING
            max_attempts = self.recovery_manager.max_retries
            success = False

            while not success:
                self.recovery_manager.record_attempt(decision.notification_id)
                decision.delivery_state = DeliveryState.GENERATED

                # Check if synthesizer is operational
                if not self.synthesizer.is_available():
                    logger.warning("Synthesizer unavailable, triggering recovery.")
                    is_perm = getattr(self.synthesizer, "is_permanent_failure", lambda: False)()
                    category = FailureCategory.PERMANENT if is_perm else FailureCategory.TRANSIENT
                    should_retry = self.recovery_manager.handle_failure(
                        decision,
                        error_details="Voice synthesizer unavailable or offline.",
                        category=category,
                    )
                    if not should_retry:
                        break
                    continue

                # Initiate Audio Playback
                decision.delivery_state = DeliveryState.PLAYING
                try:
                    audio_delivered = self.synthesizer.synthesize_and_play(
                        text=decision.intended_message,
                        priority=decision.priority.value,
                    )
                except Exception as playback_err:
                    audio_delivered = False
                    logger.error(f"Playback exception: {playback_err}")

                if audio_delivered:
                    success = True
                    self.recovery_manager.record_success(decision)
                    with self._history_lock:
                        self._history.append(decision)
                    logger.info(f"[MIND Central Voice Delivered]: {decision.intended_message}")
                    break
                else:
                    should_retry = self.recovery_manager.handle_failure(
                        decision,
                        error_details="Synthesizer audio playback failed.",
                        category=FailureCategory.TRANSIENT,
                    )
                    if not should_retry:
                        break

        finally:
            self.is_speaking.clear()

    def stop(self) -> None:
        """Flushes queue and safely stops worker thread."""
        self._shutdown_event.set()
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
            except Exception:
                break
        self.is_speaking.clear()

    def get_history(self) -> List[NotificationDecision]:
        with self._history_lock:
            return list(self._history)

    def is_busy(self) -> bool:
        return self.is_speaking.is_set() or not self._speech_queue.empty()
