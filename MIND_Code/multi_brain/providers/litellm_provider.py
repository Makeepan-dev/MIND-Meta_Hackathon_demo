"""Cloud Inference Provider Adapter using LiteLLM."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from multi_brain.providers.base_provider import BaseProviderAdapter

logger = logging.getLogger("mind.multi_brain.providers.litellm")


class LiteLLMProviderAdapter(BaseProviderAdapter):
    """Integrates remote AI models via LiteLLM with strict credential isolation."""

    def __init__(
        self,
        provider_id: str,
        name: str,
        default_model: str,
        env_key_name: str,
        api_base: Optional[str] = None,
        supported_modalities: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            name=name,
            execution_mode="cloud",
            supported_modalities=supported_modalities or ["text"],
            is_cloud=True,
        )
        self.default_model = default_model
        self.env_key_name = env_key_name
        self.api_base = api_base

    def check_health(self) -> Dict[str, Any]:
        """Validates API key presence in environment without printing value."""
        val = os.getenv(self.env_key_name)
        if val and val.strip():
            return {
                "status": "healthy",
                "configured": True,
                "key_env_var": self.env_key_name,
                "model": self.default_model,
            }
        return {
            "status": "unconfigured",
            "configured": False,
            "message": f"Environment variable '{self.env_key_name}' is not set or empty.",
        }

    def prepare_input(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        prompt = task_input.get("prompt", "")
        system = task_input.get("system_prompt")
        model = task_input.get("model") or self.default_model
        temperature = float(task_input.get("temperature", 0.7))

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "api_base": self.api_base,
            "api_key": os.getenv(self.env_key_name),
            "timeout": float(task_input.get("timeout", 15.0)),
        }

    def execute(self, prepared_input: Dict[str, Any]) -> Dict[str, Any]:
        api_key = prepared_input.get("api_key")
        if not api_key:
            raise RuntimeError(
                f"Missing credentials for {self.name}. "
                f"Configure '{self.env_key_name}' in your .env file."
            )

        start = time.time()
        try:
            from litellm import completion

            resp = completion(
                model=prepared_input["model"],
                messages=prepared_input["messages"],
                api_key=api_key,
                api_base=prepared_input.get("api_base"),
                temperature=prepared_input.get("temperature", 0.7),
                timeout=prepared_input.get("timeout", 15.0),
            )
            text_out = resp.choices[0].message.content or ""
            return {
                "output": text_out,
                "model": prepared_input["model"],
                "duration_seconds": time.time() - start,
                "status": "success",
            }
        except Exception as e:
            raise RuntimeError(self.normalize_error(e))
