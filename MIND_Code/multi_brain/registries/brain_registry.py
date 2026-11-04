"""Central registry for discovering, managing, and inspecting Specialist Brains."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from multi_brain.brains.base import SpecialistBrain

logger = logging.getLogger("mind.multi_brain.brain_registry")


class BrainRegistry:
    """Manages registration, discovery, and availability of specialist brains in MIND."""

    def __init__(self) -> None:
        self._brains: Dict[str, SpecialistBrain] = {}

    def register(self, brain: SpecialistBrain, allow_overwrite: bool = False) -> None:
        """
        Registers a new specialist brain.
        Validates the brain contract and prevents duplicate registrations unless allowed.
        """
        if not isinstance(brain, SpecialistBrain):
            raise TypeError(f"Expected instance of SpecialistBrain, got {type(brain).__name__}")

        b_id = brain.brain_id.strip()
        if not b_id:
            raise ValueError("Specialist brain has an empty brain_id.")

        if b_id in self._brains and not allow_overwrite:
            raise ValueError(
                f"Brain with ID '{b_id}' is already registered. "
                "Use allow_overwrite=True to replace an existing brain."
            )

        self._brains[b_id] = brain
        logger.info(f"Registered brain '{brain.name}' [{b_id}] (domain: {brain.domain})")

    def unregister(self, brain_id: str) -> bool:
        """Removes a specialist brain from the registry by ID."""
        b_id = brain_id.strip()
        if b_id in self._brains:
            del self._brains[b_id]
            logger.info(f"Unregistered brain [{b_id}]")
            return True
        return False

    def get(self, brain_id: str) -> Optional[SpecialistBrain]:
        """Retrieves a registered brain by its unique identifier."""
        return self._brains.get(brain_id.strip())

    def get_required(self, brain_id: str) -> SpecialistBrain:
        """Retrieves a registered brain or raises KeyError if not found."""
        b_id = brain_id.strip()
        if b_id not in self._brains:
            raise KeyError(f"Specialist brain '{b_id}' is not registered in MIND.")
        return self._brains[b_id]

    def find_by_capability(self, capability_name: str, only_available: bool = True) -> List[SpecialistBrain]:
        """Finds all registered brains declaring the given capability."""
        cap_clean = capability_name.strip().lower()
        matches = []
        for brain in self._brains.values():
            if brain.has_capability(cap_clean):
                if not only_available or brain.is_available:
                    matches.append(brain)
        return matches

    def find_by_domain(self, domain_name: str, only_available: bool = True) -> List[SpecialistBrain]:
        """Finds all registered brains belonging to a specific domain."""
        dom_clean = domain_name.strip().lower()
        matches = []
        for brain in self._brains.values():
            if brain.domain.lower() == dom_clean:
                if not only_available or brain.is_available:
                    matches.append(brain)
        return matches

    def list_all(self, only_available: bool = False) -> List[Dict[str, Any]]:
        """Returns metadata for all registered brains."""
        results = []
        for brain in self._brains.values():
            if not only_available or brain.is_available:
                results.append(brain.to_metadata())
        return results

    def clear(self) -> None:
        """Clears all registrations (primarily for testing)."""
        self._brains.clear()

    def __len__(self) -> int:
        return len(self._brains)

    def __contains__(self, brain_id: str) -> bool:
        return brain_id.strip() in self._brains
