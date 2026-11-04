"""
MIND Base Design Provider Interface.
Defines the standard contract for any design generation engine (Native or Stitch).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from multi_brain.design.contracts import (
    DesignResult,
    DesignRevisionRequest,
    DesignSpecification,
)


class BaseDesignProvider(ABC):
    """Abstract base class for all MIND design generation and revision engines."""

    @abstractmethod
    def generate_design(
        self,
        specification: DesignSpecification,
        output_dir: Path,
    ) -> DesignResult:
        """Generates a complete visual design prototype matching the specification."""
        ...

    @abstractmethod
    def revise_design(
        self,
        previous_result: DesignResult,
        revision: DesignRevisionRequest,
        output_dir: Path,
    ) -> DesignResult:
        """Applies surgical or architectural revisions to an existing design result."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the provider is currently available and properly configured."""
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the canonical provider name."""
        ...
