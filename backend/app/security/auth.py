"""Authentication placeholder helpers."""

from datetime import datetime, timedelta, timezone


def create_access_token(subject: str, expires_minutes: int = 60) -> dict[str, str]:
    """Return a placeholder token payload description.

    TODO: Replace with signed JWT generation.
    """

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    return {"subject": subject, "expires_at": expires_at.isoformat(), "status": "placeholder"}

