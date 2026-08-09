"""Phase 5 — Government Agent + LLM provider tests.

All tests that require LLM responses use a MockLLMProvider so that
NO HF credentials are needed during the test suite.

One optional integration test is gated behind the presence of
HF_API_TOKEN; it is skipped automatically in CI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.base import AgentRequest
from backend.app.agents.government.agent import (
    GovernmentAgent,
    _build_evidence_block,
    _build_user_prompt,
    _parse_llm_response,
)
from backend.app.database.base import Base
from backend.app.database.models.entities import Scheme
from backend.app.rag.retrieval.hybrid import HybridRetriever
from backend.app.rag.retrieval.structured import SchemeStructuredRetriever
from backend.app.services.llm_provider import (
    BaseLLMProvider,
    GraniteLLMProvider,
    PlaceholderLLMProvider,
    get_llm_provider,
)

# ---------------------------------------------------------------------------
# HF provider unit tests (mocked — no real API calls)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------

class MockLLMProvider(BaseLLMProvider):
    """Deterministic LLM stub for unit/integration tests.

    ``responses`` is a dict mapping prompt substrings to canned responses.
    If no key matches, ``default`` is returned.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default: str | None = None,
    ) -> None:
        self._responses = responses or {}
        self._default = default or json.dumps({
            "answer": "Based on the evidence you qualify for the provided schemes.",
            "recommended_schemes": [],
            "additional_context": "Mock context.",
            "sources": ["mock_source"],
        })
        self.last_prompt: str = ""
        self.last_system: str | None = None
        self.call_count: int = 0

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.last_prompt = prompt
        self.last_system = system
        self.call_count += 1
        for key, resp in self._responses.items():
            if key in prompt:
                return resp
        return self._default


# ---------------------------------------------------------------------------
# Stubs for retriever components
# ---------------------------------------------------------------------------

class _StubStructuredRetriever:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def retrieve(self, query: str, filters: dict | None = None) -> list[dict[str, Any]]:
        return self._rows


class _StubVectorStore:
    def __init__(self, results: list[Any] | None = None):
        self._results = results or []

    def upsert_documents(self, documents: list[dict[str, Any]]) -> None:
        pass

    def similarity_search(self, query: str, limit: int = 5):
        return self._results[:limit]


# ---------------------------------------------------------------------------
# SQLite DB helpers
# ---------------------------------------------------------------------------

def _make_session(tmp_path: Path) -> tuple[Session, Any]:
    url = f"sqlite+pysqlite:///{tmp_path / 'gov_agent_test.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory(), engine


def _add_scheme(session: Session, **kwargs) -> Scheme:
    defaults = dict(
        scheme_id="S001", scheme_name="Test Scheme", category="General",
        state="All States", target_group="women", active_status=True,
        source="test_db", benefits=[], required_documents=[],
    )
    defaults.update(kwargs)
    scheme = Scheme(**defaults)
    session.add(scheme)
    session.commit()
    session.refresh(scheme)
    return scheme


# ---------------------------------------------------------------------------
# LLM provider tests
# ---------------------------------------------------------------------------

def _make_fake_httpx_post(content: str = "ok", status_code: int = 200,
                           captured: list | None = None):
    """Return a monkeypatch-compatible replacement for httpx.post.

    Captures the JSON payload in ``captured[0]`` if provided.
    Returns a minimal Response-like object whose .json() matches the
    OpenAI chat/completions shape.
    """
    import httpx

    class _FakeResponse:
        def raise_for_status(self):
            if status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"HTTP {status_code}", request=None, response=self  # type: ignore[arg-type]
                )

        def json(self):
            return {
                "choices": [{"message": {"content": content}}]
            } if content is not None else {"choices": []}

    def _fake_post(url, *, json=None, headers=None, timeout=None, **kw):
        if captured is not None:
            captured.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse()

    return _fake_post


class TestLLMProvider:
    def test_placeholder_returns_string(self):
        provider = PlaceholderLLMProvider()
        result = provider.generate("any prompt")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_placeholder_ignores_system(self):
        provider = PlaceholderLLMProvider()
        r1 = provider.generate("q")
        r2 = provider.generate("q", system="system instructions")
        assert r1 == r2

    def test_get_llm_provider_local_url_returns_granite(self, monkeypatch):
        """GRANITE_BASE_URL set → local GraniteLLMProvider."""
        monkeypatch.setenv("GRANITE_BASE_URL", "http://127.0.0.1:8080/v1")
        monkeypatch.setenv("GRANITE_LOCAL_MODEL_ID", "mlx-community/granite-3.3-8b-instruct-8bit")
        monkeypatch.setenv("HF_API_TOKEN", "")
        from backend.app.config import get_settings
        get_settings.cache_clear()
        provider = get_llm_provider()
        assert isinstance(provider, GraniteLLMProvider)
        assert provider._base_url == "http://127.0.0.1:8080/v1"
        assert provider._api_token == ""
        get_settings.cache_clear()

    def test_get_llm_provider_hf_token_returns_granite(self, monkeypatch):
        """No local URL + HF_API_TOKEN set → HF GraniteLLMProvider."""
        monkeypatch.setenv("GRANITE_BASE_URL", "")
        monkeypatch.setenv("HF_API_TOKEN", "hf_fake_token")
        from backend.app.config import get_settings
        get_settings.cache_clear()
        provider = get_llm_provider()
        assert isinstance(provider, GraniteLLMProvider)
        assert "huggingface" in provider._base_url
        assert provider._api_token == "hf_fake_token"
        get_settings.cache_clear()

    def test_get_llm_provider_neither_returns_placeholder(self, monkeypatch):
        monkeypatch.setenv("GRANITE_BASE_URL", "")
        monkeypatch.setenv("HF_API_TOKEN", "")
        from backend.app.config import get_settings
        get_settings.cache_clear()
        provider = get_llm_provider()
        assert isinstance(provider, PlaceholderLLMProvider)
        get_settings.cache_clear()

    def test_granite_provider_instantiates_without_http_call(self):
        """GraniteLLMProvider must not make any network call at construction."""
        provider = GraniteLLMProvider(
            base_url="http://127.0.0.1:8080/v1",
            model_id="mlx-community/granite-3.3-8b-instruct-8bit",
        )
        assert provider._base_url == "http://127.0.0.1:8080/v1"
        assert provider._model_id == "mlx-community/granite-3.3-8b-instruct-8bit"
        assert provider._api_token == ""

    def test_granite_provider_stores_model_id(self):
        provider = GraniteLLMProvider(
            base_url="http://127.0.0.1:8080/v1",
            model_id="mlx-community/granite-3.3-8b-instruct-8bit",
        )
        assert provider._model_id == "mlx-community/granite-3.3-8b-instruct-8bit"

    def test_granite_provider_calls_correct_url(self, monkeypatch):
        captured: list = []
        import httpx
        monkeypatch.setattr(httpx, "post", _make_fake_httpx_post("hi", captured=captured))
        provider = GraniteLLMProvider(
            base_url="http://127.0.0.1:8080/v1",
            model_id="mlx-community/granite-3.3-8b-instruct-8bit",
        )
        provider.generate("hello")
        assert len(captured) == 1
        assert captured[0]["url"] == "http://127.0.0.1:8080/v1/chat/completions"

    def test_granite_provider_returns_content(self, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "post", _make_fake_httpx_post("the answer"))
        provider = GraniteLLMProvider(base_url="http://x/v1", model_id="m")
        assert provider.generate("q") == "the answer"

    def test_granite_provider_passes_system_as_system_message(self, monkeypatch):
        """System prompt must appear as a 'system' role message in the payload."""
        captured: list = []
        import httpx
        monkeypatch.setattr(httpx, "post", _make_fake_httpx_post("resp", captured=captured))
        provider = GraniteLLMProvider(base_url="http://x/v1", model_id="m")
        provider.generate("user msg", system="system msg")
        messages = captured[0]["json"]["messages"]
        roles = [m["role"] for m in messages]
        assert roles[0] == "system"
        assert roles[1] == "user"
        assert messages[0]["content"] == "system msg"
        assert messages[1]["content"] == "user msg"

    def test_granite_provider_no_system_omits_system_message(self, monkeypatch):
        captured: list = []
        import httpx
        monkeypatch.setattr(httpx, "post", _make_fake_httpx_post("resp", captured=captured))
        provider = GraniteLLMProvider(base_url="http://x/v1", model_id="m")
        provider.generate("only user msg")
        messages = captured[0]["json"]["messages"]
        assert all(m["role"] != "system" for m in messages)

    def test_granite_provider_no_auth_header_for_local(self, monkeypatch):
        """No Authorization header when api_token is empty."""
        captured: list = []
        import httpx
        monkeypatch.setattr(httpx, "post", _make_fake_httpx_post("ok", captured=captured))
        provider = GraniteLLMProvider(base_url="http://x/v1", model_id="m", api_token="")
        provider.generate("q")
        assert "Authorization" not in (captured[0]["headers"] or {})

    def test_granite_provider_auth_header_when_token_set(self, monkeypatch):
        """Authorization header present when api_token is non-empty."""
        captured: list = []
        import httpx
        monkeypatch.setattr(httpx, "post", _make_fake_httpx_post("ok", captured=captured))
        provider = GraniteLLMProvider(base_url="http://x/v1", model_id="m", api_token="hf_abc")
        provider.generate("q")
        assert captured[0]["headers"].get("Authorization") == "Bearer hf_abc"

    def test_granite_provider_empty_choices_returns_empty_string(self, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "post", _make_fake_httpx_post(None))
        provider = GraniteLLMProvider(base_url="http://x/v1", model_id="m")
        assert provider.generate("q") == ""

    def test_mock_provider_captures_prompt(self):
        mock = MockLLMProvider()
        mock.generate("hello world", system="sys")
        assert "hello world" in mock.last_prompt
        assert mock.last_system == "sys"
        assert mock.call_count == 1


# ---------------------------------------------------------------------------
# Agent helper function tests
# ---------------------------------------------------------------------------

class TestAgentHelpers:
    def test_build_evidence_block_with_schemes(self):
        evidence = {
            "schemes": [{"name": "PMAY", "category": "Housing", "state": "Karnataka",
                         "target_group": "women", "benefits": ["Subsidy"],
                         "required_documents": ["Aadhaar"], "source": "gov"}],
            "documents": [],
        }
        block = _build_evidence_block(evidence)
        assert "PMAY" in block
        assert "Housing" in block
        assert "Subsidy" in block

    def test_build_evidence_block_no_schemes(self):
        evidence = {"schemes": [], "documents": []}
        block = _build_evidence_block(evidence)
        assert "No matching schemes" in block

    def test_build_evidence_block_with_documents(self):
        from backend.app.rag.interfaces import RetrievalResult, DocumentMetadata
        evidence = {
            "schemes": [],
            "documents": [
                {"content": "PMAY housing subsidy details", "score": 0.9,
                 "source_id": "c1", "metadata": {"source": "pdf_ingest"}, "_source_type": "vector_store"}
            ],
        }
        block = _build_evidence_block(evidence)
        assert "PMAY housing subsidy details" in block
        assert "pdf_ingest" in block

    def test_build_user_prompt_includes_profile(self):
        prompt = _build_user_prompt(
            "What support can I get?",
            {"state": "Karnataka", "age": 30, "income": 180000},
            "EVIDENCE",
        )
        assert "Karnataka" in prompt
        assert "30" in prompt
        assert "180,000" in prompt
        assert "What support can I get?" in prompt

    def test_build_user_prompt_no_profile(self):
        prompt = _build_user_prompt("My query", {}, "EVIDENCE")
        assert "No profile provided" in prompt

    def test_parse_llm_response_valid_json(self):
        payload = json.dumps({
            "answer": "You qualify.",
            "recommended_schemes": [{"name": "PMAY"}],
            "additional_context": "ctx",
            "sources": ["gov"],
        })
        parsed = _parse_llm_response(payload)
        assert parsed["answer"] == "You qualify."
        assert parsed["recommended_schemes"][0]["name"] == "PMAY"
        assert parsed["sources"] == ["gov"]

    def test_parse_llm_response_insufficient(self):
        parsed = _parse_llm_response("I could not find sufficient verified information.")
        assert parsed["answer"] == "I could not find sufficient verified information."
        assert parsed["recommended_schemes"] == []

    def test_parse_llm_response_empty_string(self):
        parsed = _parse_llm_response("")
        assert parsed["answer"] == "I could not find sufficient verified information."

    def test_parse_llm_response_json_embedded_in_prose(self):
        raw = 'Here is my answer: {"answer": "OK", "recommended_schemes": [], "additional_context": "", "sources": []}'
        parsed = _parse_llm_response(raw)
        assert parsed["answer"] == "OK"

    def test_parse_llm_response_bad_json_returns_raw(self):
        raw = "This is plain prose that is not JSON."
        parsed = _parse_llm_response(raw)
        assert parsed["answer"] == raw
        assert parsed["recommended_schemes"] == []


# ---------------------------------------------------------------------------
# GovernmentAgent unit tests (mocked retriever + mocked LLM)
# ---------------------------------------------------------------------------

class TestGovernmentAgent:
    def _make_agent(self, schemes: list[dict], llm_response: str) -> GovernmentAgent:
        retriever = HybridRetriever(
            structured_retriever=_StubStructuredRetriever(schemes),
            vector_store=_StubVectorStore([]),
        )
        llm = MockLLMProvider(default=llm_response)
        return GovernmentAgent(hybrid_retriever=retriever, llm_provider=llm)

    def test_agent_name(self):
        agent = self._make_agent([], '{"answer":"","recommended_schemes":[],"additional_context":"","sources":[]}')
        assert agent.name == "government"

    def test_returns_agentresponse(self):
        from backend.app.agents.base import AgentResponse
        agent = self._make_agent([], '{"answer":"ok","recommended_schemes":[],"additional_context":"","sources":[]}')
        result = agent.handle(AgentRequest(query="test"))
        assert isinstance(result, AgentResponse)
        assert result.agent_name == "government"
        assert result.status == "ok"

    def test_llm_called_once(self):
        llm = MockLLMProvider()
        retriever = HybridRetriever(structured_retriever=_StubStructuredRetriever([]))
        agent = GovernmentAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.call_count == 1

    def test_system_prompt_passed_to_llm(self):
        llm = MockLLMProvider()
        retriever = HybridRetriever(structured_retriever=_StubStructuredRetriever([]))
        agent = GovernmentAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.last_system is not None
        assert "evidence" in llm.last_system.lower() or "welfare" in llm.last_system.lower()

    def test_profile_filters_passed_to_retriever(self):
        captured_filters: dict[str, Any] = {}

        class CapturingRetriever:
            def retrieve(self, query: str, filters: dict | None = None):
                captured_filters.update(filters or {})
                return []

        retriever = HybridRetriever(structured_retriever=CapturingRetriever())
        agent = GovernmentAgent(hybrid_retriever=retriever, llm_provider=MockLLMProvider())
        agent.handle(AgentRequest(query="q", context={"state": "Karnataka", "age": 30, "income": 180000}))
        assert captured_filters["state"] == "Karnataka"
        assert captured_filters["age"] == 30
        assert captured_filters["income"] == 180000

    def test_sources_merged_from_retriever_and_llm(self):
        schemes = [{"scheme_id": "s1", "name": "PMAY", "source": "gov_db", "_source_type": "structured_db"}]
        llm_resp = json.dumps({
            "answer": "ok", "recommended_schemes": [],
            "additional_context": "", "sources": ["llm_src"],
        })
        agent = self._make_agent(schemes, llm_resp)
        result = agent.handle(AgentRequest(query="housing support"))
        assert "gov_db" in result.sources
        assert "llm_src" in result.sources

    def test_insufficient_evidence_returns_sentinel(self):
        agent = self._make_agent(
            [],
            "I could not find sufficient verified information.",
        )
        result = agent.handle(AgentRequest(query="obscure query"))
        assert "could not find" in result.summary.lower()

    def test_evidence_counts_in_data(self):
        from backend.app.rag.interfaces import RetrievalResult
        schemes = [{"scheme_id": "s1", "name": "X", "source": "s", "_source_type": "structured_db"}]
        doc_hit = RetrievalResult(content="chunk", score=0.9, source_id="c1")
        retriever = HybridRetriever(
            structured_retriever=_StubStructuredRetriever(schemes),
            vector_store=_StubVectorStore([doc_hit]),
        )
        agent = GovernmentAgent(hybrid_retriever=retriever, llm_provider=MockLLMProvider())
        result = agent.handle(AgentRequest(query="q"))
        ev = result.data["evidence"]
        assert ev["schemes_count"] == 1
        assert ev["documents_count"] == 1

    def test_recommended_schemes_in_data_when_llm_returns_them(self):
        llm_resp = json.dumps({
            "answer": "You qualify.",
            "recommended_schemes": [{"name": "PMAY", "eligibility_reasoning": "income < 200000"}],
            "additional_context": "",
            "sources": [],
        })
        agent = self._make_agent([], llm_resp)
        result = agent.handle(AgentRequest(query="housing"))
        schemes = result.data["recommended_schemes"]
        assert len(schemes) == 1
        assert schemes[0]["name"] == "PMAY"

    def test_query_appears_in_llm_prompt(self):
        llm = MockLLMProvider()
        retriever = HybridRetriever(structured_retriever=_StubStructuredRetriever([]))
        agent = GovernmentAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="maternity support Karnataka"))
        assert "maternity support Karnataka" in llm.last_prompt

    def test_source_deduplication(self):
        schemes = [
            {"scheme_id": "s1", "name": "A", "source": "shared_src", "_source_type": "structured_db"},
            {"scheme_id": "s2", "name": "B", "source": "shared_src", "_source_type": "structured_db"},
        ]
        llm_resp = json.dumps({
            "answer": "ok", "recommended_schemes": [],
            "additional_context": "", "sources": ["shared_src"],
        })
        agent = self._make_agent(schemes, llm_resp)
        result = agent.handle(AgentRequest(query="q"))
        assert result.sources.count("shared_src") == 1


# ---------------------------------------------------------------------------
# POST /api/v1/agents/government endpoint tests
# ---------------------------------------------------------------------------

class TestGovernmentAgentEndpoint:
    @pytest.fixture()
    def gov_client(self, tmp_path, monkeypatch):
        """Isolated test client with mocked LLM and empty DB."""
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
        os.environ["CHROMA_PERSIST_DIRECTORY"] = str(tmp_path / "gov_chroma")
        os.environ["CHROMA_COLLECTION_NAME"] = "gov_test_col"
        os.environ["EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
        # Override .env values so pydantic-settings picks up empty strings
        # (os.environ takes precedence over the .env file).
        # Blank both the local URL and HF token so PlaceholderLLMProvider is used.
        os.environ["GRANITE_BASE_URL"] = ""
        os.environ["HF_API_TOKEN"] = ""
        os.environ["GRANITE_MODEL_ID"] = ""

        from backend.app.config import get_settings
        from backend.app.database.session import configure_session_factory, get_engine
        from backend.app.database.base import Base
        get_settings.cache_clear()
        get_engine.cache_clear()
        engine = configure_session_factory(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(bind=engine)

        # Reset lazy singletons
        import backend.app.api.routes.agents as agents_module
        import backend.app.api.routes.rag as rag_module
        monkeypatch.setattr(agents_module, "_embedding_provider", None)
        monkeypatch.setattr(agents_module, "_vector_store", None)
        monkeypatch.setattr(rag_module, "_embedding_provider", None)
        monkeypatch.setattr(rag_module, "_vector_store", None)

        from backend.app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            yield c

        Base.metadata.drop_all(bind=engine)
        get_settings.cache_clear()
        get_engine.cache_clear()
        for key in ("DATABASE_URL", "CHROMA_PERSIST_DIRECTORY", "CHROMA_COLLECTION_NAME",
                    "EMBEDDING_MODEL", "GRANITE_BASE_URL", "HF_API_TOKEN", "GRANITE_MODEL_ID"):
            os.environ.pop(key, None)

    def _seed(self, client, scheme_id="GOV001", name="Test Scheme", state="Karnataka",
              category="Housing", target_group="women", active_status=True):
        resp = client.post("/api/v1/schemes/", json={
            "scheme_id": scheme_id, "name": name, "description": "desc",
            "category": category, "state": state, "target_group": target_group,
            "min_age": None, "max_age": None, "income_limit": None,
            "eligibility": None, "age_criteria": None, "income_criteria": None,
            "benefits": ["Cash grant"], "required_documents": ["Aadhaar"],
            "application_process": "Apply online", "official_url": None,
            "source": "test_seed", "last_verified": None, "active_status": active_status,
        })
        assert resp.status_code == 201

    def _register_and_login(self, client) -> str:
        """Register a user and return a valid Bearer token."""
        client.post("/api/v1/auth/register", json={
            "email": "govtest@example.com", "password": "govpass123",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "govtest@example.com", "password": "govpass123",
        })
        return resp.json()["access_token"]

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_unauthenticated_returns_401(self, gov_client):
        resp = gov_client.post("/api/v1/agents/government", json={"query": "housing"})
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, gov_client):
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "housing"},
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401

    def test_empty_query_returns_422(self, gov_client):
        token = self._register_and_login(gov_client)
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "  "},
            headers=self._auth(token),
        )
        assert resp.status_code == 422

    def test_response_shape(self, gov_client):
        token = self._register_and_login(gov_client)
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "housing support"},
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        for key in ("agent_name", "status", "answer", "recommended_schemes",
                    "additional_context", "evidence_summary", "sources"):
            assert key in data, f"Missing key: {key}"

    def test_agent_name_is_government(self, gov_client):
        token = self._register_and_login(gov_client)
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "housing"},
            headers=self._auth(token),
        )
        assert resp.json()["agent_name"] == "government"

    def test_empty_db_gives_zero_schemes(self, gov_client):
        token = self._register_and_login(gov_client)
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "housing support"},
            headers=self._auth(token),
        )
        assert resp.json()["evidence_summary"].get("schemes_count", 0) == 0

    def test_seeded_scheme_appears_in_evidence(self, gov_client):
        token = self._register_and_login(gov_client)
        self._seed(gov_client)
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "housing support", "state": "Karnataka"},
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["evidence_summary"]["schemes_count"] >= 1

    def test_state_filter_applied(self, gov_client):
        token = self._register_and_login(gov_client)
        self._seed(gov_client, scheme_id="K1", name="Karnataka Scheme", state="Karnataka")
        self._seed(gov_client, scheme_id="D1", name="Delhi Scheme", state="Delhi")
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "scheme", "state": "Karnataka"},
            headers=self._auth(token),
        )
        ev = resp.json()["evidence_summary"]
        # only Karnataka (1 scheme) should be included
        assert ev["schemes_count"] == 1

    def test_inactive_scheme_excluded(self, gov_client):
        token = self._register_and_login(gov_client)
        self._seed(gov_client, scheme_id="A1", name="Active",   active_status=True)
        self._seed(gov_client, scheme_id="I1", name="Inactive", active_status=False)
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "scheme"},
            headers=self._auth(token),
        )
        ev = resp.json()["evidence_summary"]
        assert ev["schemes_count"] == 1

    def test_placeholder_llm_answer_present(self, gov_client):
        """Without HF_API_TOKEN the placeholder LLM returns a non-empty string."""
        token = self._register_and_login(gov_client)
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "test query"},
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["answer"], str)
        assert len(resp.json()["answer"]) > 0

    def test_vector_results_after_ingest(self, gov_client):
        """Ingest a doc, then run the agent — documents_count should be > 0."""
        token = self._register_and_login(gov_client)
        gov_client.post("/api/v1/rag/ingest", json={
            "document_id": "gov-doc-1",
            "path": "n/a",
            "text": "Pradhan Mantri Matru Vandana Yojana provides cash incentives to pregnant women.",
            "metadata": {"source": "gov_test"},
        })
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "maternity support", "vector_limit": 3},
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["evidence_summary"]["documents_count"] >= 1

    def test_sources_populated_from_db(self, gov_client):
        token = self._register_and_login(gov_client)
        self._seed(gov_client, scheme_id="SRC1", name="PMAY")
        resp = gov_client.post(
            "/api/v1/agents/government",
            json={"query": "housing"},
            headers=self._auth(token),
        )
        # "test_seed" is the source label used in _seed
        assert "test_seed" in resp.json()["sources"]

    def test_list_agents_endpoint(self, gov_client):
        resp = gov_client.get("/api/v1/agents/")
        assert resp.status_code == 200
        data = resp.json()
        assert "government" in data.get("implemented", [])


# ---------------------------------------------------------------------------
# Optional local MLX integration test
# — skipped automatically when the local server is not reachable
# ---------------------------------------------------------------------------

def _local_server_reachable() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8080/v1/models", timeout=2)
        return True
    except Exception:
        return False


_LOCAL_SERVER_UP = _local_server_reachable()


@pytest.mark.skipif(
    not _LOCAL_SERVER_UP,
    reason="Local MLX server not reachable at http://127.0.0.1:8080 — skipping live integration test",
)
class TestGraniteLocalIntegration:
    """Live integration tests against the local MLX server.

    Run with the MLX server already started:
        python -m mlx_lm.server --model mlx-community/granite-3.3-8b-instruct-8bit
        pytest backend/tests/test_government_agent.py -k integration -v
    """

    _BASE_URL = "http://127.0.0.1:8080/v1"
    _MODEL = "mlx-community/granite-3.3-8b-instruct-8bit"

    def test_granite_generate_returns_string(self):
        provider = GraniteLLMProvider(
            base_url=self._BASE_URL,
            model_id=self._MODEL,
        )
        result = provider.generate(
            "In one sentence, what is Pradhan Mantri Awas Yojana?",
            system="You are a concise assistant.",
        )
        assert isinstance(result, str)
        assert len(result) > 10

    def test_granite_generate_with_system_prompt(self):
        provider = GraniteLLMProvider(
            base_url=self._BASE_URL,
            model_id=self._MODEL,
            max_new_tokens=64,
            temperature=0.0,
        )
        result = provider.generate(
            "Reply with a single word: yes or no. Is PMAY a housing scheme?",
            system="Answer with a single word only.",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_government_agent_with_real_llm(self):
        provider = GraniteLLMProvider(
            base_url=self._BASE_URL,
            model_id=self._MODEL,
        )
        schemes = [{
            "scheme_id": "PMAY", "name": "Pradhan Mantri Awas Yojana",
            "category": "Housing", "state": "All States",
            "target_group": "women", "income_limit": 300000,
            "benefits": ["Housing subsidy up to ₹2.67 lakh"],
            "required_documents": ["Aadhaar", "Income certificate"],
            "application_process": "Apply via Common Service Centre",
            "official_url": "https://pmaymis.gov.in",
            "source": "pmaymis.gov.in",
            "_source_type": "structured_db",
        }]
        retriever = HybridRetriever(structured_retriever=_StubStructuredRetriever(schemes))
        agent = GovernmentAgent(hybrid_retriever=retriever, llm_provider=provider)
        result = agent.handle(AgentRequest(
            query="I am a pregnant woman with low income. What housing support can I get?",
            context={"state": "Karnataka", "age": 28, "income": 150000},
        ))
        assert result.status == "ok"
        assert isinstance(result.summary, str)
        assert len(result.summary) > 10
