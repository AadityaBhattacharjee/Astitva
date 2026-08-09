import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.database.base import Base
from backend.app.database.session import configure_session_factory, get_engine


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = configure_session_factory(database_url)
    Base.metadata.create_all(bind=engine)

    from backend.app.main import app

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)
    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    get_engine.cache_clear()
