"""Task-aware guide tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.agents.base import AgentResponse
from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.models import entities as _entities_import  # noqa: F401
from backend.app.database.models.entities import Progress, Roadmap, RoadmapTask, User, UserProfile
from backend.app.database.session import SessionLocal, configure_session_factory, get_engine
from backend.app.security.passwords import hash_password
from backend.app.services.resource_registry import get_resource, list_resources, map_resource_types

_TEST_SECRET = "test-secret-task-guide"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "task_guide_test.db"
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


def _register_and_login(client: TestClient, email: str, password: str = "pass123") -> str:
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_task(
    email: str = "user@example.com",
    state: str = "Karnataka",
    agent_type: str = "legal",
    resource_ids: list[str] | None = None,
) -> tuple[int, int]:
    with SessionLocal() as db:
        user = User(email=email, hashed_password=hash_password("pass123"), role="USER")
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(
            UserProfile(
                user_id=user.id,
                full_name="Asha",
                state=state,
                language="English",
                onboarding_data={"location": state, "situation": ["Career break"], "goals": ["Get support"]},
            )
        )
        roadmap = Roadmap(user_id=user.id, title="Plan", summary="Summary", status="ACTIVE")
        db.add(roadmap)
        db.commit()
        db.refresh(roadmap)

        task = RoadmapTask(
            roadmap_id=roadmap.id,
            title="Get legal aid",
            description="Open the right legal service.",
            agent_type=agent_type,
            objective="Understand how to access legal aid.",
            required_information=["State", "case summary"],
            required_documents=["Aadhaar"],
            completion_criteria="You have contacted or submitted through the official legal aid service.",
            resource_ids=resource_ids if resource_ids is not None else ["nalsa", "karnataka_slsa"],
            priority="HIGH",
            status="PENDING",
            sequence=1,
        )
        db.add(task)
        db.add(Progress(roadmap_id=roadmap.id, engagement_history=[]))
        db.commit()
        db.refresh(task)
        return user.id, task.id


def test_resource_registry_mapping_and_lookup() -> None:
    ids = map_resource_types(["employment_service", "unknown"], agent_type="employment", state="Karnataka")
    assert "national_career_service" in ids
    assert "eshram" in ids
    assert "unknown" not in ids
    resource = get_resource("national_career_service")
    assert resource is not None
    assert resource.official_url == "https://www.ncs.gov.in/"


def test_resource_registry_karnataka_legal_adds_state_resource() -> None:
    ids = map_resource_types([], agent_type="legal", state="Karnataka")
    assert "nalsa" in ids
    assert "karnataka_slsa" in ids


def test_task_guide_endpoint_returns_task_context_and_resources(client: TestClient) -> None:
    _seed_task(email="guide@example.com")
    token = _register_and_login(client, "guide@example.com")

    with SessionLocal() as db:
        task_id = db.query(RoadmapTask).filter(RoadmapTask.agent_type == "legal").one().id

    resp = client.get(f"/api/v1/roadmaps/tasks/{task_id}/guide", headers=_auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["task"]["title"] == "Get legal aid"
    assert body["agent_type"] == "legal"
    assert "required_information" in body
    assert len(body["official_resources"]) == 2
    assert body["official_resources"][0]["official_url"].startswith("https://")


def test_task_guide_invalid_task_returns_404(client: TestClient) -> None:
    token = _register_and_login(client, "missing@example.com")
    resp = client.get("/api/v1/roadmaps/tasks/9999/guide", headers=_auth_headers(token))
    assert resp.status_code == 404


def test_task_guide_jwt_ownership_enforced(client: TestClient) -> None:
    _, task_id = _seed_task(email="owner-guide@example.com")
    owner_token = _register_and_login(client, "owner-guide@example.com")
    other_token = _register_and_login(client, "other-guide@example.com")

    ok = client.get(f"/api/v1/roadmaps/tasks/{task_id}/guide", headers=_auth_headers(owner_token))
    forbidden = client.get(f"/api/v1/roadmaps/tasks/{task_id}/guide", headers=_auth_headers(other_token))
    assert ok.status_code == 200
    assert forbidden.status_code == 404


def test_task_guide_no_resources_available_returns_empty_list(client: TestClient) -> None:
    _, task_id = _seed_task(email="noresources@example.com", resource_ids=[])
    token = _register_and_login(client, "noresources@example.com")
    resp = client.get(f"/api/v1/roadmaps/tasks/{task_id}/guide", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["official_resources"] == []


def test_task_follow_up_chat_routes_by_task_agent_type(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, task_id = _seed_task(email="route@example.com", agent_type="employment", resource_ids=["national_career_service"])
    token = _register_and_login(client, "route@example.com")

    captured: dict[str, str] = {}

    def _fake_run(self, agent_type: str, user_id: int, query: str, profile_context: dict[str, object]) -> AgentResponse:
        captured["agent_type"] = agent_type
        captured["query"] = query
        return AgentResponse(agent_name=agent_type, status="ok", summary="Employment guidance.", sources=["verified_source"])

    monkeypatch.setattr("backend.app.services.task_guide_service.TaskGuideService._run_specialist_agent", _fake_run)

    resp = client.post(
        f"/api/v1/roadmaps/tasks/{task_id}/guide/chat",
        json={"query": "Where should I apply first?"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    assert captured["agent_type"] == "employment"
    assert "Where should I apply first?" in captured["query"]
    assert resp.json()["answer"] == "Employment guidance."
    assert resp.json()["official_resources"][0]["name"] == "National Career Service"


def test_task_follow_up_chat_unauthorized_task_returns_404(client: TestClient) -> None:
    _, task_id = _seed_task(email="owner-chat@example.com")
    other_token = _register_and_login(client, "other-chat@example.com")
    resp = client.post(
        f"/api/v1/roadmaps/tasks/{task_id}/guide/chat",
        json={"query": "Help me"},
        headers=_auth_headers(other_token),
    )
    assert resp.status_code == 404


def test_existing_task_completion_still_works(client: TestClient) -> None:
    _, task_id = _seed_task(email="complete@example.com")
    token = _register_and_login(client, "complete@example.com")
    resp = client.patch(
        f"/api/v1/roadmaps/tasks/{task_id}",
        json={"status": "COMPLETED"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["progress"]["completed_milestones"] == 1


def test_list_resources_filters_unknown_ids() -> None:
    resources = list_resources(["nalsa", "missing", "nalsa"])
    assert len(resources) == 1
    assert resources[0].name == "NALSA"
