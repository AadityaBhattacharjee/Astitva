"""Shared API dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.models.entities import User
from backend.app.database.session import get_db
from backend.app.security.jwt import decode_access_token
from backend.app.security.rbac import Role

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate a Bearer JWT; return the corresponding User."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise exc

    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise exc

    user = db.scalar(select(User).where(User.id == int(user_id_str)))
    if user is None:
        raise exc

    return user


def require_role(role: Role) -> Role:
    """Placeholder dependency for future role-based access checks."""
    return role
