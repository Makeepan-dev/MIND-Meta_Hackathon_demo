"""
MIND Native Design Engine Provider.
Implements autonomous design reasoning, generation, and revision without external APIs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from multi_brain.design.contracts import (
    DesignResult,
    DesignRevisionRequest,
    DesignSpecification,
)
from multi_brain.design.evaluation.evaluator import VisualEvaluator
from multi_brain.design.evaluation.revision import DesignRevision
from multi_brain.design.generation.prototype_engine import PrototypeEngine
from multi_brain.design.providers.base import BaseDesignProvider

logger = logging.getLogger("mind.multi_brain.design.providers.native")


class MindNativeDesignProvider(BaseDesignProvider):
    """MIND's own AI-driven design intelligence and generation engine."""

    def __init__(self) -> None:
        self.prototype_engine = PrototypeEngine()
        self.evaluator = VisualEvaluator()
        self.revision_engine = DesignRevision()

    def generate_design(
        self,
        specification: DesignSpecification,
        output_dir: Path,
    ) -> DesignResult:
        """Generates complete native HTML/CSS/JS interface prototype."""
        logger.info("MindNativeDesignProvider generating design for '%s'...", specification.project_name)
        result = self.prototype_engine.build_prototype(
            spec=specification,
            output_dir=output_dir,
            version=1,
        )
        
        # Run automated evaluation
        report = self.evaluator.evaluate(result)
        result.evaluation = report
        return result

    def revise_design(
        self,
        previous_result: DesignResult,
        revision: DesignRevisionRequest,
        output_dir: Path,
    ) -> DesignResult:
        """Applies targeted revision without full regeneration."""
        logger.info("MindNativeDesignProvider revising design (version %d)...", revision.new_version)
        return self.revision_engine.revise(
            previous_result=previous_result,
            revision_request=revision,
            output_dir=output_dir,
        )

    def is_available(self) -> bool:
        """Native engine is always available locally without network dependencies."""
        return True

    def get_provider_name(self) -> str:
        return "native"
