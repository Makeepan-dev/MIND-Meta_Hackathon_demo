"""Capability Registry: Central index for all capabilities across brains, models, and tools."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from multi_brain.contracts import Capability, PermissionTier

logger = logging.getLogger("mind.multi_brain.capability_registry")


class CapabilityRegistry:
    """
    Central discovery and resolution service for MIND capabilities.
    Tracks what MIND can do, which specialist coordinates it,
    which provider/tool executes it, and whether it is currently operational.
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, Capability] = {}

    def register(self, capability: Capability, allow_overwrite: bool = True) -> None:
        if not isinstance(capability, Capability):
            raise TypeError(f"Expected Capability, got {type(capability).__name__}")
        cid = capability.capability_id.strip()
        if not cid:
            raise ValueError("Capability ID cannot be empty.")
        if cid in self._capabilities and not allow_overwrite:
            raise ValueError(f"Capability '{cid}' is already registered.")
        self._capabilities[cid] = capability
        logger.debug(f"Registered capability: {capability.name} [{cid}]")

    def unregister(self, capability_id: str) -> bool:
        cid = capability_id.strip()
        if cid in self._capabilities:
            del self._capabilities[cid]
            return True
        return False

    def get(self, capability_id: str) -> Optional[Capability]:
        return self._capabilities.get(capability_id.strip())

    def find_capabilities(
        self,
        domain: Optional[str] = None,
        modality: Optional[str] = None,
        execution_mode: Optional[str] = None,
        only_available: bool = True,
    ) -> List[Capability]:
        """Finds capabilities matching specific criteria."""
        matches = []
        for cap in self._capabilities.values():
            if domain and cap.domain.lower() != domain.lower():
                continue
            if modality and modality not in cap.modalities:
                continue
            if execution_mode and execution_mode not in cap.execution_modes:
                continue
            if only_available and not cap.is_available:
                continue
            matches.append(cap)
        return matches

    def generate_inventory(self) -> List[Dict[str, Any]]:
        """Generates the required system capability inventory."""
        inventory = []
        for cap in self._capabilities.values():
            inventory.append({
                "capability": cap.name,
                "capability_id": cap.capability_id,
                "domain": cap.domain,
                "execution_modes": cap.execution_modes,
                "permission_tier": cap.permission_tier.value,
                "is_available": cap.is_available,
                "health_status": cap.health_status,
                "supported_formats": cap.supported_formats,
                "compatible_providers": cap.compatible_providers,
            })
        return inventory

    def list_all(self, only_available: bool = False) -> List[Dict[str, Any]]:
        results = []
        for cap in self._capabilities.values():
            if not only_available or cap.is_available:
                results.append(cap.to_dict())
        return results
