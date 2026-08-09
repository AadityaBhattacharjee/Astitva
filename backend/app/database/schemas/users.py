"""User and profile schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from backend.app.database.schemas.common import TimestampedSchema


class UserBase(BaseModel):
    email: EmailStr
    role: str = "USER"
    is_active: bool = True


class UserCreate(UserBase):
    password: str
    full_name: str | None = None
    state: str | None = None
    language: str | None = None


class UserRead(UserBase, TimestampedSchema):
    id: int
    profile: "UserProfileRead | None" = None


class UserProfileBase(BaseModel):
    full_name: str | None = None
    state: str | None = None
    language: str | None = None
    onboarding_data: dict[str, object] = Field(default_factory=dict)


class UserProfileCreate(UserProfileBase):
    user_id: int


class UserProfileUpsert(UserProfileBase):
    onboarding_completed_at: datetime | None = None


class UserProfileRead(UserProfileBase, TimestampedSchema):
    id: int
    user_id: int
    onboarding_completed_at: datetime | None = None


UserRead.model_rebuild()
