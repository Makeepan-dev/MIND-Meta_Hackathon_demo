"""
MIND — Prompt Synthesizer (Stage A & B)
Transforms user voice or text requests into detailed, 3D-optimized visual concept prompts
using local LLM inference (Ollama) with fallback to deterministic artistic expansion.
"""

import os
import re
import requests
from typing import Dict, Any, Optional


SYSTEM_3D_PROMPT_DIRECTIVE = """You are an expert 3D Concept Artist and Technical Director.
Transform the user's character request into a detailed, high-quality image-generation prompt specifically designed for Image-to-3D mesh reconstruction.

CRITICAL 3D RECONSTRUCTION RULES:
1. Composition: Full-body character, completely centered, front-facing neutral A-pose or T-pose.
2. Visibility: Entire subject visible from head to toe with zero cropping. Hands slightly open, feet flat on the ground.
3. Background: Solid, neutral plain studio background (pure white or neutral grey) with no clutter, no shadows, and no floor textures.
4. Lighting: Clean, even, soft diffuse studio lighting with zero harsh shadows.
5. Style Preservation: If the user asks for stylized, low-poly, anime, or voxel, preserve that exact style. Do NOT force photorealism unless requested.
6. Detail: Specify clothing, materials, colors, facial features, textures, and silhouette.

OUTPUT FORMAT:
Output ONLY the final image generation prompt string. Do not include introductory text, explanations, or quotes.
"""


class PromptSynthesizer:
    """Interprets user intent and generates detailed visual prompts for 3D reconstruction."""

    def __init__(self, ollama_url: str = "http://localhost:11434", default_model: str = "gemma3:1b") -> None:
        self.ollama_url = os.getenv("OLLAMA_API_BASE", ollama_url)
        self.default_model = default_model

    def synthesize_prompt(self, user_goal: str) -> Dict[str, Any]:
        """
        Interprets the user request and generates a detailed image prompt.
        Returns a dict containing the generated prompt, detected style, and metadata.
        """
        if not user_goal or not user_goal.strip():
            raise ValueError("User request cannot be empty.")

        goal_clean = user_goal.strip()
        style_hints = self._detect_style(goal_clean)

        # Attempt Meta AI Model API (muse-spark-1.1) first when configured
        meta_prompt = self._call_meta_llm(goal_clean, style_hints)
        if meta_prompt and len(meta_prompt) > 20:
            final_prompt = self._ensure_3d_criteria(meta_prompt, style_hints)
            return {
                "user_request": goal_clean,
                "prompt": final_prompt,
                "engine": "meta_llm",
                "model": "muse-spark-1.1",
                "style": style_hints["primary_style"],
                "pose": "neutral_a_pose",
            }

        # Attempt local LLM generation fallback
        llm_prompt = self._call_local_llm(goal_clean, style_hints)
        if llm_prompt and len(llm_prompt) > 20:
            final_prompt = self._ensure_3d_criteria(llm_prompt, style_hints)
            return {
                "user_request": goal_clean,
                "prompt": final_prompt,
                "engine": "local_llm",
                "model": self.default_model,
                "style": style_hints["primary_style"],
                "pose": "neutral_a_pose",
            }

        # Deterministic artistic expansion fallback
        fallback_prompt = self._expand_deterministically(goal_clean, style_hints)
        return {
            "user_request": goal_clean,
            "prompt": fallback_prompt,
            "engine": "deterministic_expander",
            "model": "rule_based_3d_template",
            "style": style_hints["primary_style"],
            "pose": "neutral_a_pose",
        }

    def _detect_style(self, text: str) -> Dict[str, Any]:
        """Extracts stylistic constraints from user text."""
        lower = text.lower()
        if "low-poly" in lower or "low poly" in lower or "boxovara" in lower or "poly" in lower:
            style = "low-poly stylized"
            material = "flat-shaded matte polygons, clean geometric facets"
        elif "pixel" in lower or "voxel" in lower:
            style = "voxel 3d"
            material = "blocky voxel topology, crisp colored cubes"
        elif "anime" in lower or "cel-shaded" in lower or "toon" in lower:
            style = "cel-shaded anime"
            material = "clean line-art, vibrant saturated flat materials"
        elif "stylized" in lower or "fantasy" in lower:
            style = "stylized fantasy"
            material = "hand-painted textures, exaggerated heroic proportions"
        elif "cyberpunk" in lower or "sci-fi" in lower:
            style = "sci-fi tech"
            material = "matte composite armor, subtle glowing emissive accents"
        elif "realistic" in lower or "photorealistic" in lower or "human" in lower:
            style = "realistic"
            material = "high-fidelity fabric weave, natural skin texture and specularity"
        else:
            style = "stylized 3D character"
            material = "clean PBR materials, balanced roughness and specularity"

        return {
            "primary_style": style,
            "materials": material,
            "is_human": any(k in lower for k in ["human", "guard", "man", "woman", "blacksmith", "warrior", "character", "adventurer"]),
        }

    def _call_meta_llm(self, user_goal: str, style_hints: Dict[str, Any]) -> Optional[str]:
        """Calls Meta Model API (muse-spark-1.1) for 3D concept prompt expansion."""
        if os.getenv("MIND_TEST_MODE") == "1" and os.getenv("MIND_FORCE_LIVE_META") != "1":
            return None
        try:
            from multi_brain.providers.meta_provider import MetaModelClient
            client = MetaModelClient.get_instance()
            if not client.is_configured:
                return None
            messages = [
                {"role": "system", "content": SYSTEM_3D_PROMPT_DIRECTIVE},
                {
                    "role": "user",
                    "content": (
                        f"User request: '{user_goal}'\n"
                        f"Required style: {style_hints['primary_style']}\n"
                        "Create a detailed 3D concept prompt in neutral A-pose on a white background."
                    ),
                },
            ]
            res = client.chat_completion(
                messages=messages,
                model="muse-spark-1.1",
                agent_id="PromptSynthesizer",
                temperature=0.3,
                max_tokens=768,
            )
            raw_text = (res.get("content") or "").strip()
            cleaned = re.sub(r"^['\"]|['\"]$", "", raw_text).strip()
            cleaned = cleaned.replace("```prompt", "").replace("```", "").strip()
            return cleaned if cleaned else None
        except Exception:
            return None

    def _call_local_llm(self, user_goal: str, style_hints: Dict[str, Any]) -> Optional[str]:
        """Calls local Ollama instance with timeout safety."""
        # Check if testing mode is active
        if os.getenv("MIND_TEST_MODE") == "1":
            return None

        endpoint = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.default_model,
            "system": SYSTEM_3D_PROMPT_DIRECTIVE,
            "prompt": (
                f"User request: '{user_goal}'\n"
                f"Required style: {style_hints['primary_style']}\n"
                "Create a detailed 3D concept prompt in neutral A-pose on a white background."
            ),
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 150},
        }

        try:
            resp = requests.post(endpoint, json=payload, timeout=8)
            if resp.status_code == 200:
                raw_text = resp.json().get("response", "").strip()
                # Clean markdown or quotes
                cleaned = re.sub(r"^['\"]|['\"]$", "", raw_text).strip()
                cleaned = cleaned.replace("```prompt", "").replace("```", "").strip()
                return cleaned
        except Exception:
            pass
        return None

    def _ensure_3d_criteria(self, prompt: str, style_hints: Dict[str, Any]) -> str:
        """Appends mandatory 3D reconstruction tokens if missing."""
        required_tokens = []
        lower = prompt.lower()
        if "full body" not in lower and "full-body" not in lower:
            required_tokens.append("full-body view")
        if "a-pose" not in lower and "t-pose" not in lower and "neutral pose" not in lower:
            required_tokens.append("neutral front-facing A-pose")
        if "background" not in lower:
            required_tokens.append("plain neutral solid white background")
        if "lighting" not in lower:
            required_tokens.append("even diffuse studio lighting, no shadows")
        if "crop" not in lower:
            required_tokens.append("entire subject visible, uncropped silhouette")

        if required_tokens:
            prompt = f"{prompt.rstrip('.')}, {', '.join(required_tokens)}."
        return prompt

    def _expand_deterministically(self, user_goal: str, style_hints: Dict[str, Any]) -> str:
        """Fallback deterministic prompt expansion."""
        style = style_hints["primary_style"]
        mat = style_hints["materials"]

        # Clean prompt base
        subject = user_goal
        for prefix in ["create a", "generate a", "make a", "create an", "generate an", "design a"]:
            if subject.lower().startswith(prefix):
                subject = subject[len(prefix):].strip()
                break

        return (
            f"3D character concept sheet of a {subject}. "
            f"Style: {style}, rendered with {mat}. "
            f"Composition: full-body, centered, front-facing neutral A-pose with arms slightly angled and feet planted. "
            f"Background: solid clean neutral light-grey background, isolated silhouette. "
            f"Lighting: soft even diffuse studio lighting, ambient occlusion, no harsh directional shadows. "
            f"No cropping, complete figure visible from head to toe, optimized for image-to-3D mesh generation."
        )
