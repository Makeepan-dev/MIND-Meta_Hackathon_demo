"""Provider Registry: Manages AI, local inference, and generation providers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from multi_brain.providers.base_provider import BaseProviderAdapter
from multi_brain.providers.local_document_provider import LocalDocumentProviderAdapter
from multi_brain.providers.local_media_provider import LocalMediaProviderAdapter
from multi_brain.providers.meta_provider import MetaProviderAdapter
from multi_brain.providers.ollama_provider import OllamaProviderAdapter

logger = logging.getLogger("mind.multi_brain.provider_registry")


class ProviderRegistry:
    """Manages AI inference engines, generation backends, and tool runtimes."""

    def __init__(self) -> None:
        self._providers: Dict[str, BaseProviderAdapter] = {}
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        # Primary Cloud LLM Provider: Meta AI Model API
        self.register(MetaProviderAdapter())
        # Local Ollama Provider (Offline / Local Fallback)
        self.register(OllamaProviderAdapter())
        # Local Media Engine (Pillow 2D + Wavefront OBJ 3D)
        self.register(LocalMediaProviderAdapter())
        # Local Document Reader (PyPDF2 + python-docx)
        self.register(LocalDocumentProviderAdapter())

    def register(self, provider: BaseProviderAdapter, allow_overwrite: bool = True) -> None:
        if not isinstance(provider, BaseProviderAdapter):
            raise TypeError(f"Expected BaseProviderAdapter, got {type(provider).__name__}")
        if not provider.provider_id:
            raise ValueError("Provider has an empty provider_id.")
        if provider.provider_id in self._providers and not allow_overwrite:
            raise ValueError(f"Provider '{provider.provider_id}' is already registered.")
        self._providers[provider.provider_id] = provider
        logger.info(f"Registered provider: {provider.name} [{provider.provider_id}]")

    def unregister(self, provider_id: str) -> bool:
        if provider_id in self._providers:
            del self._providers[provider_id]
            return True
        return False

    def get(self, provider_id: str) -> Optional[BaseProviderAdapter]:
        return self._providers.get(provider_id)

    def find_providers(
        self,
        modality: Optional[str] = None,
        execution_mode: Optional[str] = None,
        only_available: bool = True,
    ) -> List[BaseProviderAdapter]:
        """Discovers providers matching filters."""
        matches = []
        for p in self._providers.values():
            if modality and modality not in p.supported_modalities:
                continue
            if execution_mode and p.execution_mode != execution_mode:
                continue
            if only_available and not p.is_available:
                continue
            matches.append(p)

        # Sort: local first when local is requested, otherwise keep registration order
        matches.sort(key=lambda p: 0 if p.execution_mode == "local" else 1)
        return matches

    def refresh_health(self) -> Dict[str, Dict[str, Any]]:
        """Refreshes health status across all registered providers dynamically."""
        health_report = {}
        for p_id, provider in self._providers.items():
            health_report[p_id] = provider.check_health()
        return health_report

    def list_all(self, only_available: bool = False) -> List[Dict[str, Any]]:
        results = []
        for p in self._providers.values():
            if not only_available or p.is_available:
                results.append(p.get_metadata())
        return results
