"""Scheme CRUD routes with structured filtering for Phase 2."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from backend.app.database.models.entities import Scheme
from backend.app.database.schemas.schemes import SchemeCreate, SchemeRead
from backend.app.database.session import get_db

router = APIRouter(prefix="/schemes", tags=["schemes"])


def _normalized_equals(column: object, value: str) -> object:
    return func.lower(column) == value.strip().lower()


def _scheme_query(
    *,
    state: str | None = None,
    category: str | None = None,
    target_group: str | None = None,
    active_status: bool | None = None,
    income: int | None = None,
    age: int | None = None,
) -> Select[tuple[Scheme]]:
    statement = select(Scheme)

    if state:
        normalized_state = state.strip().lower()
        statement = statement.where(
            or_(
                func.lower(Scheme.state) == normalized_state,
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
        statement = statement.where(or_(Scheme.income_limit.is_(None), Scheme.income_limit >= income))

    if age is not None:
        statement = statement.where(or_(Scheme.min_age.is_(None), Scheme.min_age <= age))
        statement = statement.where(or_(Scheme.max_age.is_(None), Scheme.max_age >= age))

    return statement.order_by(Scheme.scheme_name)


@router.get("/", response_model=list[SchemeRead])
def list_schemes(
    state: str | None = None,
    category: str | None = None,
    target_group: str | None = None,
    active_status: bool | None = None,
    income: int | None = Query(default=None, ge=0),
    age: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
) -> list[Scheme]:
    statement = _scheme_query(
        state=state,
        category=category,
        target_group=target_group,
        active_status=active_status,
        income=income,
        age=age,
    )
    return list(db.scalars(statement).all())


@router.get("/eligible", response_model=list[SchemeRead])
def list_eligible_schemes(
    state: str | None = None,
    category: str | None = None,
    target_group: str | None = None,
    income: int | None = Query(default=None, ge=0),
    age: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
) -> list[Scheme]:
    statement = _scheme_query(
        state=state,
        category=category,
        target_group=target_group,
        active_status=True,
        income=income,
        age=age,
    )
    return list(db.scalars(statement).all())


@router.post("/", response_model=SchemeRead, status_code=status.HTTP_201_CREATED)
def create_scheme(payload: SchemeCreate, db: Session = Depends(get_db)) -> Scheme:
    existing = db.scalar(select(Scheme).where(Scheme.scheme_id == payload.scheme_id))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scheme with this scheme_id already exists.")

    payload_data = payload.model_dump(mode="json")
    scheme = Scheme(**payload_data, scheme_name=payload_data["name"])
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return scheme
