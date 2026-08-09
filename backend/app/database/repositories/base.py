"""Base repository placeholder."""

from typing import Any


class BaseRepository:
    """Minimal repository abstraction for future data access logic."""

    def __init__(self, session: Any) -> None:
        self.session = session

