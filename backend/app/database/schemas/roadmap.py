"""Roadmap and progress schemas."""

from pydantic import BaseModel, Field

from backend.app.database.schemas.common import TimestampedSchema


class RoadmapTaskBase(BaseModel):
    title: str
    description: str | None = None
    agent_type: str = "planning"
    objective: str | None = None
    required_information: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    completion_criteria: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    sequence: int = 0
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


class RoadmapGenerateRequest(BaseModel):
    force_refresh: bool = False


class RoadmapTaskUpdate(BaseModel):
    status: str


class RoadmapStatusRead(BaseModel):
    roadmap: RoadmapRead
    progress: "ProgressRead"
    created: bool


class ApprovedResourceRead(BaseModel):
    resource_id: str
    name: str
    category: str
    description: str
    official_url: str
    applicable_agent_types: list[str] = Field(default_factory=list)


class TaskGuideRead(BaseModel):
    task: RoadmapTaskRead
    agent_type: str
    explanation: str
    next_steps: list[str] = Field(default_factory=list)
    required_information: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    official_resources: list[ApprovedResourceRead] = Field(default_factory=list)
    completion_guidance: str
    current_task_status: str


class TaskGuideChatRequest(BaseModel):
    query: str


class TaskGuideChatResponse(BaseModel):
    task_id: int
    agent_type: str
    answer: str
    official_resources: list[ApprovedResourceRead] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


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


RoadmapStatusRead.model_rebuild()
