"""
MIND Design Intelligence Subsystem.
Unifies Native AI Design Reasoning, Generation, Evaluation, and Google Stitch integration.
"""

from multi_brain.design.contracts import (
    ColorTokens,
    ComponentStructure,
    DesignEvaluationReport,
    DesignProviderType,
    DesignResult,
    DesignRevisionRequest,
    DesignSpecification,
    DesignTokens,
    DeviceType,
    EvaluationIssue,
    ScreenSpec,
    TypographyTokens,
    VisualTone,
)
from multi_brain.design.coordinator import DesignProviderCoordinator
from multi_brain.design.memory import DesignMemory
from multi_brain.design.providers.base import BaseDesignProvider
from multi_brain.design.providers.native import MindNativeDesignProvider
from multi_brain.design.providers.stitch import StitchDesignProvider
from multi_brain.design.specification import DesignSpecificationBuilder

__all__ = [
    "BaseDesignProvider",
    "ColorTokens",
    "ComponentStructure",
    "DesignEvaluationReport",
    "DesignMemory",
    "DesignProviderCoordinator",
    "DesignProviderType",
    "DesignResult",
    "DesignRevisionRequest",
    "DesignSpecification",
    "DesignSpecificationBuilder",
    "DesignTokens",
    "DeviceType",
    "EvaluationIssue",
    "MindNativeDesignProvider",
    "ScreenSpec",
    "StitchDesignProvider",
    "TypographyTokens",
    "VisualTone",
]
