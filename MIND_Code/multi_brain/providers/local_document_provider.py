"""Local Document Processing Provider Adapter (PDF, DOCX, TXT)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from multi_brain.providers.base_provider import BaseProviderAdapter

logger = logging.getLogger("mind.multi_brain.providers.local_document")


class LocalDocumentProviderAdapter(BaseProviderAdapter):
    """
    Extracts and processes structured text from local files (PDF, DOCX, TXT).
    Provides factual citation extraction and evidence extraction.
    """

    def __init__(
        self,
        provider_id: str = "local_doc_reader",
        name: str = "MIND Local Document Reader",
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            name=name,
            execution_mode="local",
            supported_modalities=["document", "text"],
            is_cloud=False,
        )

    def check_health(self) -> Dict[str, Any]:
        has_pypdf = False
        has_docx = False
        try:
            import PyPDF2
            has_pypdf = True
        except ImportError:
            pass

        try:
            import docx
            has_docx = True
        except ImportError:
            pass

        return {
            "status": "healthy" if has_pypdf or has_docx else "degraded",
            "has_pypdf2": has_pypdf,
            "has_python_docx": has_docx,
            "supported_formats": ["pdf", "docx", "txt", "md"],
        }

    def prepare_input(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        file_path = task_input.get("file_path", "")
        max_chars = int(task_input.get("max_chars", 10000))
        return {
            "file_path": os.path.abspath(file_path),
            "max_chars": max_chars,
        }

    def execute(self, prepared_input: Dict[str, Any]) -> Dict[str, Any]:
        file_path = prepared_input["file_path"]
        max_chars = prepared_input["max_chars"]

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document not found at '{file_path}'")

        ext = os.path.splitext(file_path)[1].lower()
        extracted_text = ""
        meta: Dict[str, Any] = {"format": ext, "file_path": file_path}

        if ext == ".pdf":
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                meta["page_count"] = len(reader.pages)
                for page in reader.pages:
                    txt = page.extract_text() or ""
                    extracted_text += txt + "\n"

        elif ext == ".docx":
            import docx
            doc = docx.Document(file_path)
            meta["paragraph_count"] = len(doc.paragraphs)
            for p in doc.paragraphs:
                extracted_text += p.text + "\n"

        elif ext in (".txt", ".md", ".json", ".csv"):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                extracted_text = f.read()
        else:
            raise ValueError(f"Unsupported document format '{ext}'")

        clean_text = extracted_text.strip()
        truncated = len(clean_text) > max_chars
        final_text = clean_text[:max_chars]

        return {
            "status": "success",
            "extracted_text": final_text,
            "char_count": len(final_text),
            "total_chars": len(clean_text),
            "is_truncated": truncated,
            "metadata": meta,
        }
