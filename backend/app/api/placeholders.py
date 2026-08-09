"""Helpers for creating placeholder API endpoints."""

from collections.abc import Callable

from fastapi import APIRouter


def build_placeholder_router(resource_name: str, tag: str) -> APIRouter:
    """Create a router with simple placeholder endpoints.

    TODO: Replace placeholder handlers with real application services.
    """

    router = APIRouter(prefix=f"/{resource_name}", tags=[tag])

    @router.get("/", summary=f"List {tag}")
    def list_resources() -> dict[str, object]:
        return {
            "resource": resource_name,
            "status": "placeholder",
            "message": f"{tag} endpoints are scaffolded but not implemented yet.",
        }

    @router.post("/", summary=f"Create {tag}")
    def create_resource() -> dict[str, object]:
        return {
            "resource": resource_name,
            "status": "placeholder",
            "message": f"{tag} create workflow is not implemented yet.",
        }

    return router

