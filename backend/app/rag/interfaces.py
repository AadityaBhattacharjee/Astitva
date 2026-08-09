"""Abstract interfaces for retrieval and ingestion providers."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    source: str
    document_type: str | None = None
    organization: str | None = None
    category: str | None = None
    state: str | None = None
    publication_date: str | None = None
    last_verified_date: str | None = None
    url: str | None = None
    trust_level: str | None = None


class RetrievalResult(BaseModel):
    content: str
    score: float | None = None
    metadata: DocumentMetadata | None = None
    source_id: str | None = None


class BaseEmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for input texts."""


class BaseVectorStore(ABC):
    @abstractmethod
    def upsert_documents(self, documents: list[dict[str, Any]]) -> None:
        """Persist documents into the vector store."""

    @abstractmethod
    def similarity_search(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        """Run semantic retrieval against the store."""


class BaseStructuredRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run structured retrieval against SQL-backed datasets."""


class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Reorder retrieval results using a future validation strategy."""

