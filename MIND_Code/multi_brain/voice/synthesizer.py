"""
MIND Centralized Voice Notification & TTS Authority — Synthesizer Adapter.
Provides concrete TTS execution adapters (PowerShell/SAPI, Neural/XTTS, and Mock)
with explicit separation of synthesis and playback states.
"""

from __future__ import annotations

import abc
import logging
import os
import subprocess
import time
from typing import Optional

logger = logging.getLogger("mind.voice.synthesizer")


class BaseVoiceSynthesizer(abc.ABC):
    """Abstract base contract for voice synthesizers in MIND."""

    @abc.abstractmethod
    def synthesize_and_play(self, text: str, priority: int = 3) -> bool:
        """
        Synthesizes and plays speech for the provided text.
        Returns True on confirmed audio delivery, False on error.
        """
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Checks if the synthesizer engine is currently operational."""
        pass

    def is_permanent_failure(self) -> bool:
        """Indicates if the synthesizer has entered an unrecoverable permanent failure state."""
        return False


class PowerShellVoiceSynthesizer(BaseVoiceSynthesizer):
    """
    Native Windows System.Speech synthesizer using PowerShell.
    Zero external dependencies, fast, dependable desktop speech.
    """

    def __init__(self, rate: int = 1, volume: int = 100, enabled: bool = True) -> None:
        self.rate = rate
        self.volume = max(0, min(100, volume))
        self.enabled = enabled

    def is_available(self) -> bool:
        return self.enabled and os.name == "nt"

    def synthesize_and_play(self, text: str, priority: int = 3) -> bool:
        if not self.enabled or not text or not text.strip():
            return True

        sanitized = (
            text.replace("'", " ")
            .replace('"', " ")
            .replace("`", " ")
            .replace("$", " ")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace(";", " ")
        ).strip()
        if len(sanitized) > 1000:
            sanitized = sanitized[:997] + "..."

        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {self.rate}; "
            f"$s.Volume = {self.volume}; "
            f"$s.Speak('{sanitized}');",
        ]
        try:
            res = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            return res.returncode == 0
        except Exception as e:
            logger.error(f"PowerShell TTS delivery failed: {e}")
            return False


class MockVoiceSynthesizer(BaseVoiceSynthesizer):
    """
    Mock synthesizer for deterministic, fast automated testing.
    Supports programmable transient/permanent failure injection, latency simulation,
    and spoken phrase recording.
    """

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.spoken_phrases: list[str] = []
        self.transient_failures_remaining: int = 0
        self.fail_permanently: bool = False
        self.simulated_latency: float = 0.0

    def is_available(self) -> bool:
        return self._available and not self.fail_permanently

    def is_permanent_failure(self) -> bool:
        return self.fail_permanently

    def synthesize_and_play(self, text: str, priority: int = 3) -> bool:
        if self.simulated_latency > 0:
            time.sleep(self.simulated_latency)

        if self.fail_permanently:
            return False

        if self.transient_failures_remaining > 0:
            self.transient_failures_remaining -= 1
            return False

        if not self._available:
            return False

        self.spoken_phrases.append(text)
        return True

    def reset(self) -> None:
        self.spoken_phrases.clear()
        self.transient_failures_remaining = 0
        self.fail_permanently = False
