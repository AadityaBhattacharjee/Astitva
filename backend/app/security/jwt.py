"""JWT creation and decoding helpers."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from backend.app.config import get_settings


def create_access_token(user_id: int, role: str) -> str:
    """Return a signed JWT for *user_id* with *role* in the payload."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and verify *token*; raise JWTError on any failure."""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
