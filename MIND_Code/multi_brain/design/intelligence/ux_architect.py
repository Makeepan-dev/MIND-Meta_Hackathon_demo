"""
MIND UX Architect.
Plans screen hierarchies, navigation flows, and user journeys.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from multi_brain.design.contracts import DesignSpecification, ScreenSpec

logger = logging.getLogger("mind.multi_brain.design.ux")


class UXArchitect:
    """Architects information hierarchy, multi-screen navigation, and user flow."""

    def architect_experience(self, spec: DesignSpecification) -> DesignSpecification:
        """
        Refines screen definitions, layout types, and interactive navigation paths.
        """
        logger.info("UXArchitect structuring user journey for '%s'...", spec.project_name)

        # Ensure consistent navigation map exists
        if not spec.navigation_flow and len(spec.screens) > 1:
            flow: List[Dict[str, str]] = []
            for i in range(len(spec.screens) - 1):
                flow.append({
                    "from": spec.screens[i].screen_id,
                    "to": spec.screens[i + 1].screen_id,
                    "action": f"Navigate to {spec.screens[i + 1].title}",
                })
            spec.navigation_flow = flow

        return spec
