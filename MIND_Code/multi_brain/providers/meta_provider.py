"""
Centralized Meta AI Model API Configuration, Client, Usage Tracker, and Provider Adapter.

Provides the authoritative Meta Model API integration (`https://api.meta.ai/v1`) for MIND's
agent ecosystem using Meta Global AI Developer Hackathon credits, while explicitly preserving
Google Stitch (`https://stitch.googleapis.com/mcp`) as the dedicated UI/UX design provider.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from multi_brain.providers.base_provider import BaseProviderAdapter

logger = logging.getLogger("mind.multi_brain.providers.meta")

# Load .env safely if environment variables are not yet populated
try:
    from dotenv import load_dotenv
    _root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
except Exception:
    pass


# ==============================================================================
# 1. CENTRALIZED META MODEL CATALOG & CAPABILITY ROUTING
# ==============================================================================

DEFAULT_META_API_BASE = "https://api.meta.ai/v1"

# Official Meta Model API identifiers verified via GET https://api.meta.ai/v1/models
META_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "muse-spark-1.3": {
        "model_id": "muse-spark-1.3",
        "registry_id": "meta-muse-spark-1.3",
        "tier": "flagship_coding_and_reasoning",
        "context_window": 1000000,
        "modalities": ["text", "code", "vision"],
        "default_max_tokens": 4096,
        "min_max_tokens": 512,
        "default_temperature": 0.2,
        "description": "Meta's flagship 1M-context reasoning, software engineering, debugging, and tool-use model.",
    },
    "muse-wonder-1.0": {
        "model_id": "muse-wonder-1.0",
        "registry_id": "meta-muse-wonder-1.0",
        "tier": "frontier_reasoning_and_synthesis",
        "context_window": 256000,
        "modalities": ["text", "code"],
        "default_max_tokens": 2048,
        "min_max_tokens": 512,
        "default_temperature": 0.5,
        "description": "Meta's frontier deep reasoning, complex architecture, problem decomposition, and creative synthesis model.",
    },
    "muse-spark-1.2": {
        "model_id": "muse-spark-1.2",
        "registry_id": "meta-muse-spark-1.2",
        "tier": "balanced_analysis_and_verification",
        "context_window": 256000,
        "modalities": ["text", "code"],
        "default_max_tokens": 2048,
        "min_max_tokens": 512,
        "default_temperature": 0.3,
        "description": "Meta's balanced analytical model for quantitative analysis, research synthesis, security review, and verification critique.",
    },
    "muse-spark-1.1": {
        "model_id": "muse-spark-1.1",
        "registry_id": "meta-muse-spark-1.1",
        "tier": "fast_routing_and_coordination",
        "context_window": 128000,
        "modalities": ["text", "code"],
        "default_max_tokens": 1024,
        "min_max_tokens": 512,
        "default_temperature": 0.2,
        "description": "Meta's fast, low-latency, credit-efficient model for intent classification, routing, and conversational coordination.",
    },
    "muse-spark-1.3-contributor": {
        "model_id": "muse-spark-1.3-contributor",
        "registry_id": "meta-muse-spark-1.3-contributor",
        "tier": "contributor_coding",
        "context_window": 1000000,
        "modalities": ["text", "code"],
        "default_max_tokens": 2048,
        "min_max_tokens": 512,
        "default_temperature": 0.2,
        "description": "Meta contributor-tier coding and reasoning model.",
    },
    "muse-spark-1.2-contributor": {
        "model_id": "muse-spark-1.2-contributor",
        "registry_id": "meta-muse-spark-1.2-contributor",
        "tier": "contributor_analysis",
        "context_window": 256000,
        "modalities": ["text", "code"],
        "default_max_tokens": 1536,
        "min_max_tokens": 512,
        "default_temperature": 0.3,
        "description": "Meta contributor-tier analysis model.",
    },
    "muse-image-1.0": {
        "model_id": "muse-image-1.0",
        "registry_id": "meta-muse-image-1.0",
        "tier": "multimodal_image",
        "context_window": 32000,
        "modalities": ["image"],
        "default_max_tokens": 1024,
        "min_max_tokens": 256,
        "default_temperature": 0.7,
        "description": "Meta multimodal image model (Responses API).",
    },
    "muse-voice-transcribe-1.0": {
        "model_id": "muse-voice-transcribe-1.0",
        "registry_id": "meta-muse-voice-transcribe-1.0",
        "tier": "speech_to_text",
        "context_window": 32000,
        "modalities": ["audio"],
        "default_max_tokens": 1024,
        "min_max_tokens": 256,
        "default_temperature": 0.0,
        "description": "Meta voice transcription model.",
    },
    "sam-3.1": {
        "model_id": "sam-3.1",
        "registry_id": "meta-sam-3.1",
        "tier": "vision_segmentation",
        "context_window": 32000,
        "modalities": ["vision"],
        "default_max_tokens": 1024,
        "min_max_tokens": 256,
        "default_temperature": 0.0,
        "description": "Meta Segment Anything Model 3.1.",
    },
}

# Capability-based mapping of every MIND agent/brain to its optimal Meta model
AGENT_META_MODEL_MAPPING: Dict[str, Dict[str, Any]] = {
    # 1. Orchestration & Routing
    "orchestrator_brain": {
        "primary_model": "muse-spark-1.1",
        "complex_model": "muse-wonder-1.0",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.2,
        "max_tokens": 1024,
        "rationale": "Fast, credit-efficient intent classification and routing with muse-spark-1.1; escalates to muse-wonder-1.0 for complex multi-step planning.",
    },
    "MANAGER": {
        "primary_model": "muse-spark-1.1",
        "complex_model": "muse-wonder-1.0",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.2,
        "max_tokens": 1536,
        "rationale": "Executive task decomposition, delegation, and synthesis.",
    },
    "SLM_GATE": {
        "primary_model": "muse-spark-1.1",
        "complex_model": "muse-spark-1.1",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.1,
        "max_tokens": 768,
        "rationale": "Front-door request classification requires minimal latency and credit usage.",
    },
    "CEREBRAS": {
        "primary_model": "muse-spark-1.1",
        "complex_model": "muse-spark-1.2",
        "fallback_model": "muse-spark-1.3",
        "temperature": 0.2,
        "max_tokens": 1024,
        "rationale": "High-speed low-latency responses.",
    },
    # 2. Software Engineering, Code Generation & Debugging
    "coding_brain": {
        "primary_model": "muse-spark-1.3",
        "complex_model": "muse-spark-1.3",
        "lightweight_model": "muse-spark-1.1",
        "fallback_model": "muse-wonder-1.0",
        "temperature": 0.2,
        "max_tokens": 4096,
        "rationale": "Flagship 1M-context coding model for full-stack generation, debugging, AST-valid Python/Blender scripts, and repair.",
    },
    "CODER": {
        "primary_model": "muse-spark-1.3",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-wonder-1.0",
        "temperature": 0.2,
        "max_tokens": 4096,
        "rationale": "Software engineering, debugging, refactoring, and code generation.",
    },
    "CodingAgent": {
        "primary_model": "muse-spark-1.3",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-wonder-1.0",
        "temperature": 0.2,
        "max_tokens": 4096,
        "rationale": "GameDev & website code generation, repair, and Blender bpy script synthesis.",
    },
    # 3. Deep Reasoning, Planning, Logic & Mathematics
    "reasoning_brain": {
        "primary_model": "muse-wonder-1.0",
        "complex_model": "muse-wonder-1.0",
        "fallback_model": "muse-spark-1.3",
        "temperature": 0.4,
        "max_tokens": 2048,
        "rationale": "Frontier reasoning model for problem decomposition, formal logic, mathematical proofs, and trade-off analysis.",
    },
    "THEORIST": {
        "primary_model": "muse-wonder-1.0",
        "complex_model": "muse-wonder-1.0",
        "fallback_model": "muse-spark-1.3",
        "temperature": 0.4,
        "max_tokens": 2048,
        "rationale": "Deep multi-step chain-of-thought reasoning and hypothesis generation.",
    },
    "DEEPSEEK": {
        "primary_model": "muse-wonder-1.0",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.3,
        "max_tokens": 2048,
        "rationale": "Complex algorithmic reasoning, ML architecture, and mathematics.",
    },
    "GLM": {
        "primary_model": "muse-wonder-1.0",
        "complex_model": "muse-spark-1.2",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.5,
        "max_tokens": 1536,
        "rationale": "Dialectical synthesis and conflict resolution.",
    },
    # 4. Data Analysis, Research & Investigation
    "analysis_brain": {
        "primary_model": "muse-spark-1.2",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.2,
        "max_tokens": 2048,
        "rationale": "Balanced analytical model for structured data evaluation and technical investigation.",
    },
    "ANALYST": {
        "primary_model": "muse-spark-1.2",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-wonder-1.0",
        "temperature": 0.2,
        "max_tokens": 2048,
        "rationale": "Quantitative/qualitative data analysis, pattern detection, and evidence evaluation.",
    },
    "OSS_LLM": {
        "primary_model": "muse-spark-1.2",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.3,
        "max_tokens": 1536,
        "rationale": "Analytical reasoning and general investigation.",
    },
    "research_brain": {
        "primary_model": "muse-spark-1.2",
        "complex_model": "muse-wonder-1.0",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.3,
        "max_tokens": 2048,
        "rationale": "Research synthesis, document grounding, and citation analysis.",
    },
    # 5. Creative, Visual & Concept Direction
    "creative_brain": {
        "primary_model": "muse-wonder-1.0",
        "complex_model": "muse-wonder-1.0",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.7,
        "max_tokens": 2048,
        "rationale": "Frontier creative model for visual concepts, narrative synthesis, and art direction.",
    },
    "CREATIVE": {
        "primary_model": "muse-wonder-1.0",
        "complex_model": "muse-wonder-1.0",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.7,
        "max_tokens": 2048,
        "rationale": "Creative content, visual concept direction, and prompt engineering.",
    },
    # 6. Verification, Critique & Security Auditing
    "verification_brain": {
        "primary_model": "muse-spark-1.2",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.1,
        "max_tokens": 1536,
        "rationale": "High-precision critique, consistency checking, and diagnostic verification.",
    },
    "SECURITY": {
        "primary_model": "muse-spark-1.2",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-wonder-1.0",
        "temperature": 0.1,
        "max_tokens": 2048,
        "rationale": "Defensive security auditing, vulnerability analysis, and policy enforcement.",
    },
    # 7. Multimodal, 3D, Audio & Video Coordination
    "threed_brain": {
        "primary_model": "muse-spark-1.3",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.2,
        "max_tokens": 2048,
        "rationale": "3D spatial workflow coordination, geometric breakdown, and Blender bpy script specification.",
    },
    "PromptSynthesizer": {
        "primary_model": "muse-spark-1.1",
        "complex_model": "muse-spark-1.2",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.3,
        "max_tokens": 1024,
        "rationale": "Fast 3D concept prompt expansion.",
    },
    "audio_brain": {
        "primary_model": "muse-spark-1.1",
        "complex_model": "muse-spark-1.2",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.2,
        "max_tokens": 1024,
        "rationale": "Audio workflow coordination alongside Whisper/muse-voice-transcribe-1.0 STT and SAPI5 TTS.",
    },
    "video_brain": {
        "primary_model": "muse-spark-1.1",
        "complex_model": "muse-spark-1.2",
        "fallback_model": "muse-spark-1.1",
        "temperature": 0.3,
        "max_tokens": 1024,
        "rationale": "Video storyboard and workflow coordination.",
    },
    "VISION": {
        "primary_model": "muse-spark-1.3",
        "complex_model": "muse-spark-1.3",
        "fallback_model": "muse-spark-1.2",
        "temperature": 0.2,
        "max_tokens": 2048,
        "rationale": "Visual grounding and multimodal understanding.",
    },
}


def redact_meta_key(secret: Optional[str]) -> str:
    """Safely masks an API key so raw credentials never appear in logs or UI."""
    if not secret or not isinstance(secret, str):
        return "<NOT_SET>"
    clean = secret.strip()
    if not clean:
        return "<NOT_SET>"
    if len(clean) <= 10:
        return "***"
    return f"{clean[:6]}...{clean[-4:]}"


def get_meta_api_key() -> str:
    """
    Retrieves the configured Meta Model API key from environment variables.
    Checks MODEL_API_KEY, META_API_KEY, and LLAMA_API_KEY in priority order.
    """
    for env_name in ("MODEL_API_KEY", "META_API_KEY", "LLAMA_API_KEY"):
        val = os.getenv(env_name, "").strip()
        if val and not val.startswith("your_"):
            return val
    return ""


def get_meta_api_base() -> str:
    """Retrieves the Meta Model API base URL (defaults to https://api.meta.ai/v1)."""
    return os.getenv("META_API_BASE", DEFAULT_META_API_BASE).strip().rstrip("/")


def normalize_meta_model_id(model_id: str) -> str:
    """
    Normalizes registry or prefixed model identifiers (e.g. 'meta-muse-spark-1.3',
    'meta/muse-spark-1.3', 'muse-spark-1.3') to the canonical Meta API model ID ('muse-spark-1.3').
    """
    if not model_id:
        return "muse-spark-1.3"
    clean = model_id.strip()
    if clean.startswith("meta/"):
        clean = clean[len("meta/"):]
    elif clean.startswith("meta-"):
        candidate = clean[len("meta-"):]
        if candidate in META_MODEL_CATALOG:
            clean = candidate
    return clean


# ==============================================================================
# 2. CREDIT & TOKEN USAGE TRACKER
# ==============================================================================

@dataclass
class MetaUsageTracker:
    """Thread-safe tracker for Meta Model API requests, tokens, and hackathon credit usage."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retried_requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    per_model_usage: Dict[str, Dict[str, int]] = field(default_factory=dict)
    per_agent_usage: Dict[str, Dict[str, int]] = field(default_factory=dict)
    recent_calls: List[Dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_call(
        self,
        model: str,
        agent_id: str,
        success: bool,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        total_tokens: int = 0,
        retried: int = 0,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            self.retried_requests += retried
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.reasoning_tokens += reasoning_tokens
            self.total_tokens += total_tokens

            m_stats = self.per_model_usage.setdefault(
                model,
                {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0},
            )
            m_stats["requests"] += 1
            m_stats["prompt_tokens"] += prompt_tokens
            m_stats["completion_tokens"] += completion_tokens
            m_stats["reasoning_tokens"] += reasoning_tokens
            m_stats["total_tokens"] += total_tokens

            if agent_id:
                a_stats = self.per_agent_usage.setdefault(
                    agent_id,
                    {"requests": 0, "total_tokens": 0, "model": model},
                )
                a_stats["requests"] += 1
                a_stats["total_tokens"] += total_tokens
                a_stats["model"] = model

            entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model": model,
                "agent_id": agent_id or "general",
                "success": success,
                "latency_ms": round(latency_ms, 2),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": total_tokens,
            }
            if error:
                entry["error"] = error
            self.recent_calls.append(entry)
            if len(self.recent_calls) > 100:
                self.recent_calls.pop(0)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "provider": "Meta Model API",
                "api_base": get_meta_api_base(),
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "retried_requests": self.retried_requests,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "reasoning_tokens": self.reasoning_tokens,
                "total_tokens": self.total_tokens,
                "per_model_usage": dict(self.per_model_usage),
                "per_agent_usage": dict(self.per_agent_usage),
                "recent_calls": list(self.recent_calls[-20:]),
            }


# Global singleton usage tracker
GLOBAL_META_USAGE = MetaUsageTracker()


# ==============================================================================
# 3. META MODEL API CLIENT
# ==============================================================================

class MetaModelClient:
    """
    Production client for Meta's OpenAI-compatible Model API (`https://api.meta.ai/v1`).

    Features:
    - Capability-based agent-to-model routing (`get_model_for_agent`)
    - Reasoning-token floor protection (`max_tokens >= 512` so chain-of-thought never starves content)
    - Distinct connect and read timeouts (`(10.0, 90.0)`)
    - Rate-limit (`HTTP 429 Retry-After`) and exponential backoff retry on transient 5xx/network errors
    - Automatic model fallback (`muse-spark-1.3` -> `muse-wonder-1.0` -> `muse-spark-1.2` -> `muse-spark-1.1`)
    - Live `/v1/models` availability validation with caching
    - Strict secret redaction
    """

    _instance: Optional["MetaModelClient"] = None
    _cached_remote_models: Optional[Tuple[float, List[str]]] = None

    @classmethod
    def get_instance(cls) -> "MetaModelClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 90.0,
        max_retries: int = 2,
    ) -> None:
        self._explicit_api_key = api_key
        self._explicit_api_base = api_base
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_retries = max_retries
        self.usage = GLOBAL_META_USAGE

    @property
    def api_key(self) -> str:
        if self._explicit_api_key is not None:
            return self._explicit_api_key.strip()
        return get_meta_api_key()

    @property
    def api_base(self) -> str:
        if self._explicit_api_base is not None:
            return self._explicit_api_base.strip().rstrip("/")
        return get_meta_api_base()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 8)

    @staticmethod
    def get_agent_config(agent_id: str, task_complexity: str = "standard") -> Dict[str, Any]:
        """Returns the Meta model configuration for a specific agent/brain and task complexity."""
        cfg = AGENT_META_MODEL_MAPPING.get(agent_id)
        if not cfg:
            # Case-insensitive lookup
            for k, v in AGENT_META_MODEL_MAPPING.items():
                if k.lower() == (agent_id or "").lower():
                    cfg = v
                    break
        if not cfg:
            cfg = AGENT_META_MODEL_MAPPING["orchestrator_brain"]

        if task_complexity == "complex":
            selected_model = cfg.get("complex_model", cfg["primary_model"])
        elif task_complexity == "lightweight":
            selected_model = cfg.get("lightweight_model", cfg["primary_model"])
        else:
            selected_model = cfg["primary_model"]

        model_meta = META_MODEL_CATALOG.get(selected_model, META_MODEL_CATALOG["muse-spark-1.3"])
        return {
            "agent_id": agent_id,
            "model": selected_model,
            "registry_id": model_meta["registry_id"],
            "fallback_model": cfg.get("fallback_model", "muse-spark-1.2"),
            "temperature": cfg.get("temperature", model_meta["default_temperature"]),
            "max_tokens": cfg.get("max_tokens", model_meta["default_max_tokens"]),
            "rationale": cfg.get("rationale", ""),
        }

    def validate_models(self, force_refresh: bool = False, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Queries `GET https://api.meta.ai/v1/models` to verify API key validity and available models.
        Caches results for 60 seconds to conserve quota and latency.
        """
        if not self.is_configured:
            return {
                "valid": False,
                "status": "unconfigured",
                "available_models": [],
                "error": "Meta API key (MODEL_API_KEY / META_API_KEY) is not configured in .env.",
            }

        now = time.time()
        if (
            not force_refresh
            and MetaModelClient._cached_remote_models is not None
            and (now - MetaModelClient._cached_remote_models[0]) < 60.0
        ):
            models = MetaModelClient._cached_remote_models[1]
            return {
                "valid": True,
                "status": "healthy",
                "available_models": models,
                "api_base": self.api_base,
                "key_masked": redact_meta_key(self.api_key),
                "cached": True,
            }

        url = f"{self.api_base}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                payload = resp.json()
                models = [m.get("id", "") for m in payload.get("data", []) if m.get("id")]
                MetaModelClient._cached_remote_models = (now, models)
                return {
                    "valid": True,
                    "status": "healthy",
                    "available_models": models,
                    "api_base": self.api_base,
                    "key_masked": redact_meta_key(self.api_key),
                    "cached": False,
                }
            return {
                "valid": False,
                "status": f"http_{resp.status_code}",
                "available_models": [],
                "error": f"Meta API /models returned HTTP {resp.status_code}",
            }
        except Exception as exc:
            return {
                "valid": False,
                "status": "unreachable",
                "available_models": [],
                "error": self._sanitize_error(exc),
            }

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        agent_id: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        allow_model_fallback: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes a chat completion against `POST https://api.meta.ai/v1/chat/completions`.

        Enforces:
        - Safe reasoning-token floor (`max_tokens >= 512`) so internal chain-of-thought
          tokens never truncate `message.content` to null.
        - Automatic retry with exponential backoff on HTTP 429 / 5xx / transient network errors.
        - Fallback to secondary Meta model if the primary model is unavailable.
        - Full token and credit telemetry tracking.
        """
        if not self.is_configured:
            raise RuntimeError(
                "Meta Model API credentials missing. Set MODEL_API_KEY or META_API_KEY in .env."
            )

        agent_cfg = self.get_agent_config(agent_id or "orchestrator_brain")
        target_model = normalize_meta_model_id(model or agent_cfg["model"])
        model_info = META_MODEL_CATALOG.get(target_model, META_MODEL_CATALOG["muse-spark-1.3"])

        eff_temp = temperature if temperature is not None else agent_cfg["temperature"]
        requested_max = max_tokens if max_tokens is not None else agent_cfg["max_tokens"]
        min_floor = model_info.get("min_max_tokens", 512)
        eff_max_tokens = max(int(requested_max), min_floor)

        read_to = float(timeout) if timeout is not None else self.read_timeout
        candidate_models = [target_model]
        if allow_model_fallback:
            fb_model = normalize_meta_model_id(agent_cfg.get("fallback_model", "muse-spark-1.2"))
            if fb_model not in candidate_models:
                candidate_models.append(fb_model)
            if "muse-spark-1.1" not in candidate_models:
                candidate_models.append("muse-spark-1.1")

        last_error = ""
        total_retries = 0

        for candidate in candidate_models:
            for attempt in range(self.max_retries + 1):
                start_ts = time.time()
                try:
                    result = self._send_single_request(
                        model=candidate,
                        messages=messages,
                        temperature=eff_temp,
                        max_tokens=eff_max_tokens,
                        read_timeout=read_to,
                    )
                    latency_ms = (time.time() - start_ts) * 1000.0
                    usage = result.get("usage", {})
                    p_tok = int(usage.get("prompt_tokens", 0) or 0)
                    c_tok = int(usage.get("completion_tokens", 0) or 0)
                    t_tok = int(usage.get("total_tokens", p_tok + c_tok) or 0)
                    details = usage.get("completion_tokens_details") or {}
                    r_tok = int(details.get("reasoning_tokens", 0) or 0)

                    self.usage.record_call(
                        model=candidate,
                        agent_id=agent_id,
                        success=True,
                        latency_ms=latency_ms,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        reasoning_tokens=r_tok,
                        total_tokens=t_tok,
                        retried=total_retries,
                    )

                    return {
                        "content": result["content"],
                        "model": candidate,
                        "provider": "meta",
                        "agent_id": agent_id,
                        "finish_reason": result.get("finish_reason", "stop"),
                        "latency_ms": round(latency_ms, 2),
                        "usage": {
                            "prompt_tokens": p_tok,
                            "completion_tokens": c_tok,
                            "reasoning_tokens": r_tok,
                            "total_tokens": t_tok,
                        },
                        "fallback_used": candidate != target_model,
                        "primary_model": target_model,
                    }

                except _MetaRateLimitError as rl_err:
                    total_retries += 1
                    last_error = str(rl_err)
                    if attempt < self.max_retries:
                        wait_s = min(rl_err.retry_after or (1.5 * (2 ** attempt)), 10.0)
                        logger.warning(
                            f"Meta API rate limit on {candidate} (attempt {attempt + 1}); waiting {wait_s:.1f}s"
                        )
                        time.sleep(wait_s)
                        continue
                    break

                except _MetaTransientError as tr_err:
                    total_retries += 1
                    last_error = str(tr_err)
                    if attempt < self.max_retries:
                        wait_s = min(1.0 * (2 ** attempt), 6.0)
                        logger.warning(
                            f"Meta API transient error on {candidate} (attempt {attempt + 1}): {last_error}; retrying in {wait_s:.1f}s"
                        )
                        time.sleep(wait_s)
                        continue
                    break

                except Exception as fatal_err:
                    latency_ms = (time.time() - start_ts) * 1000.0
                    last_error = self._sanitize_error(fatal_err)
                    self.usage.record_call(
                        model=candidate,
                        agent_id=agent_id,
                        success=False,
                        latency_ms=latency_ms,
                        retried=total_retries,
                        error=last_error,
                    )
                    break

        raise RuntimeError(f"Meta Model API request failed ({target_model}): {last_error}")

    def _send_single_request(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        read_timeout: float,
    ) -> Dict[str, Any]:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(self.connect_timeout, read_timeout),
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_exc:
            raise _MetaTransientError(self._sanitize_error(net_exc)) from net_exc

        if resp.status_code == 429:
            retry_after = 2.0
            ra_hdr = resp.headers.get("Retry-After")
            if ra_hdr:
                try:
                    retry_after = float(ra_hdr)
                except ValueError:
                    pass
            raise _MetaRateLimitError(f"HTTP 429 rate limit on {model}", retry_after=retry_after)

        if resp.status_code in (500, 502, 503, 504):
            raise _MetaTransientError(f"HTTP {resp.status_code} from Meta API ({model})")

        if resp.status_code != 200:
            err_detail = ""
            try:
                err_json = resp.json()
                err_detail = err_json.get("error", {}).get("message", "") or str(err_json)
            except Exception:
                err_detail = resp.text[:250]
            raise RuntimeError(self._sanitize_error(f"HTTP {resp.status_code}: {err_detail}"))

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Meta API returned empty choices for model '{model}'.")

        msg = choices[0].get("message") or {}
        content = msg.get("content")
        finish_reason = choices[0].get("finish_reason", "stop")

        # If reasoning tokens consumed the budget and content is None, retry once with doubled max_tokens
        if content is None and finish_reason == "length" and max_tokens < 4096:
            payload["max_tokens"] = min(max_tokens * 2, 4096)
            resp2 = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(self.connect_timeout, read_timeout),
            )
            if resp2.status_code == 200:
                data = resp2.json()
                choices = data.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    content = msg.get("content")
                    finish_reason = choices[0].get("finish_reason", "stop")

        return {
            "content": (content or "").strip(),
            "finish_reason": finish_reason,
            "usage": data.get("usage") or {},
        }

    @staticmethod
    def _sanitize_error(err: Any) -> str:
        text = str(err)
        for prefix in ("LLM_", "sk-", "gsk_", "AIza"):
            if prefix in text:
                text = re.sub(rf"{prefix}[A-Za-z0-9_\-\|]+", "[REDACTED_KEY]", text)
        return text


class _MetaRateLimitError(Exception):
    def __init__(self, message: str, retry_after: float = 2.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class _MetaTransientError(Exception):
    pass


# ==============================================================================
# 4. MULTI-BRAIN PROVIDER ADAPTER FOR REGISTRY
# ==============================================================================

class MetaProviderAdapter(BaseProviderAdapter):
    """
    ProviderRegistry adapter for Meta AI models (`https://api.meta.ai/v1`).
    """

    def __init__(
        self,
        provider_id: str = "meta",
        name: str = "Meta AI Model API",
        default_model: str = "muse-spark-1.3",
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            name=name,
            execution_mode="cloud",
            supported_modalities=["text", "code", "vision", "audio", "image"],
            is_cloud=True,
        )
        self.default_model = default_model
        self.client = MetaModelClient.get_instance()

    def check_health(self) -> Dict[str, Any]:
        if not self.client.is_configured:
            return {
                "status": "unconfigured",
                "configured": False,
                "message": "Environment variable 'MODEL_API_KEY' or 'META_API_KEY' is not set.",
            }
        return {
            "status": "healthy",
            "configured": True,
            "api_base": self.client.api_base,
            "key_masked": redact_meta_key(self.client.api_key),
            "default_model": self.default_model,
            "models": list(META_MODEL_CATALOG.keys()),
        }

    def prepare_input(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        prompt = task_input.get("prompt", "")
        system = task_input.get("system_prompt")
        messages = task_input.get("messages")
        if not messages:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

        return {
            "model": normalize_meta_model_id(task_input.get("model") or self.default_model),
            "messages": messages,
            "agent_id": task_input.get("agent_id", ""),
            "temperature": float(task_input.get("temperature", 0.3)),
            "max_tokens": int(task_input.get("max_tokens", 2048)),
            "timeout": float(task_input.get("timeout", 60.0)),
        }

    def execute(self, prepared_input: Dict[str, Any]) -> Dict[str, Any]:
        res = self.client.chat_completion(
            messages=prepared_input["messages"],
            model=prepared_input["model"],
            agent_id=prepared_input.get("agent_id", ""),
            temperature=prepared_input.get("temperature"),
            max_tokens=prepared_input.get("max_tokens"),
            timeout=prepared_input.get("timeout"),
        )
        return {
            "output": res["content"],
            "model": res["model"],
            "provider": "meta",
            "duration_seconds": res["latency_ms"] / 1000.0,
            "usage": res["usage"],
            "status": "success",
        }
