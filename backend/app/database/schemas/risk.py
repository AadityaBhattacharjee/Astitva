"""Risk prediction schemas."""

from enum import Enum

from pydantic import BaseModel, Field

from backend.app.database.schemas.common import TimestampedSchema


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskFeatures(BaseModel):
    missed_milestones: int = 0
    completed_milestones: int = 0
    overdue_tasks: int = 0
    application_status: str | None = None
    employment_status: str | None = None
    financial_constraints: str | None = None
    document_completion: float = 0.0
    engagement_progress_history: list[str] = Field(default_factory=list)


class RiskPredictionSchema(TimestampedSchema):
    id: int | None = None
    case_id: int
    risk_level: RiskLevel
    risk_score: float
    contributing_factors: list[str] = Field(default_factory=list)
    recommended_intervention: str | None = None
