"""Local Ollama Inference Provider Adapter."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
import requests

from multi_brain.providers.base_provider import BaseProviderAdapter

logger = logging.getLogger("mind.multi_brain.providers.ollama")


class OllamaProviderAdapter(BaseProviderAdapter):
    """Integrates local Ollama daemon for local-first LLM inference."""

    def __init__(
        self,
        provider_id: str = "ollama_local",
        name: str = "Ollama Local Engine",
        base_url: str = "http://localhost:11434",
        default_model: str = "qwen2.5-coder:7b",
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            name=name,
            execution_mode="local",
            supported_modalities=["text", "code"],
            is_cloud=False,
        )
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    def check_health(self) -> Dict[str, Any]:
        """Checks if local Ollama daemon is reachable and lists installed models."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", [])]
                return {
                    "status": "healthy",
                    "daemon_online": True,
                    "models_count": len(models),
                    "installed_models": models,
                }
            return {"status": "degraded", "daemon_online": True, "http_status": resp.status_code}
        except Exception as e:
            return {"status": "unavailable", "daemon_online": False, "error": str(e)}

    def prepare_input(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        prompt = task_input.get("prompt", "")
        model = task_input.get("model") or self.default_model
        system = task_input.get("system_prompt", "You are MIND, a helpful AI assistant.")
        temperature = float(task_input.get("temperature", 0.7))
        return {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": temperature},
        }

    def execute(self, prepared_input: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=prepared_input,
                timeout=self.timeout_seconds,
            )
            if resp.status_code == 200:
                data = resp.json()
                output_text = data.get("response", "")
                return {
                    "output": output_text,
                    "model": prepared_input.get("model"),
                    "duration_seconds": time.time() - start,
                    "total_duration_ns": data.get("total_duration"),
                    "status": "success",
                }
            raise RuntimeError(f"Ollama returned HTTP status {resp.status_code}: {resp.text}")
        except Exception as e:
            raise RuntimeError(self.normalize_error(e))
