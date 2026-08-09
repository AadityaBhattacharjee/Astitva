"""Shared schema primitives."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMBaseModel(BaseModel):
    """Base schema with ORM support enabled."""

    model_config = ConfigDict(from_attributes=True)


class TimestampedSchema(ORMBaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None

