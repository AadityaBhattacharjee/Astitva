"""Hybrid retrieval: combines structured PostgreSQL results with ChromaDB semantic search."""

from typing import Any

from backend.app.rag.interfaces import BaseStructuredRetriever, BaseVectorStore, RetrievalResult


class HybridRetriever:
    """Combines structured scheme retrieval with vector semantic search.

    Neither retriever is mandatory; pass only the ones available.
    Results are clearly tagged by source so callers can distinguish them.

    Usage::

        retriever = HybridRetriever(
            structured_retriever=SchemeStructuredRetriever(db_session),
            vector_store=chroma_store,
        )
        result = retriever.search(
            query="housing support for single mothers",
            filters={"state": "Karnataka", "age": 34, "income": 180000},
            vector_limit=5,
        )
    """

    def __init__(
        self,
        structured_retriever: BaseStructuredRetriever | None = None,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        self.structured_retriever = structured_retriever
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        vector_limit: int = 5,
    ) -> dict[str, Any]:
        """Run both retrieval arms and return combined evidence.

        Returns::

            {
                "query":     str,
                "schemes":   list[dict],      # structured DB results
                "documents": list[dict],      # vector store chunks
                "sources":   list[str],       # distinct source labels
            }
        """
        # ── Structured retrieval ──────────────────────────────────────────
        schemes: list[dict[str, Any]] = []
        if self.structured_retriever is not None:
            schemes = self.structured_retriever.retrieve(query, filters)

        # ── Semantic retrieval ────────────────────────────────────────────
        documents: list[dict[str, Any]] = []
        if self.vector_store is not None:
            raw: list[RetrievalResult] = self.vector_store.similarity_search(
                query, limit=vector_limit
            )
            for r in raw:
                documents.append(
                    {
                        "content": r.content,
                        "score": r.score,
                        "source_id": r.source_id,
                        "metadata": r.metadata.model_dump() if r.metadata else {},
                        "_source_type": "vector_store",
                    }
                )

        # ── Collect distinct source labels ────────────────────────────────
        sources: list[str] = []
        for s in schemes:
            label = s.get("source") or s.get("scheme_id") or "structured_db"
            if label not in sources:
                sources.append(label)
        for d in documents:
            meta = d.get("metadata") or {}
            label = meta.get("source") or d.get("source_id") or "vector_store"
            if label not in sources:
                sources.append(label)

        return {
            "query": query,
            "schemes": schemes,
            "documents": documents,
            "sources": sources,
        }
