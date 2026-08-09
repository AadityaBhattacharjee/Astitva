"""Embedding provider implementations."""

from backend.app.rag.interfaces import BaseEmbeddingProvider


class PlaceholderEmbeddingProvider(BaseEmbeddingProvider):
    """No-op embedding provider kept for tests that don't need real vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 3 for _ in texts]


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """Real embedding provider backed by a local SentenceTransformer model.

    The model is loaded once on first use and cached on the instance.
    Configurable via ``embedding_model`` in Settings.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None  # lazy-load to avoid import overhead at module level

    def _get_model(self):  # type: ignore[return]
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]
