"""
MIND_GameDev — Voice Output Adapter.
Provides spoken feedback to the user using PowerShell System.Speech,
with non-blocking background queues and feedback-loop suppression.
Does not import mind_core_loop.py or global state.
"""

import queue
import subprocess
import threading
from typing import Optional, Callable


class VoiceOutputAdapter:
    """
    Synthesizes and speaks text responses asynchronously.
    Suppresses acoustic feedback with an internal is_speaking lock.
    """

    def __init__(self, rate: int = 1, volume: int = 100, enabled: bool = True) -> None:
        self.rate = rate
        self.volume = max(0, min(100, volume))
        self.enabled = enabled
        self._speech_queue: queue.Queue[str] = queue.Queue()
        self.is_speaking = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        if self.enabled:
            self._start_worker()

    def _start_worker(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_thread = threading.Thread(target=self._speech_loop, daemon=True, name="GameDev_VoiceOut")
        self._worker_thread.start()

    def speak(self, text: str, block: bool = False) -> None:
        """Enqueues text for spoken audio delivery via Central Voice Authority."""
        if not text or not text.strip():
            return

        clean_text = text.strip()
        if not self.enabled:
            print(f"[MIND Voice Output (Muted)]: {clean_text}")
            return

        print(f"[MIND Voice Output]: {clean_text}")
        # Keep spoken audio concise so PowerShell TTS never exceeds its 20s timeout on multi-line markdown
        first_para = clean_text.split("\n\n")[0].replace("**", "").replace("*", "").replace("#", "").strip()
        spoken_text = first_para[:200] if len(first_para) > 200 else first_para
        try:
            from multi_brain.voice.authority import CentralVoiceNotificationAuthority
            CentralVoiceNotificationAuthority.get_instance().speak(spoken_text)
            return
        except Exception:
            pass

        try:
            if block:
                self._speak_powershell(spoken_text)
            else:
                self._speech_queue.put(spoken_text)
        except Exception as e:
            print(f"[MIND Voice Notice]: Voice output could not be delivered: {e}")

    def _speech_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                text = self._speech_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self.is_speaking.set()
                self._speak_powershell(text)
            except Exception as e:
                # Log without crashing
                pass
            finally:
                self.is_speaking.clear()
                self._speech_queue.task_done()

    def _speak_powershell(self, text: str) -> None:
        """Executes native Windows PowerShell speech synthesis."""
        # Sanitize text against PowerShell injection
        sanitized = (
            text.replace("'", " ")
            .replace('"', " ")
            .replace("`", " ")
            .replace("$", " ")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace(";", " ")
        )
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
            subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except Exception:
            pass

    def stop(self) -> None:
        """Flushes remaining speech items and signals thread termination."""
        self._shutdown_event.set()
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
            except Exception:
                break
        self.is_speaking.clear()
