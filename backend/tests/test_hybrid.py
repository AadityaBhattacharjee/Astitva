"""Phase 4 Hybrid RAG tests.

Covers:
  - SchemeStructuredRetriever: full eligibility filter matrix
  - SchemeStructuredRetriever: empty result when no schemes match
  - HybridRetriever: structured-only mode
  - HybridRetriever: vector-only mode
  - HybridRetriever: combined mode, source labelling
  - HybridRetriever: empty structured results (vector-only response)
  - HybridRetriever: empty vector results (structured-only response)
  - HybridRetriever: both arms empty
  - POST /api/v1/rag/hybrid-search endpoint (happy path, filter variants,
    empty query validation, empty-DB graceful response)
"""

import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database.base import Base
from backend.app.database.models.entities import Scheme
from backend.app.rag.retrieval.structured import SchemeStructuredRetriever, build_scheme_query


# ---------------------------------------------------------------------------
# Shared DB helpers
# ---------------------------------------------------------------------------

def _make_sqlite_session(tmp_path: Path) -> tuple[Session, Any]:
    """Return a (session, engine) pair backed by a temp SQLite file."""
    url = f"sqlite+pysqlite:///{tmp_path / 'hybrid_test.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory(), engine


def _add_scheme(
    session: Session,
    *,
    scheme_id: str,
    name: str,
    category: str = "General",
    state: str = "All States",
    target_group: str | None = "women",
    min_age: int | None = None,
    max_age: int | None = None,
    income_limit: int | None = None,
    active_status: bool = True,
    source: str = "test",
) -> Scheme:
    scheme = Scheme(
        scheme_id=scheme_id,
        scheme_name=name,
        category=category,
        state=state,
        target_group=target_group,
        min_age=min_age,
        max_age=max_age,
        income_limit=income_limit,
        active_status=active_status,
        source=source,
        benefits=[],
        required_documents=[],
    )
    session.add(scheme)
    session.commit()
    session.refresh(scheme)
    return scheme


# ---------------------------------------------------------------------------
# SchemeStructuredRetriever unit tests
# ---------------------------------------------------------------------------

class TestSchemeStructuredRetriever:
    @pytest.fixture()
    def db(self, tmp_path):
        session, engine = _make_sqlite_session(tmp_path)
        yield session
        session.close()
        Base.metadata.drop_all(bind=engine)

    def test_returns_all_active_when_no_filters(self, db):
        _add_scheme(db, scheme_id="s1", name="Alpha", active_status=True)
        _add_scheme(db, scheme_id="s2", name="Beta",  active_status=True)
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("anything")
        assert len(results) == 2

    def test_inactive_excluded_by_default(self, db):
        _add_scheme(db, scheme_id="s1", name="Active",   active_status=True)
        _add_scheme(db, scheme_id="s2", name="Inactive", active_status=False)
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("anything")
        assert len(results) == 1
        assert results[0]["name"] == "Active"

    def test_inactive_included_when_flag_cleared(self, db):
        _add_scheme(db, scheme_id="s1", name="Active",   active_status=True)
        _add_scheme(db, scheme_id="s2", name="Inactive", active_status=False)
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {"active_status": None})
        assert len(results) == 2

    def test_state_filter(self, db):
        _add_scheme(db, scheme_id="s1", name="Karnataka Scheme", state="Karnataka")
        _add_scheme(db, scheme_id="s2", name="Delhi Scheme",     state="Delhi")
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {"state": "Karnataka"})
        assert len(results) == 1
        assert results[0]["name"] == "Karnataka Scheme"

    def test_all_states_matches_any_state_filter(self, db):
        _add_scheme(db, scheme_id="s1", name="National", state="All States")
        _add_scheme(db, scheme_id="s2", name="Local",    state="Delhi")
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {"state": "Karnataka"})
        assert len(results) == 1
        assert results[0]["name"] == "National"

    def test_category_filter(self, db):
        _add_scheme(db, scheme_id="s1", name="Housing Scheme",   category="Housing")
        _add_scheme(db, scheme_id="s2", name="Healthcare Scheme", category="Healthcare")
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {"category": "Housing"})
        assert len(results) == 1
        assert results[0]["name"] == "Housing Scheme"

    def test_target_group_filter_exact(self, db):
        _add_scheme(db, scheme_id="s1", name="Women Scheme",          target_group="women")
        _add_scheme(db, scheme_id="s2", name="Single Parent Scheme",   target_group="single_parent")
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {"target_group": "women"})
        assert len(results) == 1
        assert results[0]["name"] == "Women Scheme"

    def test_target_group_none_always_matches(self, db):
        _add_scheme(db, scheme_id="s1", name="Universal", target_group=None)
        _add_scheme(db, scheme_id="s2", name="Specific",  target_group="widow")
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {"target_group": "women"})
        # NULL target_group passes through; "widow" does not match "women"
        assert len(results) == 1
        assert results[0]["name"] == "Universal"

    def test_age_filter_within_range(self, db):
        _add_scheme(db, scheme_id="s1", name="Youth Scheme",  min_age=18, max_age=35)
        _add_scheme(db, scheme_id="s2", name="Senior Scheme", min_age=60)
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {"age": 30})
        assert len(results) == 1
        assert results[0]["name"] == "Youth Scheme"

    def test_income_filter(self, db):
        _add_scheme(db, scheme_id="s1", name="Low Income",  income_limit=200000)
        _add_scheme(db, scheme_id="s2", name="No Cap",      income_limit=None)
        retriever = SchemeStructuredRetriever(db)
        # income=250000 > limit of 200000 → Low Income excluded, No Cap matches
        results = retriever.retrieve("q", {"income": 250000})
        assert len(results) == 1
        assert results[0]["name"] == "No Cap"

    def test_combined_filters(self, db):
        _add_scheme(db, scheme_id="s1", name="Match",    state="Karnataka", category="Housing",
                    target_group="women", min_age=21, max_age=45, income_limit=200000)
        _add_scheme(db, scheme_id="s2", name="No Match", state="Karnataka", category="Housing",
                    target_group="women", min_age=21, max_age=45, income_limit=150000)
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q", {
            "state": "Karnataka", "category": "Housing",
            "target_group": "women", "age": 34, "income": 180000,
        })
        assert len(results) == 1
        assert results[0]["name"] == "Match"

    def test_empty_result(self, db):
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("anything")
        assert results == []

    def test_result_has_source_type_tag(self, db):
        _add_scheme(db, scheme_id="s1", name="Scheme A")
        retriever = SchemeStructuredRetriever(db)
        results = retriever.retrieve("q")
        assert results[0]["_source_type"] == "structured_db"

    def test_result_fields_present(self, db):
        _add_scheme(db, scheme_id="s1", name="Scheme A", category="Housing", state="Delhi")
        retriever = SchemeStructuredRetriever(db)
        result = retriever.retrieve("q")[0]
        for field in ("scheme_id", "name", "category", "state", "active_status", "_source_type"):
            assert field in result, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# HybridRetriever unit tests (no database — uses mocks/stubs)
# ---------------------------------------------------------------------------

class _StubStructuredRetriever:
    """Stub that returns a fixed list of scheme dicts."""
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def retrieve(self, query, filters=None):
        return self._rows


class _StubVectorStore:
    """Stub that returns a fixed list of RetrievalResult objects."""
    def __init__(self, results):
        self._results = results

    def upsert_documents(self, documents):
        pass

    def similarity_search(self, query, limit=5):
        return self._results[:limit]


class TestHybridRetriever:
    from backend.app.rag.retrieval.hybrid import HybridRetriever

    def test_structured_only(self):
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        rows = [{"scheme_id": "s1", "name": "Housing", "source": "gov", "_source_type": "structured_db"}]
        retriever = HybridRetriever(structured_retriever=_StubStructuredRetriever(rows))
        result = retriever.search("housing support")
        assert len(result["schemes"]) == 1
        assert result["documents"] == []
        assert "gov" in result["sources"]

    def test_vector_only(self):
        from backend.app.rag.interfaces import RetrievalResult, DocumentMetadata
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        hits = [RetrievalResult(content="chunk text", score=0.9, source_id="doc-1",
                                metadata=DocumentMetadata(source="pdf_ingestion"))]
        retriever = HybridRetriever(vector_store=_StubVectorStore(hits))
        result = retriever.search("housing support")
        assert result["schemes"] == []
        assert len(result["documents"]) == 1
        assert result["documents"][0]["_source_type"] == "vector_store"
        assert "pdf_ingestion" in result["sources"]

    def test_combined_both_arms(self):
        from backend.app.rag.interfaces import RetrievalResult, DocumentMetadata
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        rows = [{"scheme_id": "s1", "name": "PMAY", "source": "gov_db", "_source_type": "structured_db"}]
        hits = [RetrievalResult(content="chunk", score=0.8, source_id="c1",
                                metadata=DocumentMetadata(source="pdf"))]
        retriever = HybridRetriever(
            structured_retriever=_StubStructuredRetriever(rows),
            vector_store=_StubVectorStore(hits),
        )
        result = retriever.search("housing")
        assert len(result["schemes"]) == 1
        assert len(result["documents"]) == 1
        assert "gov_db" in result["sources"]
        assert "pdf" in result["sources"]

    def test_both_arms_empty(self):
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        retriever = HybridRetriever(
            structured_retriever=_StubStructuredRetriever([]),
            vector_store=_StubVectorStore([]),
        )
        result = retriever.search("anything")
        assert result["schemes"] == []
        assert result["documents"] == []
        assert result["sources"] == []

    def test_no_retrievers_returns_empty(self):
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        retriever = HybridRetriever()
        result = retriever.search("query")
        assert result["schemes"] == []
        assert result["documents"] == []

    def test_vector_limit_respected(self):
        from backend.app.rag.interfaces import RetrievalResult
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        hits = [RetrievalResult(content=f"chunk {i}", score=0.9 - i * 0.1, source_id=f"c{i}") for i in range(10)]
        retriever = HybridRetriever(vector_store=_StubVectorStore(hits))
        result = retriever.search("query", vector_limit=3)
        assert len(result["documents"]) <= 3

    def test_result_query_field_preserved(self):
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        retriever = HybridRetriever()
        result = retriever.search("my specific query")
        assert result["query"] == "my specific query"

    def test_source_deduplication(self):
        from backend.app.rag.interfaces import RetrievalResult, DocumentMetadata
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        hits = [
            RetrievalResult(content="a", score=0.9, source_id="c1", metadata=DocumentMetadata(source="shared_src")),
            RetrievalResult(content="b", score=0.8, source_id="c2", metadata=DocumentMetadata(source="shared_src")),
        ]
        retriever = HybridRetriever(vector_store=_StubVectorStore(hits))
        result = retriever.search("q")
        assert result["sources"].count("shared_src") == 1

    def test_document_score_preserved(self):
        from backend.app.rag.interfaces import RetrievalResult
        from backend.app.rag.retrieval.hybrid import HybridRetriever
        hits = [RetrievalResult(content="text", score=0.753, source_id="x")]
        retriever = HybridRetriever(vector_store=_StubVectorStore(hits))
        result = retriever.search("q")
        assert result["documents"][0]["score"] == pytest.approx(0.753)


# ---------------------------------------------------------------------------
# POST /api/v1/rag/hybrid-search endpoint tests
# ---------------------------------------------------------------------------

class TestHybridSearchEndpoint:
    """Test the hybrid-search endpoint through the FastAPI test client.

    Uses an isolated SQLite DB + isolated Chroma instance per test.
    """

    @pytest.fixture()
    def hybrid_client(self, tmp_path, monkeypatch):
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
        os.environ["CHROMA_PERSIST_DIRECTORY"] = str(tmp_path / "hybrid_chroma")
        os.environ["CHROMA_COLLECTION_NAME"] = "hybrid_test_col"
        os.environ["EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"

        from backend.app.config import get_settings
        from backend.app.database.session import configure_session_factory, get_engine
        from backend.app.database.base import Base
        get_settings.cache_clear()
        get_engine.cache_clear()
        engine = configure_session_factory(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(bind=engine)

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
        for key in ("DATABASE_URL", "CHROMA_PERSIST_DIRECTORY", "CHROMA_COLLECTION_NAME", "EMBEDDING_MODEL"):
            os.environ.pop(key, None)

    def _seed_scheme(self, client, **kwargs):
        """Helper: seed a scheme via the schemes API."""
        defaults = dict(
            scheme_id="HYBRID-001", name="Test Scheme",
            description="Test", category="Housing", state="Karnataka",
            target_group="women", min_age=None, max_age=None,
            income_limit=None, eligibility=None, age_criteria=None,
            income_criteria=None, benefits=[], required_documents=[],
            application_process=None, official_url=None,
            source="test", last_verified=None, active_status=True,
        )
        defaults.update(kwargs)
        resp = client.post("/api/v1/schemes/", json=defaults)
        assert resp.status_code == 201, resp.text

    def test_empty_query_returns_422(self, hybrid_client):
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={"query": "   "})
        assert resp.status_code == 422

    def test_response_has_required_keys(self, hybrid_client):
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={"query": "housing"})
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data
        assert "schemes" in data
        assert "documents" in data
        assert "sources" in data

    def test_empty_db_returns_empty_schemes(self, hybrid_client):
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={"query": "housing support"})
        assert resp.status_code == 200
        assert resp.json()["schemes"] == []

    def test_structured_result_returned(self, hybrid_client):
        self._seed_scheme(hybrid_client, scheme_id="H001", name="Karnataka Housing",
                          state="Karnataka", category="Housing", target_group="women")
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={
            "query": "housing support", "state": "Karnataka",
        })
        assert resp.status_code == 200
        schemes = resp.json()["schemes"]
        assert len(schemes) == 1
        assert schemes[0]["name"] == "Karnataka Housing"

    def test_state_filter_applied(self, hybrid_client):
        self._seed_scheme(hybrid_client, scheme_id="H001", name="Karnataka Scheme", state="Karnataka")
        self._seed_scheme(hybrid_client, scheme_id="H002", name="Delhi Scheme",     state="Delhi")
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={
            "query": "scheme", "state": "Karnataka",
        })
        schemes = resp.json()["schemes"]
        assert all(s["state"] == "Karnataka" for s in schemes)
        names = [s["name"] for s in schemes]
        assert "Delhi Scheme" not in names

    def test_age_income_filters_applied(self, hybrid_client):
        self._seed_scheme(hybrid_client, scheme_id="H001", name="Eligible",   income_limit=200000, min_age=20, max_age=40)
        self._seed_scheme(hybrid_client, scheme_id="H002", name="Too Old",    income_limit=200000, min_age=50)
        self._seed_scheme(hybrid_client, scheme_id="H003", name="Too Costly", income_limit=100000)
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={
            "query": "benefit", "age": 30, "income": 180000,
        })
        names = [s["name"] for s in resp.json()["schemes"]]
        assert "Eligible" in names
        assert "Too Old" not in names
        assert "Too Costly" not in names

    def test_inactive_excluded_by_default(self, hybrid_client):
        self._seed_scheme(hybrid_client, scheme_id="H001", name="Active",   active_status=True)
        self._seed_scheme(hybrid_client, scheme_id="H002", name="Inactive", active_status=False)
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={"query": "scheme"})
        names = [s["name"] for s in resp.json()["schemes"]]
        assert "Active" in names
        assert "Inactive" not in names

    def test_vector_results_when_docs_ingested(self, hybrid_client):
        hybrid_client.post("/api/v1/rag/ingest", json={
            "document_id": "hyb-doc-1",
            "path": "n/a",
            "text": "Pradhan Mantri Awas Yojana provides housing assistance to low income families.",
            "metadata": {"source": "hybrid_test"},
        })
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={
            "query": "housing for poor families", "vector_limit": 3,
        })
        assert resp.status_code == 200
        assert len(resp.json()["documents"]) >= 1

    def test_combined_result_has_both_arms(self, hybrid_client):
        self._seed_scheme(hybrid_client, scheme_id="H001", name="Combined Scheme")
        hybrid_client.post("/api/v1/rag/ingest", json={
            "document_id": "hyb-doc-2",
            "path": "n/a",
            "text": "Government support scheme for women entrepreneurship and skill development.",
            "metadata": {"source": "hybrid_test"},
        })
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={
            "query": "women support scheme", "vector_limit": 3,
        })
        data = resp.json()
        assert len(data["schemes"]) >= 1
        assert len(data["documents"]) >= 1

    def test_sources_list_populated(self, hybrid_client):
        self._seed_scheme(hybrid_client, scheme_id="H001", name="PMAY", source="govt_portal")
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={"query": "housing"})
        assert "govt_portal" in resp.json()["sources"]

    def test_query_echoed_in_response(self, hybrid_client):
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={"query": "my test query"})
        assert resp.json()["query"] == "my test query"

    def test_vector_limit_parameter_respected(self, hybrid_client):
        for i in range(8):
            hybrid_client.post("/api/v1/rag/ingest", json={
                "document_id": f"lim-doc-{i}",
                "path": "n/a",
                "text": f"Government welfare scheme number {i} for women in India.",
                "metadata": {"source": "limit_test"},
            })
        resp = hybrid_client.post("/api/v1/rag/hybrid-search", json={
            "query": "welfare scheme women", "vector_limit": 2,
        })
        assert len(resp.json()["documents"]) <= 2
