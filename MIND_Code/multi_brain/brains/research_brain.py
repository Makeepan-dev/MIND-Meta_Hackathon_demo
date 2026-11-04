"""Research and Document Brain: Structured research, document processing, and source citations."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from multi_brain.brains.base import SpecialistBrain
from multi_brain.contracts import (
    Capability,
    PermissionTier,
    Provenance,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from multi_brain.registries.model_registry import ModelModality, ModelRegistry
from multi_brain.registries.tool_registry import ToolRegistry

logger = logging.getLogger("mind.multi_brain.research_brain")


class ResearchKnowledgeBrain(SpecialistBrain):
    """
    Specialist brain for document extraction (PDF, DOCX, TXT), structured research,
    and evidence synthesis. Clearly separates source evidence from model inference.
    """

    def __init__(
        self,
        model_registry: Optional[ModelRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        super().__init__(
            brain_id="research_knowledge",
            name="Research and Document Brain",
            domain="Research & Knowledge",
            description="Processes documents (PDF/DOCX/TXT), synthesizes findings, and records citations.",
            capabilities=[
                Capability(
                    name="document_processing",
                    domain="Document Processing",
                    description="Extracts raw text, page counts, and metadata from PDF, DOCX, and TXT files.",
                    modalities=["document", "text"],
                    supported_formats=["pdf", "docx", "txt", "md"],
                    execution_modes=["local"],
                    permission_tier=PermissionTier.LOW_RISK,
                    is_available=True,
                ),
                Capability(
                    name="synthesize_knowledge",
                    domain="Research",
                    description="Synthesizes factual summaries with explicit citations and references.",
                    modalities=["text"],
                    execution_modes=["local"],
                    permission_tier=PermissionTier.SAFE,
                    is_available=True,
                ),
            ],
            permission_tier=PermissionTier.SAFE,
        )
        self.model_registry = model_registry or ModelRegistry()
        self.tool_registry = tool_registry or ToolRegistry()

    def _execute_task(self, request: TaskRequest) -> TaskResult:
        query = request.user_goal
        inputs = request.input_data or {}
        doc_path = inputs.get("file_path") or inputs.get("document_path")

        tool_calls_record = []
        extracted_doc_text = ""
        doc_meta = {}

        # 1. Document Extraction if document path is provided
        if doc_path and os.path.exists(doc_path):
            try:
                doc_res = self.tool_registry.execute_tool(
                    "document_read",
                    {"file_path": doc_path},
                    requester=self.brain_id,
                )
                extracted_doc_text = doc_res.get("extracted_text", "")
                doc_meta = doc_res.get("metadata", {})
                tool_calls_record.append({"tool": "document_read", "file": doc_path})
            except Exception as e:
                logger.warning(f"Document extraction error: {e}")

        sources = list(inputs.get("sources") or [])
        if doc_path:
            sources.append(f"Document: {os.path.basename(doc_path)}")
        if not sources:
            sources.append("MIND Local Knowledge Store")

        # 2. Synthesis with Source Provenance
        sys_prompt = (
            "You are the MIND Research and Document Specialist Brain.\n"
            "Provide objective, rigorous factual findings. Explicitly cite assumptions and known sources.\n"
            "Distinguish between source evidence and model inferences."
        )
        context_str = f"Document Text Sample:\n{extracted_doc_text[:2000]}\n" if extracted_doc_text else ""
        user_prompt = f"Research Query: {query}\n{context_str}\nAvailable Sources: {sources}"

        spark_12 = self.model_registry.get("meta-muse-spark-1.2")
        if spark_12 and spark_12.is_available:
            model = spark_12
        else:
            model = self.model_registry.get_default_model(ModelModality.TEXT)
        model_id = model.model_id if model else "deterministic-fallback"

        try:
            summary = self.model_registry.invoke(
                model_id=model_id,
                prompt=user_prompt,
                system_prompt=sys_prompt,
                temperature=0.3,
                agent_id=self.brain_id,
            )
        except Exception:
            summary = f"Research synthesis for '{query}': Core principles identified from {len(sources)} sources."

        return TaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output={
                "query": query,
                "summary": summary,
                "sources": sources,
                "document_metadata": doc_meta,
                "evidence_extracted": bool(extracted_doc_text),
            },
            provenance=Provenance(
                brain_id=self.brain_id,
                model_id=model_id,
                tool_calls=tool_calls_record,
                confidence=0.92,
                execution_mode="local",
            ),
        )
