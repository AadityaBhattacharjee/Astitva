"""Case Worker Agent tests — Phase 6.

Covers:
- Successful case request with full DB data
- Missing case data (no profile, no docs, no roadmap)
- No user_id → error response
- Invalid user_id → error response
- Prompt building with real data
- Case Worker endpoint authentication (401 unauthenticated)
- Authenticated case worker query → 200
- Empty query → 422
- Wrong token → 401
- Supervisor routes 'case_worker' queries correctly
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.base import AgentRequest
from backend.app.agents.case_worker.agent import (
    CaseWorkerAgent,
    _NO_DATA_MSG,
    _build_case_context,
    _build_case_prompt,
    _parse_case_response,
)
from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.models import entities as _entities_import  # noqa: F401
from backend.app.database.models.entities import Document, Roadmap, RoadmapTask, UserProfile
from backend.app.database.session import configure_session_factory, get_engine
from backend.app.services.llm_provider import BaseLLMProvider, PlaceholderLLMProvider

_TEST_SECRET = "test-secret-caseworker"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "case_worker_test.db"
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


@pytest.fixture()
def db_session(tmp_path: Path):
    """Isolated SQLite session for unit tests."""
    url = f"sqlite+pysqlite:///{tmp_path / 'cw_unit.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(
    client: TestClient,
    email: str = "cw@example.com",
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


def _add_user(session: Session, email: str = "u@test.com") -> int:
    from backend.app.database.models.entities import User
    from backend.app.security.passwords import hash_password
    user = User(email=email, hashed_password=hash_password("pass"), role="USER")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id


# ---------------------------------------------------------------------------
# Unit tests — _build_case_context
# ---------------------------------------------------------------------------

class TestBuildCaseContext:
    def test_empty_user_returns_empty_dicts(self, db_session: Session):
        ctx = _build_case_context(9999, db_session)
        assert ctx["profile"] == {}
        assert ctx["documents"] == []
        assert ctx["roadmaps"] == []

    def test_user_with_profile_populated(self, db_session: Session):
        uid = _add_user(db_session)
        profile = UserProfile(user_id=uid, full_name="Priya", state="Maharashtra")
        db_session.add(profile)
        db_session.commit()

        ctx = _build_case_context(uid, db_session)
        assert ctx["profile"]["full_name"] == "Priya"
        assert ctx["profile"]["state"] == "Maharashtra"

    def test_user_with_documents(self, db_session: Session):
        uid = _add_user(db_session, "docs@test.com")
        doc = Document(user_id=uid, document_type="Aadhaar", status="PENDING")
        db_session.add(doc)
        db_session.commit()

        ctx = _build_case_context(uid, db_session)
        assert len(ctx["documents"]) == 1
        assert ctx["documents"][0]["type"] == "Aadhaar"
        assert ctx["documents"][0]["status"] == "PENDING"

    def test_user_with_roadmap_and_tasks(self, db_session: Session):
        uid = _add_user(db_session, "rm@test.com")
        roadmap = Roadmap(user_id=uid, title="My Plan", status="ACTIVE")
        db_session.add(roadmap)
        db_session.commit()
        task = RoadmapTask(roadmap_id=roadmap.id, title="Apply for Aadhaar", status="PENDING", priority="HIGH")
        db_session.add(task)
        db_session.commit()

        ctx = _build_case_context(uid, db_session)
        assert len(ctx["roadmaps"]) == 1
        assert ctx["roadmaps"][0]["title"] == "My Plan"
        assert ctx["roadmaps"][0]["tasks"][0]["title"] == "Apply for Aadhaar"


# ---------------------------------------------------------------------------
# Unit tests — _parse_case_response
# ---------------------------------------------------------------------------

class TestParseCaseResponse:
    def test_no_data_sentinel_returns_fallback(self):
        result = _parse_case_response(_NO_DATA_MSG)
        assert result["case_summary"] == _NO_DATA_MSG
        assert result["priority_actions"] == []

    def test_empty_response_returns_fallback(self):
        result = _parse_case_response("")
        assert result["case_summary"] == _NO_DATA_MSG

    def test_valid_json_parsed(self):
        payload = {
            "case_summary": "User has two pending documents.",
            "priority_actions": [{"action": "Submit Aadhaar", "reason": "Required for scheme"}],
            "document_gaps": ["PAN Card"],
            "roadmap_status": "In progress",
            "risk_flags": [],
        }
        result = _parse_case_response(json.dumps(payload))
        assert result["case_summary"] == "User has two pending documents."
        assert result["document_gaps"] == ["PAN Card"]

    def test_unparseable_returns_raw_text(self):
        result = _parse_case_response("some plain text from LLM")
        assert result["case_summary"] == "some plain text from LLM"


# ---------------------------------------------------------------------------
# Unit tests — CaseWorkerAgent.handle
# ---------------------------------------------------------------------------

class TestCaseWorkerAgentHandle:
    def test_missing_user_id_returns_error(self, db_session: Session):
        llm = _MockLLM("irrelevant")
        agent = CaseWorkerAgent(db=db_session, llm_provider=llm)
        resp = agent.handle(AgentRequest(query="Show case status"))
        assert resp.status == "error"
        assert "user_id" in resp.summary.lower()

    def test_invalid_user_id_returns_error(self, db_session: Session):
        llm = _MockLLM("irrelevant")
        agent = CaseWorkerAgent(db=db_session, llm_provider=llm)
        resp = agent.handle(AgentRequest(query="status", user_id="not-an-int"))
        assert resp.status == "error"

    def test_user_with_no_data_returns_no_data_status(self, db_session: Session):
        uid = _add_user(db_session, "empty@test.com")
        llm = _MockLLM(_NO_DATA_MSG)
        agent = CaseWorkerAgent(db=db_session, llm_provider=llm)
        resp = agent.handle(AgentRequest(query="Show my case", user_id=str(uid)))
        assert resp.status == "no_data"

    def test_user_with_data_returns_ok_status(self, db_session: Session):
        uid = _add_user(db_session, "rich@test.com")
        profile = UserProfile(user_id=uid, full_name="Meera", state="Kerala")
        doc = Document(user_id=uid, document_type="Aadhaar", status="VERIFIED")
        db_session.add_all([profile, doc])
        db_session.commit()

        good_response = json.dumps({
            "case_summary": "Meera has a verified Aadhaar.",
            "priority_actions": [{"action": "Apply for scheme", "reason": "Aadhaar verified"}],
            "document_gaps": [],
            "roadmap_status": "No roadmap found",
            "risk_flags": [],
        })
        llm = _MockLLM(good_response)
        agent = CaseWorkerAgent(db=db_session, llm_provider=llm)
        resp = agent.handle(AgentRequest(query="What should I do next?", user_id=str(uid)))
        assert resp.status == "ok"
        assert "Meera" in resp.summary

    def test_llm_called_once(self, db_session: Session):
        uid = _add_user(db_session, "once@test.com")
        llm = _MockLLM("plain summary")
        agent = CaseWorkerAgent(db=db_session, llm_provider=llm)
        agent.handle(AgentRequest(query="test", user_id=str(uid)))
        assert llm.call_count == 1

    def test_response_includes_case_meta(self, db_session: Session):
        uid = _add_user(db_session, "meta@test.com")
        doc = Document(user_id=uid, document_type="PAN", status="PENDING")
        db_session.add(doc)
        db_session.commit()

        llm = _MockLLM("some text")
        agent = CaseWorkerAgent(db=db_session, llm_provider=llm)
        resp = agent.handle(AgentRequest(query="status", user_id=str(uid)))
        assert resp.data["case_meta"]["documents_on_file"] == 1
        assert resp.data["case_meta"]["has_profile"] is False


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestCaseWorkerEndpoint:
    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/case_worker",
            json={"query": "Show my case status"},
        )
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/case_worker",
            json={"query": "Show my case status"},
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_authenticated_query_returns_200(self, client: TestClient):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/agents/case_worker",
            json={"query": "What is my current case status?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_name"] == "case_worker"
        assert "case_summary" in body
        assert "priority_actions" in body
        assert "document_gaps" in body
        assert "roadmap_status" in body
        assert "risk_flags" in body
        assert "case_meta" in body

    def test_empty_query_returns_422(self, client: TestClient):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/agents/case_worker",
            json={"query": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_new_user_no_data_returns_no_data_status(self, client: TestClient):
        # A freshly registered user has no profile/docs/roadmaps
        token = _register_and_login(client, email="newuser@example.com")
        resp = client.post(
            "/api/v1/agents/case_worker",
            json={"query": "What should I do?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_data"

    def test_response_has_all_fields(self, client: TestClient):
        token = _register_and_login(client, email="fields@example.com")
        resp = client.post(
            "/api/v1/agents/case_worker",
            json={"query": "Give me a case summary"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        for field in ("agent_name", "status", "case_summary", "priority_actions",
                      "document_gaps", "roadmap_status", "risk_flags", "case_meta"):
            assert field in body, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Supervisor routing test for 'case_worker' domain
# ---------------------------------------------------------------------------

class TestSupervisorCaseWorkerRouting:
    def test_supervisor_routes_case_worker_query(self, client: TestClient):
        token = _register_and_login(client, email="sv_cw@example.com")
        resp = client.post(
            "/api/v1/agents/supervisor",
            json={"query": "I need a caseworker and a support worker assigned to my case"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["routed_to"] == "case_worker"
