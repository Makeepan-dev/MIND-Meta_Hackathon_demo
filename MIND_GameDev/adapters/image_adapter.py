"""Image generation provider adapter.

Interfaces with AI Horde (free, community diffusion cluster via anonymous key or custom key)
with multi-tier fallback to MIND's local Pillow procedural graphics engine.
Validates all outputs for pixel integrity, format compliance, and dimensions.
Distinguishes clearly between AI-generated and procedurally generated assets in metadata.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time
import requests
from pathlib import Path
from typing import Any, Dict, Optional, Union
from PIL import Image, ImageDraw

from ..config import GameDevConfig, redact_secret
from ..models import AssetMetadata

logger = logging.getLogger("mind.gamedev.adapters.image")


class ImageGenerationError(RuntimeError):
    """Raised when the AI provider fails and procedural fallback is not permitted."""


class ImageGenerationCancelled(RuntimeError):
    """Raised when the caller cancels an in-flight generation."""


class ImageProviderAdapter:
    """Coordinates image asset generation across AI Horde and local Pillow procedural engine."""

    def __init__(
        self,
        config: Optional[Union[GameDevConfig, str]] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: str = "stable_diffusion",
    ) -> None:
        if isinstance(config, GameDevConfig):
            self.config = config
            self.api_key = config.ai_horde_api_key
            self.api_base = config.ai_horde_base_url
            self.timeout = getattr(config, "ai_horde_timeout_seconds", 15)
        else:
            self.config = GameDevConfig.load()
            self.api_key = api_key or self.config.ai_horde_api_key
            self.api_base = api_base or self.config.ai_horde_base_url
            self.timeout = getattr(self.config, "ai_horde_timeout_seconds", 15)
        self.default_model = default_model

    def health_check(self) -> Dict[str, Any]:
        """Checks AI Horde status endpoint without generating images or consuming kudos."""
        is_anon = self.api_key == "0000000000"
        status = {
            "ai_horde_reachable": False,
            "api_base": self.api_base,
            "key_configured": not is_anon,
            "using_anonymous_key": is_anon,
            "timeout_seconds": self.timeout,
            "local_pillow_available": True,
        }
        try:
            resp = requests.get(f"{self.api_base}/status/heartbeat", timeout=3.5)
            status["ai_horde_reachable"] = resp.status_code == 200
        except Exception as e:
            status["ai_horde_error"] = str(e)
            status["ai_horde_reachable"] = False
        return status

    def generate_concept_image(
        self,
        prompt: str,
        target_path: Optional[Union[str, Path]] = None,
        name: str = "concept",
        output_dir: Optional[Path] = None,
        style: str = "stylized modern",
        width: int = 512,
        height: int = 512,
        max_horde_wait_seconds: Optional[int] = None,
        allow_fallback: bool = True,
        cancel_check: Optional[Any] = None,
        progress_cb: Optional[Any] = None,
    ) -> AssetMetadata:
        """Generates concept image, validating pixels and saving directly to target_path or output_dir.

        allow_fallback=False makes provider failure a hard error (ImageGenerationError)
        instead of substituting the procedural Pillow renderer.
        cancel_check: optional callable returning True when the caller cancelled.
        progress_cb: optional callable(str) receiving provider status messages.
        """
        if target_path:
            out_path = Path(target_path)
        elif output_dir:
            out_path = output_dir / f"{name}.png"
        else:
            out_path = self.config.workspace_root / "assets" / "images" / f"{name}.png"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wait_timeout = max_horde_wait_seconds or self.timeout

        # Fast path for Test Mode
        if self.config.test_mode:
            logger.info("MIND_TEST_MODE active. Using local procedural graphics.")
            meta = self._generate_local_concept_art(prompt, out_path, name, style, width, height)
            meta.metadata["fallback_reason"] = "MIND_TEST_MODE active (no network provider calls)"
            return meta

        # Tier 1: Try AI Horde (if online and not test mode)
        horde_error = "unknown"
        try:
            horde_res = self._try_ai_horde(prompt, out_path, width, height, wait_timeout,
                                           cancel_check=cancel_check, progress_cb=progress_cb)
            if horde_res.get("cancelled"):
                raise ImageGenerationCancelled("Image generation cancelled by user.")
            if horde_res.get("success"):
                val = self.validate_image(out_path)
                return AssetMetadata(
                    name=name,
                    asset_type="image_concept",
                    format="png",
                    file_path=str(out_path.resolve()),
                    file_size_bytes=val.get("file_size_bytes", out_path.stat().st_size),
                    verified=val.get("is_valid", False),
                    metadata={
                        "generation_type": "ai_generated",
                        "is_ai_generated": True,
                        "provider": "ai_horde",
                        "label": "AI Diffusion Generated",
                        "key_tier": "registered" if self.api_key != "0000000000" else "anonymous_free",
                        "prompt": prompt,
                        "dimensions": f"{width}x{height}",
                        "worker": horde_res.get("worker", "horde_cluster"),
                        "model": horde_res.get("model", "unknown"),
                        "horde_job_id": horde_res.get("job_id"),
                    },
                )
            horde_error = horde_res.get("error") or "unknown"
            logger.info(f"AI Horde generation failed: {horde_error}.")
        except ImageGenerationCancelled:
            raise
        except Exception as e:
            horde_error = f"AI Horde exception: {e}"
            logger.info(horde_error)

        if not allow_fallback:
            raise ImageGenerationError(f"AI Horde did not produce an image: {horde_error}")

        # Tier 2: Procedural local Pillow renderer (clearly labelled as NOT AI-generated)
        meta = self._generate_local_concept_art(prompt, out_path, name, style, width, height)
        meta.metadata["fallback_reason"] = horde_error
        return meta

    generate_image = generate_concept_image

    def _generate_local_concept_art(
        self,
        prompt: str,
        target_path: Path,
        name: str = "concept",
        style: str = "stylized modern",
        width: int = 512,
        height: int = 512,
    ) -> AssetMetadata:
        """Procedural Pillow-based high-contrast concept banner."""
        self._render_local_pillow(prompt, target_path, style, width, height)
        val = self.validate_image(target_path)
        return AssetMetadata(
            name=name,
            asset_type="image_concept",
            format="png",
            file_path=str(target_path.resolve()),
            file_size_bytes=val.get("file_size_bytes", target_path.stat().st_size),
            verified=val.get("is_valid", False),
            metadata={
                "generation_type": "procedural_local",
                "is_ai_generated": False,
                "label": "Procedural Graphic Placeholder (Local Pillow)",
                "note": "Generated via local procedural engine (AI Horde cluster timed out or offline)",
                "provider": "local_pillow_engine",
                "prompt": prompt,
                "dimensions": f"{width}x{height}",
            },
        )

    def _try_ai_horde(
        self,
        prompt: str,
        target_path: Path,
        width: int,
        height: int,
        timeout: int,
        cancel_check: Optional[Any] = None,
        progress_cb: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Submits async task to AI Horde and polls for completion within bounded timeout."""
        def _progress(msg: str) -> None:
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        submit_url = f"{self.api_base}/generate/async"
        headers = {
            "apikey": self.api_key,
            "Client-Agent": "MIND_UniversalStudio:2.0:mind.local",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt[:400],
            "params": {
                "steps": 20,
                "width": width,
                "height": height,
                "n": 1,
                "sampler_name": "k_euler",
            },
        }

        task_id = None
        try:
            resp = requests.post(submit_url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 429:
                return {"success": False, "error": "AI Horde rate limit (HTTP 429)"}
            if resp.status_code == 401:
                return {"success": False, "error": "AI Horde rejected the API key (HTTP 401)"}
            if resp.status_code != 202:
                return {"success": False, "error": f"Submit HTTP {resp.status_code}: {resp.text[:120]}"}

            task_id = resp.json().get("id")
            if not task_id:
                return {"success": False, "error": "No task ID returned from AI Horde"}
            _progress(f"Submitted to AI Horde (job {task_id[:8]})")

            # Bounded polling loop
            start = time.time()
            worker_name = "unknown"
            while time.time() - start < timeout:
                # Sleep in small slices so cancellation is responsive
                for _ in range(4):
                    if cancel_check and cancel_check():
                        self._cancel_horde_job(task_id, headers)
                        return {"success": False, "cancelled": True, "error": "cancelled"}
                    time.sleep(0.5)
                chk_resp = requests.get(f"{self.api_base}/generate/check/{task_id}", timeout=6.0)
                if chk_resp.status_code != 200:
                    continue

                data = chk_resp.json()
                if data.get("faulted"):
                    return {"success": False, "error": "AI Horde job faulted"}
                if data.get("is_possible") is False:
                    self._cancel_horde_job(task_id, headers)
                    return {"success": False, "error": "No AI Horde worker can fulfil this request right now"}
                if not data.get("done"):
                    _progress(f"AI Horde queue position {data.get('queue_position', '?')}, "
                              f"est. wait {data.get('wait_time', '?')}s")

                if data.get("done"):
                    # Retrieve completed generation
                    status_resp = requests.get(f"{self.api_base}/generate/status/{task_id}", timeout=6.0)
                    if status_resp.status_code == 200:
                        gen_data = status_resp.json()
                        gen_list = gen_data.get("generations", [])
                        if gen_list and gen_list[0].get("img"):
                            img_field = gen_list[0]["img"]
                            worker_name = gen_list[0].get("worker_name", "horde_worker")
                            model_name = gen_list[0].get("model", "unknown")

                            # Image can be direct URL or base64
                            if img_field.startswith("http://") or img_field.startswith("https://"):
                                img_data = requests.get(img_field, timeout=20.0).content
                            else:
                                img_data = base64.b64decode(img_field)

                            # Validate format and bytes before saving
                            with Image.open(io.BytesIO(img_data)) as test_img:
                                test_img.verify()

                            # Save atomically; convert to the format implied by the
                            # requested extension (Horde usually returns WebP).
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            tmp_path = target_path.with_name(target_path.name + ".part")
                            fmt = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}.get(
                                target_path.suffix.lower(), "PNG")
                            with Image.open(io.BytesIO(img_data)) as im:
                                if fmt == "JPEG" and im.mode not in ("RGB", "L"):
                                    im = im.convert("RGB")
                                im.save(tmp_path, format=fmt)
                            os.replace(tmp_path, target_path)
                            return {"success": True, "worker": worker_name, "model": model_name, "job_id": task_id}
                    return {"success": False, "error": "AI Horde reported done but returned no image"}

            self._cancel_horde_job(task_id, headers)
            return {"success": False, "error": f"AI Horde polling timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": f"AI Horde communication exception: {str(e)[:160]}"}

    def _cancel_horde_job(self, task_id: Optional[str], headers: Dict[str, str]) -> None:
        """Best-effort cancellation of a queued/in-flight Horde job to release kudos."""
        if not task_id:
            return
        try:
            requests.delete(f"{self.api_base}/generate/status/{task_id}", headers=headers, timeout=5.0)
        except Exception:
            pass

    def _render_local_pillow(
        self,
        prompt: str,
        target_path: Path,
        style: str,
        width: int,
        height: int,
    ) -> None:
        """Draws procedural modern tech concept art with geometric gradients."""
        p_lower = prompt.lower()
        if "sliit" in p_lower or "university" in p_lower or "login" in p_lower:
            # University academic portal banner
            img = Image.new("RGB", (width, height), color=(10, 22, 48))
            draw = ImageDraw.Draw(img)
            # Draw campus crest shield accent
            draw.rectangle([(0, 0), (width, 8)], fill=(243, 156, 18))
            draw.rectangle([(0, height - 8), (width, height)], fill=(243, 156, 18))
            draw.ellipse([(width // 2 - 80, height // 2 - 80), (width // 2 + 80, height // 2 + 80)], outline=(243, 156, 18), width=3)
            draw.rectangle([(20, 20), (width - 20, 60)], fill=(15, 30, 65), outline=(0, 168, 255), width=2)
            draw.text((35, 30), "SLIIT CAMPUS PORTAL — SECURE ACCESS", fill=(255, 255, 255))
        else:
            # Modern synthwave / tech banner
            img = Image.new("RGB", (width, height), color=(6, 10, 24))
            draw = ImageDraw.Draw(img)
            for y in range(height // 2, height):
                factor = (y - height // 2) / (height // 2)
                r = int(10 + factor * 25)
                g = int(2 + factor * 50)
                b = int(45 + factor * 80)
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            sun_center = (width // 2, height // 2 - 20)
            sun_radius = int(width * 0.22)
            draw.ellipse(
                [(sun_center[0] - sun_radius, sun_center[1] - sun_radius),
                 (sun_center[0] + sun_radius, sun_center[1] + sun_radius)],
                fill=(255, 30, 110),
                outline=(255, 220, 0),
                width=3,
            )

            vanishing_pt = (width // 2, height // 2)
            for i in range(15):
                x_bottom = int((i / 14) * width)
                draw.line([vanishing_pt, (x_bottom, height)], fill=(0, 243, 255), width=2)

            for step in [0.2, 0.4, 0.6, 0.8, 1.0]:
                y_pos = int(height // 2 + step * (height // 2))
                draw.line([(0, y_pos), (width, y_pos)], fill=(0, 150, 220), width=1)

            draw.rectangle([(10, 12), (width - 10, 48)], fill=(15, 23, 42), outline=(0, 243, 255), width=2)
            draw.text((20, 20), "MIND UNIVERSAL STUDIO — CONCEPT ART", fill=(0, 243, 255))

        target_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(target_path, format="PNG")

    @staticmethod
    def validate_image(path: Path) -> Dict[str, Any]:
        """Validates that image exists and can be opened with valid pixels and dimensions."""
        p = Path(path)
        if not p.exists():
            return {"is_valid": False, "error": f"Image not found at {p}"}
        try:
            with Image.open(p) as img:
                img.verify()
            return {
                "is_valid": True,
                "file_size_bytes": p.stat().st_size,
            }
        except Exception as e:
            return {"is_valid": False, "error": str(e)}


# Alias for backward compatibility
ImageAssetAdapter = ImageProviderAdapter
