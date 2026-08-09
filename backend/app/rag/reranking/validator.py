"""Placeholder reranking and validation logic."""

from backend.app.rag.interfaces import BaseReranker, RetrievalResult


class PlaceholderReranker(BaseReranker):
    """Pass-through reranker until real source validation is added."""

    def rerank(self, query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
        return results

