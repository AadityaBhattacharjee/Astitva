"""Document ingestion pipeline: PDF → extract → clean → chunk → embed → ChromaDB."""

import hashlib
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.app.rag.interfaces import DocumentMetadata


# ---------------------------------------------------------------------------
# Public input contract (unchanged from scaffold)
# ---------------------------------------------------------------------------

class IngestionDocument(BaseModel):
    """Input contract for ingestion jobs."""

    document_id: str
    path: str
    metadata: DocumentMetadata
    text: str | None = None  # pre-supplied text bypasses PDF extraction


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_BLANK_LINE_RE = re.compile(r"\n{3,}")


def _extract_text_from_pdf(path: str) -> str:
    """Extract raw text from a PDF file using pypdf."""
    from pypdf import PdfReader  # noqa: PLC0415

    reader = PdfReader(path)
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    return "\n".join(parts)


def _clean_text(raw: str) -> str:
    """Normalise whitespace and collapse blank lines."""
    text = _WHITESPACE_RE.sub(" ", raw)
    text = text.replace("\f", "\n")
    text = _BLANK_LINE_RE.sub("\n\n", text)
    return text.strip()


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping word-level chunks.

    ``chunk_size`` and ``overlap`` are measured in *words*.
    Returns at least one chunk even if the text is shorter than chunk_size.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


def _chunk_id(document_id: str, chunk_index: int) -> str:
    """Deterministic chunk identifier."""
    raw = f"{document_id}__chunk_{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class DocumentIngestionPipeline:
    """PDF → text extraction → cleaning → chunking → embedding → ChromaDB."""

    def __init__(
        self,
        vector_store: "Any | None" = None,
        embedding_provider: "Any | None" = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def ingest(self, document: IngestionDocument) -> dict[str, Any]:
        """Run the full ingestion pipeline for one document.

        Returns a result dict with status, document_id, and chunk_count.
        """
        # 1. Extract text
        if document.text:
            raw_text = document.text
        elif Path(document.path).suffix.lower() == ".pdf":
            raw_text = _extract_text_from_pdf(document.path)
        else:
            raw_text = Path(document.path).read_text(encoding="utf-8", errors="replace")

        # 2. Clean
        clean = _clean_text(raw_text)
        if not clean:
            return {"document_id": document.document_id, "status": "skipped", "chunk_count": 0,
                    "message": "Document produced no usable text."}

        # 3. Chunk
        chunks = _chunk_text(clean, self._chunk_size, self._chunk_overlap)

        # 4. Embed
        if self._embedding_provider is None:
            return {"document_id": document.document_id, "status": "no_embedder", "chunk_count": len(chunks),
                    "message": "No embedding provider attached; chunks not stored."}

        vectors = self._embedding_provider.embed(chunks)

        # 5. Store
        meta_dict: dict[str, Any] = {
            k: v for k, v in document.metadata.model_dump().items() if v is not None
        }

        docs_to_upsert = [
            {
                "id": _chunk_id(document.document_id, i),
                "text": chunk,
                "embedding": vec,
                "metadata": {**meta_dict, "document_id": document.document_id, "chunk_index": i},
            }
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]

        if self._vector_store is not None:
            self._vector_store.upsert_documents(docs_to_upsert)

        return {
            "document_id": document.document_id,
            "status": "ok",
            "chunk_count": len(chunks),
        }
