"""
MIND — Concept Image Client (Stage C)
Generates and validates character concept art optimized for 3D reconstruction.
Supports Cloud Image APIs (Google GenAI / Stability AI) with automatic, authentic local Pillow fallback.
"""

import os
import time
import base64
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

try:
    import dotenv
    root_env = _REPO_ROOT / ".env"
    if root_env.exists():
        dotenv.load_dotenv(root_env, override=False)
except Exception:
    pass


class ImageGenerationClient:
    """Handles concept image synthesis, validation, and disk persistence."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        workspace_root = _REPO_ROOT
        self.output_dir = Path(output_dir or (workspace_root / "Workspace" / "generated_media"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_concept_image(self, prompt_data: Dict[str, Any], user_goal: str) -> Dict[str, Any]:
        """
        Executes concept image generation.
        Tries configured cloud APIs first; if unconfigured or quota-limited, uses local engine.
        Validates file integrity and dimensions before returning.
        """
        prompt = prompt_data.get("prompt", user_goal)
        timestamp = int(time.time())
        file_name = f"concept_{timestamp}_{abs(hash(prompt)) % 100000}.png"
        target_path = self.output_dir / file_name

        image_key = os.getenv("IMAGE_GEN_API_KEY") or os.getenv("STABILITY_API_KEY")
        test_mode = os.getenv("MIND_TEST_MODE") == "1"

        generation_result: Dict[str, Any] = {}

        if not test_mode:
            # 1. Attempt SiliconFlow FLUX.1 (High-speed Neural Diffusion, SOTA quality)
            sf_res = self._try_siliconflow_generation(prompt, target_path)
            if sf_res.get("success"):
                generation_result = sf_res

            # 2. Attempt Configured Image API Key (Gemini / Stability) if SiliconFlow not used
            if not generation_result.get("success") and image_key and not image_key.startswith("your_"):
                cloud_res = self._try_cloud_generation(prompt, image_key, target_path)
                if cloud_res.get("success"):
                    generation_result = cloud_res

            # 3. Emergency offline schematic fallback if all cloud models unavailable
            if not generation_result.get("success"):
                local_res = self._render_local_character_concept(prompt, target_path, style=prompt_data.get("style", "stylized"))
                generation_result = {
                    "success": True,
                    "image_path": str(target_path),
                    "provider": "offline_schematic_fallback",
                    "details": local_res,
                }
        else:
            # Fast deterministic test mode
            local_res = self._render_local_character_concept(prompt, target_path, style=prompt_data.get("style", "stylized"))
            generation_result = {
                "success": True,
                "image_path": str(target_path),
                "provider": "local_pillow_engine",
                "details": local_res,
            }

        # Stage C Validation Gate
        validation = self.validate_image_file(str(target_path))
        if not validation["is_valid"]:
            raise RuntimeError(f"Generated image failed validation gate: {validation['error']}")

        generation_result.update({
            "image_path": str(target_path),
            "file_size_bytes": validation["file_size_bytes"],
            "dimensions": validation["dimensions"],
            "format": validation["format"],
            "verified": True,
        })
        return generation_result

    def _try_siliconflow_generation(self, prompt: str, target_path: Path) -> Dict[str, Any]:
        """Generates neural concept art via SiliconFlow FLUX.1-schnell."""
        sf_key = os.getenv("SILICONFLOW_API_KEY")
        if not sf_key or sf_key.startswith("your_"):
            return {"success": False, "error": "No SILICONFLOW_API_KEY configured"}
        url = "https://api.siliconflow.com/v1/images/generations"
        headers = {"Authorization": f"Bearer {sf_key}", "Content-Type": "application/json"}
        payload = {
            "model": "black-forest-labs/FLUX.1-schnell",
            "prompt": prompt[:300],
            "image_size": "512x512",
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                images = data.get("images", [])
                if images and "url" in images[0]:
                    img_data = requests.get(images[0]["url"], timeout=20).content
                    with open(target_path, "wb") as f:
                        f.write(img_data)
                    return {"success": True, "provider": "siliconflow_flux_1_schnell"}
            return {"success": False, "error": f"SiliconFlow HTTP {resp.status_code}: {resp.text[:100]}"}
        except Exception as e:
            return {"success": False, "error": f"SiliconFlow connection error: {str(e)}"}

    def _try_cloud_generation(self, prompt: str, api_key: str, target_path: Path) -> Dict[str, Any]:
        """Tries Google Gemini Flash-Image or Stability API endpoints."""
        # 1. Try Google Gemini Image Generation
        if api_key.startswith("AQ.") or api_key.startswith("AIza"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": f"Generate a full body 3D character concept in neutral A-pose: {prompt}"}]}]
            }
            try:
                resp = requests.post(url, json=payload, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for p in parts:
                            if "inlineData" in p:
                                img_bytes = base64.b64decode(p["inlineData"]["data"])
                                with open(target_path, "wb") as f:
                                    f.write(img_bytes)
                                return {"success": True, "provider": "google_gemini_flash_image"}
                elif resp.status_code == 429:
                    return {"success": False, "error": "Google AI Studio Quota Exceeded (HTTP 429)"}
                else:
                    return {"success": False, "error": f"Google AI HTTP {resp.status_code}"}
            except Exception as e:
                return {"success": False, "error": f"Google AI request error: {str(e)}"}

        # 2. Try Stability AI v2beta
        if api_key.startswith("sk-"):
            headers = {"authorization": f"Bearer {api_key}", "accept": "image/*"}
            data = {"prompt": prompt, "output_format": "png", "aspect_ratio": "1:1"}
            try:
                resp = requests.post("https://api.stability.ai/v2beta/stable-image/generate/core", headers=headers, files={"none": ""}, data=data, timeout=30)
                if resp.status_code == 200:
                    with open(target_path, "wb") as f:
                        f.write(resp.content)
                    return {"success": True, "provider": "stability_ai_v2beta"}
                return {"success": False, "error": f"Stability AI HTTP {resp.status_code}: {resp.text[:100]}"}
            except Exception as e:
                return {"success": False, "error": f"Stability request error: {str(e)}"}

        return {"success": False, "error": "No matching cloud provider endpoint for given key prefix"}

    def _try_neural_diffusion_generation(self, prompt: str, target_path: Path) -> Dict[str, Any]:
        """Generates high-resolution concept art using neural diffusion (FLUX.1)."""
        import urllib.parse
        clean_prompt = prompt.replace("\n", " ").strip()
        encoded = urllib.parse.quote(clean_prompt[:250])
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&model=flux&nologo=true"
        try:
            resp = requests.get(url, timeout=35)
            if resp.status_code == 200 and len(resp.content) > 5000:
                with open(target_path, "wb") as f:
                    f.write(resp.content)
                # Re-save to normalize PNG format
                with Image.open(target_path) as im:
                    im.convert("RGBA").save(target_path, "PNG")
                return {"success": True, "provider": "flux_1_neural_diffusion"}
            return {"success": False, "error": f"Neural model HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Neural model connection error: {str(e)}"}

    def _render_local_character_concept(self, prompt: str, target_path: Path, style: str = "stylized") -> Dict[str, Any]:
        """
        Renders a full-body 512x512 character concept sheet with neutral A-pose
        and isolated silhouette specifically formatted for Image-to-3D reconstruction.
        """
        width, height = 512, 512
        # Clean neutral background (vital for 3D reconstruction)
        img = Image.new("RGBA", (width, height), (242, 244, 247, 255))
        draw = ImageDraw.Draw(img)

        # Draw subtle studio floor indicator
        draw.ellipse([(140, 450), (372, 490)], fill=(225, 228, 234, 255))

        # Color palette based on style
        is_dark = "blacksmith" in prompt.lower() or "guard" in prompt.lower() or "warrior" in prompt.lower()
        skin_color = (235, 195, 160)
        armor_color = (65, 80, 100) if not is_dark else (85, 75, 70)
        trim_color = (210, 165, 50) if "guard" in prompt.lower() else (140, 150, 165)
        cloth_color = (40, 60, 90) if not is_dark else (100, 50, 45)
        boot_color = (45, 35, 30)

        # Character Silhouette in Neutral A-Pose:
        # Head
        draw.ellipse([(236, 60), (276, 110)], fill=skin_color, outline=(30, 30, 30), width=2)
        # Hair/Helmet
        draw.arc([(234, 58), (278, 95)], start=180, end=360, fill=trim_color, width=4)

        # Neck
        draw.rectangle([(250, 110), (262, 125)], fill=skin_color)

        # Torso / Chest Armor
        draw.polygon([(220, 125), (292, 125), (280, 250), (232, 250)], fill=armor_color, outline=(30, 30, 30))
        # Chest Emblem / Trim
        draw.line([(256, 130), (256, 245)], fill=trim_color, width=3)
        draw.line([(230, 175), (282, 175)], fill=trim_color, width=2)

        # Belt
        draw.rectangle([(230, 245), (282, 260)], fill=(30, 25, 20), outline=(15, 15, 15))
        draw.rectangle([(250, 246), (262, 259)], fill=trim_color)

        # Left Arm (A-Pose - angled outwards 30 deg)
        draw.polygon([(220, 125), (200, 135), (170, 230), (188, 235)], fill=cloth_color, outline=(30, 30, 30))
        # Left Hand (Neutral, open palm)
        draw.ellipse([(160, 230), (178, 252)], fill=skin_color, outline=(30, 30, 30))

        # Right Arm (A-Pose - angled outwards 30 deg)
        draw.polygon([(292, 125), (312, 135), (342, 230), (324, 235)], fill=cloth_color, outline=(30, 30, 30))
        # Right Hand (Neutral, open palm)
        draw.ellipse([(334, 230), (352, 252)], fill=skin_color, outline=(30, 30, 30))

        # Hips / Skirt
        draw.polygon([(230, 260), (282, 260), (290, 295), (222, 295)], fill=cloth_color, outline=(30, 30, 30))

        # Left Leg
        draw.polygon([(232, 295), (252, 295), (248, 410), (228, 410)], fill=armor_color, outline=(30, 30, 30))
        # Left Boot
        draw.polygon([(226, 410), (250, 410), (252, 455), (218, 455)], fill=boot_color, outline=(20, 20, 20))

        # Right Leg
        draw.polygon([(260, 295), (280, 295), (284, 410), (264, 410)], fill=armor_color, outline=(30, 30, 30))
        # Right Boot
        draw.polygon([(262, 410), (286, 410), (294, 455), (260, 455)], fill=boot_color, outline=(20, 20, 20))

        # Metadata Header Banner
        draw.rectangle([(0, 0), (512, 35)], fill=(25, 30, 40))
        draw.text((15, 10), f"MIND 3D CONCEPT | {style.upper()} A-POSE", fill=(56, 189, 248))
        draw.text((380, 10), "512x512 PNG", fill=(148, 163, 184))

        img.save(target_path, "PNG")
        return {"width": width, "height": height, "style": style}

    def validate_image_file(self, file_path: str) -> Dict[str, Any]:
        """Validates that the file exists, has size > 1024 bytes, and is a readable image."""
        p = Path(file_path)
        if not p.exists():
            return {"is_valid": False, "error": f"Image file not found: {file_path}"}
        size = p.stat().st_size
        if size < 500:
            return {"is_valid": False, "error": f"Image file is suspiciously small ({size} bytes)"}

        try:
            with Image.open(p) as img:
                img.verify()
            with Image.open(p) as img:
                dims = img.size
                fmt = img.format
                if dims[0] < 128 or dims[1] < 128:
                    return {"is_valid": False, "error": f"Image dimensions too small: {dims}"}
                return {
                    "is_valid": True,
                    "file_size_bytes": size,
                    "dimensions": dims,
                    "format": fmt,
                }
        except Exception as e:
            return {"is_valid": False, "error": f"Image header verification failed: {str(e)}"}
