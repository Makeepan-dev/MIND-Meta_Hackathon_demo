"""
MIND Design Subsystem Shared Contracts.
Defines provider-independent specifications, design results, design tokens,
evaluation reports, and revision requests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class DesignProviderType(str, Enum):
    AUTO = "auto"
    NATIVE = "native"
    STITCH = "stitch"


class DeviceType(str, Enum):
    DESKTOP = "DESKTOP"
    MOBILE = "MOBILE"
    TABLET = "TABLET"


class VisualTone(str, Enum):
    CYBERPUNK = "cyberpunk"
    MINIMALIST = "minimalist"
    ENTERPRISE = "enterprise"
    CREATIVE = "creative"
    MODERN = "modern"
    EDITORIAL = "editorial"


@dataclass
class ColorTokens:
    primary: str = "#00F5FF"
    secondary: str = "#10B981"
    accent: str = "#8B5CF6"
    background: str = "#050811"
    surface: str = "#101A2C"
    text_primary: str = "#EAF7FF"
    text_secondary: str = "#8095AC"
    border: str = "#1B2A47"

    def to_dict(self) -> Dict[str, str]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "accent": self.accent,
            "background": self.background,
            "surface": self.surface,
            "text_primary": self.text_primary,
            "text_secondary": self.text_secondary,
            "border": self.border,
        }


@dataclass
class TypographyTokens:
    font_family_heading: str = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    font_family_body: str = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    scale_h1: str = "36px"
    scale_h2: str = "24px"
    scale_body: str = "15px"

    def to_dict(self) -> Dict[str, str]:
        return {
            "font_family_heading": self.font_family_heading,
            "font_family_body": self.font_family_body,
            "scale_h1": self.scale_h1,
            "scale_h2": self.scale_h2,
            "scale_body": self.scale_body,
        }


@dataclass
class DesignTokens:
    colors: ColorTokens = field(default_factory=ColorTokens)
    typography: TypographyTokens = field(default_factory=TypographyTokens)
    spacing_unit: int = 8
    border_radius: str = "8px"
    box_shadow: str = "0 4px 20px rgba(0, 245, 255, 0.1)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "colors": self.colors.to_dict(),
            "typography": self.typography.to_dict(),
            "spacing_unit": self.spacing_unit,
            "border_radius": self.border_radius,
            "box_shadow": self.box_shadow,
        }


@dataclass
class ScreenSpec:
    screen_id: str
    title: str
    route: str
    purpose: str
    components: List[str] = field(default_factory=list)
    layout_type: str = "grid_hero"
    user_journey_step: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "title": self.title,
            "route": self.route,
            "purpose": self.purpose,
            "components": self.components,
            "layout_type": self.layout_type,
            "user_journey_step": self.user_journey_step,
        }


@dataclass
class DesignSpecification:
    """Comprehensive design requirements consumed by both Native and Stitch providers."""
    project_name: str
    purpose: str
    target_audience: str
    raw_prompt: str
    device_type: DeviceType = DeviceType.DESKTOP
    visual_tone: VisualTone = VisualTone.CYBERPUNK
    screens: List[ScreenSpec] = field(default_factory=list)
    navigation_flow: List[Dict[str, str]] = field(default_factory=list)
    tokens: DesignTokens = field(default_factory=DesignTokens)
    required_components: List[str] = field(default_factory=list)
    accessibility_requirements: List[str] = field(default_factory=list)
    technical_constraints: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "purpose": self.purpose,
            "target_audience": self.target_audience,
            "raw_prompt": self.raw_prompt,
            "device_type": self.device_type.value,
            "visual_tone": self.visual_tone.value,
            "screens": [s.to_dict() for s in self.screens],
            "navigation_flow": self.navigation_flow,
            "tokens": self.tokens.to_dict(),
            "required_components": self.required_components,
            "accessibility_requirements": self.accessibility_requirements,
            "technical_constraints": self.technical_constraints,
            "created_at": self.created_at,
        }


@dataclass
class ComponentStructure:
    component_id: str
    name: str
    category: str
    html_snippet: str
    css_classes: str = ""
    responsive_rules: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "category": self.category,
            "html_snippet": self.html_snippet,
            "css_classes": self.css_classes,
            "responsive_rules": self.responsive_rules,
        }


@dataclass
class EvaluationIssue:
    issue_id: str
    category: str  # hierarchy, spacing, contrast, accessibility, responsive, dom
    severity: str  # CRITICAL, WARNING, SUGGESTION
    description: str
    affected_element: str
    suggested_fix: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "issue_id": self.issue_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "affected_element": self.affected_element,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class DesignEvaluationReport:
    is_valid: bool
    overall_score: float  # 0.0 - 1.0
    hierarchy_score: float
    contrast_score: float
    responsiveness_score: float
    accessibility_score: float
    issues: List[EvaluationIssue] = field(default_factory=list)
    screenshot_analyzed: bool = False
    critique_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "overall_score": self.overall_score,
            "hierarchy_score": self.hierarchy_score,
            "contrast_score": self.contrast_score,
            "responsiveness_score": self.responsiveness_score,
            "accessibility_score": self.accessibility_score,
            "issues": [i.to_dict() for i in self.issues],
            "screenshot_analyzed": self.screenshot_analyzed,
            "critique_summary": self.critique_summary,
        }


@dataclass
class DesignRevisionRequest:
    feedback: str
    target_screen_id: Optional[str] = None
    target_component_id: Optional[str] = None
    token_overrides: Dict[str, Any] = field(default_factory=dict)
    new_version: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedback": self.feedback,
            "target_screen_id": self.target_screen_id,
            "target_component_id": self.target_component_id,
            "token_overrides": self.token_overrides,
            "new_version": self.new_version,
        }


@dataclass
class DesignResult:
    """Standardized output produced by any design provider (Native or Stitch)."""
    provider: str  # "native" or "stitch"
    success: bool
    specification: DesignSpecification
    primary_html: str
    style_css: str
    design_md: str
    site_md: str
    preview_file: str
    preview_url: str
    version: int = 1
    screens: Dict[str, str] = field(default_factory=dict)
    screenshot_file: Optional[str] = None
    components: List[ComponentStructure] = field(default_factory=list)
    evaluation: Optional[DesignEvaluationReport] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "success": self.success,
            "specification": self.specification.to_dict(),
            "primary_html": self.primary_html,
            "style_css": self.style_css,
            "design_md": self.design_md,
            "site_md": self.site_md,
            "preview_file": self.preview_file,
            "preview_url": self.preview_url,
            "version": self.version,
            "screens": list(self.screens.keys()),
            "screenshot_file": self.screenshot_file,
            "components": [c.to_dict() for c in self.components],
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }
