"""Database session helpers."""

from functools import lru_cache
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings


def _engine_options(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


@lru_cache
def get_engine() -> Engine:
    """Create a cached SQLAlchemy engine from current settings."""

    settings = get_settings()
    return create_engine(settings.database_url, future=True, **_engine_options(settings.database_url))


SessionLocal = sessionmaker(autoflush=False, autocommit=False, future=True)
SessionLocal.configure(bind=get_engine())


def configure_session_factory(database_url: str) -> Engine:
    """Rebind the global session factory, primarily for tests and scripts."""

    engine = create_engine(database_url, future=True, **_engine_options(database_url))
    SessionLocal.configure(bind=engine)
    return engine


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for request-scoped usage."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
