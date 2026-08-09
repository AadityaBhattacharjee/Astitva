"""Structured retriever for government schemes backed by PostgreSQL/SQLite."""

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.database.models.entities import Scheme
from backend.app.rag.interfaces import BaseStructuredRetriever


def _normalized_equals(column: object, value: str) -> object:
    """Case-insensitive exact match on a string column."""
    return func.lower(column) == value.strip().lower()


def build_scheme_query(
    *,
    state: str | None = None,
    category: str | None = None,
    target_group: str | None = None,
    active_status: bool | None = True,
    income: int | None = None,
    age: int | None = None,
):
    """Build a SQLAlchemy SELECT statement for the Scheme table.

    Shared by SchemeStructuredRetriever and (via re-export) by the scheme routes.
    Defaults ``active_status`` to ``True`` so retrieval only surfaces live schemes.
    """
    statement = select(Scheme)

    if state:
        normalized = state.strip().lower()
        statement = statement.where(
            or_(
                func.lower(Scheme.state) == normalized,
                func.lower(Scheme.state) == "all states",
            )
        )

    if category:
        statement = statement.where(_normalized_equals(Scheme.category, category))

    if target_group:
        statement = statement.where(
            or_(
                Scheme.target_group.is_(None),
                _normalized_equals(Scheme.target_group, target_group),
            )
        )

    if active_status is not None:
        statement = statement.where(Scheme.active_status.is_(active_status))

    if income is not None:
        statement = statement.where(
            or_(Scheme.income_limit.is_(None), Scheme.income_limit >= income)
        )

    if age is not None:
        statement = statement.where(
            or_(Scheme.min_age.is_(None), Scheme.min_age <= age)
        )
        statement = statement.where(
            or_(Scheme.max_age.is_(None), Scheme.max_age >= age)
        )

    return statement.order_by(Scheme.scheme_name)


def scheme_to_dict(scheme: Scheme) -> dict[str, Any]:
    """Serialise a Scheme ORM object to a plain dict safe for JSON responses."""
    return {
        "id": scheme.id,
        "scheme_id": scheme.scheme_id,
        "name": scheme.scheme_name,
        "description": scheme.description,
        "category": scheme.category,
        "state": scheme.state,
        "target_group": scheme.target_group,
        "min_age": scheme.min_age,
        "max_age": scheme.max_age,
        "income_limit": scheme.income_limit,
        "eligibility": scheme.eligibility,
        "benefits": scheme.benefits,
        "required_documents": scheme.required_documents,
        "application_process": scheme.application_process,
        "official_url": str(scheme.official_url) if scheme.official_url else None,
        "source": scheme.source,
        "last_verified": scheme.last_verified,
        "active_status": scheme.active_status,
        "_source_type": "structured_db",
    }


class SchemeStructuredRetriever(BaseStructuredRetriever):
    """Retrieves government schemes from SQL using profile-based eligibility filters.

    Filters are passed through the ``filters`` dict and may include:
      state, category, target_group, age (int), income (int), active_status (bool).

    The ``query`` string is currently unused for SQL retrieval (no full-text
    search on descriptions yet); it is preserved in the contract for future use.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def retrieve(
        self,
        query: str,  # noqa: ARG002 – reserved for future full-text use
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        statement = build_scheme_query(
            state=filters.get("state"),
            category=filters.get("category"),
            target_group=filters.get("target_group"),
            active_status=filters.get("active_status", True),
            income=filters.get("income"),
            age=filters.get("age"),
        )
        schemes = list(self._session.scalars(statement).all())
        return [scheme_to_dict(s) for s in schemes]
