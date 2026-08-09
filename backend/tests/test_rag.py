"""RAG foundation tests.

Covers:
  - real embedding generation (SentenceTransformer)
  - ChromaDB upsert and count
  - ChromaDB persistence across store re-instantiation
  - semantic similarity search
  - metadata round-trip preservation
  - ingestion pipeline helper functions (_clean_text, _chunk_text, _chunk_id)
  - end-to-end ingestion + search (text-based, no PDF needed)
  - PDF extraction via pypdf (using a minimal in-memory PDF fixture)
  - POST /rag/ingest and POST /rag/search API endpoints
"""

import io
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal in-memory PDF fixture (created without any external tool)
# ---------------------------------------------------------------------------

def _make_minimal_pdf(text: str) -> bytes:
    """Build a bare-bones valid PDF in memory containing ``text``.

    This avoids any external PDF-generation dependency.  The PDF structure
    is intentionally minimal but valid enough for pypdf to parse.
    """
    # We embed the text as a raw PDF content stream.
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_stream = f"BT /F1 12 Tf 50 750 Td ({safe_text}) Tj ET"
    stream_bytes = content_stream.encode("latin-1")
    stream_len = len(stream_bytes)

    objects: dict[int, bytes] = {}

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objects[3] = (
        b"<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] "
        b"/Contents 4 0 R "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
        b">>"
    )
    objects[4] = (
        f"<< /Length {stream_len} >>\nstream\n".encode("latin-1")
        + stream_bytes
        + b"\nendstream"
    )

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_num, obj_body in objects.items():
        offsets[obj_num] = buf.tell()
        buf.write(f"{obj_num} 0 obj\n".encode())
        buf.write(obj_body)
        buf.write(b"\nendobj\n")

    xref_offset = buf.tell()
    buf.write(b"xref\n")
    buf.write(f"0 {len(objects) + 1}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for i in range(1, len(objects) + 1):
        buf.write(f"{offsets[i]:010d} 00000 n \n".encode())

    buf.write(b"trailer\n")
    buf.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
    buf.write(b"startxref\n")
    buf.write(f"{xref_offset}\n".encode())
    buf.write(b"%%EOF\n")

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def embed_provider():
    """Real SentenceTransformer provider (model is cached after first load)."""
    from backend.app.rag.embeddings.provider import SentenceTransformerEmbeddingProvider
    return SentenceTransformerEmbeddingProvider(model_name="all-MiniLM-L6-v2")


@pytest.fixture()
def chroma_store(tmp_path, embed_provider):
    """Ephemeral ChromaStore in a temp directory."""
    from backend.app.rag.vector_store.chroma_store import ChromaStore
    store = ChromaStore(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="test_collection",
        embedding_provider=embed_provider,
    )
    yield store
    try:
        store.delete_collection()
    except Exception:
        pass


@pytest.fixture()
def sample_pdf(tmp_path) -> Path:
    """Write a minimal valid PDF to disk and return its path."""
    content = (
        "Pradhan Mantri Awas Yojana provides housing assistance to women "
        "headed households and economically weaker sections in India. "
        "Eligible beneficiaries receive a subsidy on home loans. "
        "The scheme covers urban and rural areas across all states."
    )
    pdf_bytes = _make_minimal_pdf(content)
    pdf_path = tmp_path / "fixture_scheme.pdf"
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path


@pytest.fixture()
def pipeline(embed_provider, chroma_store):
    """Ingestion pipeline wired to the ephemeral store."""
    from backend.app.rag.ingestion.pipeline import DocumentIngestionPipeline
    return DocumentIngestionPipeline(
        vector_store=chroma_store,
        embedding_provider=embed_provider,
        chunk_size=50,
        chunk_overlap=5,
    )


# ---------------------------------------------------------------------------
# Embedding tests
# ---------------------------------------------------------------------------

class TestEmbeddingProvider:
    def test_returns_correct_batch_size(self, embed_provider):
        texts = ["hello world", "government scheme", "housing benefit"]
        vecs = embed_provider.embed(texts)
        assert len(vecs) == 3

    def test_embedding_dimension(self, embed_provider):
        vecs = embed_provider.embed(["test sentence"])
        # all-MiniLM-L6-v2 produces 384-dim vectors
        assert len(vecs[0]) == 384

    def test_embeddings_are_floats(self, embed_provider):
        vecs = embed_provider.embed(["sample text"])
        assert all(isinstance(v, float) for v in vecs[0])

    def test_different_texts_give_different_vectors(self, embed_provider):
        v1 = embed_provider.embed(["cat"])[0]
        v2 = embed_provider.embed(["government subsidy scheme"])[0]
        assert v1 != v2

    def test_same_text_gives_same_vector(self, embed_provider):
        text = "deterministic embedding"
        v1 = embed_provider.embed([text])[0]
        v2 = embed_provider.embed([text])[0]
        assert v1 == v2


# ---------------------------------------------------------------------------
# ChromaDB store tests
# ---------------------------------------------------------------------------

class TestChromaStore:
    def _make_doc(self, embed_provider, doc_id: str, text: str, meta: dict | None = None):
        vec = embed_provider.embed([text])[0]
        return {"id": doc_id, "text": text, "embedding": vec, "metadata": meta or {"source": "test"}}

    def test_upsert_and_count(self, chroma_store, embed_provider):
        chroma_store.upsert_documents([
            self._make_doc(embed_provider, "d1", "housing scheme for women"),
            self._make_doc(embed_provider, "d2", "maternity benefit programme"),
        ])
        assert chroma_store.count() == 2

    def test_empty_upsert_is_noop(self, chroma_store):
        chroma_store.upsert_documents([])
        assert chroma_store.count() == 0

    def test_upsert_is_idempotent(self, chroma_store, embed_provider):
        doc = self._make_doc(embed_provider, "d1", "duplicate document")
        chroma_store.upsert_documents([doc])
        chroma_store.upsert_documents([doc])  # upsert again with same id
        assert chroma_store.count() == 1

    def test_metadata_round_trip(self, chroma_store, embed_provider):
        chroma_store.upsert_documents([
            self._make_doc(embed_provider, "d1", "scheme text", {"source": "unit_test", "category": "housing"})
        ])
        results = chroma_store.similarity_search("scheme", limit=1)
        assert len(results) == 1
        assert results[0].metadata is not None
        assert results[0].metadata.source == "unit_test"

    def test_similarity_search_returns_results(self, chroma_store, embed_provider):
        chroma_store.upsert_documents([
            self._make_doc(embed_provider, "d1", "Pradhan Mantri Awas Yojana housing scheme"),
            self._make_doc(embed_provider, "d2", "maternity leave policy for working women"),
            self._make_doc(embed_provider, "d3", "agricultural loan subsidy for farmers"),
        ])
        results = chroma_store.similarity_search("housing benefit for families", limit=2)
        assert len(results) == 2
        assert all(r.score is not None for r in results)

    def test_top_result_is_semantically_relevant(self, chroma_store, embed_provider):
        chroma_store.upsert_documents([
            self._make_doc(embed_provider, "housing", "housing loan subsidy scheme for low income families"),
            self._make_doc(embed_provider, "farming", "agricultural drought relief fund for rural farmers"),
            self._make_doc(embed_provider, "health",  "free maternal health checkup programme"),
        ])
        results = chroma_store.similarity_search("affordable home loan for poor families", limit=1)
        assert len(results) == 1
        assert results[0].source_id == "housing"

    def test_scores_are_between_minus_one_and_one(self, chroma_store, embed_provider):
        chroma_store.upsert_documents([
            self._make_doc(embed_provider, "d1", "sample sentence for scoring check"),
        ])
        results = chroma_store.similarity_search("sample sentence", limit=1)
        assert -1.0 <= results[0].score <= 1.0

    def test_source_id_preserved(self, chroma_store, embed_provider):
        chroma_store.upsert_documents([
            self._make_doc(embed_provider, "unique-id-42", "test content"),
        ])
        results = chroma_store.similarity_search("test", limit=1)
        assert results[0].source_id == "unique-id-42"


# ---------------------------------------------------------------------------
# Persistence test
# ---------------------------------------------------------------------------

class TestChromaPersistence:
    def test_data_survives_store_reinstantiation(self, tmp_path, embed_provider):
        from backend.app.rag.vector_store.chroma_store import ChromaStore

        store1 = ChromaStore(
            persist_directory=str(tmp_path / "persist_chroma"),
            collection_name="persist_col",
            embedding_provider=embed_provider,
        )
        vec = embed_provider.embed(["persistent data"])[0]
        store1.upsert_documents([{"id": "p1", "text": "persistent data", "embedding": vec, "metadata": {"source": "persist_test"}}])
        assert store1.count() == 1

        # Re-open the same directory
        store2 = ChromaStore(
            persist_directory=str(tmp_path / "persist_chroma"),
            collection_name="persist_col",
            embedding_provider=embed_provider,
        )
        assert store2.count() == 1


# ---------------------------------------------------------------------------
# Ingestion pipeline helper unit tests
# ---------------------------------------------------------------------------

class TestPipelineHelpers:
    def test_clean_text_collapses_whitespace(self):
        from backend.app.rag.ingestion.pipeline import _clean_text
        assert _clean_text("  hello   world  ") == "hello world"

    def test_clean_text_handles_empty(self):
        from backend.app.rag.ingestion.pipeline import _clean_text
        assert _clean_text("") == ""

    def test_chunk_text_respects_size(self):
        from backend.app.rag.ingestion.pipeline import _chunk_text
        words = ["word"] * 120
        text = " ".join(words)
        chunks = _chunk_text(text, chunk_size=50, overlap=10)
        assert all(len(c.split()) <= 50 for c in chunks)

    def test_chunk_text_short_text_gives_one_chunk(self):
        from backend.app.rag.ingestion.pipeline import _chunk_text
        chunks = _chunk_text("short text here", chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0] == "short text here"

    def test_chunk_text_empty_gives_no_chunks(self):
        from backend.app.rag.ingestion.pipeline import _chunk_text
        assert _chunk_text("", chunk_size=100, overlap=10) == []

    def test_chunk_id_is_deterministic(self):
        from backend.app.rag.ingestion.pipeline import _chunk_id
        assert _chunk_id("doc-1", 0) == _chunk_id("doc-1", 0)
        assert _chunk_id("doc-1", 0) != _chunk_id("doc-1", 1)

    def test_chunk_id_is_16_chars(self):
        from backend.app.rag.ingestion.pipeline import _chunk_id
        assert len(_chunk_id("doc-abc", 3)) == 16


# ---------------------------------------------------------------------------
# End-to-end ingestion pipeline tests
# ---------------------------------------------------------------------------

class TestIngestionPipeline:
    def test_text_ingest_status_ok(self, pipeline):
        from backend.app.rag.ingestion.pipeline import IngestionDocument
        from backend.app.rag.interfaces import DocumentMetadata

        doc = IngestionDocument(
            document_id="e2e-001",
            path="n/a",
            text="Women headed households receive housing subsidy under PMAY scheme.",
            metadata=DocumentMetadata(source="test", category="housing"),
        )
        result = pipeline.ingest(doc)
        assert result["status"] == "ok"
        assert result["chunk_count"] >= 1

    def test_ingested_chunks_are_searchable(self, pipeline, chroma_store):
        from backend.app.rag.ingestion.pipeline import IngestionDocument
        from backend.app.rag.interfaces import DocumentMetadata

        doc = IngestionDocument(
            document_id="e2e-002",
            path="n/a",
            text=(
                "Sukanya Samriddhi Yojana is a savings scheme for the girl child in India. "
                "Parents can open an account and receive tax benefits and interest on deposits."
            ),
            metadata=DocumentMetadata(source="test", category="financial"),
        )
        pipeline.ingest(doc)
        results = chroma_store.similarity_search("savings account for girl child", limit=3)
        assert len(results) >= 1
        assert any("Sukanya" in r.content or "girl" in r.content or "savings" in r.content for r in results)

    def test_metadata_propagated_through_pipeline(self, pipeline, chroma_store):
        from backend.app.rag.ingestion.pipeline import IngestionDocument
        from backend.app.rag.interfaces import DocumentMetadata

        doc = IngestionDocument(
            document_id="e2e-003",
            path="n/a",
            text="Maternity Benefit Act covers all women in organised sector employment.",
            metadata=DocumentMetadata(source="gov_portal", category="maternity", state="All States"),
        )
        pipeline.ingest(doc)
        results = chroma_store.similarity_search("maternity employment coverage", limit=1)
        assert len(results) == 1
        assert results[0].metadata is not None
        assert results[0].metadata.source == "gov_portal"

    def test_empty_text_returns_skipped(self, pipeline):
        from backend.app.rag.ingestion.pipeline import IngestionDocument
        from backend.app.rag.interfaces import DocumentMetadata

        doc = IngestionDocument(
            document_id="e2e-004",
            path="n/a",
            text="   ",
            metadata=DocumentMetadata(source="test"),
        )
        result = pipeline.ingest(doc)
        assert result["status"] == "skipped"

    def test_pdf_extraction_and_ingest(self, pipeline, chroma_store, sample_pdf):
        from backend.app.rag.ingestion.pipeline import IngestionDocument
        from backend.app.rag.interfaces import DocumentMetadata

        doc = IngestionDocument(
            document_id="e2e-pdf-001",
            path=str(sample_pdf),
            metadata=DocumentMetadata(source="fixture_pdf", document_type="scheme"),
        )
        result = pipeline.ingest(doc)
        assert result["status"] == "ok"
        assert result["chunk_count"] >= 1

        results = chroma_store.similarity_search("housing subsidy women", limit=3)
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestRagEndpoints:
    """Test the /rag/* HTTP endpoints through the FastAPI test client.

    These tests use isolated ChromaDB instances so they don't pollute the
    production store or depend on the lazy singletons in the route module.
    """

    @pytest.fixture()
    def rag_client(self, tmp_path, monkeypatch):
        """FastAPI test client with RAG singletons patched to use tmp_path."""
        import os
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
        os.environ["CHROMA_PERSIST_DIRECTORY"] = str(tmp_path / "rag_chroma")
        os.environ["CHROMA_COLLECTION_NAME"] = "test_rag_col"
        os.environ["EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"

        from backend.app.config import get_settings
        from backend.app.database.session import configure_session_factory, get_engine
        from backend.app.database.base import Base
        get_settings.cache_clear()
        get_engine.cache_clear()
        engine = configure_session_factory(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(bind=engine)

        # Reset the module-level singletons before each test
        import backend.app.api.routes.rag as rag_module
        monkeypatch.setattr(rag_module, "_embedding_provider", None)
        monkeypatch.setattr(rag_module, "_vector_store", None)

        from backend.app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            yield c

        Base.metadata.drop_all(bind=engine)
        get_settings.cache_clear()
        get_engine.cache_clear()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("CHROMA_PERSIST_DIRECTORY", None)
        os.environ.pop("CHROMA_COLLECTION_NAME", None)
        os.environ.pop("EMBEDDING_MODEL", None)

    def test_rag_status_returns_ok(self, rag_client):
        response = rag_client.get("/api/v1/rag/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "chunk_count" in data

    def test_ingest_text_endpoint(self, rag_client):
        payload = {
            "document_id": "api-test-001",
            "path": "n/a",
            "text": "Pradhan Mantri Matru Vandana Yojana provides cash incentives to pregnant women.",
            "metadata": {"source": "api_test"},
        }
        response = rag_client.post("/api/v1/rag/ingest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["chunk_count"] >= 1

    def test_search_endpoint_returns_results(self, rag_client):
        # First ingest something
        rag_client.post("/api/v1/rag/ingest", json={
            "document_id": "api-test-002",
            "path": "n/a",
            "text": "Beti Bachao Beti Padhao promotes education and welfare of girl children across India.",
            "metadata": {"source": "api_test"},
        })
        response = rag_client.post("/api/v1/rag/search", json={"query": "girl child education welfare", "limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "girl child education welfare"
        assert isinstance(data["results"], list)
        assert data["total"] >= 1

    def test_search_empty_store_returns_empty(self, rag_client):
        response = rag_client.post("/api/v1/rag/search", json={"query": "housing scheme", "limit": 5})
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_search_limit_respected(self, rag_client):
        for i in range(5):
            rag_client.post("/api/v1/rag/ingest", json={
                "document_id": f"api-test-limit-{i}",
                "path": "n/a",
                "text": f"Government welfare scheme number {i} for women and children in India.",
                "metadata": {"source": "api_test"},
            })
        response = rag_client.post("/api/v1/rag/search", json={"query": "welfare scheme", "limit": 2})
        assert response.status_code == 200
        assert len(response.json()["results"]) <= 2
