"""JWT authentication tests."""

import os
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.models import entities as _entities_import  # noqa: F401 — ensures models register into Base.metadata
from backend.app.database.session import configure_session_factory, get_engine

_TEST_SECRET = "test-secret-key-for-auth-tests"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "auth_test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    os.environ["DATABASE_URL"] = database_url
    os.environ["SECRET_KEY"] = _TEST_SECRET
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
    get_settings.cache_clear()
    get_engine.cache_clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client: TestClient, email: str = "user@example.com", password: str = "secret123") -> dict:
    return client.post("/api/v1/auth/register", json={"email": email, "password": password}).json()


def _login_token(client: TestClient, email: str = "user@example.com", password: str = "secret123") -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def test_register_returns_201(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/register", json={"email": "new@example.com", "password": "pass"})
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_returns_409(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "pass"})
    resp = client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "pass"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_valid_returns_200_with_token(client: TestClient) -> None:
    _register(client)
    resp = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "secret123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    _register(client)
    resp = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_email_returns_401(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "pass"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------

def test_users_me_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 401


def test_users_me_with_valid_token_returns_200(client: TestClient) -> None:
    _register(client, "me@example.com")
    token = _login_token(client, "me@example.com")
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


def test_users_me_with_tampered_token_returns_401(client: TestClient) -> None:
    _register(client)
    token = _login_token(client)
    tampered = token[:-5] + "XXXXX"
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tampered}"})
    assert resp.status_code == 401


def test_users_me_with_expired_token_returns_401(client: TestClient) -> None:
    """Issue a token with a -1 minute TTL (already expired) and confirm 401."""
    from datetime import datetime, timezone
    from jose import jwt

    payload = {
        "sub": "999",
        "role": "USER",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Role in token payload
# ---------------------------------------------------------------------------

def test_role_included_in_token_payload(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "pass", "role": "ADMIN"})
    token = _login_token(client, "admin@example.com", "pass")

    from jose import jwt
    payload = jwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
    assert payload["role"] == "ADMIN"
    assert "sub" in payload
    assert "exp" in payload
