"""FastAPI entrypoint for the Astitva backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api.router import api_router
from backend.app.config import get_settings
from backend.app.database.session import get_engine

settings = get_settings()

app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    description="Placeholder backend scaffold for the Astitva platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Return app and database readiness for local and container checks."""

    database_status = "ok"
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

    return {"status": "ok", "service": settings.project_name, "database": database_status}


app.include_router(api_router, prefix=settings.api_v1_prefix)
