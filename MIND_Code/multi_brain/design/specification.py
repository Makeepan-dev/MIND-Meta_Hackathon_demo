"""
MIND Design Specification Builder and Validator.
Transforms user natural language requests into structured, validated DesignSpecification contracts.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from multi_brain.design.contracts import (
    ColorTokens,
    DesignSpecification,
    DesignTokens,
    DeviceType,
    ScreenSpec,
    TypographyTokens,
    VisualTone,
)


class DesignSpecificationBuilder:
    """Builds and validates typed DesignSpecifications."""

    @staticmethod
    def infer_device_type(prompt: str) -> DeviceType:
        p = prompt.lower()
        if any(w in p for w in ["mobile", "phone", "iphone", "android", "ios"]):
            return DeviceType.MOBILE
        if "tablet" in p or "ipad" in p:
            return DeviceType.TABLET
        return DeviceType.DESKTOP

    @staticmethod
    def infer_visual_tone(prompt: str) -> VisualTone:
        p = prompt.lower()
        if any(w in p for w in ["cyber", "neon", "matrix", "dark mode", "futuristic", "telemetry", "ai"]):
            return VisualTone.CYBERPUNK
        if any(w in p for w in ["minimal", "clean", "simple", "swiss", "monochrome"]):
            return VisualTone.MINIMALIST
        if any(w in p for w in ["enterprise", "corporate", "saas", "dashboard", "b2b", "analytics"]):
            return VisualTone.ENTERPRISE
        if any(w in p for w in ["art", "creative", "portfolio", "studio", "gallery"]):
            return VisualTone.CREATIVE
        if any(w in p for w in ["blog", "editorial", "magazine", "reading", "news"]):
            return VisualTone.EDITORIAL
        return VisualTone.MODERN

    @classmethod
    def from_prompt(cls, prompt: str) -> DesignSpecification:
        """Constructs a complete, typed DesignSpecification from raw prompt."""
        clean_title = (
            prompt.replace("create a", "")
            .replace("build a", "")
            .replace("generate a", "")
            .replace("design a", "")
            .strip()
            .title()
        ) or "MIND Web Application"

        device = cls.infer_device_type(prompt)
        tone = cls.infer_visual_tone(prompt)

        # Tone-specific tokens
        colors = ColorTokens()
        if tone == VisualTone.CYBERPUNK:
            colors = ColorTokens(
                primary="#00F5FF",
                secondary="#10B981",
                accent="#FF0077",
                background="#050811",
                surface="#101A2C",
                text_primary="#EAF7FF",
                text_secondary="#8095AC",
                border="#1B2A47",
            )
        elif tone == VisualTone.MINIMALIST:
            colors = ColorTokens(
                primary="#111827",
                secondary="#4B5563",
                accent="#6B7280",
                background="#FFFFFF",
                surface="#F9FAFB",
                text_primary="#111827",
                text_secondary="#6B7280",
                border="#E5E7EB",
            )
        elif tone == VisualTone.ENTERPRISE:
            colors = ColorTokens(
                primary="#2563EB",
                secondary="#0D9488",
                accent="#4F46E5",
                background="#0F172A",
                surface="#1E293B",
                text_primary="#F8FAFC",
                text_secondary="#94A3B8",
                border="#334155",
            )
        elif tone == VisualTone.CREATIVE:
            colors = ColorTokens(
                primary="#8B5CF6",
                secondary="#EC4899",
                accent="#F59E0B",
                background="#090514",
                surface="#19102E",
                text_primary="#FAF5FF",
                text_secondary="#A78BFA",
                border="#3B2668",
            )

        tokens = DesignTokens(
            colors=colors,
            typography=TypographyTokens(),
            spacing_unit=8,
            border_radius="10px" if tone != VisualTone.MINIMALIST else "4px",
        )

        # Standard Multi-Screen Journey
        screens = [
            ScreenSpec(
                screen_id="landing",
                title=f"{clean_title} — Overview",
                route="/",
                purpose=f"Primary showcase and core user proposition for {clean_title}",
                components=["navbar", "hero", "metrics_strip", "card_grid", "footer"],
                layout_type="responsive_grid",
                user_journey_step="Discovery & Engagement",
            ),
            ScreenSpec(
                screen_id="features",
                title=f"{clean_title} — Capabilities & Architecture",
                route="/features",
                purpose="Detailed breakdown of technical modules and workflows",
                components=["navbar", "feature_showcase", "cta_strip", "footer"],
                layout_type="split_detail",
                user_journey_step="Evaluation & Deep Dive",
            ),
            ScreenSpec(
                screen_id="console",
                title=f"{clean_title} — Interactive Console",
                route="/app",
                purpose="Operational dashboard and live telemetry controls",
                components=["navbar", "telemetry_hud", "action_panel", "footer"],
                layout_type="dashboard_grid",
                user_journey_step="Execution & Interaction",
            ),
        ]

        navigation_flow = [
            {"from": "landing", "to": "features", "action": "Click 'Explore Architecture'"},
            {"from": "features", "to": "console", "action": "Click 'Launch System'"},
            {"from": "console", "to": "landing", "action": "Click Brand Logo / Return Home"},
        ]

        required_components = [
            "GlobalNavbar",
            "HeroBanner",
            "TelemetryMetricGrid",
            "InteractiveShowcaseCard",
            "ActionDock",
            "SystemFooter",
        ]

        accessibility = [
            "WCAG 2.1 AA Contrast Ratio (minimum 4.5:1 for body, 3:1 for large headings)",
            "Keyboard navigability with visible focus indicators",
            "Semantic landmark roles (header, nav, main, section, footer)",
            "Screen reader accessible ARIA attributes",
        ]

        technical_constraints = [
            "Zero external bundle requirement — self-contained responsive CSS/JS",
            "Tailwind CSS compatibility via CDN or pure embedded semantic stylesheet",
            "Responsive breakpoints: Mobile (<640px), Tablet (640-1024px), Desktop (>1024px)",
            "QtWebEngine compatible without reliance on modern unsupported Web APIs",
        ]

        return DesignSpecification(
            project_name=clean_title,
            purpose=f"Deliver a high-impact, production-grade interface for: {prompt}",
            target_audience="General professional and technical users",
            raw_prompt=prompt,
            device_type=device,
            visual_tone=tone,
            screens=screens,
            navigation_flow=navigation_flow,
            tokens=tokens,
            required_components=required_components,
            accessibility_requirements=accessibility,
            technical_constraints=technical_constraints,
        )

    @classmethod
    def validate(cls, spec: DesignSpecification) -> List[str]:
        """Validates that a DesignSpecification satisfies all architectural constraints."""
        errors: List[str] = []
        if not spec.project_name.strip():
            errors.append("Specification project_name must not be empty.")
        if not spec.screens:
            errors.append("Specification must define at least one screen.")
        if not spec.tokens.colors.primary:
            errors.append("Design tokens must define a primary color.")
        if not spec.tokens.colors.background:
            errors.append("Design tokens must define a background color.")
        return errors
