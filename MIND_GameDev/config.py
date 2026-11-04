"""Configuration module for MIND Game Development Studio.

Loads environment variables safely without mutating .env, provides defaults,
and specifies workspace boundaries.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional

PACKAGE_ROOT: Path = Path(__file__).resolve().parent
REPO_ROOT: Path = PACKAGE_ROOT.parent
DEFAULT_WORKSPACE: Path = PACKAGE_ROOT / "workspace"
MIND_CODE_ROOT: Path = REPO_ROOT / "MIND_Code"
ASSETS_DIR: str = str(REPO_ROOT / "assets")

try:
    import dotenv
    for _candidate_env in (REPO_ROOT / ".env", PACKAGE_ROOT / ".env", Path.cwd() / ".env"):
        if _candidate_env.exists():
            dotenv.load_dotenv(_candidate_env, override=False)
            break
except Exception:
    pass

# Ensure workspace directory exists
DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)

# Primary Cloud Provider: Official Meta AI Model API (Hackathon Credits)
META_API_KEY: Optional[str] = (
    os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY") or os.getenv("LLAMA_API_KEY")
)
META_API_BASE: str = os.getenv("META_API_BASE", "https://api.meta.ai/v1")
META_CODING_MODEL: str = os.getenv("META_CODING_MODEL", "muse-spark-1.3")
META_REASONING_MODEL: str = os.getenv("META_REASONING_MODEL", "muse-wonder-1.0")
META_ANALYSIS_MODEL: str = os.getenv("META_ANALYSIS_MODEL", "muse-spark-1.2")
META_FAST_MODEL: str = os.getenv("META_FAST_MODEL", "muse-spark-1.1")

# Legacy OpenRouter Provider Configuration (Retained for unit test compatibility)
OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "cohere/north-mini-code:free")
OPENROUTER_API_BASE: str = "https://openrouter.ai/api/v1"
OPENROUTER_FREE_ONLY: bool = os.getenv("OPENROUTER_FREE_ONLY", "1") == "1"

# Known verified free-tier models on OpenRouter
VERIFIED_FREE_MODELS = {
    "cohere/north-mini-code:free",
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-2-9b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "deepseek/deepseek-r1:free",
    "muse-spark-1.3",
    "muse-wonder-1.0",
    "muse-spark-1.2",
    "muse-spark-1.1",
}

OLLAMA_API_BASE: str = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_CODING_MODEL: str = os.getenv("OLLAMA_CODING_MODEL", "qwen2.5-coder:7b")
OLLAMA_META_MODEL: str = os.getenv("OLLAMA_META_MODEL", "llama3.2:1b")

AI_HORDE_API_KEY: str = os.getenv("AI_HORDE_API_KEY", "0000000000")  # Anonymous key by default
AI_HORDE_API_BASE: str = os.getenv("AI_HORDE_API_BASE", "https://aihorde.net/api/v2")
AI_HORDE_TIMEOUT_SECONDS: int = int(os.getenv("AI_HORDE_TIMEOUT_SECONDS", "15"))

# 3D Providers
HUNYUAN_SECRET_ID: Optional[str] = os.getenv("HUNYUAN_SECRET_ID") or os.getenv("TENCENTCLOUD_SECRET_ID")
HUNYUAN_SECRET_KEY: Optional[str] = os.getenv("HUNYUAN_SECRET_KEY") or os.getenv("TENCENTCLOUD_SECRET_KEY")
TRIPO_API_KEY: Optional[str] = os.getenv("TRIPO_API_KEY")

# Google Stitch Design Provider
STITCH_API_KEY: Optional[str] = os.getenv("STITCH_API_KEY")
STITCH_MCP_URL: str = os.getenv("STITCH_MCP_URL", "https://stitch.googleapis.com/mcp")
STITCH_TIMEOUT_SECONDS: float = float(os.getenv("STITCH_TIMEOUT_SECONDS", "300.0"))

# Local & Test Modes
MIND_TEST_MODE: bool = os.getenv("MIND_TEST_MODE", "0") == "1"
MIND_HEADLESS: bool = os.getenv("MIND_HEADLESS") == "1"

# Audio Settings
VOICE_INPUT_ENABLED: bool = os.getenv("MIND_VOICE_INPUT", "1") == "1"
VOICE_OUTPUT_ENABLED: bool = os.getenv("MIND_VOICE_OUTPUT", "1") == "1"
WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")
AUDIO_SAMPLE_RATE: int = 16000

# Sandbox Security Policy
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB per file limit
EXECUTION_TIMEOUT_SECONDS: float = 30.0


def redact_secret(val: Optional[str]) -> str:
    """Returns a safe redacted representation of a secret string."""
    if not val:
        return "[UNSET]"
    if len(val) <= 8:
        return "[SET]"
    return f"{val[:3]}...{val[-3:]} (len={len(val)})"


@dataclass
class GameDevConfig:
    """Encapsulates runtime configuration and secrets for MIND GameDev Studio."""

    package_root: Path = PACKAGE_ROOT
    repo_root: Path = REPO_ROOT
    workspace_root: Path = DEFAULT_WORKSPACE
    mind_code_root: Path = MIND_CODE_ROOT

    meta_api_key: Optional[str] = META_API_KEY
    meta_api_base: str = META_API_BASE
    meta_coding_model: str = META_CODING_MODEL
    meta_reasoning_model: str = META_REASONING_MODEL
    meta_analysis_model: str = META_ANALYSIS_MODEL
    meta_fast_model: str = META_FAST_MODEL

    openrouter_api_key: Optional[str] = OPENROUTER_API_KEY
    openrouter_model: str = OPENROUTER_MODEL
    openrouter_base_url: str = OPENROUTER_API_BASE
    openrouter_free_only: bool = OPENROUTER_FREE_ONLY

    ollama_base_url: str = OLLAMA_API_BASE
    ollama_coding_model: str = OLLAMA_CODING_MODEL
    ollama_meta_model: str = OLLAMA_META_MODEL

    ai_horde_api_key: str = AI_HORDE_API_KEY
    ai_horde_base_url: str = AI_HORDE_API_BASE
    ai_horde_timeout_seconds: int = AI_HORDE_TIMEOUT_SECONDS

    tripo_api_key: Optional[str] = TRIPO_API_KEY
    hunyuan_secret_id: Optional[str] = HUNYUAN_SECRET_ID
    hunyuan_secret_key: Optional[str] = HUNYUAN_SECRET_KEY

    stitch_api_key: Optional[str] = STITCH_API_KEY
    stitch_mcp_url: str = STITCH_MCP_URL
    stitch_timeout_seconds: float = STITCH_TIMEOUT_SECONDS

    test_mode: bool = MIND_TEST_MODE
    headless: bool = MIND_HEADLESS
    voice_enabled: bool = VOICE_OUTPUT_ENABLED

    # Closed-loop repair & verification settings
    max_repair_retries: int = int(os.getenv("MIND_MAX_REPAIR_RETRIES", "3"))
    repair_timeout_seconds: float = float(os.getenv("MIND_REPAIR_TIMEOUT_SECONDS", "60.0"))
    require_design_approval: bool = os.getenv("MIND_REQUIRE_DESIGN_APPROVAL", "1") == "1"

    @classmethod
    def load(cls) -> "GameDevConfig":
        return cls()

    def get_secret(self, key: str, default: str = "") -> str:
        """Retrieves a configuration secret or environment variable."""
        return os.getenv(key, default)

    def get_project_dir(self, project_name: str) -> Path:
        """Returns the project directory path within the workspace root."""
        clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in project_name)
        p = self.workspace_root / clean_name
        p.mkdir(parents=True, exist_ok=True)
        return p


def get_system_status() -> Dict[str, Any]:
    """Returns safe metadata about available providers and runtime flags."""
    return {
        "package_root": str(PACKAGE_ROOT),
        "workspace_root": str(DEFAULT_WORKSPACE),
        "test_mode": MIND_TEST_MODE,
        "headless": MIND_HEADLESS,
        "meta_configured": bool(META_API_KEY and not META_API_KEY.startswith("your_")),
        "meta_api_base": META_API_BASE,
        "meta_coding_model": META_CODING_MODEL,
        "meta_reasoning_model": META_REASONING_MODEL,
        "meta_analysis_model": META_ANALYSIS_MODEL,
        "meta_fast_model": META_FAST_MODEL,
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "openrouter_model": OPENROUTER_MODEL,
        "openrouter_free_only": OPENROUTER_FREE_ONLY,
        "ollama_base": OLLAMA_API_BASE,
        "ollama_model": OLLAMA_CODING_MODEL,
        "ai_horde_configured": AI_HORDE_API_KEY != "0000000000",
        "ai_horde_timeout_seconds": AI_HORDE_TIMEOUT_SECONDS,
        "tripo_configured": bool(TRIPO_API_KEY and not TRIPO_API_KEY.startswith("your_")),
        "hunyuan_configured": bool(HUNYUAN_SECRET_ID and HUNYUAN_SECRET_KEY),
        "stitch_configured": bool(STITCH_API_KEY and not STITCH_API_KEY.startswith("your_")),
        "voice_input_enabled": VOICE_INPUT_ENABLED,
        "voice_output_enabled": VOICE_OUTPUT_ENABLED,
    }
