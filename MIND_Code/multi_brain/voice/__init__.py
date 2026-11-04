"""
MIND Centralized Voice Notification & TTS Authority Package.
Sole authority for user-facing speech and centralized task notifications.
"""

from multi_brain.voice.contracts import (
    DeliveryChannel,
    DeliveryRecord,
    DeliveryState,
    FailureCategory,
    NotificationDecision,
    NotificationEvent,
    NotificationEventType,
    NotificationPriority,
    TaskLifecycleState,
)
from multi_brain.voice.synthesizer import (
    BaseVoiceSynthesizer,
    MockVoiceSynthesizer,
    PowerShellVoiceSynthesizer,
)
from multi_brain.voice.recovery_manager import DeliveryRecoveryManager
from multi_brain.voice.event_manager import NotificationEventManager
from multi_brain.voice.controller import CentralVoiceController
from multi_brain.voice.authority import CentralVoiceNotificationAuthority

__all__ = [
    "DeliveryChannel",
    "DeliveryRecord",
    "DeliveryState",
    "FailureCategory",
    "NotificationDecision",
    "NotificationEvent",
    "NotificationEventType",
    "NotificationPriority",
    "TaskLifecycleState",
    "BaseVoiceSynthesizer",
    "MockVoiceSynthesizer",
    "PowerShellVoiceSynthesizer",
    "DeliveryRecoveryManager",
    "NotificationEventManager",
    "CentralVoiceController",
    "CentralVoiceNotificationAuthority",
]
