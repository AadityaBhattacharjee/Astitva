"""User CRUD routes for Phase 1."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.dependencies import get_current_user
from backend.app.database.models.entities import User, UserProfile
from backend.app.database.schemas.users import UserCreate, UserRead
from backend.app.database.session import get_db

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    statement = select(User).options(selectinload(User.profile)).order_by(User.id)
    return list(db.scalars(statement).all())


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this email already exists.")

    user = User(
        email=payload.email,
        hashed_password=f"demo-hash::{payload.password}",
        role=payload.role,
        is_active=payload.is_active,
    )
    if payload.full_name or payload.state or payload.language:
        user.profile = UserProfile(
            full_name=payload.full_name,
            state=payload.state,
            language=payload.language,
        )

    db.add(user)
    db.commit()
    db.refresh(user)
    return db.scalar(select(User).options(selectinload(User.profile)).where(User.id == user.id)) or user


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Return the authenticated user's own record."""
    return db.scalar(
        select(User).options(selectinload(User.profile)).where(User.id == current_user.id)
    ) or current_user
