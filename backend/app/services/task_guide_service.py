"""Task-aware guide service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.base import AgentRequest, AgentResponse
from backend.app.agents.case_worker.agent import CaseWorkerAgent
from backend.app.agents.document.agent import DocumentAgent
from backend.app.agents.employment.agent import EmploymentAgent
from backend.app.agents.finance.agent import FinanceAgent
from backend.app.agents.government.agent import GovernmentAgent
from backend.app.agents.healthcare.agent import HealthcareAgent
from backend.app.agents.legal.agent import LegalAgent
from backend.app.agents.mentor_matching.agent import MentorMatchingAgent
from backend.app.agents.planning.agent import PlanningAgent
from backend.app.agents.progress.agent import ProgressAgent
from backend.app.agents.risk.agent import RiskPredictionAgent
from backend.app.database.models.entities import Document, RoadmapTask, UserProfile
from backend.app.rag.embeddings.provider import SentenceTransformerEmbeddingProvider
from backend.app.rag.retrieval.hybrid import HybridRetriever
from backend.app.rag.retrieval.structured import SchemeStructuredRetriever
from backend.app.rag.vector_store.chroma_store import ChromaStore
from backend.app.services.llm_provider import BaseLLMProvider
from backend.app.services.resource_registry import ApprovedResource, list_resources
from backend.app.services.roadmap_service import RoadmapService, RoadmapValidationError

_embedding_provider: SentenceTransformerEmbeddingProvider | None = None
_vector_store: ChromaStore | None = None


def _default_completion_guidance(task: RoadmapTask) -> str:
    if task.completion_criteria:
        return task.completion_criteria
    return "Use the official resource, complete the external action, save any acknowledgement, then mark this task complete in Astitva."


class TaskGuideService:
    """Loads task context and routes follow-up guide queries."""

    def __init__(self, db: Session, llm_provider: BaseLLMProvider) -> None:
        self._db = db
        self._llm = llm_provider
        self._roadmap_service = RoadmapService(db=db, llm_provider=llm_provider)

    def get_task(self, user_id: int, task_id: int) -> RoadmapTask:
        task = self._roadmap_service.get_task_for_user(user_id, task_id)
        if task is None:
            raise RoadmapValidationError("Task not found.")
        return task

    def build_initial_guide(self, user_id: int, task_id: int) -> dict[str, Any]:
        task = self.get_task(user_id, task_id)
        resources = self._serialize_resources(list_resources(task.resource_ids or []))

        next_steps: list[str] = []
        if task.required_information:
            next_steps.append("Gather the required information for this task.")
        if task.required_documents:
            next_steps.append("Collect the required documents before starting the external process.")
        if resources:
            next_steps.append(f"Open {resources[0]['name']} and follow the official process.")
        next_steps.append("Save any acknowledgement or reference number for your records.")
        next_steps.append("Mark the task complete in Astitva after you finish the external action.")

        explanation = task.objective or task.description or (
            f"This task helps you make progress on '{task.title}'."
        )
        return {
            "task": task,
            "agent_type": task.agent_type,
            "explanation": explanation,
            "next_steps": next_steps,
            "required_information": list(task.required_information or []),
            "required_documents": list(task.required_documents or []),
            "official_resources": resources,
            "completion_guidance": _default_completion_guidance(task),
            "current_task_status": task.status,
        }

    def answer_follow_up(self, user_id: int, task_id: int, query: str) -> dict[str, Any]:
        task = self.get_task(user_id, task_id)
        response = self._run_specialist_agent(
            agent_type=task.agent_type,
            user_id=user_id,
            query=self._build_task_query(task, query),
            profile_context=self._build_profile_context(user_id),
        )
        return {
            "task_id": task.id,
            "agent_type": task.agent_type,
            "answer": response.summary,
            "official_resources": self._serialize_resources(list_resources(task.resource_ids or [])),
            "sources": response.sources,
        }

    def _build_task_query(self, task: RoadmapTask, query: str) -> str:
        lines = [
            f"Task title: {task.title}",
            f"Task description: {task.description or ''}",
            f"Task objective: {task.objective or ''}",
            f"Required information: {', '.join(task.required_information or []) or 'Not specified'}",
            f"Required documents: {', '.join(task.required_documents or []) or 'Not specified'}",
            f"Completion criteria: {task.completion_criteria or 'Not specified'}",
            f"User question: {query}",
        ]
        return "\n".join(lines)

    def _build_profile_context(self, user_id: int) -> dict[str, Any]:
        profile = self._db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
        documents = self._db.scalars(select(Document).where(Document.user_id == user_id)).all()
        context: dict[str, Any] = {}
        if profile is not None:
            if profile.state:
                context["state"] = profile.state
            if profile.language:
                context["language"] = profile.language
            onboarding_data = profile.onboarding_data or {}
            situation = onboarding_data.get("situation")
            if isinstance(situation, list) and situation:
                context["target_group"] = str(situation[0]).lower().replace(" ", "_")
        if documents:
            context["document_types"] = [doc.document_type for doc in documents]
        return context

    def _run_specialist_agent(
        self,
        agent_type: str,
        user_id: int,
        query: str,
        profile_context: dict[str, Any],
    ) -> AgentResponse:
        request = AgentRequest(
            user_id=str(user_id),
            query=query,
            context=profile_context,
        )
        if agent_type == "government":
            agent = GovernmentAgent(
                hybrid_retriever=self._hybrid_retriever(),
                llm_provider=self._llm,
            )
        elif agent_type == "document":
            agent = DocumentAgent(vector_store=self._vector_store_instance(), llm_provider=self._llm)
        elif agent_type == "employment":
            agent = EmploymentAgent(
                hybrid_retriever=self._hybrid_retriever(),
                llm_provider=self._llm,
            )
        elif agent_type == "finance":
            agent = FinanceAgent(
                hybrid_retriever=self._hybrid_retriever(),
                llm_provider=self._llm,
            )
        elif agent_type == "healthcare":
            agent = HealthcareAgent(
                hybrid_retriever=self._hybrid_retriever(),
                llm_provider=self._llm,
            )
        elif agent_type == "legal":
            agent = LegalAgent(
                hybrid_retriever=self._hybrid_retriever(),
                llm_provider=self._llm,
            )
        elif agent_type == "mentor_matching":
            agent = MentorMatchingAgent(db=self._db, llm_provider=self._llm)
        elif agent_type == "progress":
            agent = ProgressAgent(db=self._db, llm_provider=self._llm)
        elif agent_type == "risk":
            agent = RiskPredictionAgent(db=self._db, llm_provider=self._llm)
        elif agent_type == "case_worker":
            agent = CaseWorkerAgent(db=self._db, llm_provider=self._llm)
        else:
            agent = PlanningAgent(db=self._db, llm_provider=self._llm)
        return agent.handle(request)

    def _hybrid_retriever(self) -> HybridRetriever:
        return HybridRetriever(
            structured_retriever=SchemeStructuredRetriever(self._db),
            vector_store=self._vector_store_instance(),
        )

    def _vector_store_instance(self) -> ChromaStore:
        global _vector_store  # noqa: PLW0603
        if _vector_store is None:
            from backend.app.config import get_settings

            settings = get_settings()
            _vector_store = ChromaStore(
                persist_directory=settings.chroma_persist_directory,
                collection_name=settings.chroma_collection_name,
                embedding_provider=self._embedding_provider_instance(),
            )
        return _vector_store

    def _embedding_provider_instance(self) -> SentenceTransformerEmbeddingProvider:
        global _embedding_provider  # noqa: PLW0603
        if _embedding_provider is None:
            from backend.app.config import get_settings

            settings = get_settings()
            _embedding_provider = SentenceTransformerEmbeddingProvider(
                model_name=settings.embedding_model,
            )
        return _embedding_provider

    def _serialize_resources(self, resources: list[ApprovedResource]) -> list[dict[str, Any]]:
        return [
            {
                "resource_id": resource.resource_id,
                "name": resource.name,
                "category": resource.category,
                "description": resource.description,
                "official_url": resource.official_url,
                "applicable_agent_types": list(resource.applicable_agent_types),
            }
            for resource in resources
        ]
