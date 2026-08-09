"""Time helper functions."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)

