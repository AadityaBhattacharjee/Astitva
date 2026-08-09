"""Factory helpers for future agent registration and lookup."""

from backend.app.agents.base import BaseAgent


class AgentRegistry:
    """Minimal registry to make agent discovery explicit from the start."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance for future orchestration."""

        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent | None:
        """Return a registered agent if present."""

        return self._agents.get(name)

