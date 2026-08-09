"""Document and ingestion schemas."""

from pydantic import BaseModel, Field

from backend.app.database.schemas.common import TimestampedSchema


class DocumentSchema(TimestampedSchema):
    id: int | None = None
    case_id: int | None = None
    document_type: str
    status: str = "PENDING"
    source: str | None = None


class DocumentRequirementSchema(BaseModel):
    name: str
    category: str | None = None
    required_for: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
