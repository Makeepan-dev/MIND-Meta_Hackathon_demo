"""
MIND — Asset Storage & Provenance Manager (Stage E)
Organizes generated character assets, maintains persistent metadata manifests,
and links prompts, images, task IDs, and output 3D models.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional


class AssetStorageManager:
    """Manages asset provenance, unique IDs, metadata manifests, and directory organization."""

    def __init__(self, workspace_root: Optional[str] = None) -> None:
        default_root = Path(__file__).resolve().parent.parent.parent.parent
        self.root = Path(workspace_root or default_root)
        self.assets_dir = self.root / "Workspace" / "generated_media"
        self.manifest_file = self.assets_dir / "asset_registry.json"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def register_asset(
        self,
        user_request: str,
        prompt_data: Dict[str, Any],
        image_result: Dict[str, Any],
        threed_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Creates a permanent manifest entry associating the request, prompt,
        concept image, and 3D model asset with full provenance.
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        asset_id = f"asset_{timestamp}_{abs(hash(user_request)) % 10000}"

        manifest = {
            "asset_id": asset_id,
            "created_at": time.time(),
            "formatted_time": time.ctime(),
            "user_request": user_request,
            "prompt": prompt_data.get("prompt"),
            "style": prompt_data.get("style"),
            "pose": prompt_data.get("pose"),
            "concept_image": {
                "path": image_result.get("image_path"),
                "provider": image_result.get("provider"),
                "dimensions": image_result.get("dimensions"),
                "file_size": image_result.get("file_size_bytes"),
                "verified": image_result.get("verified", False),
            },
            "threed_model": {
                "path": threed_result.get("model_path"),
                "alt_path": threed_result.get("alt_format_path"),
                "format": threed_result.get("format"),
                "provider": threed_result.get("provider"),
                "task_id": threed_result.get("task_id"),
                "file_size": threed_result.get("file_size_bytes"),
                "vertex_count": threed_result.get("vertex_count"),
                "face_count": threed_result.get("face_count"),
            },
            "status": "COMPLETED",
            "verified": True,
        }

        # Save individual asset manifest
        manifest_path = self.assets_dir / f"{asset_id}_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Update central asset index
        self._append_to_central_registry(manifest)
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def _append_to_central_registry(self, manifest: Dict[str, Any]) -> None:
        """Appends asset entry to central registry JSON file."""
        entries = []
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                entries = []

        entries.append({
            "asset_id": manifest["asset_id"],
            "user_request": manifest["user_request"],
            "image": manifest["concept_image"]["path"],
            "model": manifest["threed_model"]["path"],
            "time": manifest["formatted_time"],
        })

        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
