"""
MIND Centralized Voice Notification & TTS Authority — Recovery Manager.
Implements exponential backoff retry policies, failure classification (transient vs permanent),
visual notification fallback, and comprehensive diagnostic observability.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from multi_brain.voice.contracts import (
    DeliveryChannel,
    DeliveryRecord,
    DeliveryState,
    FailureCategory,
    NotificationDecision,
)

logger = logging.getLogger("mind.voice.recovery_manager")


class DeliveryRecoveryManager:
    """
    Guarantees reliable notification delivery while decoupling task completion
    from speech delivery. Enforces fallback to visual UI when speech fails.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.1,
        max_backoff_seconds: float = 1.0,
        visual_fallback_callback: Optional[Callable[[NotificationDecision], None]] = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.visual_fallback_callback = visual_fallback_callback
        self._lock = threading.RLock()

        # Diagnostic records keyed by notification_id
        self._records: Dict[str, DeliveryRecord] = {}
        self._visual_fallback_delivered: List[NotificationDecision] = []

    def register_decision(self, decision: NotificationDecision) -> DeliveryRecord:
        """Initializes a delivery tracking record for a new decision."""
        with self._lock:
            record = DeliveryRecord(
                notification_id=decision.notification_id,
                original_event_ids=list(decision.associated_event_ids),
                attempt_count=0,
                last_attempted_at=time.time(),
                final_delivery_state=DeliveryState.QUEUED,
            )
            self._records[decision.notification_id] = record
            decision.delivery_state = DeliveryState.QUEUED
            return record

    def record_attempt(self, notification_id: str) -> None:
        with self._lock:
            record = self._records.get(notification_id)
            if record:
                record.attempt_count += 1
                record.last_attempted_at = time.time()
                record.final_delivery_state = DeliveryState.PROCESSING

    def record_success(self, decision: NotificationDecision) -> None:
        """Marks a notification as DELIVERED after confirmed audio playback."""
        with self._lock:
            decision.delivery_state = DeliveryState.DELIVERED
            record = self._records.get(decision.notification_id)
            if record:
                record.final_delivery_state = DeliveryState.DELIVERED
                record.error_details = None
                record.recovery_action = "AUDIO_CONFIRMED"

    def handle_failure(
        self,
        decision: NotificationDecision,
        error_details: str,
        category: FailureCategory = FailureCategory.TRANSIENT,
    ) -> bool:
        """
        Evaluates a delivery failure:
        - If transient and retries remain: schedules retry.
        - If permanent or max retries exceeded: initiates visual fallback.
        Returns: True if a retry should be executed, False if fallen back or failed.
        """
        with self._lock:
            record = self._records.setdefault(
                decision.notification_id,
                DeliveryRecord(
                    notification_id=decision.notification_id,
                    original_event_ids=list(decision.associated_event_ids),
                ),
            )
            record.failure_classification = category
            record.error_details = error_details

            # Permanent failure or max attempts reached -> Fallback to visual
            if category == FailureCategory.PERMANENT or record.attempt_count >= self.max_retries:
                self._execute_fallback(decision, record, f"Exceeded {self.max_retries} attempts: {error_details}")
                return False

            # Transient failure -> Can retry
            decision.delivery_state = DeliveryState.RETRY_PENDING
            record.final_delivery_state = DeliveryState.RETRY_PENDING
            record.recovery_action = f"RETRY_PENDING_ATTEMPT_{record.attempt_count + 1}"

            # Calculate exponential backoff with jitter
            backoff = min(
                self.max_backoff_seconds,
                self.base_backoff_seconds * (2 ** (record.attempt_count - 1)),
            )
            jitter = random.uniform(0.01, 0.05)
            sleep_time = backoff + jitter
            time.sleep(sleep_time)
            return True

    def _execute_fallback(
        self,
        decision: NotificationDecision,
        record: DeliveryRecord,
        reason: str,
    ) -> None:
        """Executes graceful fallback to visual notification channel."""
        decision.delivery_state = DeliveryState.FALLBACK_DELIVERED
        decision.delivery_channel = DeliveryChannel.VISUAL_FALLBACK
        record.final_delivery_state = DeliveryState.FALLBACK_DELIVERED
        record.visual_fallback_delivered = True
        record.recovery_action = f"VISUAL_FALLBACK_TRIGGERED: {reason}"

        self._visual_fallback_delivered.append(decision)
        logger.warning(
            f"TTS audio delivery failed for notification {decision.notification_id}. "
            f"Executing visual fallback. Reason: {reason}"
        )

        if self.visual_fallback_callback:
            try:
                self.visual_fallback_callback(decision)
            except Exception as e:
                logger.error(f"Error in visual fallback callback: {e}")

    def get_record(self, notification_id: str) -> Optional[DeliveryRecord]:
        with self._lock:
            return self._records.get(notification_id)

    def list_records(self) -> List[DeliveryRecord]:
        with self._lock:
            return list(self._records.values())

    def get_visual_fallbacks(self) -> List[NotificationDecision]:
        with self._lock:
            return list(self._visual_fallback_delivered)
