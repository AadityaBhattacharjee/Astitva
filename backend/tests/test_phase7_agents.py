"""Phase 7 — Employment, Finance, Healthcare, and Legal Agent tests.

Covers for each agent:
- Prompt-building helpers
- LLM response parsing (valid JSON / insufficient / raw text)
- Agent.handle unit tests (mocked retriever + mocked LLM)
- HTTP endpoint: unauthenticated → 401, wrong token → 401
- HTTP endpoint: authenticated → 200 with correct response shape
- HTTP endpoint: empty query → 422
- Supervisor routing for each domain

Fixture pattern follows existing test_document_agent.py:
  - SQLite in-memory DB via tmp_path
  - os.environ overrides to suppress .env values
  - get_settings.cache_clear() before and after
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.base import AgentRequest
from backend.app.agents.employment.agent import (
    EmploymentAgent,
    _INSUFFICIENT as _EMP_INSUFFICIENT,
    _build_employment_evidence,
    _build_employment_prompt,
    _parse_employment_response,
)
from backend.app.agents.finance.agent import (
    FinanceAgent,
    _INSUFFICIENT as _FIN_INSUFFICIENT,
    _build_finance_evidence,
    _build_finance_prompt,
    _parse_finance_response,
)
from backend.app.agents.healthcare.agent import (
    HealthcareAgent,
    _INSUFFICIENT as _HC_INSUFFICIENT,
    _build_healthcare_evidence,
    _build_healthcare_prompt,
    _parse_healthcare_response,
)
from backend.app.agents.legal.agent import (
    LegalAgent,
    _INSUFFICIENT as _LEGAL_INSUFFICIENT,
    _build_legal_evidence,
    _build_legal_prompt,
    _parse_legal_response,
)
from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.models import entities as _entities_import  # noqa: F401
from backend.app.database.session import configure_session_factory, get_engine
from backend.app.rag.retrieval.hybrid import HybridRetriever
from backend.app.services.llm_provider import BaseLLMProvider

_TEST_SECRET = "test-secret-phase7"


# ---------------------------------------------------------------------------
# Stubs / helpers shared across all four agent test suites
# ---------------------------------------------------------------------------

class _MockLLM(BaseLLMProvider):
    """Deterministic LLM stub that records calls."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0
        self.last_prompt: str = ""
        self.last_system: str | None = None

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system = system
        return self._response


class _StubStructuredRetriever:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self._rows = rows or []
        self.last_filters: dict[str, Any] = {}

    def retrieve(self, query: str, filters: dict | None = None) -> list[dict[str, Any]]:
        self.last_filters = filters or {}
        return self._rows


class _StubVectorStore:
    def __init__(self, results: list[Any] | None = None):
        self._results = results or []

    def upsert_documents(self, documents: list[dict[str, Any]]) -> None:
        pass

    def similarity_search(self, query: str, limit: int = 5):
        return self._results[:limit]


def _make_hybrid_retriever(
    schemes: list[dict] | None = None,
    vector_results: list | None = None,
) -> HybridRetriever:
    return HybridRetriever(
        structured_retriever=_StubStructuredRetriever(schemes or []),
        vector_store=_StubVectorStore(vector_results or []),
    )


# ---------------------------------------------------------------------------
# HTTP client fixture (shared pattern)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "phase7_test.db"
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

    import backend.app.api.routes.agents as agents_module
    import backend.app.api.routes.rag as rag_module

    # Reset lazy singletons so each test gets a fresh in-memory ChromaDB
    agents_module._embedding_provider = None
    agents_module._vector_store = None
    rag_module._embedding_provider = None
    rag_module._vector_store = None

    from backend.app.main import app

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)
    for key in ("DATABASE_URL", "SECRET_KEY", "GRANITE_BASE_URL",
                "HF_API_TOKEN", "GRANITE_MODEL_ID"):
        os.environ.pop(key, None)
    get_settings.cache_clear()
    get_engine.cache_clear()

    agents_module._embedding_provider = None
    agents_module._vector_store = None
    rag_module._embedding_provider = None
    rag_module._vector_store = None


def _register_and_login(
    client: TestClient,
    email: str = "p7@example.com",
    password: str = "pass123",
) -> str:
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ===========================================================================
# EMPLOYMENT AGENT TESTS
# ===========================================================================

class TestBuildEmploymentEvidence:
    def test_includes_scheme_name(self):
        evidence = {
            "schemes": [{"name": "MGNREGA", "category": "employment",
                          "benefits": ["Wage employment"], "source": "test"}],
            "documents": [],
        }
        block = _build_employment_evidence(evidence)
        assert "MGNREGA" in block
        assert "Wage employment" in block

    def test_no_schemes_message(self):
        block = _build_employment_evidence({"schemes": [], "documents": []})
        assert "No matching employment schemes" in block

    def test_includes_document_excerpt(self):
        evidence = {
            "schemes": [],
            "documents": [
                {"content": "Skills training for women", "metadata": {"source": "emp_doc"}}
            ],
        }
        block = _build_employment_evidence(evidence)
        assert "Skills training for women" in block
        assert "emp_doc" in block

    def test_caps_at_six_excerpts(self):
        evidence = {
            "schemes": [],
            "documents": [{"content": f"chunk {i}", "metadata": {}} for i in range(10)],
        }
        block = _build_employment_evidence(evidence)
        assert "chunk 5" in block
        assert "chunk 6" not in block


class TestBuildEmploymentPrompt:
    def test_includes_query(self):
        prompt = _build_employment_prompt("What jobs are available?", {}, "EVIDENCE")
        assert "What jobs are available?" in prompt

    def test_includes_profile(self):
        prompt = _build_employment_prompt("jobs", {"state": "Bihar", "age": 28}, "EV")
        assert "Bihar" in prompt
        assert "28" in prompt

    def test_no_profile_shows_placeholder(self):
        prompt = _build_employment_prompt("jobs", {}, "EV")
        assert "No profile provided" in prompt


class TestParseEmploymentResponse:
    def test_insufficient_returns_fallback(self):
        result = _parse_employment_response(_EMP_INSUFFICIENT)
        assert result["answer"] == _EMP_INSUFFICIENT
        assert result["job_options"] == []

    def test_empty_returns_fallback(self):
        result = _parse_employment_response("")
        assert result["answer"] == _EMP_INSUFFICIENT

    def test_valid_json_parsed(self):
        payload = json.dumps({
            "answer": "MGNREGA offers wage work.",
            "job_options": [{"title": "MGNREGA", "description": "Wage work"}],
            "skills_guidance": ["Learn sewing"],
            "next_actions": ["Register at panchayat"],
            "sources": ["gov_db"],
        })
        result = _parse_employment_response(payload)
        assert result["answer"] == "MGNREGA offers wage work."
        assert result["job_options"][0]["title"] == "MGNREGA"

    def test_json_in_prose_extracted(self):
        inner = json.dumps({"answer": "ok", "job_options": [], "skills_guidance": [],
                            "next_actions": [], "sources": []})
        result = _parse_employment_response(f"Here you go: {inner}")
        assert result["answer"] == "ok"

    def test_unparseable_returns_raw(self):
        result = _parse_employment_response("plain text answer")
        assert result["answer"] == "plain text answer"
        assert result["job_options"] == []


class TestEmploymentAgentHandle:
    def _make_agent(self, llm_response: str, schemes: list | None = None) -> EmploymentAgent:
        retriever = _make_hybrid_retriever(schemes=schemes)
        llm = _MockLLM(llm_response)
        return EmploymentAgent(hybrid_retriever=retriever, llm_provider=llm)

    def test_agent_name(self):
        agent = self._make_agent('{"answer":"ok","job_options":[],"skills_guidance":[],"next_actions":[],"sources":[]}')
        assert agent.name == "employment"

    def test_returns_agentresponse(self):
        from backend.app.agents.base import AgentResponse
        agent = self._make_agent('{"answer":"guidance","job_options":[],"skills_guidance":[],"next_actions":[],"sources":[]}')
        result = agent.handle(AgentRequest(query="What jobs exist?"))
        assert isinstance(result, AgentResponse)
        assert result.agent_name == "employment"
        assert result.status == "ok"

    def test_insufficient_evidence_status(self):
        agent = self._make_agent(_EMP_INSUFFICIENT)
        result = agent.handle(AgentRequest(query="obscure"))
        assert result.status == "insufficient_evidence"
        assert result.data["evidence"]["insufficient_evidence"] is True

    def test_llm_called_once(self):
        llm = _MockLLM("plain text")
        retriever = _make_hybrid_retriever()
        agent = EmploymentAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.call_count == 1

    def test_system_prompt_passed_to_llm(self):
        llm = _MockLLM("plain text")
        retriever = _make_hybrid_retriever()
        agent = EmploymentAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.last_system is not None
        assert "employment" in llm.last_system.lower() or "career" in llm.last_system.lower()

    def test_query_in_prompt(self):
        llm = _MockLLM("plain text")
        retriever = _make_hybrid_retriever()
        agent = EmploymentAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="vocational training in Bihar"))
        assert "vocational training in Bihar" in llm.last_prompt

    def test_sources_merged(self):
        schemes = [{"name": "MGNREGA", "source": "emp_src", "_source_type": "structured_db"}]
        llm_resp = json.dumps({"answer": "ok", "job_options": [], "skills_guidance": [],
                                "next_actions": [], "sources": ["llm_src"]})
        agent = self._make_agent(llm_resp, schemes=schemes)
        result = agent.handle(AgentRequest(query="jobs"))
        assert "emp_src" in result.sources
        assert "llm_src" in result.sources

    def test_evidence_counts_in_data(self):
        schemes = [{"name": "MGNREGA", "source": "s", "_source_type": "structured_db"}]
        agent = self._make_agent("plain text", schemes=schemes)
        result = agent.handle(AgentRequest(query="q"))
        assert result.data["evidence"]["schemes_count"] == 1

    def test_category_filter_defaulted_to_employment(self):
        stub = _StubStructuredRetriever()
        retriever = HybridRetriever(structured_retriever=stub, vector_store=_StubVectorStore())
        agent = EmploymentAgent(hybrid_retriever=retriever, llm_provider=_MockLLM("ok"))
        agent.handle(AgentRequest(query="jobs"))
        assert stub.last_filters.get("category") == "employment"

    def test_response_data_has_all_keys(self):
        agent = self._make_agent("plain text")
        result = agent.handle(AgentRequest(query="test"))
        assert "job_options" in result.data
        assert "skills_guidance" in result.data
        assert "next_actions" in result.data
        assert "evidence" in result.data


class TestEmploymentEndpoint:
    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.post("/api/v1/agents/employment", json={"query": "What jobs exist?"})
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/employment",
            json={"query": "What jobs exist?"},
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401

    def test_authenticated_query_returns_200(self, client: TestClient):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/agents/employment",
            json={"query": "What employment schemes are available?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_name"] == "employment"
        assert "answer" in body
        assert "job_options" in body
        assert "skills_guidance" in body
        assert "next_actions" in body
        assert "sources" in body

    def test_empty_query_returns_422(self, client: TestClient):
        token = _register_and_login(client, email="emp_empty@example.com")
        resp = client.post(
            "/api/v1/agents/employment",
            json={"query": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_response_has_status_field(self, client: TestClient):
        token = _register_and_login(client, email="emp_status@example.com")
        resp = client.post(
            "/api/v1/agents/employment",
            json={"query": "Tell me about skill training"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "status" in resp.json()

    def test_response_has_evidence_summary(self, client: TestClient):
        token = _register_and_login(client, email="emp_ev@example.com")
        resp = client.post(
            "/api/v1/agents/employment",
            json={"query": "jobs for women"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "evidence_summary" in resp.json()


class TestSupervisorEmploymentRouting:
    def test_supervisor_routes_employment_query(self, client: TestClient):
        token = _register_and_login(client, email="sv_emp@example.com")
        resp = client.post(
            "/api/v1/agents/supervisor",
            json={"query": "I am looking for a job and want career guidance"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "employment"


# ===========================================================================
# FINANCE AGENT TESTS
# ===========================================================================

class TestBuildFinanceEvidence:
    def test_includes_scheme_name_and_income_limit(self):
        evidence = {
            "schemes": [{"name": "Mudra Loan", "category": "finance",
                          "income_limit": 250000, "benefits": ["Loan up to ₹10L"],
                          "source": "gov"}],
            "documents": [],
        }
        block = _build_finance_evidence(evidence)
        assert "Mudra Loan" in block
        assert "250,000" in block
        assert "Loan up to" in block

    def test_no_schemes_message(self):
        block = _build_finance_evidence({"schemes": [], "documents": []})
        assert "No matching financial schemes" in block

    def test_includes_document_excerpt(self):
        evidence = {
            "schemes": [],
            "documents": [{"content": "Microfinance details", "metadata": {"source": "fin_doc"}}],
        }
        block = _build_finance_evidence(evidence)
        assert "Microfinance details" in block
        assert "fin_doc" in block


class TestBuildFinancePrompt:
    def test_includes_query_and_income(self):
        prompt = _build_finance_prompt("Need a loan", {"income": 150000, "state": "UP"}, "EV")
        assert "Need a loan" in prompt
        assert "150,000" in prompt
        assert "UP" in prompt

    def test_no_profile_shows_placeholder(self):
        prompt = _build_finance_prompt("loan", {}, "EV")
        assert "No profile provided" in prompt


class TestParseFinanceResponse:
    def test_insufficient_returns_fallback(self):
        result = _parse_finance_response(_FIN_INSUFFICIENT)
        assert result["answer"] == _FIN_INSUFFICIENT
        assert result["financial_options"] == []

    def test_empty_returns_fallback(self):
        result = _parse_finance_response("")
        assert result["answer"] == _FIN_INSUFFICIENT

    def test_valid_json_parsed(self):
        payload = json.dumps({
            "answer": "Mudra loan available.",
            "financial_options": [{"name": "Mudra", "type": "loan"}],
            "budgeting_tips": ["Save monthly"],
            "next_actions": ["Visit bank"],
            "disclaimer": "Informational only.",
            "sources": ["mudra_gov"],
        })
        result = _parse_finance_response(payload)
        assert result["answer"] == "Mudra loan available."
        assert result["financial_options"][0]["name"] == "Mudra"

    def test_unparseable_returns_raw(self):
        result = _parse_finance_response("some plain guidance")
        assert result["answer"] == "some plain guidance"
        assert result["financial_options"] == []

    def test_fallback_has_disclaimer(self):
        result = _parse_finance_response("")
        assert "disclaimer" in result
        assert len(result["disclaimer"]) > 0


class TestFinanceAgentHandle:
    def _make_agent(self, llm_response: str, schemes: list | None = None) -> FinanceAgent:
        retriever = _make_hybrid_retriever(schemes=schemes)
        llm = _MockLLM(llm_response)
        return FinanceAgent(hybrid_retriever=retriever, llm_provider=llm)

    def test_agent_name(self):
        agent = self._make_agent('{"answer":"ok","financial_options":[],"budgeting_tips":[],"next_actions":[],"disclaimer":"x","sources":[]}')
        assert agent.name == "finance"

    def test_returns_agentresponse(self):
        from backend.app.agents.base import AgentResponse
        agent = self._make_agent('{"answer":"guidance","financial_options":[],"budgeting_tips":[],"next_actions":[],"disclaimer":"x","sources":[]}')
        result = agent.handle(AgentRequest(query="How to get a loan?"))
        assert isinstance(result, AgentResponse)
        assert result.agent_name == "finance"
        assert result.status == "ok"

    def test_insufficient_evidence_status(self):
        agent = self._make_agent(_FIN_INSUFFICIENT)
        result = agent.handle(AgentRequest(query="obscure"))
        assert result.status == "insufficient_evidence"
        assert result.data["evidence"]["insufficient_evidence"] is True

    def test_llm_called_once(self):
        llm = _MockLLM("plain text")
        retriever = _make_hybrid_retriever()
        agent = FinanceAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.call_count == 1

    def test_system_prompt_contains_financial_keywords(self):
        llm = _MockLLM("text")
        retriever = _make_hybrid_retriever()
        agent = FinanceAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.last_system is not None
        assert "financial" in llm.last_system.lower() or "loan" in llm.last_system.lower()

    def test_category_filter_defaulted_to_finance(self):
        stub = _StubStructuredRetriever()
        retriever = HybridRetriever(structured_retriever=stub, vector_store=_StubVectorStore())
        agent = FinanceAgent(hybrid_retriever=retriever, llm_provider=_MockLLM("ok"))
        agent.handle(AgentRequest(query="loan"))
        assert stub.last_filters.get("category") == "finance"

    def test_disclaimer_in_data(self):
        agent = self._make_agent("plain text")
        result = agent.handle(AgentRequest(query="test"))
        assert "disclaimer" in result.data
        assert len(result.data["disclaimer"]) > 0

    def test_sources_merged(self):
        schemes = [{"name": "Mudra", "source": "fin_src", "_source_type": "structured_db"}]
        llm_resp = json.dumps({"answer": "ok", "financial_options": [], "budgeting_tips": [],
                                "next_actions": [], "disclaimer": "x", "sources": ["llm_src"]})
        agent = self._make_agent(llm_resp, schemes=schemes)
        result = agent.handle(AgentRequest(query="loan"))
        assert "fin_src" in result.sources
        assert "llm_src" in result.sources

    def test_evidence_counts_in_data(self):
        schemes = [{"name": "Mudra", "source": "s", "_source_type": "structured_db"}]
        agent = self._make_agent("plain text", schemes=schemes)
        result = agent.handle(AgentRequest(query="q"))
        assert result.data["evidence"]["schemes_count"] == 1


class TestFinanceEndpoint:
    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.post("/api/v1/agents/finance", json={"query": "How to get a loan?"})
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/finance",
            json={"query": "Mudra loan"},
            headers={"Authorization": "Bearer bad.token"},
        )
        assert resp.status_code == 401

    def test_authenticated_query_returns_200(self, client: TestClient):
        token = _register_and_login(client, email="fin@example.com")
        resp = client.post(
            "/api/v1/agents/finance",
            json={"query": "What microfinance options do I have?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_name"] == "finance"
        assert "answer" in body
        assert "financial_options" in body
        assert "budgeting_tips" in body
        assert "next_actions" in body
        assert "disclaimer" in body
        assert "sources" in body

    def test_empty_query_returns_422(self, client: TestClient):
        token = _register_and_login(client, email="fin_empty@example.com")
        resp = client.post(
            "/api/v1/agents/finance",
            json={"query": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_income_filter_accepted(self, client: TestClient):
        token = _register_and_login(client, email="fin_income@example.com")
        resp = client.post(
            "/api/v1/agents/finance",
            json={"query": "small business loan", "income": 120000, "state": "Bihar"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_response_has_evidence_summary(self, client: TestClient):
        token = _register_and_login(client, email="fin_ev@example.com")
        resp = client.post(
            "/api/v1/agents/finance",
            json={"query": "savings scheme"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "evidence_summary" in resp.json()


class TestSupervisorFinanceRouting:
    def test_supervisor_routes_finance_query(self, client: TestClient):
        token = _register_and_login(client, email="sv_fin@example.com")
        resp = client.post(
            "/api/v1/agents/supervisor",
            json={"query": "How can I apply for a small business loan or microfinance?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "finance"


# ===========================================================================
# HEALTHCARE AGENT TESTS
# ===========================================================================

class TestBuildHealthcareEvidence:
    def test_includes_scheme_name(self):
        evidence = {
            "schemes": [{"name": "Ayushman Bharat", "category": "healthcare",
                          "benefits": ["Free hospitalisation"], "source": "gov"}],
            "documents": [],
        }
        block = _build_healthcare_evidence(evidence)
        assert "Ayushman Bharat" in block
        assert "Free hospitalisation" in block

    def test_no_schemes_message(self):
        block = _build_healthcare_evidence({"schemes": [], "documents": []})
        assert "No matching healthcare schemes" in block

    def test_includes_document_excerpt(self):
        evidence = {
            "schemes": [],
            "documents": [{"content": "Janani Suraksha Yojana provides cash", "metadata": {"source": "hc_doc"}}],
        }
        block = _build_healthcare_evidence(evidence)
        assert "Janani Suraksha Yojana" in block
        assert "hc_doc" in block


class TestBuildHealthcarePrompt:
    def test_includes_query_and_age(self):
        prompt = _build_healthcare_prompt("Free antenatal care", {"age": 25, "state": "Odisha"}, "EV")
        assert "Free antenatal care" in prompt
        assert "25" in prompt
        assert "Odisha" in prompt

    def test_no_profile_placeholder(self):
        prompt = _build_healthcare_prompt("query", {}, "EV")
        assert "No profile provided" in prompt


class TestParseHealthcareResponse:
    def test_insufficient_returns_fallback(self):
        result = _parse_healthcare_response(_HC_INSUFFICIENT)
        assert result["answer"] == _HC_INSUFFICIENT
        assert result["healthcare_schemes"] == []

    def test_empty_returns_fallback(self):
        result = _parse_healthcare_response("")
        assert result["answer"] == _HC_INSUFFICIENT

    def test_valid_json_parsed(self):
        payload = json.dumps({
            "answer": "Ayushman Bharat covers hospitalisation.",
            "healthcare_schemes": [{"name": "Ayushman Bharat", "services_covered": ["hospitalisation"]}],
            "next_actions": ["Get e-card"],
            "medical_disclaimer": "Consult a doctor.",
            "sources": ["nhm.gov.in"],
        })
        result = _parse_healthcare_response(payload)
        assert result["answer"] == "Ayushman Bharat covers hospitalisation."
        assert result["healthcare_schemes"][0]["name"] == "Ayushman Bharat"

    def test_fallback_has_disclaimer(self):
        result = _parse_healthcare_response("")
        assert "medical_disclaimer" in result
        assert "healthcare professional" in result["medical_disclaimer"].lower()

    def test_unparseable_returns_raw(self):
        result = _parse_healthcare_response("plain text")
        assert result["answer"] == "plain text"
        assert result["healthcare_schemes"] == []


class TestHealthcareAgentHandle:
    def _make_agent(self, llm_response: str, schemes: list | None = None) -> HealthcareAgent:
        retriever = _make_hybrid_retriever(schemes=schemes)
        llm = _MockLLM(llm_response)
        return HealthcareAgent(hybrid_retriever=retriever, llm_provider=llm)

    def test_agent_name(self):
        agent = self._make_agent('{"answer":"ok","healthcare_schemes":[],"next_actions":[],"medical_disclaimer":"x","sources":[]}')
        assert agent.name == "healthcare"

    def test_returns_agentresponse(self):
        from backend.app.agents.base import AgentResponse
        agent = self._make_agent('{"answer":"guidance","healthcare_schemes":[],"next_actions":[],"medical_disclaimer":"x","sources":[]}')
        result = agent.handle(AgentRequest(query="Free antenatal check?"))
        assert isinstance(result, AgentResponse)
        assert result.agent_name == "healthcare"
        assert result.status == "ok"

    def test_insufficient_evidence_status(self):
        agent = self._make_agent(_HC_INSUFFICIENT)
        result = agent.handle(AgentRequest(query="obscure"))
        assert result.status == "insufficient_evidence"
        assert result.data["evidence"]["insufficient_evidence"] is True

    def test_llm_called_once(self):
        llm = _MockLLM("text")
        retriever = _make_hybrid_retriever()
        agent = HealthcareAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.call_count == 1

    def test_system_prompt_forbids_diagnosis(self):
        llm = _MockLLM("text")
        retriever = _make_hybrid_retriever()
        agent = HealthcareAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.last_system is not None
        assert "diagnos" in llm.last_system.lower()

    def test_category_filter_defaulted_to_healthcare(self):
        stub = _StubStructuredRetriever()
        retriever = HybridRetriever(structured_retriever=stub, vector_store=_StubVectorStore())
        agent = HealthcareAgent(hybrid_retriever=retriever, llm_provider=_MockLLM("ok"))
        agent.handle(AgentRequest(query="hospital"))
        assert stub.last_filters.get("category") == "healthcare"

    def test_disclaimer_in_data(self):
        agent = self._make_agent("plain text")
        result = agent.handle(AgentRequest(query="test"))
        assert "medical_disclaimer" in result.data
        assert len(result.data["medical_disclaimer"]) > 0

    def test_sources_merged(self):
        schemes = [{"name": "AB-PMJAY", "source": "hc_src", "_source_type": "structured_db"}]
        llm_resp = json.dumps({"answer": "ok", "healthcare_schemes": [], "next_actions": [],
                                "medical_disclaimer": "x", "sources": ["llm_src"]})
        agent = self._make_agent(llm_resp, schemes=schemes)
        result = agent.handle(AgentRequest(query="q"))
        assert "hc_src" in result.sources
        assert "llm_src" in result.sources

    def test_evidence_counts_in_data(self):
        schemes = [{"name": "Janani", "source": "s", "_source_type": "structured_db"}]
        agent = self._make_agent("plain text", schemes=schemes)
        result = agent.handle(AgentRequest(query="q"))
        assert result.data["evidence"]["schemes_count"] == 1


class TestHealthcareEndpoint:
    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.post("/api/v1/agents/healthcare", json={"query": "Free health check"})
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/healthcare",
            json={"query": "Free health check"},
            headers={"Authorization": "Bearer bad.token"},
        )
        assert resp.status_code == 401

    def test_authenticated_query_returns_200(self, client: TestClient):
        token = _register_and_login(client, email="hc@example.com")
        resp = client.post(
            "/api/v1/agents/healthcare",
            json={"query": "What free health schemes exist for pregnant women?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_name"] == "healthcare"
        assert "answer" in body
        assert "healthcare_schemes" in body
        assert "next_actions" in body
        assert "medical_disclaimer" in body
        assert "sources" in body

    def test_empty_query_returns_422(self, client: TestClient):
        token = _register_and_login(client, email="hc_empty@example.com")
        resp = client.post(
            "/api/v1/agents/healthcare",
            json={"query": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_response_has_evidence_summary(self, client: TestClient):
        token = _register_and_login(client, email="hc_ev@example.com")
        resp = client.post(
            "/api/v1/agents/healthcare",
            json={"query": "immunisation services"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "evidence_summary" in resp.json()

    def test_response_has_medical_disclaimer(self, client: TestClient):
        token = _register_and_login(client, email="hc_disc@example.com")
        resp = client.post(
            "/api/v1/agents/healthcare",
            json={"query": "nutrition support for mothers"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "medical_disclaimer" in body
        assert len(body["medical_disclaimer"]) > 0


class TestSupervisorHealthcareRouting:
    def test_supervisor_routes_healthcare_query(self, client: TestClient):
        token = _register_and_login(client, email="sv_hc@example.com")
        resp = client.post(
            "/api/v1/agents/supervisor",
            json={"query": "What hospital offers free treatment and immunisation?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "healthcare"


# ===========================================================================
# LEGAL AGENT TESTS
# ===========================================================================

class TestBuildLegalEvidence:
    def test_includes_scheme_name(self):
        evidence = {
            "schemes": [{"name": "DLSA Legal Aid", "category": "legal",
                          "benefits": ["Free legal representation"], "source": "nalsa"}],
            "documents": [],
        }
        block = _build_legal_evidence(evidence)
        assert "DLSA Legal Aid" in block
        assert "Free legal representation" in block

    def test_no_schemes_message(self):
        block = _build_legal_evidence({"schemes": [], "documents": []})
        assert "No matching legal schemes" in block

    def test_includes_document_excerpt(self):
        evidence = {
            "schemes": [],
            "documents": [{"content": "Protection of Women Act details", "metadata": {"source": "legal_doc"}}],
        }
        block = _build_legal_evidence(evidence)
        assert "Protection of Women Act" in block
        assert "legal_doc" in block


class TestBuildLegalPrompt:
    def test_includes_query_and_state(self):
        prompt = _build_legal_prompt("My legal rights", {"state": "Maharashtra"}, "EV")
        assert "My legal rights" in prompt
        assert "Maharashtra" in prompt

    def test_no_profile_shows_placeholder(self):
        prompt = _build_legal_prompt("rights", {}, "EV")
        assert "No profile provided" in prompt


class TestParseLegalResponse:
    def test_insufficient_returns_fallback(self):
        result = _parse_legal_response(_LEGAL_INSUFFICIENT)
        assert result["answer"] == _LEGAL_INSUFFICIENT
        assert result["legal_information"] == []

    def test_empty_returns_fallback(self):
        result = _parse_legal_response("")
        assert result["answer"] == _LEGAL_INSUFFICIENT

    def test_valid_json_parsed(self):
        payload = json.dumps({
            "answer": "You have rights under PWDVA.",
            "legal_information": [{"topic": "PWDVA", "summary": "Covers domestic violence"}],
            "suggested_resources": ["DLSA"],
            "next_actions": ["Call helpline"],
            "legal_disclaimer": "Not legal advice.",
            "sources": ["nalsa.gov.in"],
        })
        result = _parse_legal_response(payload)
        assert result["answer"] == "You have rights under PWDVA."
        assert result["legal_information"][0]["topic"] == "PWDVA"

    def test_fallback_has_disclaimer(self):
        result = _parse_legal_response("")
        assert "legal_disclaimer" in result
        assert "legal" in result["legal_disclaimer"].lower()

    def test_unparseable_returns_raw(self):
        result = _parse_legal_response("plain guidance text")
        assert result["answer"] == "plain guidance text"
        assert result["legal_information"] == []


class TestLegalAgentHandle:
    def _make_agent(self, llm_response: str, schemes: list | None = None) -> LegalAgent:
        retriever = _make_hybrid_retriever(schemes=schemes)
        llm = _MockLLM(llm_response)
        return LegalAgent(hybrid_retriever=retriever, llm_provider=llm)

    def test_agent_name(self):
        agent = self._make_agent('{"answer":"ok","legal_information":[],"suggested_resources":[],"next_actions":[],"legal_disclaimer":"x","sources":[]}')
        assert agent.name == "legal"

    def test_returns_agentresponse(self):
        from backend.app.agents.base import AgentResponse
        agent = self._make_agent('{"answer":"guidance","legal_information":[],"suggested_resources":[],"next_actions":[],"legal_disclaimer":"x","sources":[]}')
        result = agent.handle(AgentRequest(query="What are my rights?"))
        assert isinstance(result, AgentResponse)
        assert result.agent_name == "legal"
        assert result.status == "ok"

    def test_insufficient_evidence_status(self):
        agent = self._make_agent(_LEGAL_INSUFFICIENT)
        result = agent.handle(AgentRequest(query="obscure"))
        assert result.status == "insufficient_evidence"
        assert result.data["evidence"]["insufficient_evidence"] is True

    def test_llm_called_once(self):
        llm = _MockLLM("text")
        retriever = _make_hybrid_retriever()
        agent = LegalAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.call_count == 1

    def test_system_prompt_forbids_legal_advice(self):
        llm = _MockLLM("text")
        retriever = _make_hybrid_retriever()
        agent = LegalAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="test"))
        assert llm.last_system is not None
        # System prompt must explicitly NOT claim to provide legal advice
        assert "not" in llm.last_system.lower() or "lawyer" in llm.last_system.lower()

    def test_category_filter_defaulted_to_legal(self):
        stub = _StubStructuredRetriever()
        retriever = HybridRetriever(structured_retriever=stub, vector_store=_StubVectorStore())
        agent = LegalAgent(hybrid_retriever=retriever, llm_provider=_MockLLM("ok"))
        agent.handle(AgentRequest(query="rights"))
        assert stub.last_filters.get("category") == "legal"

    def test_disclaimer_in_data(self):
        agent = self._make_agent("plain text")
        result = agent.handle(AgentRequest(query="test"))
        assert "legal_disclaimer" in result.data
        assert len(result.data["legal_disclaimer"]) > 0

    def test_sources_merged(self):
        schemes = [{"name": "NALSA", "source": "legal_src", "_source_type": "structured_db"}]
        llm_resp = json.dumps({"answer": "ok", "legal_information": [], "suggested_resources": [],
                                "next_actions": [], "legal_disclaimer": "x", "sources": ["llm_src"]})
        agent = self._make_agent(llm_resp, schemes=schemes)
        result = agent.handle(AgentRequest(query="q"))
        assert "legal_src" in result.sources
        assert "llm_src" in result.sources

    def test_evidence_counts_in_data(self):
        schemes = [{"name": "NALSA", "source": "s", "_source_type": "structured_db"}]
        agent = self._make_agent("plain text", schemes=schemes)
        result = agent.handle(AgentRequest(query="q"))
        assert result.data["evidence"]["schemes_count"] == 1

    def test_query_appears_in_prompt(self):
        llm = _MockLLM("text")
        retriever = _make_hybrid_retriever()
        agent = LegalAgent(hybrid_retriever=retriever, llm_provider=llm)
        agent.handle(AgentRequest(query="divorce rights in Karnataka"))
        assert "divorce rights in Karnataka" in llm.last_prompt


class TestLegalEndpoint:
    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.post("/api/v1/agents/legal", json={"query": "What are my legal rights?"})
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/legal",
            json={"query": "legal rights"},
            headers={"Authorization": "Bearer bad.token"},
        )
        assert resp.status_code == 401

    def test_authenticated_query_returns_200(self, client: TestClient):
        token = _register_and_login(client, email="legal@example.com")
        resp = client.post(
            "/api/v1/agents/legal",
            json={"query": "What legal rights do I have in a domestic violence situation?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_name"] == "legal"
        assert "answer" in body
        assert "legal_information" in body
        assert "suggested_resources" in body
        assert "next_actions" in body
        assert "legal_disclaimer" in body
        assert "sources" in body

    def test_empty_query_returns_422(self, client: TestClient):
        token = _register_and_login(client, email="legal_empty@example.com")
        resp = client.post(
            "/api/v1/agents/legal",
            json={"query": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_response_has_evidence_summary(self, client: TestClient):
        token = _register_and_login(client, email="legal_ev@example.com")
        resp = client.post(
            "/api/v1/agents/legal",
            json={"query": "How do I file a complaint?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "evidence_summary" in resp.json()

    def test_response_has_legal_disclaimer(self, client: TestClient):
        token = _register_and_login(client, email="legal_disc@example.com")
        resp = client.post(
            "/api/v1/agents/legal",
            json={"query": "What is the Protection of Women from Domestic Violence Act?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "legal_disclaimer" in body
        assert len(body["legal_disclaimer"]) > 0

    def test_state_filter_accepted(self, client: TestClient):
        token = _register_and_login(client, email="legal_state@example.com")
        resp = client.post(
            "/api/v1/agents/legal",
            json={"query": "legal aid available", "state": "Tamil Nadu"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


class TestSupervisorLegalRouting:
    def test_supervisor_routes_legal_query(self, client: TestClient):
        token = _register_and_login(client, email="sv_legal@example.com")
        resp = client.post(
            "/api/v1/agents/supervisor",
            json={"query": "I need a lawyer for my domestic violence complaint and court case"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "legal"


# ===========================================================================
# CROSS-AGENT: list_agents endpoint reflects new implementations
# ===========================================================================

class TestListAgentsUpdated:
    def test_employment_in_implemented(self, client: TestClient):
        resp = client.get("/api/v1/agents/")
        assert resp.status_code == 200
        data = resp.json()
        assert "employment" in data["implemented"]

    def test_finance_in_implemented(self, client: TestClient):
        resp = client.get("/api/v1/agents/")
        data = resp.json()
        assert "finance" in data["implemented"]

    def test_healthcare_in_implemented(self, client: TestClient):
        resp = client.get("/api/v1/agents/")
        data = resp.json()
        assert "healthcare" in data["implemented"]

    def test_legal_in_implemented(self, client: TestClient):
        resp = client.get("/api/v1/agents/")
        data = resp.json()
        assert "legal" in data["implemented"]

    def test_remaining_agents_now_implemented(self, client: TestClient):
        """After Phase 8, mentor_matching/planning/progress/risk are now implemented."""
        resp = client.get("/api/v1/agents/")
        data = resp.json()
        for agent in ("mentor_matching", "planning", "progress", "risk"):
            assert agent in data["implemented"], f"{agent} should be in implemented"
