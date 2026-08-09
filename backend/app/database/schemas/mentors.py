"""Mentor and consent schemas."""

from pydantic import BaseModel, Field

from backend.app.database.schemas.common import TimestampedSchema


class UserSummary(BaseModel):
    user_id: int
    language: str | None = None
    state: str | None = None
    domains: list[str] = Field(default_factory=list)


class MentorProfileSchema(TimestampedSchema):
    id: int | None = None
    user_id: int
    bio: str | None = None
    lived_experience_tags: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    availability: str | None = None
    opt_in: bool = False


class MentorSchema(TimestampedSchema):
    id: int | None = None
    user: UserSummary
    profile: MentorProfileSchema | None = None
    active: bool = False


class MentorMatchSchema(TimestampedSchema):
    id: int | None = None
    mentor_id: int
    user_id: int
    match_reasons: list[str] = Field(default_factory=list)
    status: str = "PENDING"


class ConsentSchema(TimestampedSchema):
    id: int | None = None
    user_id: int
    consent_type: str
    granted: bool
    scope: str | None = None
