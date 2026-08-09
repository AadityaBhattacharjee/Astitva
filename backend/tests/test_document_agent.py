"""Document Agent tests — Phase 6.

Covers:
- Successful RAG retrieval + Granite generation
- Insufficient evidence path
- No vector store (graceful degradation)
- Prompt building helpers
- Document endpoint authentication (401 unauthenticated)
- Authenticated document query → 200
- Empty query → 422
- Wrong token → 401
- Supervisor routes 'document' queries correctly (no changes to supervisor needed)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.agents.base import AgentRequest
from backend.app.agents.document.agent import (
    DocumentAgent,
    _INSUFFICIENT,
    _build_document_prompt,
    _parse_document_response,
)
from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.models import entities as _entities_import  # noqa: F401
from backend.app.database.session import configure_session_factory, get_engine
from backend.app.services.llm_provider import BaseLLMProvider, PlaceholderLLMProvider

_TEST_SECRET = "test-secret-doc-agent"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "doc_agent_test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"

    os.environ["DATABASE_URL"] = database_url
    os.environ["SECRET_KEY"] = _TEST_SECRET
    os.environ["GRANITE_BASE_URL"] = ""
    os.environ["HF_API_TOKEN"] = ""
    os.environ["GRANITE_MODEL_ID"] = ""

    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = configure_session_factory(database_url)
    Base.metadata.create_all(bind=engine)

    from backend.app.main import app

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SECRET_KEY", None)
    os.environ.pop("GRANITE_BASE_URL", None)
    os.environ.pop("HF_API_TOKEN", None)
    os.environ.pop("GRANITE_MODEL_ID", None)
    get_settings.cache_clear()
    get_engine.cache_clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(
    client: TestClient,
    email: str = "doc@example.com",
    password: str = "pass123",
) -> str:
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


class _MockLLM(BaseLLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.call_count += 1
        return self._response


class _MockVectorStore:
    """Minimal stub mimicking ChromaStore.similarity_search return value."""

    def __init__(self, results: list[Any] | None = None) -> None:
        self._results = results or []
        self.last_query: str = ""

    def similarity_search(self, query: str, limit: int = 5) -> list[Any]:
        self.last_query = query
        return self._results[:limit]


class _FakeResult:
    """Mimics a RetrievalResult for unit tests without loading ChromaDB."""

    def __init__(self, content: str, source_id: str = "test_src") -> None:
        self.content = content
        self.source_id = source_id
        self.score = 0.9
        self.metadata = None  # agent checks for None and skips .model_dump()


# ---------------------------------------------------------------------------
# Unit tests — _build_document_prompt
# ---------------------------------------------------------------------------

class TestBuildDocumentPrompt:
    def test_includes_query(self):
        prompt = _build_document_prompt("What is an Aadhaar card?", [])
        assert "What is an Aadhaar card?" in prompt

    def test_no_documents_shows_no_excerpts_message(self):
        prompt = _build_document_prompt("test query", [])
        assert "No relevant excerpts found" in prompt

    def test_with_documents_shows_excerpt(self):
        docs = [{"content": "Aadhaar is a 12-digit ID.", "metadata": {"source": "gov_doc"}}]
        prompt = _build_document_prompt("What is Aadhaar?", docs)
        assert "Aadhaar is a 12-digit ID." in prompt
        assert "gov_doc" in prompt

    def test_caps_at_six_excerpts(self):
        docs = [{"content": f"chunk {i}", "metadata": {}} for i in range(10)]
        prompt = _build_document_prompt("query", docs)
        assert "chunk 5" in prompt
        assert "chunk 6" not in prompt  # 0-indexed, 6 shown → chunk 0..5


# ---------------------------------------------------------------------------
# Unit tests — _parse_document_response
# ---------------------------------------------------------------------------

class TestParseDocumentResponse:
    def test_insufficient_sentinel_returns_fallback(self):
        result = _parse_document_response(_INSUFFICIENT)
        assert result["answer"] == _INSUFFICIENT
        assert result["guidance"] == []

    def test_empty_string_returns_fallback(self):
        result = _parse_document_response("")
        assert result["answer"] == _INSUFFICIENT

    def test_valid_json_parsed_correctly(self):
        payload = {
            "answer": "Bring Aadhaar and PAN.",
            "guidance": [{"step": "Visit office", "details": ""}],
            "required_documents": ["Aadhaar"],
            "sources": ["gov_portal"],
        }
        result = _parse_document_response(json.dumps(payload))
        assert result["answer"] == "Bring Aadhaar and PAN."
        assert result["required_documents"] == ["Aadhaar"]

    def test_json_wrapped_in_prose_extracted(self):
        inner = json.dumps({"answer": "ok", "guidance": [], "required_documents": [], "sources": []})
        wrapped = f"Here is the answer: {inner} end."
        result = _parse_document_response(wrapped)
        assert result["answer"] == "ok"

    def test_unparseable_returns_raw_as_answer(self):
        result = _parse_document_response("plain text response")
        assert result["answer"] == "plain text response"
        assert result["guidance"] == []


# ---------------------------------------------------------------------------
# Unit tests — DocumentAgent.handle
# ---------------------------------------------------------------------------

class TestDocumentAgentHandle:
    def _make_agent(self, llm_response: str, vector_results: list | None = None) -> DocumentAgent:
        results = [_FakeResult(c) for c in (vector_results or [])]
        vs = _MockVectorStore(results)
        llm = _MockLLM(llm_response)
        return DocumentAgent(vector_store=vs, llm_provider=llm)

    def test_successful_rag_and_generation(self):
        good_response = json.dumps({
            "answer": "You need your Aadhaar card.",
            "guidance": [{"step": "Visit CSC", "details": ""}],
            "required_documents": ["Aadhaar"],
            "sources": ["source1"],
        })
        agent = self._make_agent(good_response, ["Aadhaar is issued by UIDAI."])
        resp = agent.handle(AgentRequest(query="How do I get Aadhaar?"))
        assert resp.status == "ok"
        assert resp.agent_name == "document"
        assert "Aadhaar" in resp.summary
        assert resp.data["evidence"]["documents_count"] == 1
        assert resp.data["evidence"]["insufficient_evidence"] is False

    def test_insufficient_evidence_when_no_chunks(self):
        agent = DocumentAgent(
            vector_store=_MockVectorStore([]),
            llm_provider=_MockLLM(_INSUFFICIENT),
        )
        resp = agent.handle(AgentRequest(query="obscure query"))
        assert resp.status == "insufficient_evidence"
        assert resp.data["evidence"]["insufficient_evidence"] is True

    def test_llm_called_once_per_query(self):
        llm = _MockLLM("plain text answer")
        agent = DocumentAgent(
            vector_store=_MockVectorStore([_FakeResult("chunk content")]),
            llm_provider=llm,
        )
        agent.handle(AgentRequest(query="test"))
        assert llm.call_count == 1

    def test_no_vector_store_gracefully_returns_insufficient(self):
        agent = DocumentAgent(
            vector_store=None,  # type: ignore[arg-type]
            llm_provider=_MockLLM(_INSUFFICIENT),
        )
        resp = agent.handle(AgentRequest(query="any query"))
        assert resp.status == "insufficient_evidence"

    def test_sources_merged_from_llm_and_vector_store(self):
        chunk = _FakeResult("content", source_id="vec_src")
        chunk.metadata = type("M", (), {"model_dump": lambda self: {"source": "file_src"}})()
        vs = _MockVectorStore([chunk])
        good_resp = json.dumps({
            "answer": "ok", "guidance": [], "required_documents": [],
            "sources": ["llm_src"],
        })
        agent = DocumentAgent(vector_store=vs, llm_provider=_MockLLM(good_resp))
        resp = agent.handle(AgentRequest(query="q"))
        assert "llm_src" in resp.sources
        assert "file_src" in resp.sources

    def test_response_fields_present(self):
        agent = self._make_agent("plain answer")
        resp = agent.handle(AgentRequest(query="test"))
        assert hasattr(resp, "agent_name")
        assert hasattr(resp, "status")
        assert hasattr(resp, "summary")
        assert "guidance" in resp.data
        assert "required_documents" in resp.data


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestDocumentEndpoint:
    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/document",
            json={"query": "What documents do I need?"},
        )
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/document",
            json={"query": "What documents do I need?"},
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401

    def test_authenticated_query_returns_200(self, client: TestClient):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/agents/document",
            json={"query": "What documents do I need for Aadhaar enrolment?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_name"] == "document"
        assert "answer" in body
        assert "guidance" in body
        assert "required_documents" in body
        assert "sources" in body

    def test_empty_query_returns_422(self, client: TestClient):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/agents/document",
            json={"query": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_response_status_field_present(self, client: TestClient):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/agents/document",
            json={"query": "Tell me about PAN card application"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "status" in resp.json()

    def test_vector_limit_accepted(self, client: TestClient):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/agents/document",
            json={"query": "Aadhaar documents", "vector_limit": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Supervisor routing test for 'document' domain
# ---------------------------------------------------------------------------

class TestSupervisorDocumentRouting:
    def test_supervisor_routes_document_query(self, client: TestClient):
        token = _register_and_login(client, email="sv_doc@example.com")
        resp = client.post(
            "/api/v1/agents/supervisor",
            json={"query": "How do I get my birth certificate and Aadhaar card?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "document"
