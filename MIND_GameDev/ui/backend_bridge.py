"""
MIND Universal Studio — Meta Hackathon Edition
Backend Bridge & Background Worker Threads.

Coordinates:
- Conversational Brain (`MindBrain` or `GameDevOrchestrator`)
- Development Workflows (`GameDevOrchestrator`, `WebsiteWorkflow`, `SafeWorkspaceManager`)
- Dynamic Provider Discovery (Ollama local, Groq, OpenRouter, SiliconFlow, Gemini, Cerebras)
- Asynchronous execution threads (QThread) to ensure non-blocking 60 FPS GUI
- Spoken audio delivery via `VoiceOutputAdapter`
- Non-leaking credential masking
"""

from __future__ import annotations

import os
import sys
import time
import json
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

# Ensure project paths are resolvable
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "MIND_Code") not in sys.path:
    sys.path.insert(0, str(ROOT / "MIND_Code"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ..config import GameDevConfig, redact_secret
from ..adapters.coding_adapter import is_free_model
from ..orchestrator import GameDevOrchestrator
from ..adapters.voice_output import VoiceOutputAdapter
from ..tools.workspace_files import SafeWorkspaceManager

logger = logging.getLogger("mind.ui.bridge")


class CancellationToken:
    """Lightweight cooperative cancellation token."""
    def __init__(self) -> None:
        self.is_cancelled = False
        self.reason = ""

    def cancel(self, reason: str = "Execution cancelled by user.") -> None:
        self.is_cancelled = True
        self.reason = reason


class AIWorker(QThread):
    """Background worker thread for general-purpose multi-brain execution."""
    response_ready = pyqtSignal(str, str)        # (response_text, provider_model)
    task_progress = pyqtSignal(str, float)       # (status_message, progress_pct)
    task_failed = pyqtSignal(str)               # (error_message)
    workflow_progress = pyqtSignal(dict)        # (WorkflowProgress dict)
    workflow_completed = pyqtSignal(dict)       # (workflow result dict with artifacts, verification)

    def __init__(self, prompt: str, brain_type: str = "AUTO", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.prompt = prompt
        self.brain_type = brain_type.strip().upper()
        self.cancellation_token = CancellationToken()

    def cancel(self, reason: str = "Execution cancelled by user.") -> None:
        """Cooperatively requests cancellation of the active task."""
        self.cancellation_token.cancel(reason)

    def run(self) -> None:
        self.task_progress.emit("Routing query through neural cortex...", 0.15)
        start_time = time.time()

        try:
            # Check if prompt is a development, design, revision, or project operation
            cmd_lower = self.prompt.strip().lower()
            is_dev_cmd = any(cmd_lower.startswith(w) for w in [
                "create", "build", "generate", "make", "design", "develop",
                "revise", "change", "modify", "verify", "run", "serve",
                "list", "read", "update", "delete", "plan", "approve", "reject", "cancel",
                "add", "include", "highlight", "use", "switch", "replace", "remove", "make it",
            ]) or any(p in cmd_lower for p in [
                "approve design", "approve plan", "confirm design", "proceed with implementation",
                "design looks good", "lgtm", "looks good to build", "reject design",
            ])

            has_active_orch_context = False
            clean_brain_init = self.brain_type.split()[0].upper() if self.brain_type else "AUTO"
            if not is_dev_cmd and clean_brain_init in ("AUTO", "DEV", "STUDIO", "ORCHESTRATOR", "GAMEDEV"):
                if cmd_lower not in ("hello", "hello mind", "hi", "hi mind"):
                    try:
                        from ..tools.session_memory import SessionMemory
                        from ..tools.instruction_parser import InstructionParser
                        mem = SessionMemory()
                        if mem.get_pending_clarification() is not None:
                            has_active_orch_context = True
                        elif mem.get_pending_design() is not None and InstructionParser._is_pending_design_revision_request(self.prompt, cmd_lower):
                            has_active_orch_context = True
                    except Exception:
                        pass

            if is_dev_cmd or has_active_orch_context or self.brain_type in ("DEV", "STUDIO", "ORCHESTRATOR", "GAMEDEV"):
                self.task_progress.emit("Orchestrating closed-loop development and independent verification...", 0.3)
                orch = GameDevOrchestrator()

                def _on_orch_progress(data: Any, pct: float = 0.5) -> None:
                    if isinstance(data, dict):
                        self.workflow_progress.emit(data)
                        msg = data.get("message", "Processing stage...")
                        p_val = data.get("progress", pct)
                        self.task_progress.emit(msg, p_val)
                    else:
                        self.task_progress.emit(str(data), pct)

                res = orch.execute_command(
                    self.prompt,
                    progress_callback=_on_orch_progress,
                    cancellation_token=self.cancellation_token,
                )
                elapsed = round(time.time() - start_time, 2)
                self.task_progress.emit(f"Completed in {elapsed}s", 1.0)
                self.workflow_completed.emit(res)
                if res.get("status") == "CLARIFY":
                    return
                resp_text = res.get("message") or f"Task processed with status {res.get('status')}."
                if res.get("provider") == "stitch":
                    provider_tag = "MIND // GOOGLE STITCH DESIGN"
                else:
                    provider_tag = "MIND // CLOSED-LOOP ORCHESTRATOR"
                self.response_ready.emit(resp_text, provider_tag)
                return

            # Non-development conversational queries: try MultiBrainAdapter if present, else native CodingAdapter
            try:
                from multi_brain.adapter import MultiBrainAdapter
                adapter = MultiBrainAdapter.get_instance()

                # Manual Brain Selection
                clean_brain = self.brain_type.split()[0].upper()
                if clean_brain not in ("AUTO", "AUTO (MULTI-BRAIN ROUTER)"):
                    self.task_progress.emit(f"Synthesizing with specialized brain '{clean_brain}'...", 0.5)

                    # Try direct MindBrain query if available for this specific brain
                    try:
                        from mind_brain import MindBrain
                        mb = MindBrain()
                        if clean_brain in getattr(mb, "brains", {}) or clean_brain == "THEORIST":
                            try:
                                resp_text = mb.query_specific_brain(clean_brain, self.prompt)
                                elapsed = round(time.time() - start_time, 2)
                                self.task_progress.emit(f"Response completed in {elapsed}s", 1.0)
                                self.response_ready.emit(resp_text, f"MIND // {clean_brain}")
                                return
                            except Exception as direct_err:
                                self.task_failed.emit(f"Brain '{clean_brain}' failed: {direct_err}")
                                return
                    except (ImportError, Exception):
                        pass

                    result = adapter.execute_single_brain(clean_brain, self.prompt)
                    if not result.is_success:
                        self.task_failed.emit(result.error or f"Brain '{clean_brain}' failed.")
                        return

                    out = result.output or {}
                    resp_text = out.get("response") or out.get("text") or (out.get("plan_text") if isinstance(out, dict) and "plan_text" in out else str(out))
                    model_tag = out.get("model_tag") or f"MIND // {clean_brain}"
                    elapsed = round(time.time() - start_time, 2)
                    self.task_progress.emit(f"Response completed in {elapsed}s", 1.0)
                    self.response_ready.emit(resp_text, model_tag)
                    return

                # AUTO Mode
                def _on_progress(prog: Any) -> None:
                    if hasattr(prog, "message") and hasattr(prog, "progress_pct"):
                        self.task_progress.emit(prog.message, prog.progress_pct)
                    if hasattr(prog, "to_dict"):
                        self.workflow_progress.emit(prog.to_dict())

                res = adapter.process_detailed(
                    self.prompt,
                    progress_callback=_on_progress,
                    cancellation_token=self.cancellation_token,
                )

                elapsed = round(time.time() - start_time, 2)
                self.task_progress.emit(f"Completed in {elapsed}s", 1.0)

                wf_res = res.get("workflow_result")
                if wf_res or res.get("design_state") or res.get("prototype") or res.get("artifacts"):
                    self.workflow_completed.emit(res)

                resp_text = res.get("response", "Task processed.")
                classif = res.get("classification", "CORTEX")
                self.response_ready.emit(resp_text, f"MIND // {classif.upper()}")
                return

            except (ImportError, Exception) as mb_err:
                clean_brain = self.brain_type.split()[0].upper()
                if clean_brain not in ("AUTO", "AUTO (MULTI-BRAIN ROUTER)", "DEV", "STUDIO", "ORCHESTRATOR"):
                    self.task_failed.emit(f"Brain '{clean_brain}' failed: {mb_err}")
                    return
                # Native Fallback for conversational queries
                logger.info(f"Using native reasoning adapter: {mb_err}")
                from ..adapters.coding_adapter import CodingAdapter
                cadapter = CodingAdapter()
                res = cadapter.generate(
                    prompt=self.prompt,
                    system_prompt="You are MIND AI Developer Assistant. Provide a clear, helpful response.",
                )
                elapsed = round(time.time() - start_time, 2)
                self.task_progress.emit(f"Completed in {elapsed}s", 1.0)
                code_resp = res.get("code") or "Response generated."
                self.response_ready.emit(code_resp, f"MIND // {res.get('provider', 'NATIVE')}")

        except Exception as e:
            logger.error(f"AIWorker error: {e}", exc_info=True)
            self.task_failed.emit(str(e))


class DevStudioWorker(QThread):
    """Background worker thread for autonomous software development tasks."""
    step_update = pyqtSignal(str, float)   # (step_description, progress_float 0.0-1.0)
    build_complete = pyqtSignal(dict)      # (execution_result_dict)
    build_failed = pyqtSignal(str)         # (error_message)

    def __init__(
        self,
        command: str,
        dest_dir: Optional[str] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.command = command
        self.dest_dir = dest_dir

    def run(self) -> None:
        self.step_update.emit("Parsing development specification and domain...", 0.15)
        
        try:
            orch = GameDevOrchestrator()
            
            # Execute command through orchestrator with live stage callback
            res = orch.execute_command(
                self.command,
                progress_callback=self.step_update.emit,
            )

            if not res.get("success", True) and res.get("status") in ("VALIDATION_FAILED", "BLENDER_EXECUTION_FAILED", "GLB_VERIFICATION_FAILED", "FAILED"):
                err_msg = res.get("error") or res.get("message") or "Pipeline execution failed."
                self.build_failed.emit(err_msg)
                return
            
            self.step_update.emit("Completed.", 1.0)
            self.build_complete.emit(res)
            
        except Exception as e:
            logger.error(f"DevStudioWorker error: {e}", exc_info=True)
            self.build_failed.emit(str(e))


class BackendBridge(QObject):
    """
    Central operational hub for the desktop application.
    Interacts safely with the backend without freezing the GUI.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = GameDevConfig.load()
        self.voice = VoiceOutputAdapter(enabled=self.config.voice_enabled)
        self.active_worker: Optional[QThread] = None
        self.active_workers: List[QThread] = []

    def track_worker(self, worker: QThread) -> None:
        """Safely tracks an active background worker thread, cleaning it up upon completion."""
        self.active_worker = worker
        self.active_workers.append(worker)
        def _cleanup():
            if worker in self.active_workers:
                self.active_workers.remove(worker)
        worker.finished.connect(_cleanup)

    def check_ollama(self) -> Dict[str, Any]:
        """Queries local Ollama instance for installed models."""
        url = f"{self.config.ollama_base_url}/api/tags"
        try:
            r = requests.get(url, timeout=1.5)
            if r.status_code == 200:
                models = [m.get("name", "") for m in r.json().get("models", [])]
                return {"online": True, "models": models, "count": len(models)}
            return {"online": False, "models": [], "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"online": False, "models": [], "error": "Offline or unreachable"}

    def check_remote_cortex(self) -> Dict[str, Any]:
        """Checks if local FastAPI server on port 8000 is running."""
        try:
            r = requests.get("http://localhost:8000/status", timeout=1.0)
            if r.status_code == 200:
                return {"online": True, "data": r.json()}
            return {"online": False, "error": f"HTTP {r.status_code}"}
        except Exception:
            return {"online": False, "error": "Cortex service on :8000 not detected"}

    def get_configured_providers(self) -> List[Dict[str, Any]]:
        """Returns detected Meta AI Model API, Google Stitch, and local Ollama providers with masked credentials."""
        providers = []

        meta_key = (
            os.getenv("MODEL_API_KEY", "")
            or os.getenv("META_API_KEY", "")
            or os.getenv("LLAMA_API_KEY", "")
        )
        meta_configured = bool(meta_key and not meta_key.startswith("your_"))

        # 1. Meta AI Flagship Coding & Engineering (muse-spark-1.3)
        providers.append({
            "name": "Meta AI (Coding & Engineering)",
            "model": "muse-spark-1.3",
            "tier": "Meta Model API (1M Context Flagship)",
            "configured": meta_configured,
            "key_masked": redact_secret(meta_key),
            "status": "READY" if meta_configured else "NO_KEY",
        })

        # 2. Meta AI Frontier Reasoning & Synthesis (muse-wonder-1.0)
        providers.append({
            "name": "Meta AI (Frontier Reasoning & Creative)",
            "model": "muse-wonder-1.0",
            "tier": "Meta Model API (Frontier Reasoning)",
            "configured": meta_configured,
            "key_masked": redact_secret(meta_key),
            "status": "READY" if meta_configured else "NO_KEY",
        })

        # 3. Meta AI Analysis, Research & Security (muse-spark-1.2)
        providers.append({
            "name": "Meta AI (Analysis, Research & Verification)",
            "model": "muse-spark-1.2",
            "tier": "Meta Model API (Balanced Analytical)",
            "configured": meta_configured,
            "key_masked": redact_secret(meta_key),
            "status": "READY" if meta_configured else "NO_KEY",
        })

        # 4. Meta AI Fast Routing & Orchestration (muse-spark-1.1)
        providers.append({
            "name": "Meta AI (Fast Orchestrator & Router)",
            "model": "muse-spark-1.1",
            "tier": "Meta Model API (Low-Latency Routing)",
            "configured": meta_configured,
            "key_masked": redact_secret(meta_key),
            "status": "READY" if meta_configured else "NO_KEY",
        })

        # 5. Google Stitch (Dedicated UI/UX & Website Design Exception)
        stitch_key = os.getenv("STITCH_API_KEY", "")
        stitch_configured = bool(stitch_key and not stitch_key.startswith("your_"))
        providers.append({
            "name": "Google Stitch (Dedicated UI/UX Design)",
            "model": "stitch-mcp-v1",
            "tier": "Dedicated Design MCP (https://stitch.googleapis.com/mcp)",
            "configured": stitch_configured,
            "key_masked": redact_secret(stitch_key),
            "status": "READY" if stitch_configured else "NO_KEY",
        })

        # 6. Local Ollama
        ollama_status = self.check_ollama()
        providers.append({
            "name": "Ollama Local",
            "model": self.config.ollama_coding_model,
            "tier": "Local (On-Device GPU/CPU Fallback)",
            "configured": True,
            "key_masked": "N/A (Local Daemon)",
            "status": "ONLINE" if ollama_status["online"] else "OFFLINE",
            "local_models": ollama_status.get("models", []),
        })

        return providers

    def speak(self, text: str) -> None:
        """Asynchronously vocalizes text using Windows System.Speech."""
        if self.voice and self.config.voice_enabled:
            self.voice.speak(text)
