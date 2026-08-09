"""Roadmap and progress schemas."""

from pydantic import BaseModel, Field

from backend.app.database.schemas.common import TimestampedSchema


class RoadmapTaskBase(BaseModel):
    title: str
    description: str | None = None
    status: str = "PENDING"
    priority: str = "MEDIUM"


class RoadmapTaskCreate(RoadmapTaskBase):
    roadmap_id: int


class RoadmapTaskRead(RoadmapTaskBase, TimestampedSchema):
    id: int
    roadmap_id: int


class RoadmapBase(BaseModel):
    title: str = "Personalized Roadmap"
    summary: str | None = None
    status: str = "DRAFT"


class RoadmapCreate(RoadmapBase):
    user_id: int


class RoadmapRead(RoadmapBase, TimestampedSchema):
    id: int
    user_id: int
    tasks: list[RoadmapTaskRead] = Field(default_factory=list)


class ProgressBase(BaseModel):
    status: str = "ACTIVE"
    completed_milestones: int = 0
    missed_milestones: int = 0
    overdue_tasks: int = 0
    engagement_history: list[str] = Field(default_factory=list)


class ProgressCreate(ProgressBase):
    roadmap_id: int


class ProgressRead(ProgressBase, TimestampedSchema):
    id: int
    roadmap_id: int
