"""Profile routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.dependencies import get_current_user
from backend.app.database.models.entities import User, UserProfile
from backend.app.database.schemas.users import UserProfileRead
from backend.app.database.session import get_db

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=UserProfileRead)
def get_my_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserProfile:
    """Return the authenticated user's profile."""
    user = db.scalar(
        select(User).options(selectinload(User.profile)).where(User.id == current_user.id)
    )
    if user is None or user.profile is None:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return user.profile
