"""
MIND_GameDev — Voice Input Adapter.
Provides speech-to-text intake for hands-free game development commands,
with automatic graceful fallback to text input when mic or neural models are offline.
"""

import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional, Callable


class VoiceInputAdapter:
    """
    Handles speech input and transcription.
    Fails over gracefully to console text input if audio devices or Whisper are unavailable.
    """

    def __init__(self, model_size: str = "base", device: str = "cpu", voice_out_lock: Optional[threading.Event] = None) -> None:
        self.model_size = model_size
        self.device = device
        self.voice_out_lock = voice_out_lock
        self._whisper_model = None
        self._has_whisper: Optional[bool] = None
        self._has_sounddevice: Optional[bool] = None

    def _check_sounddevice(self) -> bool:
        if self._has_sounddevice is not None:
            return self._has_sounddevice
        try:
            import sounddevice as sd
            # Verify input device exists
            devices = sd.query_devices()
            has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
            self._has_sounddevice = has_input
        except Exception:
            self._has_sounddevice = False
        return self._has_sounddevice

    def _get_whisper_model(self):
        if self._has_whisper is False:
            return None
        if self._whisper_model is not None:
            return self._whisper_model

        try:
            from faster_whisper import WhisperModel
            from ..config import REPO_ROOT
            cache_dir = REPO_ROOT / "models" / "whisper"
            if cache_dir.exists():
                self._whisper_model = WhisperModel(self.model_size, device=self.device, compute_type="int8", download_root=str(cache_dir))
            else:
                self._whisper_model = WhisperModel(self.model_size, device=self.device, compute_type="int8")
            self._has_whisper = True
            return self._whisper_model
        except Exception as e:
            self._has_whisper = False
            return None

    def listen_or_input(self, prompt: str = "GameDev Voice/Text Command: ", timeout_secs: float = 6.0) -> str:
        """
        Listens for audio command if mic is active; otherwise prompts via console.
        Blocks while voice output is active to prevent acoustic feedback loop.
        """
        if self.voice_out_lock and self.voice_out_lock.is_set():
            # Wait for speech output to conclude
            self.voice_out_lock.wait(timeout=5.0)

        # Attempt mic recording if sounddevice and whisper are present
        if self._check_sounddevice():
            try:
                text = self._record_and_transcribe(duration=timeout_secs)
                if text and text.strip():
                    print(f"\n[Transcribed Voice]: {text.strip()}")
                    return text.strip()
            except Exception:
                pass

        # Fallback to standard input
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    def _record_and_transcribe(self, duration: float = 5.0, sample_rate: int = 16000) -> str:
        """Records from microphone and transcribes using faster-whisper."""
        import sounddevice as sd
        import numpy as np
        import soundfile as sf

        model = self._get_whisper_model()
        if not model:
            return ""

        print(f"[Listening for {int(duration)}s... speak command]")
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()

        # Check for non-silence
        max_amplitude = float(np.max(np.abs(recording)))
        if max_amplitude < 0.03:
            # Below silence threshold
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name

        try:
            sf.write(wav_path, recording, sample_rate)
            segments, _ = model.transcribe(wav_path, beam_size=1)
            transcribed = " ".join([seg.text for seg in segments]).strip()
            return transcribed
        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass

    def transcribe_file(self, audio_path: Path) -> str:
        """Transcribes an existing audio file."""
        model = self._get_whisper_model()
        if not model or not Path(audio_path).exists():
            return ""
        try:
            segments, _ = model.transcribe(str(audio_path))
            return " ".join([seg.text for seg in segments]).strip()
        except Exception:
            return ""
