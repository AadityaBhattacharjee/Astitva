"""User and profile schemas."""

from pydantic import BaseModel, EmailStr

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


class UserProfileCreate(UserProfileBase):
    user_id: int


class UserProfileRead(UserProfileBase, TimestampedSchema):
    id: int
    user_id: int


UserRead.model_rebuild()
