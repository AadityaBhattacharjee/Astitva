"""Phase 6 — Supervisor Agent tests.

Covers:
- Rule-based routing for all key domains
- LLM fallback for genuinely ambiguous queries (mocked)
- Empty / whitespace query handling (agent level and endpoint level)
- Unauthenticated request → 401
- Authenticated request → 200 with correct routing fields

Fixture pattern follows test_auth.py:
  - SQLite in-memory DB via tmp_path
  - os.environ overrides to suppress .env values (GRANITE_BASE_URL, HF_API_TOKEN)
  - get_settings.cache_clear() before and after
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.agents.base import AgentRequest
from backend.app.agents.supervisor.agent import (
    SupervisorAgent,
    _llm_route,
    _rule_based_route,
    KEYWORD_RULES,
    _AGENT_NAMES,
)
from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.models import entities as _entities_import  # noqa: F401
from backend.app.database.session import configure_session_factory, get_engine
from backend.app.services.llm_provider import BaseLLMProvider, PlaceholderLLMProvider

_TEST_SECRET = "test-secret-for-supervisor"


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "supervisor_test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"

    os.environ["DATABASE_URL"] = database_url
    os.environ["SECRET_KEY"] = _TEST_SECRET
    # Suppress .env from leaking a live GRANITE_BASE_URL or HF_API_TOKEN
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

def _register_and_login(client: TestClient, email: str = "sv@example.com",
                         password: str = "pass123") -> str:
    """Register a user and return a valid Bearer token."""
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _post_supervisor(client: TestClient, query: str, token: str) -> dict:
    resp = client.post(
        "/api/v1/agents/supervisor",
        json={"query": query},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


# ---------------------------------------------------------------------------
# Unit tests — _rule_based_route (no HTTP, no fixtures needed)
# ---------------------------------------------------------------------------

class TestRuleBasedRoute:
    def test_government_keyword(self):
        assert _rule_based_route("What government schemes are available?") == "government"

    def test_yojana_keyword(self):
        assert _rule_based_route("Tell me about PM yojana benefits") == "government"

    def test_employment_keyword(self):
        assert _rule_based_route("I am looking for a job near my city") == "employment"

    def test_legal_keyword(self):
        assert _rule_based_route("I need a lawyer for domestic violence complaint") == "legal"

    def test_finance_keyword(self):
        assert _rule_based_route("How do I apply for a small business loan?") == "finance"

    def test_healthcare_keyword(self):
        assert _rule_based_route("Which hospital offers free pregnancy check-up?") == "healthcare"

    def test_document_keyword(self):
        assert _rule_based_route("I need my Aadhaar certificate and birth certificate") == "document"

    def test_risk_keyword(self):
        assert _rule_based_route("I am in danger and unsafe at home") == "risk"

    def test_mentor_keyword(self):
        assert _rule_based_route("I want a mentor and mentorship sessions") == "mentor_matching"

    def test_ambiguous_returns_none(self):
        # "Hello" matches no keywords → None
        assert _rule_based_route("Hello") is None

    def test_empty_query_returns_none(self):
        assert _rule_based_route("") is None

    def test_returns_single_winner_only(self):
        # A query dominated by a single domain
        result = _rule_based_route("I need a loan from the bank to start a business")
        assert result == "finance"


# ---------------------------------------------------------------------------
# Unit tests — _llm_route
# ---------------------------------------------------------------------------

class _MockLLM(BaseLLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return self._response


class TestLLMRoute:
    def test_returns_valid_agent_name(self):
        llm = _MockLLM("healthcare")
        assert _llm_route("I feel sick", llm) == "healthcare"

    def test_strips_whitespace_and_casing(self):
        llm = _MockLLM("  Employment  ")
        assert _llm_route("need work", llm) == "employment"

    def test_unknown_response_returns_unknown(self):
        llm = _MockLLM("unknown_agent_xyz")
        assert _llm_route("gibberish", llm) == "unknown"

    def test_empty_response_returns_unknown(self):
        llm = _MockLLM("")
        assert _llm_route("something", llm) == "unknown"

    def test_placeholder_llm_returns_unknown(self):
        # PlaceholderLLMProvider returns a fixed string that is not a valid agent
        result = _llm_route("ambiguous query here", PlaceholderLLMProvider())
        assert result == "unknown"


# ---------------------------------------------------------------------------
# Unit tests — SupervisorAgent.handle
# ---------------------------------------------------------------------------

class TestSupervisorAgentHandle:
    def test_routes_government_query(self):
        agent = SupervisorAgent()
        response = agent.handle(AgentRequest(query="What subsidy is available for women?"))
        assert response.data["routed_to"] == "government"
        assert response.data["method"] == "rule"
        assert response.status == "routed"

    def test_routes_legal_query(self):
        agent = SupervisorAgent()
        response = agent.handle(AgentRequest(query="I need legal advice about my rights"))
        assert response.data["routed_to"] == "legal"

    def test_empty_query_returns_error(self):
        agent = SupervisorAgent()
        response = agent.handle(AgentRequest(query="   "))
        assert response.status == "error"
        assert response.data["routed_to"] is None

    def test_ambiguous_falls_back_to_llm(self):
        llm = _MockLLM("healthcare")
        agent = SupervisorAgent(llm_provider=llm)
        response = agent.handle(AgentRequest(query="Hello there"))
        assert response.data["routed_to"] == "healthcare"
        assert response.data["method"] == "llm"

    def test_response_contains_required_fields(self):
        agent = SupervisorAgent()
        response = agent.handle(AgentRequest(query="I want a loan"))
        assert response.agent_name == "supervisor"
        assert "routed_to" in response.data
        assert "intent" in response.data
        assert "method" in response.data


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestSupervisorEndpoint:
    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.post("/api/v1/agents/supervisor", json={"query": "What schemes exist?"})
        assert resp.status_code == 401

    def test_authenticated_government_query_returns_200(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "Which government scheme helps women entrepreneurs?", token)
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_name"] == "supervisor"
        assert body["routed_to"] == "government"
        assert body["method"] == "rule"
        assert body["status"] == "routed"

    def test_authenticated_employment_query(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "I am looking for a job in Delhi", token)
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "employment"

    def test_authenticated_legal_query(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "What are my legal rights in a divorce case?", token)
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "legal"

    def test_authenticated_finance_query(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "How can I get a microloan for my business?", token)
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "finance"

    def test_authenticated_healthcare_query(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "Where can I find a free health clinic nearby?", token)
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "healthcare"

    def test_authenticated_document_query(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "How do I get my birth certificate reissued?", token)
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "document"

    def test_empty_query_returns_422(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "   ", token)
        assert resp.status_code == 422

    def test_ambiguous_query_uses_llm_fallback(self, client: TestClient):
        token = _register_and_login(client)
        # "Hello" matches no keywords → LLM fallback (PlaceholderLLMProvider → "unknown")
        resp = _post_supervisor(client, "Hello there", token)
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "llm"
        # PlaceholderLLMProvider can't classify → routed_to is "unknown"
        assert body["routed_to"] == "unknown"

    def test_response_has_all_fields(self, client: TestClient):
        token = _register_and_login(client)
        resp = _post_supervisor(client, "I need a lawyer", token)
        assert resp.status_code == 200
        body = resp.json()
        for field in ("agent_name", "status", "summary", "routed_to", "intent", "method"):
            assert field in body, f"Missing field: {field}"

    def test_wrong_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/supervisor",
            json={"query": "What scheme am I eligible for?"},
            headers={"Authorization": "Bearer totally.invalid.token"},
        )
        assert resp.status_code == 401
