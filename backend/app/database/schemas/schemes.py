"""Government scheme schemas."""

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from backend.app.database.schemas.common import TimestampedSchema


class SchemeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scheme_id: str
    name: str
    description: str | None = None
    category: str | None = None
    state: str | None = None
    target_group: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    income_limit: int | None = None
    eligibility: str | None = None
    age_criteria: str | None = None
    income_criteria: str | None = None
    benefits: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    application_process: str | None = None
    official_url: HttpUrl | None = None
    source: str | None = None
    last_verified: str | None = None
    active_status: bool = True


class SchemeCreate(SchemeBase):
    pass


class SchemeRead(SchemeBase, TimestampedSchema):
    id: int
