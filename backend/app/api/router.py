"""Aggregate API router for versioned endpoints."""

from fastapi import APIRouter

from backend.app.api.routes import (
    admin,
    agents,
    auth,
    case_workers,
    cases,
    documents,
    healthcare,
    jobs,
    mentors,
    profile,
    progress,
    rag,
    risk,
    roadmap,
    schemes,
    users,
)

api_router = APIRouter()

for router in [
    auth.router,
    users.router,
    profile.router,
    cases.router,
    agents.router,
    schemes.router,
    jobs.router,
    healthcare.router,
    documents.router,
    rag.router,
    roadmap.router,
    progress.router,
    risk.router,
    mentors.router,
    case_workers.router,
    admin.router,
]:
    api_router.include_router(router)

