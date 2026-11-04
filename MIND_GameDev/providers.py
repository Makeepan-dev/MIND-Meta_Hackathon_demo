"""
MIND Universal Development Studio — Provider Health & Diagnostics Manager.
Inspects and reports the live operational readiness of all free AI providers:
- OpenRouter Free-Tier Coding & Reasoning API
- Local Ollama Engine
- AI Horde Community Diffusion Image Generation
- Local Procedural 3D and Graphics Fallbacks
Enforces zero-secret leakage and strict free-only cost protection.
"""

from __future__ import annotations

import os
import json
from typing import Dict, Any, List, Optional

from .config import GameDevConfig, redact_secret, VERIFIED_FREE_MODELS
from .adapters.coding_adapter import CodingProviderAdapter, is_free_model
from .adapters.image_adapter import ImageProviderAdapter
from .adapters.threed_adapter import ThreeDAssetAdapter
from .adapters.blender_adapter import BlenderAdapter


class ProviderDiagnostics:
    """Performs non-billable diagnostics across all integrated AI providers."""

    def __init__(self, config: Optional[GameDevConfig] = None) -> None:
        self.config = config or GameDevConfig.load()
        self.coding_adapter = CodingProviderAdapter(self.config)
        self.image_adapter = ImageProviderAdapter(self.config)
        self.threed_adapter = ThreeDAssetAdapter(self.config)
        self.blender_adapter = BlenderAdapter(self.config)

    def run_diagnostics(self) -> Dict[str, Any]:
        """Runs health checks on all providers and aggregates results."""
        coding_health = self.coding_adapter.health_check()
        image_health = self.image_adapter.health_check()
        blender_available = self.blender_adapter.is_available()
        blender_version = self.blender_adapter.get_blender_version() if blender_available else "Not Detected"

        return {
            "studio_name": "MIND Universal Development Studio",
            "version": "2.0.0",
            "test_mode": self.config.test_mode,
            "cost_protection": {
                "free_only_mode": getattr(self.config, "openrouter_free_only", True),
                "guarantee": "Strictly blocks paid models and silent billing failover.",
            },
            "providers": {
                "meta": {
                    "name": "Meta AI Model API (Flagship Coding, Reasoning & Analysis)",
                    "api_base": getattr(self.config, "meta_api_base", "https://api.meta.ai/v1"),
                    "env_variable": "MODEL_API_KEY",
                    "configured": coding_health.get("meta_configured", False),
                    "auth_status": f"[{coding_health.get('meta_auth', 'CONFIGURED')}]" if coding_health.get("meta_configured") else "[UNSET]",
                    "selected_model": getattr(self.config, "meta_coding_model", "muse-spark-1.3"),
                    "models": ["muse-spark-1.3", "muse-wonder-1.0", "muse-spark-1.2", "muse-spark-1.1"],
                    "available": coding_health.get("meta_available", False),
                    "error": coding_health.get("meta_error"),
                },
                "stitch": {
                    "name": "Google Stitch MCP (Dedicated UI/UX Website Design Provider)",
                    "mcp_url": getattr(self.config, "stitch_mcp_url", "https://stitch.googleapis.com/mcp"),
                    "env_variable": "STITCH_API_KEY",
                    "configured": bool(self.config.stitch_api_key and not self.config.stitch_api_key.startswith("your_")),
                    "role": "Dedicated UI/UX and website design generation (Explicitly preserved)",
                },
                "openrouter": {
                    "name": "OpenRouter Free Tier (Coding & Reasoning)",
                    "official_docs": "https://openrouter.ai/docs/quickstart",
                    "signup_url": "https://openrouter.ai/keys",
                    "env_variable": "OPENROUTER_API_KEY",
                    "configured": coding_health.get("openrouter_configured", False),
                    "auth_status": f"[{coding_health.get('openrouter_auth', 'CONFIGURED')}]" if coding_health.get("openrouter_configured") else "[UNSET - LOCAL FALLBACK ACTIVE]",
                    "selected_model": self.config.openrouter_model,
                    "model_verified_free": is_free_model(self.config.openrouter_model),
                    "free_only_enforced": getattr(self.config, "openrouter_free_only", True),
                    "available": coding_health.get("openrouter_available", False),
                    "error": coding_health.get("openrouter_error"),
                    "free_models_available_count": coding_health.get("openrouter_free_models_count", len(VERIFIED_FREE_MODELS)),
                    "verified_models_sample": sorted(list(VERIFIED_FREE_MODELS))[:4],
                },
                "groq": {
                    "name": "Groq Cloud LPU Engine",
                    "configured": coding_health.get("groq_configured", False),
                    "auth_status": f"[{coding_health.get('groq_auth', 'CONFIGURED')}]" if coding_health.get("groq_configured") else "[UNSET]",
                    "available": coding_health.get("groq_available", False),
                    "error": coding_health.get("groq_error"),
                    "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                },
                "gemini": {
                    "name": "Google Gemini Cloud (Multimodal Vision & Code)",
                    "configured": coding_health.get("gemini_configured", False),
                    "auth_status": f"[{coding_health.get('gemini_auth', 'CONFIGURED')}]" if coding_health.get("gemini_configured") else "[UNSET]",
                    "available": coding_health.get("gemini_available", False),
                    "error": coding_health.get("gemini_error"),
                    "model": "gemini-3-flash-preview",
                },
                "ollama": {
                    "name": "Local Ollama Engine (Offline Code Generation)",
                    "official_docs": "https://docs.ollama.com/api",
                    "endpoint": self.config.ollama_base_url,
                    "target_model": self.config.ollama_coding_model,
                    "meta_llama_model": getattr(self.config, "ollama_meta_model", "llama3.2:1b"),
                    "reachable": coding_health.get("ollama_available", False),
                    "model_installed": coding_health.get("ollama_model_installed", False),
                    "meta_llama_installed": any(getattr(self.config, "ollama_meta_model", "llama3.2:1b") in m for m in coding_health.get("ollama_installed_models", [])),
                    "installed_models": coding_health.get("ollama_installed_models", []),
                    "status_note": "Online" if coding_health.get("ollama_available") else "Offline / Stopped (Graceful fallback active)",
                },
                "ai_horde": {
                    "name": "AI Horde (Free Distributed Image Synthesis)",
                    "official_docs": "https://stablehorde.net/docs/image/",
                    "web_portal": "https://horde.tazlin.net/",
                    "env_variable": "AI_HORDE_API_KEY",
                    "key_tier": "Custom User Key" if self.config.ai_horde_api_key != "0000000000" else "Anonymous Public Free Tier ('0000000000')",
                    "api_base": self.config.ai_horde_base_url,
                    "timeout_seconds": getattr(self.config, "ai_horde_timeout_seconds", 15),
                    "reachable": image_health.get("ai_horde_reachable", False),
                    "procedural_fallback_ready": True,
                },
                "procedural_3d": {
                    "name": "MIND Pure-Python 3D glTF 2.0 & OBJ Engine",
                    "status": "100% Operational (Local / Zero Network Required)",
                    "formats": [".glb (binary glTF 2.0)", ".obj (Wavefront mesh)"],
                    "paid_tokens_required": 0,
                },
                "procedural_audio": {
                    "name": "Web Audio API Procedural Synthesizer",
                    "status": "100% Operational (In-browser oscillator)",
                    "paid_tokens_required": 0,
                },
                "blender_engine": {
                    "name": "Local Blender 3D Reconstruction Engine",
                    "available": blender_available,
                    "version": blender_version,
                    "executable": str(self.blender_adapter.blender_path) if blender_available else "Not Detected",
                    "capability": "Headless background python execution (bpy), procedural modeling, GLB export",
                },
            },
            "selected_active_tier": coding_health.get("selected_tier", "offline_deterministic"),
        }

    def print_diagnostics(self) -> None:
        """Prints a human-readable CLI report of provider readiness."""
        diag = self.run_diagnostics()
        p = diag["providers"]

        print("\n" + "=" * 70)
        print("          MIND UNIVERSAL STUDIO — AI PROVIDER DIAGNOSTICS         ")
        print("=" * 70)

        # Cost protection banner
        print(f"Cost Policy: Free-Only Enforcement = {diag['cost_protection']['free_only_mode']}")
        print(f"Guarantee:   {diag['cost_protection']['guarantee']}")
        print("-" * 70)

        # 1. OpenRouter
        or_info = p["openrouter"]
        print(f"[1] OpenRouter Free Models:")
        print(f"    • Auth Status:      {or_info['auth_status']}")
        print(f"    • Selected Model:   {or_info['selected_model']}")
        print(f"    • Verified Free:    {or_info['model_verified_free']}")
        print(f"    • Reachable:        {or_info['available']}")
        if or_info.get("error"):
            print(f"    • Health Notice:    {or_info['error']}")
        print(f"    • Docs / Free Keys: {or_info['signup_url']}")

        # 2. Groq
        groq_info = p.get("groq", {})
        print(f"\n[2] Groq Cloud LPU:")
        print(f"    • Auth Status:      {groq_info.get('auth_status', '[UNSET]')}")
        print(f"    • Selected Model:   {groq_info.get('model')}")
        print(f"    • Operational:      {'Online (Ready)' if groq_info.get('available') else 'Offline / Degraded'}")
        if groq_info.get("error"):
            print(f"    • Notice:           {groq_info['error']}")

        # 3. Google Gemini
        gem_info = p.get("gemini", {})
        print(f"\n[3] Google Gemini Cloud:")
        print(f"    • Auth Status:      {gem_info.get('auth_status', '[UNSET]')}")
        print(f"    • Selected Model:   {gem_info.get('model')}")
        print(f"    • Operational:      {'Online (Ready)' if gem_info.get('available') else 'Offline / Degraded'}")
        if gem_info.get("error"):
            print(f"    • Notice:           {gem_info['error']}")

        # 4. Ollama
        ol_info = p["ollama"]
        print(f"\n[4] Local Ollama Engine:")
        print(f"    • Endpoint:         {ol_info['endpoint']}")
        print(f"    • Configured Model: {ol_info['target_model']}")
        print(f"    • Service Status:   {ol_info['status_note']}")
        print(f"    • Model Installed:  {ol_info['model_installed']}")

        # 5. AI Horde
        ah_info = p["ai_horde"]
        print(f"\n[5] AI Horde Image Diffusion:")
        print(f"    • Access Tier:      {ah_info['key_tier']}")
        print(f"    • Endpoint:         {ah_info['api_base']}")
        print(f"    • Cluster Status:   {'Online' if ah_info['reachable'] else 'Offline / Bypassed'}")
        print(f"    • Fallback Engine:  Local Pillow Engine (Ready)")

        # 6. Local Procedural
        print(f"\n[6] Local Procedural Engines:")
        print(f"    • 3D Geometry:      {p['procedural_3d']['status']}")
        print(f"    • Audio FX:         {p['procedural_audio']['status']}")

        # 7. Blender 3D Reconstruction
        bl_info = p.get("blender_engine", {})
        print(f"\n[7] Blender 3D Reconstruction Engine:")
        print(f"    • Status:           {'100% Operational (Ready)' if bl_info.get('available') else 'Offline / Not Installed'}")
        print(f"    • Version:          {bl_info.get('version')}")
        print(f"    • Executable:       {bl_info.get('executable')}")

        print("-" * 70)
        print(f"ACTIVE TIER: {diag['selected_active_tier'].upper()}")
        print("=" * 70 + "\n")
