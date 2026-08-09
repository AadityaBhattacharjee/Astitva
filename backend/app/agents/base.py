"""Base classes shared by future agent implementations."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    """Common request shape passed into agent workflows."""

    user_id: str | None = None
    case_id: str | None = None
    query: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """Common placeholder response returned from agent workflows."""

    agent_name: str
    status: str = "placeholder"
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)


class BaseAgent(ABC):
    """Abstract base class for all future Astitva agents."""

    name: str
    responsibilities: tuple[str, ...]

    @abstractmethod
    def handle(self, request: AgentRequest) -> AgentResponse:
        """Process an agent request.

        TODO: Implement domain-specific logic and retrieval orchestration.
        """

