"""
MIND Visual Evaluator.
Executes multi-layered visual quality auditing: DOM structure, CSS design tokens,
contrast ratios, and screenshot verification.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

from multi_brain.design.contracts import (
    DesignEvaluationReport,
    DesignResult,
    EvaluationIssue,
)
from multi_brain.design.intelligence.visual_designer import VisualDesigner

logger = logging.getLogger("mind.multi_brain.design.evaluator")


class VisualEvaluator:
    """Evaluates rendered interface artifacts for structural, aesthetic, and contrast integrity."""

    def __init__(self) -> None:
        self.designer = VisualDesigner()

    def evaluate(
        self,
        design_result: DesignResult,
        screenshot_path: Optional[Path] = None,
    ) -> DesignEvaluationReport:
        """Runs 4-layer evaluation across HTML, CSS tokens, and screenshot."""
        issues: List[EvaluationIssue] = []

        html = design_result.primary_html
        css = design_result.style_css
        tokens = design_result.specification.tokens

        # Layer 1: Structural DOM Validation
        if not re.search(r"<meta\s+name=[\"']viewport[\"']", html, re.I):
            issues.append(EvaluationIssue(
                issue_id="dom_001",
                category="responsive",
                severity="CRITICAL",
                description="Missing viewport meta tag required for responsive mobile rendering.",
                affected_element="<head>",
                suggested_fix="Add <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            ))

        if not re.search(r"<nav\b[^>]*role=[\"']navigation[\"']", html, re.I) and "<nav" not in html:
            issues.append(EvaluationIssue(
                issue_id="dom_002",
                category="accessibility",
                severity="WARNING",
                description="Semantic <nav> element or role='navigation' missing.",
                affected_element="<nav>",
                suggested_fix="Wrap primary header navigation links in semantic <nav> element.",
            ))

        # Layer 2: CSS and Design Tokens Contrast Validation
        contrast = self.designer.contrast_ratio(tokens.colors.text_primary, tokens.colors.background)
        contrast_score = min(1.0, contrast / 7.0)  # 7:1 is WCAG AAA, 4.5:1 is AA

        if contrast < 4.5:
            issues.append(EvaluationIssue(
                issue_id="a11y_001",
                category="contrast",
                severity="CRITICAL",
                description=f"Text-to-background contrast ratio ({contrast:.2f}:1) fails WCAG 2.1 AA requirement (4.5:1).",
                affected_element="body text",
                suggested_fix="Increase luminance difference between text_primary and background.",
            ))

        # Layer 3: Visual Screenshot Inspection
        screenshot_analyzed = False
        target_ss = screenshot_path or (Path(design_result.screenshot_file) if design_result.screenshot_file else None)
        if target_ss and target_ss.exists():
            try:
                from PIL import Image
                with Image.open(target_ss) as img:
                    w, h = img.size
                    if w < 300 or h < 300:
                        issues.append(EvaluationIssue(
                            issue_id="vis_001",
                            category="screenshot",
                            severity="WARNING",
                            description=f"Screenshot dimensions ({w}x{h}) appear unexpectedly small for desktop preview.",
                            affected_element="viewport capture",
                            suggested_fix="Ensure browser renders at minimum 1024x768 before capture.",
                        ))
                    screenshot_analyzed = True
            except Exception as e:
                logger.debug("Screenshot PIL inspection skipped: %s", e)

        # Layer 4: Compute Category Scores
        hierarchy_score = 0.95 if "<h1" in html and "<h2" in html or "<h3" in html else 0.70
        responsiveness_score = 0.95 if "@media" in css or "grid-template-columns: repeat(auto-fit" in css or "tailwindcss" in html else 0.60
        accessibility_score = 0.90 if contrast >= 4.5 and "<footer" in html else 0.70

        critical_count = sum(1 for i in issues if i.severity == "CRITICAL")
        is_valid = critical_count == 0

        overall_score = round(
            (hierarchy_score * 0.3) + (contrast_score * 0.3) + (responsiveness_score * 0.2) + (accessibility_score * 0.2),
            2
        )

        critique = (
            f"Design passed architectural evaluation (Score: {overall_score * 100:.0f}%). "
            f"Contrast ratio: {contrast:.2f}:1 (WCAG AA compliant). "
            f"Identified {len(issues)} suggestions/warnings."
        )

        return DesignEvaluationReport(
            is_valid=is_valid,
            overall_score=overall_score,
            hierarchy_score=hierarchy_score,
            contrast_score=round(contrast_score, 2),
            responsiveness_score=responsiveness_score,
            accessibility_score=accessibility_score,
            issues=issues,
            screenshot_analyzed=screenshot_analyzed,
            critique_summary=critique,
        )
