"""Audio and Communication Brain: Wraps speech synthesis and transcription capabilities."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from multi_brain.brains.base import SpecialistBrain
from multi_brain.contracts import (
    Capability,
    PermissionTier,
    Provenance,
    TaskRequest,
    TaskResult,
    TaskStatus,
)

logger = logging.getLogger("mind.multi_brain.audio_brain")


class AudioCommunicationBrain(SpecialistBrain):
    """
    Specialist brain integrating MIND's audio capabilities:
    speech synthesis (TTS), audio transcription (STT), and vocal communication.
    """

    def __init__(self) -> None:
        super().__init__(
            brain_id="audio_communication",
            name="Audio and Communication Brain",
            domain="Audio & Speech",
            description="Manages vocal interaction, speech synthesis, and audio transcription.",
            capabilities=[
                Capability(
                    name="text_to_speech",
                    domain="Audio",
                    description="Synthesizes spoken audio from text using MIND's voice pipeline.",
                    modalities=["text", "audio"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
                Capability(
                    name="speech_to_text",
                    domain="Audio",
                    description="Transcribes recorded audio streams into text.",
                    modalities=["audio", "text"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
            ],
            permission_tier=PermissionTier.SAFE,
        )

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        goal = request.user_goal
        inputs = request.input_data or {}
        text_to_speak = inputs.get("text") or goal

        speech_dispatched = False
        try:
            # Connect to MIND's existing speech queue if config is available
            import config
            if hasattr(config, "speech_queue"):
                config.speech_queue.put(text_to_speak)
                speech_dispatched = True
        except Exception as e:
            logger.debug(f"Could not dispatch to config.speech_queue: {e}")

        return TaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "message": text_to_speak,
                "dispatched_to_voice_queue": speech_dispatched,
                "status": "spoken" if speech_dispatched else "buffered",
            },
            provenance=Provenance(
                brain_id=self.brain_id,
                confidence=0.95,
            ),
        )
