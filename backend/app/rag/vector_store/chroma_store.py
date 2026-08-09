"""ChromaDB vector store implementation."""

from typing import Any

import chromadb

from backend.app.rag.interfaces import BaseVectorStore, DocumentMetadata, RetrievalResult


class ChromaStore(BaseVectorStore):
    """Persistent ChromaDB-backed vector store.

    Each document dict passed to ``upsert_documents`` must contain:
      - ``id``        (str)  — unique chunk identifier
      - ``text``      (str)  — chunk content
      - ``embedding`` (list[float]) — pre-computed embedding vector
      - ``metadata``  (dict, optional) — arbitrary key/value metadata

    Metadata values must be str, int, float, or bool (ChromaDB constraint).
    None values are dropped automatically.
    """

    def __init__(
        self,
        persist_directory: str,
        collection_name: str,
        embedding_provider: "Any | None" = None,
    ) -> None:
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedding_provider = embedding_provider

    # ------------------------------------------------------------------
    # BaseVectorStore contract
    # ------------------------------------------------------------------

    def upsert_documents(self, documents: list[dict[str, Any]]) -> None:
        """Upsert a batch of pre-embedded document chunks into ChromaDB."""
        if not documents:
            return

        ids: list[str] = []
        texts: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []

        for doc in documents:
            ids.append(str(doc["id"]))
            texts.append(doc["text"])
            embeddings.append(doc["embedding"])
            # ChromaDB rejects None values; drop them
            meta = {k: v for k, v in (doc.get("metadata") or {}).items() if v is not None}
            metadatas.append(meta)

        self._collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def similarity_search(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        """Run cosine-similarity search using the attached embedding provider."""
        if self._embedding_provider is None:
            return []

        query_vec = self._embedding_provider.embed([query])[0]
        results = self._collection.query(
            query_embeddings=[query_vec],
            n_results=min(limit, max(self._collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )

        output: list[RetrievalResult] = []
        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        dists = results.get("distances") or [[]]
        ids_list = results.get("ids") or [[]]

        for doc, meta, dist, rid in zip(docs[0], metas[0], dists[0], ids_list[0]):
            # cosine distance → similarity score (1 - distance)
            score = float(1.0 - dist) if dist is not None else None
            metadata: DocumentMetadata | None = None
            if meta:
                try:
                    metadata = DocumentMetadata(**{k: v for k, v in meta.items() if k in DocumentMetadata.model_fields})
                except Exception:
                    pass
            output.append(RetrievalResult(content=doc, score=score, metadata=metadata, source_id=str(rid)))

        return output

    # ------------------------------------------------------------------
    # Convenience helpers used by the ingestion pipeline and tests
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return total number of chunks in the collection."""
        return self._collection.count()

    def delete_collection(self) -> None:
        """Drop the collection entirely (useful in tests)."""
        self._client.delete_collection(self._collection.name)
