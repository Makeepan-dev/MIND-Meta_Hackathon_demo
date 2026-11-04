"""
MIND Design Revision Subsystem.
Executes surgical, targeted modifications to components, styling tokens, and layout.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

from multi_brain.design.contracts import (
    ColorTokens,
    DesignResult,
    DesignRevisionRequest,
    DesignTokens,
)
from multi_brain.design.evaluation.evaluator import VisualEvaluator
from multi_brain.design.generation.prototype_engine import PrototypeEngine

logger = logging.getLogger("mind.multi_brain.design.revision")


class DesignRevision:
    """Applies targeted modifications without regenerating the entire design from scratch."""

    def __init__(self) -> None:
        self.prototype_engine = PrototypeEngine()
        self.evaluator = VisualEvaluator()

    def revise(
        self,
        previous_result: DesignResult,
        revision_request: DesignRevisionRequest,
        output_dir: Path,
    ) -> DesignResult:
        """
        Surgically alters tokens and affected components based on revision feedback,
        updates output directory, and evaluates the revised result.
        """
        logger.info("DesignRevision applying: '%s'...", revision_request.feedback)
        feedback = revision_request.feedback.lower()
        new_version = revision_request.new_version

        # 1. Clone specification
        spec = previous_result.specification
        tokens = spec.tokens
        colors = tokens.colors

        # Detect Color Revisions
        if "green" in feedback or "emerald" in feedback:
            colors.primary = "#10B981"
        elif "purple" in feedback or "violet" in feedback:
            colors.primary = "#8B5CF6"
        elif "blue" in feedback or "ocean" in feedback:
            colors.primary = "#0284C7"
        elif "red" in feedback or "crimson" in feedback:
            colors.primary = "#DC2626"
        elif "amber" in feedback or "gold" in feedback or "yellow" in feedback:
            colors.primary = "#F59E0B"

        # Apply any explicit token overrides
        for k, v in revision_request.token_overrides.items():
            if hasattr(colors, k):
                setattr(colors, k, v)

        # 2. Re-generate prototype with updated tokens
        new_result = self.prototype_engine.build_prototype(
            spec=spec,
            output_dir=output_dir,
            version=new_version,
        )

        # Apply layout overrides if requested in feedback
        if "smaller" in feedback or "compact" in feedback or "narrow" in feedback:
            css_file = output_dir / "style.css"
            if css_file.exists():
                curr_css = css_file.read_text(encoding="utf-8")
                updated_css = curr_css + "\n/* Surgical Layout Revision */\n.navbar { padding: 8px 20px; }\n"
                css_file.write_text(updated_css, encoding="utf-8")
                new_result.style_css = updated_css

        # 3. Add revision banner into primary_html for user visual confirmation
        revision_banner_html = f"""
  <div style="background: rgba(255,255,255,0.04); border-left: 4px solid var(--primary); padding: 12px 18px; margin: 20px auto; max-width: 860px; text-align: left; border-radius: var(--radius);">
    <strong style="color:var(--primary); font-size:12px; text-transform:uppercase; letter-spacing:1px;">Applied Revision:</strong>
    <p style="font-size:14px; color:var(--text-main); margin-top:4px;">{revision_request.feedback}</p>
  </div>
"""
        updated_html = new_result.primary_html.replace(
            '<main class="app-container">',
            f'<main class="app-container">\n{revision_banner_html}'
        )
        (output_dir / "index.html").write_text(updated_html, encoding="utf-8")
        new_result.primary_html = updated_html

        # 4. Run automated visual evaluation on the revised prototype
        eval_report = self.evaluator.evaluate(new_result)
        new_result.evaluation = eval_report

        return new_result
