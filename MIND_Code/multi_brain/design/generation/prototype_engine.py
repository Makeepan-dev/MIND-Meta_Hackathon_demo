"""
MIND Prototype Engine.
Coordinates multi-screen prototype artifacts, preview links, and interactive states.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from multi_brain.design.contracts import (
    ComponentStructure,
    DesignResult,
    DesignSpecification,
)
from multi_brain.design.generation.generator import DesignGenerator

logger = logging.getLogger("mind.multi_brain.design.prototype")


class PrototypeEngine:
    """Manages the creation, linking, and local disk paths of prototype artifacts."""

    def __init__(self) -> None:
        self.generator = DesignGenerator()

    def build_prototype(
        self,
        spec: DesignSpecification,
        output_dir: Path,
        version: int = 1,
    ) -> DesignResult:
        """Constructs a fully functional interactive prototype and registers its file artifacts."""
        html, css, design_md, site_md, components = self.generator.generate(
            spec=spec,
            output_dir=output_dir,
            version=version,
        )

        html_file = output_dir / "index.html"
        preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"

        # Build screen map
        screens: Dict[str, str] = {
            s.screen_id: html for s in spec.screens
        }

        # Check for screenshot if already captured
        screenshot_path = output_dir / "preview.png"
        screenshot_file = str(screenshot_path) if screenshot_path.exists() else None

        return DesignResult(
            provider="native",
            success=True,
            specification=spec,
            primary_html=html,
            style_css=css,
            design_md=design_md,
            site_md=site_md,
            preview_file=str(html_file),
            preview_url=preview_url,
            version=version,
            screens=screens,
            screenshot_file=screenshot_file,
            components=components,
            metadata={
                "engine": "MIND Native Design Intelligence",
                "layout_model": "CSS Grid / Flexbox",
                "screen_count": len(spec.screens),
            },
        )
