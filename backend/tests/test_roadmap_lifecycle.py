"""Roadmap lifecycle tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.models import entities as _entities_import  # noqa: F401
from backend.app.database.models.entities import Progress, Roadmap, RoadmapTask, UserProfile
from backend.app.database.session import SessionLocal, configure_session_factory, get_engine
from backend.app.services.llm_provider import BaseLLMProvider, PlaceholderLLMProvider

_TEST_SECRET = "test-secret-roadmap"


class _FakeRoadmapLLM(BaseLLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response

    def generate(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        return self._response


class _FailingRoadmapLLM(BaseLLMProvider):
    def generate(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        raise RuntimeError("Granite offline")


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "roadmap_test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    os.environ["DATABASE_URL"] = database_url
    os.environ["SECRET_KEY"] = _TEST_SECRET
    os.environ["GRANITE_BASE_URL"] = ""
    os.environ["HF_API_TOKEN"] = ""
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = configure_session_factory(database_url)
    Base.metadata.create_all(bind=engine)

    from backend.app.main import app

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)
    for key in ("DATABASE_URL", "SECRET_KEY", "GRANITE_BASE_URL", "HF_API_TOKEN"):
        os.environ.pop(key, None)
    get_settings.cache_clear()
    get_engine.cache_clear()


def _register_and_login(
    client: TestClient,
    email: str = "roadmap@example.com",
    password: str = "pass123",
) -> str:
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _valid_onboarding_payload() -> dict[str, object]:
    return {
        "full_name": "Asha",
        "state": "Pune, Maharashtra",
        "language": "English",
        "onboarding_data": {
            "ageRange": "25-29",
            "location": "Pune, Maharashtra",
            "language": "English",
            "situation": ["Career break"],
            "employmentStatus": "Not working right now",
            "housing": "Rented accommodation",
            "dependents": "1 child",
            "safetyConcern": "No",
            "legalNeeds": ["Not sure yet"],
            "healthcareNeeds": ["Counselling"],
            "financialNeeds": ["Emergency assistance"],
            "goals": ["Earn an income of my own"],
            "careerNeeds": ["Job placement"],
            "constraints": ["Limited free time on weekdays"],
            "communicationPreference": "In-app messages",
        },
    }


def test_onboarding_persists_profile(client: TestClient) -> None:
    token = _register_and_login(client)
    resp = client.put("/api/v1/profile/me", json=_valid_onboarding_payload(), headers=_auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Asha"
    assert body["onboarding_data"]["goals"] == ["Earn an income of my own"]
    assert body["onboarding_completed_at"] is not None


def test_generate_roadmap_persists_roadmap_tasks_and_progress(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.api.routes.roadmap as roadmap_module

    monkeypatch.setattr(
        roadmap_module,
        "get_llm_provider",
        lambda: _FakeRoadmapLLM(
            """
            {
              "title": "Income Restart Plan",
              "summary": "Focus on stabilising income and preparing for applications.",
              "tasks": [
                {"title": "Update your documents", "description": "Collect ID and bank proof.", "priority": "HIGH"},
                {"title": "Apply for support", "description": "Start with the most relevant scheme.", "priority": "MEDIUM"}
              ]
            }
            """
        ),
    )

    token = _register_and_login(client)
    profile_resp = client.put("/api/v1/profile/me", json=_valid_onboarding_payload(), headers=_auth_headers(token))
    assert profile_resp.status_code == 200

    resp = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token))
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["roadmap"]["title"] == "Income Restart Plan"
    assert len(body["roadmap"]["tasks"]) == 2
    assert body["roadmap"]["tasks"][0]["sequence"] == 1
    assert body["progress"]["completed_milestones"] == 0

    with SessionLocal() as db:
        roadmap_count = db.query(Roadmap).count()
        task_count = db.query(RoadmapTask).count()
        progress_count = db.query(Progress).count()

    assert roadmap_count == 1
    assert task_count == 2
    assert progress_count == 1


def test_generate_roadmap_is_idempotent_by_default(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.api.routes.roadmap as roadmap_module

    monkeypatch.setattr(
        roadmap_module,
        "get_llm_provider",
        lambda: _FakeRoadmapLLM(
            '{"title":"Plan","summary":"Summary","tasks":[{"title":"Task 1","description":"D","priority":"HIGH"}]}'
        ),
    )

    token = _register_and_login(client)
    client.put("/api/v1/profile/me", json=_valid_onboarding_payload(), headers=_auth_headers(token))

    first = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token))
    second = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token))

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["roadmap"]["id"] == second.json()["roadmap"]["id"]
    assert second.json()["created"] is False

    with SessionLocal() as db:
        assert db.query(Roadmap).count() == 1


def test_generate_roadmap_rejects_malformed_granite_output(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.api.routes.roadmap as roadmap_module

    monkeypatch.setattr(roadmap_module, "get_llm_provider", lambda: _FakeRoadmapLLM("not json"))

    token = _register_and_login(client)
    client.put("/api/v1/profile/me", json=_valid_onboarding_payload(), headers=_auth_headers(token))

    resp = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token))
    assert resp.status_code == 422

    with SessionLocal() as db:
        assert db.query(Roadmap).count() == 0


def test_generate_roadmap_handles_granite_unavailable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.api.routes.roadmap as roadmap_module

    monkeypatch.setattr(roadmap_module, "get_llm_provider", lambda: _FailingRoadmapLLM())

    token = _register_and_login(client)
    client.put("/api/v1/profile/me", json=_valid_onboarding_payload(), headers=_auth_headers(token))

    resp = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token))
    assert resp.status_code == 503


def test_generate_roadmap_rejects_placeholder_provider(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.api.routes.roadmap as roadmap_module

    monkeypatch.setattr(roadmap_module, "get_llm_provider", lambda: PlaceholderLLMProvider())

    token = _register_and_login(client)
    client.put("/api/v1/profile/me", json=_valid_onboarding_payload(), headers=_auth_headers(token))

    resp = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token))
    assert resp.status_code == 503


def test_task_completion_updates_progress_and_enforces_ownership(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.api.routes.roadmap as roadmap_module

    monkeypatch.setattr(
        roadmap_module,
        "get_llm_provider",
        lambda: _FakeRoadmapLLM(
            """
            {
              "title": "Safety Plan",
              "summary": "A short plan.",
              "tasks": [
                {"title": "Task 1", "description": "First", "priority": "HIGH"},
                {"title": "Task 2", "description": "Second", "priority": "LOW"}
              ]
            }
            """
        ),
    )

    token_one = _register_and_login(client, "owner@example.com")
    token_two = _register_and_login(client, "other@example.com")
    client.put("/api/v1/profile/me", json=_valid_onboarding_payload(), headers=_auth_headers(token_one))
    client.put(
        "/api/v1/profile/me",
        json={**_valid_onboarding_payload(), "full_name": "Meera"},
        headers=_auth_headers(token_two),
    )

    generated = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token_one))
    task_id = generated.json()["roadmap"]["tasks"][0]["id"]

    forbidden = client.patch(
        f"/api/v1/roadmaps/tasks/{task_id}",
        json={"status": "COMPLETED"},
        headers=_auth_headers(token_two),
    )
    assert forbidden.status_code == 404

    completed = client.patch(
        f"/api/v1/roadmaps/tasks/{task_id}",
        json={"status": "COMPLETED"},
        headers=_auth_headers(token_one),
    )
    assert completed.status_code == 200
    assert completed.json()["progress"]["completed_milestones"] == 1

    progress_resp = client.get("/api/v1/progress/me", headers=_auth_headers(token_one))
    assert progress_resp.status_code == 200
    assert progress_resp.json()["completed_milestones"] == 1


def test_roadmap_generation_requires_complete_profile_context(client: TestClient) -> None:
    token = _register_and_login(client)
    incomplete = {
        "full_name": "Asha",
        "state": "Pune, Maharashtra",
        "language": "English",
        "onboarding_data": {
            "location": "Pune, Maharashtra",
            "goals": [],
            "situation": [],
        },
    }
    client.put("/api/v1/profile/me", json=incomplete, headers=_auth_headers(token))
    resp = client.post("/api/v1/roadmaps/generate", json={"force_refresh": False}, headers=_auth_headers(token))
    assert resp.status_code == 422


def test_brand_new_user_has_no_roadmap(client: TestClient) -> None:
    token = _register_and_login(client)
    resp = client.get("/api/v1/roadmaps/me", headers=_auth_headers(token))
    assert resp.status_code == 404
