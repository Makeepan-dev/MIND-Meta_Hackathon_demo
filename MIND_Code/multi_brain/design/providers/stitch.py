"""
Google Stitch Design Provider.
Adapts Google Stitch cloud design engine into MIND's shared design provider interface.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from multi_brain.design.contracts import (
    DesignResult,
    DesignRevisionRequest,
    DesignSpecification,
)
from multi_brain.design.evaluation.evaluator import VisualEvaluator
from multi_brain.design.providers.base import BaseDesignProvider
from multi_brain.stitch.stitch_client import StitchClient

logger = logging.getLogger("mind.multi_brain.design.providers.stitch")


class StitchDesignProvider(BaseDesignProvider):
    """External specialist design provider integrating Google Stitch."""

    def __init__(self, stitch_client: Optional[StitchClient] = None) -> None:
        self.stitch_client = stitch_client or StitchClient()
        self.evaluator = VisualEvaluator()

    def generate_design(
        self,
        specification: DesignSpecification,
        output_dir: Path,
    ) -> DesignResult:
        """Invokes Google Stitch to generate Tailwind interface and normalizes output."""
        logger.info("StitchDesignProvider generating screen for '%s'...", specification.project_name)
        
        # Call Stitch
        screen_data = self.stitch_client.generate_screen(
            prompt=specification.raw_prompt,
            device_type=specification.device_type.value,
        )

        # Persist assets
        saved = self.stitch_client.save_screen_assets(
            screen_data=screen_data,
            output_dir=output_dir,
            prompt=specification.raw_prompt,
        )

        html_file = Path(saved.html_path)
        css_file = output_dir / "style.css"
        if not css_file.exists():
            c = specification.tokens.colors
            css_file.write_text(
                f"/* Google Stitch Design Tokens */\n:root {{\n  --primary: {c.primary};\n  --bg-dark: {c.background};\n}}\n",
                encoding="utf-8",
            )

        preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"
        
        result = DesignResult(
            provider="stitch",
            success=True,
            specification=specification,
            primary_html=saved.html_content,
            style_css=css_file.read_text(encoding="utf-8") if css_file.exists() else "",
            design_md=Path(saved.design_md_path).read_text(encoding="utf-8") if saved.design_md_path else "",
            site_md=Path(saved.site_md_path).read_text(encoding="utf-8") if saved.site_md_path else "",
            preview_file=str(html_file),
            preview_url=preview_url,
            version=1,
            screenshot_file=saved.screenshot_path,
            metadata={
                "stitch_screen_id": saved.screen_id,
                "stitch_project_id": saved.project_id,
                "stitch_design_system_id": saved.design_system_id,
            },
        )

        # Evaluate result
        result.evaluation = self.evaluator.evaluate(result)
        return result

    def revise_design(
        self,
        previous_result: DesignResult,
        revision: DesignRevisionRequest,
        output_dir: Path,
    ) -> DesignResult:
        """Applies revision to existing Stitch screen."""
        logger.info("StitchDesignProvider revising screen: '%s'...", revision.feedback)
        screen_id = previous_result.metadata.get("stitch_screen_id", "")
        project_id = previous_result.metadata.get("stitch_project_id")

        edit_res = self.stitch_client.edit_screen(
            screen_id=screen_id,
            prompt=revision.feedback,
            project_id=project_id,
            device_type=previous_result.specification.device_type.value,
        )
        screens = edit_res.get("screens", [])
        screen_data = screens[0] if screens else edit_res

        saved = self.stitch_client.save_screen_assets(
            screen_data=screen_data,
            output_dir=output_dir,
            prompt=revision.feedback,
        )

        html_file = Path(saved.html_path)
        css_file = output_dir / "style.css"
        
        fb = revision.feedback.lower()
        color = "#00F5FF"
        if "green" in fb or "emerald" in fb:
            color = "#10B981"
        elif "purple" in fb or "violet" in fb:
            color = "#8B5CF6"
        elif "blue" in fb or "ocean" in fb:
            color = "#0284C7"
        elif "crimson" in fb or "red" in fb:
            color = "#DC2626"

        nav_padding = "8px 20px" if any(w in fb for w in ["smaller", "compact", "narrow"]) else "16px 32px"
        css_file.write_text(
            f"/* Google Stitch Design Tokens v{revision.new_version} — Revised: {revision.feedback} */\n"
            f":root {{\n  --primary: {color};\n  --primary-color: {color};\n  --bg-dark: #050811;\n}}\n"
            f".navbar {{\n  padding: {nav_padding};\n}}\n",
            encoding="utf-8",
        )

        preview_url = f"file:///{str(html_file).replace(os.sep, '/')}"

        meta = dict(previous_result.metadata)
        meta["stitch_screen_id"] = saved.screen_id
        meta["revision_feedback"] = revision.feedback

        result = DesignResult(
            provider="stitch",
            success=True,
            specification=previous_result.specification,
            primary_html=saved.html_content,
            style_css=css_file.read_text(encoding="utf-8") if css_file.exists() else "",
            design_md=Path(saved.design_md_path).read_text(encoding="utf-8") if saved.design_md_path else "",
            site_md=Path(saved.site_md_path).read_text(encoding="utf-8") if saved.site_md_path else "",
            preview_file=str(html_file),
            preview_url=preview_url,
            version=revision.new_version,
            screenshot_file=saved.screenshot_path,
            metadata=meta,
        )

        result.evaluation = self.evaluator.evaluate(result)
        return result

    def is_available(self) -> bool:
        """Returns True if Stitch is configured and accessible."""
        return self.stitch_client.is_available()

    def get_provider_name(self) -> str:
        return "stitch"
