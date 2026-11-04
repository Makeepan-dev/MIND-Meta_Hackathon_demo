"""Project Inspector Tool.

Inspects an existing or target game workspace before modifying or generating files,
providing a non-destructive census of existing content and readiness checks.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Union

from .workspace_files import SafeWorkspaceManager


class ProjectInspector:
    """Read-only inspector for game project directories."""

    def __init__(self, workspace_or_path: Union[SafeWorkspaceManager, Path, str]) -> None:
        if isinstance(workspace_or_path, SafeWorkspaceManager):
            self.workspace = workspace_or_path
        else:
            p = Path(workspace_or_path).resolve()
            self.workspace = SafeWorkspaceManager(p)

    def inspect(self, sub_dir: Union[str, Path] = "") -> Dict[str, Any]:
        """Alias for inspect_project."""
        return self.inspect_project(sub_dir)

    def inspect_project(self, sub_dir: Union[str, Path] = "") -> Dict[str, Any]:
        """Performs a comprehensive read-only audit of the target project directory."""
        files = self.workspace.list_files(sub_dir=sub_dir)

        total_bytes = sum(
            f.stat().st_size if isinstance(f, Path) else f.get("size_bytes", 0)
            for f in files
        )
        file_extensions: Dict[str, int] = {}
        for f in files:
            name = f.name if isinstance(f, Path) else f.get("name", "")
            ext = Path(name).suffix.lower() or ".no_ext"
            file_extensions[ext] = file_extensions.get(ext, 0) + 1

        has_index_html = any(
            (f.name if isinstance(f, Path) else f.get("name", "")).lower() == "index.html"
            for f in files
        )
        has_assets = any(
            Path(f.name if isinstance(f, Path) else f.get("name", "")).suffix.lower()
            in [".glb", ".gltf", ".obj", ".png", ".jpg", ".wav", ".mp3"]
            for f in files
        )

        return {
            "workspace_root": str(self.workspace.workspace_root),
            "target_sub_dir": str(sub_dir),
            "total_files": len(files),
            "total_size_bytes": total_bytes,
            "file_types": file_extensions,
            "has_index_html": has_index_html,
            "has_assets": has_assets,
            "is_clean_directory": len(files) == 0,
        }
