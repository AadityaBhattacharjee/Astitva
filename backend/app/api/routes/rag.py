"""RAG ingestion, search, and hybrid-search endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database.session import get_db
from backend.app.rag.embeddings.provider import SentenceTransformerEmbeddingProvider
from backend.app.rag.ingestion.pipeline import DocumentIngestionPipeline, IngestionDocument
from backend.app.rag.interfaces import DocumentMetadata, RetrievalResult
from backend.app.rag.retrieval.hybrid import HybridRetriever
from backend.app.rag.retrieval.structured import SchemeStructuredRetriever
from backend.app.rag.vector_store.chroma_store import ChromaStore

router = APIRouter(prefix="/rag", tags=["rag"])

# ---------------------------------------------------------------------------
# Lazy singletons — created on first request, shared across requests.
# This keeps startup fast and avoids loading 90 MB of model weights unless
# the RAG endpoints are actually used.
# ---------------------------------------------------------------------------

_embedding_provider: SentenceTransformerEmbeddingProvider | None = None
_vector_store: ChromaStore | None = None


def _get_embedding_provider() -> SentenceTransformerEmbeddingProvider:
    global _embedding_provider  # noqa: PLW0603
    if _embedding_provider is None:
        settings = get_settings()
        _embedding_provider = SentenceTransformerEmbeddingProvider(model_name=settings.embedding_model)
    return _embedding_provider


def _get_vector_store() -> ChromaStore:
    global _vector_store  # noqa: PLW0603
    if _vector_store is None:
        settings = get_settings()
        _vector_store = ChromaStore(
            persist_directory=settings.chroma_persist_directory,
            collection_name=settings.chroma_collection_name,
            embedding_provider=_get_embedding_provider(),
        )
    return _vector_store


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    document_id: str
    path: str
    text: str | None = None
    metadata: DocumentMetadata = Field(default_factory=lambda: DocumentMetadata(source="api"))


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=50)


class SearchResponse(BaseModel):
    query: str
    results: list[RetrievalResult]
    total: int


class IngestResponse(BaseModel):
    document_id: str
    status: str
    chunk_count: int
    message: str | None = None


class HybridSearchRequest(BaseModel):
    query: str
    state: str | None = None
    category: str | None = None
    target_group: str | None = None
    age: int | None = Field(default=None, ge=0)
    income: int | None = Field(default=None, ge=0)
    active_status: bool | None = True
    vector_limit: int = Field(default=5, ge=1, le=50)


class HybridSearchResponse(BaseModel):
    query: str
    schemes: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    sources: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a document into the vector store",
)
def ingest_document(payload: IngestRequest) -> dict[str, Any]:
    """Extract, chunk, embed, and store a document.

    Supply either ``path`` to a PDF/text file, or ``text`` directly.
    """
    doc = IngestionDocument(
        document_id=payload.document_id,
        path=payload.path,
        metadata=payload.metadata,
        text=payload.text,
    )
    pipeline = DocumentIngestionPipeline(
        vector_store=_get_vector_store(),
        embedding_provider=_get_embedding_provider(),
    )
    result = pipeline.ingest(doc)
    return {
        "document_id": result["document_id"],
        "status": result["status"],
        "chunk_count": result.get("chunk_count", 0),
        "message": result.get("message"),
    }


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic search over ingested documents",
)
def semantic_search(payload: SearchRequest) -> dict[str, Any]:
    """Return the top-k most semantically relevant document chunks."""
    if not payload.query.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query must not be empty.")

    store = _get_vector_store()
    results = store.similarity_search(payload.query, limit=payload.limit)
    return {"query": payload.query, "results": results, "total": len(results)}


@router.get(
    "/status",
    summary="Return the number of chunks in the vector store",
)
def rag_status() -> dict[str, Any]:
    """Return basic stats about the vector store collection."""
    store = _get_vector_store()
    return {
        "status": "ok",
        "chunk_count": store.count(),
        "collection": get_settings().chroma_collection_name,
    }


@router.post(
    "/hybrid-search",
    response_model=HybridSearchResponse,
    summary="Hybrid search: structured scheme DB + semantic vector store",
)
def hybrid_search(
    payload: HybridSearchRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve evidence from both the scheme database and the vector store.

    Structured arm filters schemes by state/category/target_group/age/income.
    Semantic arm returns the top-k most relevant document chunks from ChromaDB.
    No LLM is invoked; raw evidence is returned for the caller to consume.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    filters: dict[str, Any] = {}
    if payload.state is not None:
        filters["state"] = payload.state
    if payload.category is not None:
        filters["category"] = payload.category
    if payload.target_group is not None:
        filters["target_group"] = payload.target_group
    if payload.age is not None:
        filters["age"] = payload.age
    if payload.income is not None:
        filters["income"] = payload.income
    if payload.active_status is not None:
        filters["active_status"] = payload.active_status

    retriever = HybridRetriever(
        structured_retriever=SchemeStructuredRetriever(db),
        vector_store=_get_vector_store(),
    )
    return retriever.search(
        query=payload.query,
        filters=filters,
        vector_limit=payload.vector_limit,
    )
