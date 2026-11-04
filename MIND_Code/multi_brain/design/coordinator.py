"""
MIND Design Provider Coordinator.
Orchestrates design generation and revision between Native MIND and Google Stitch providers.
Supports 'Auto', 'Native', and 'Stitch' execution modes with automatic graceful fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Union

from multi_brain.design.contracts import (
    DesignProviderType,
    DesignResult,
    DesignRevisionRequest,
    DesignSpecification,
)
from multi_brain.design.memory import DesignMemory
from multi_brain.design.providers.base import BaseDesignProvider
from multi_brain.design.providers.native import MindNativeDesignProvider
from multi_brain.design.providers.stitch import StitchDesignProvider
from multi_brain.design.specification import DesignSpecificationBuilder

logger = logging.getLogger("mind.multi_brain.design.coordinator")


class DesignProviderCoordinator:
    """Coordinates design requests across Native MIND and Google Stitch providers."""

    def __init__(
        self,
        native_provider: Optional[BaseDesignProvider] = None,
        stitch_provider: Optional[BaseDesignProvider] = None,
        memory: Optional[DesignMemory] = None,
        default_mode: DesignProviderType = DesignProviderType.AUTO,
    ) -> None:
        self.native_provider = native_provider or MindNativeDesignProvider()
        self.stitch_provider = stitch_provider or StitchDesignProvider()
        self.memory = memory or DesignMemory()
        self.default_mode = default_mode

    def generate_design(
        self,
        specification_or_prompt: Union[DesignSpecification, str],
        output_dir: Path,
        mode: Optional[DesignProviderType] = None,
    ) -> DesignResult:
        """
        Generates a design prototype through the requested provider mode.
        Auto: Prefers Stitch if configured; automatically falls back to Native.
        Native: Strictly executes MIND Native Design Engine.
        Stitch: Strictly executes Google Stitch.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        spec = (
            specification_or_prompt
            if isinstance(specification_or_prompt, DesignSpecification)
            else DesignSpecificationBuilder.from_prompt(specification_or_prompt)
        )

        target_mode = mode or self.default_mode

        if target_mode == DesignProviderType.NATIVE:
            logger.info("Executing via MIND Native Design Engine (Explicit)...")
            return self.native_provider.generate_design(spec, output_dir)

        elif target_mode == DesignProviderType.STITCH:
            if not self.stitch_provider.is_available():
                raise RuntimeError(
                    "Google Stitch provider is not available or STITCH_API_KEY is not configured."
                )
            logger.info("Executing via Google Stitch Engine (Explicit)...")
            return self.stitch_provider.generate_design(spec, output_dir)

        else:  # AUTO mode
            if self.stitch_provider.is_available():
                try:
                    logger.info("Auto mode: Attempting Google Stitch Engine...")
                    res = self.stitch_provider.generate_design(spec, output_dir)
                    if res and res.success and res.primary_html and len(res.primary_html.strip()) >= 50:
                        return res
                    logger.warning("Stitch provider produced empty or incomplete HTML. Falling back to Native Engine.")
                except Exception as e:
                    logger.warning("Stitch provider generation failed (%s). Falling back to Native Engine.", e)

            logger.info("Auto mode: Executing MIND Native Design Engine...")
            return self.native_provider.generate_design(spec, output_dir)

    def revise_design(
        self,
        previous_result: DesignResult,
        revision_request: DesignRevisionRequest,
        output_dir: Path,
    ) -> DesignResult:
        """
        Applies revision through the originating provider or native fallback.
        Preserves design continuity and version tracking.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        provider = previous_result.provider

        if provider == "stitch" and self.stitch_provider.is_available():
            try:
                return self.stitch_provider.revise_design(previous_result, revision_request, output_dir)
            except Exception as e:
                logger.warning("Stitch revision failed (%s). Falling back to Native revision engine.", e)

        # Fallback to Native Revision
        return self.native_provider.revise_design(previous_result, revision_request, output_dir)
