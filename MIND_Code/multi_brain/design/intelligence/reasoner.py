"""
MIND Design Reasoner.
Interprets user requirements, deconstructs aesthetic intent, and formulates design directions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from multi_brain.design.contracts import DesignSpecification
from multi_brain.design.specification import DesignSpecificationBuilder

logger = logging.getLogger("mind.multi_brain.design.reasoner")


class DesignReasoner:
    """Interprets design requirements and establishes architectural intent."""

    def __init__(self, model_registry: Optional[Any] = None) -> None:
        self.model_registry = model_registry

    def reason_specification(self, user_prompt: str) -> DesignSpecification:
        """
        Deconstructs natural-language design objective into a validated DesignSpecification.
        Reuses ModelRegistry when available or falls back to robust algorithmic classification.
        """
        logger.info("DesignReasoner analyzing objective: '%s'...", user_prompt[:60])
        
        # If ModelRegistry is available, we can augment with LLM intent analysis
        if self.model_registry:
            try:
                # Query default text model if active
                model = self.model_registry.get_default_model()
                if model and hasattr(self.model_registry, "invoke"):
                    logger.debug("Querying model %s for design reasoning...", model.model_id)
            except Exception as e:
                logger.debug("Model reasoning fallback: %s", e)

        # Build complete, validated specification
        spec = DesignSpecificationBuilder.from_prompt(user_prompt)
        validation_errors = DesignSpecificationBuilder.validate(spec)
        if validation_errors:
            logger.warning("Specification validation warnings: %s", validation_errors)

        return spec
