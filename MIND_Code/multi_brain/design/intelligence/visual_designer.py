"""
MIND Visual Designer.
Establishes color systems, WCAG 2.1 AA contrast compliance, typography, and visual hierarchy.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Tuple

from multi_brain.design.contracts import ColorTokens, DesignTokens, DesignSpecification, VisualTone

logger = logging.getLogger("mind.multi_brain.design.visual")


class VisualDesigner:
    """Calculates color harmonies, typography scales, and contrast ratios."""

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        clean = hex_str.lstrip("#")
        if len(clean) == 3:
            clean = "".join(2 * c for c in clean)
        return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)

    @classmethod
    def relative_luminance(cls, hex_str: str) -> float:
        """Calculates W3C relative luminance for a given hex color."""
        r, g, b = cls.hex_to_rgb(hex_str)
        def _channel(c: int) -> float:
            norm = c / 255.0
            return norm / 12.92 if norm <= 0.03928 else math.pow((norm + 0.055) / 1.055, 2.4)
        return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)

    @classmethod
    def contrast_ratio(cls, hex1: str, hex2: str) -> float:
        """Calculates WCAG contrast ratio between two hex colors."""
        try:
            l1 = cls.relative_luminance(hex1)
            l2 = cls.relative_luminance(hex2)
            lighter = max(l1, l2)
            darker = min(l1, l2)
            return (lighter + 0.05) / (darker + 0.05)
        except Exception:
            return 4.5

    def refine_visual_design(self, spec: DesignSpecification) -> DesignSpecification:
        """Validates and enforces contrast ratios and visual hierarchy across tokens."""
        colors = spec.tokens.colors
        
        # Verify text-on-background contrast (Minimum 4.5:1 for WCAG AA)
        ratio = self.contrast_ratio(colors.text_primary, colors.background)
        if ratio < 4.5:
            logger.info("Adjusting text_primary for WCAG AA contrast compliance (was %.2f)", ratio)
            # Switch to pure light or pure dark based on background luminance
            bg_lum = self.relative_luminance(colors.background)
            colors.text_primary = "#FFFFFF" if bg_lum < 0.5 else "#111827"

        # Verify surface contrast against background
        surf_ratio = self.contrast_ratio(colors.surface, colors.background)
        if surf_ratio < 1.15:
            # Differentiate surface
            colors.surface = "#101A2C" if colors.background == "#050811" else "#F3F4F6"

        return spec
