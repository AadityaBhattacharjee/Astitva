"""Roadmap lifecycle service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.database.models.entities import Progress, Roadmap, RoadmapTask, User, UserProfile
from backend.app.services.llm_provider import BaseLLMProvider, PlaceholderLLMProvider


class RoadmapError(Exception):
    """Base roadmap lifecycle error."""


class RoadmapValidationError(RoadmapError):
    """Raised when user data or LLM output is invalid."""


class RoadmapUnavailableError(RoadmapError):
    """Raised when roadmap generation cannot reach Granite."""


@dataclass
class RoadmapGenerationResult:
    roadmap: Roadmap
    progress: Progress
    created: bool


_SYSTEM_PROMPT = """\
You create structured, practical roadmaps for Astitva users.

Rules:
- Output JSON only. No markdown.
- Use only the supplied user profile and onboarding context.
- Do not invent achievements, documents, or completed tasks.
- Return 3 to 7 concrete tasks.
- Keep priorities to HIGH, MEDIUM, or LOW.
- Keep task statuses as PENDING.

Return this exact schema:
{
  "title": "<short roadmap title>",
  "summary": "<1-2 sentence roadmap summary>",
  "tasks": [
    {
      "title": "<task title>",
      "description": "<task description>",
      "priority": "<HIGH|MEDIUM|LOW>"
    }
  ]
}
"""


def _normalize_priority(value: Any) -> str:
    priority = str(value or "MEDIUM").upper()
    if priority not in {"HIGH", "MEDIUM", "LOW"}:
        return "MEDIUM"
    return priority


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise RoadmapValidationError("Granite returned an empty roadmap response.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            raise RoadmapValidationError("Granite returned malformed roadmap JSON.") from None
        try:
            payload = json.loads(text[start:end])
        except json.JSONDecodeError as exc:
            raise RoadmapValidationError("Granite returned malformed roadmap JSON.") from exc
    if not isinstance(payload, dict):
        raise RoadmapValidationError("Granite roadmap output must be a JSON object.")
    return payload


def _validate_roadmap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    tasks = payload.get("tasks")

    if not title:
        raise RoadmapValidationError("Generated roadmap is missing a title.")
    if not summary:
        raise RoadmapValidationError("Generated roadmap is missing a summary.")
    if not isinstance(tasks, list) or not tasks:
        raise RoadmapValidationError("Generated roadmap must include at least one task.")

    normalized_tasks: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise RoadmapValidationError("Each generated roadmap task must be an object.")
        task_title = str(task.get("title") or "").strip()
        if not task_title:
            raise RoadmapValidationError("Generated roadmap task is missing a title.")
        normalized_tasks.append(
            {
                "title": task_title,
                "description": str(task.get("description") or "").strip() or None,
                "priority": _normalize_priority(task.get("priority")),
                "sequence": index,
                "status": "PENDING",
            }
        )

    return {"title": title, "summary": summary, "tasks": normalized_tasks}


def _location_from_profile(profile: UserProfile) -> str | None:
    onboarding_data = profile.onboarding_data or {}
    location = onboarding_data.get("location")
    if isinstance(location, str) and location.strip():
        return location.strip()
    if profile.state and profile.state.strip():
        return profile.state.strip()
    return None


class RoadmapService:
    """Persisted roadmap generation and task lifecycle."""

    def __init__(self, db: Session, llm_provider: BaseLLMProvider) -> None:
        self._db = db
        self._llm = llm_provider

    def get_current_roadmap(self, user_id: int) -> Roadmap | None:
        statement = (
            select(Roadmap)
            .options(
                selectinload(Roadmap.tasks),
                selectinload(Roadmap.progress_entries),
            )
            .where(Roadmap.user_id == user_id, Roadmap.status != "ARCHIVED")
            .order_by(Roadmap.updated_at.desc(), Roadmap.id.desc())
        )
        return self._db.scalar(statement)

    def get_task_for_user(self, user_id: int, task_id: int) -> RoadmapTask | None:
        statement = (
            select(RoadmapTask)
            .join(Roadmap, RoadmapTask.roadmap_id == Roadmap.id)
            .options(
                selectinload(RoadmapTask.roadmap).selectinload(Roadmap.progress_entries),
            )
            .where(RoadmapTask.id == task_id, Roadmap.user_id == user_id)
        )
        return self._db.scalar(statement)

    def get_or_create_progress(self, roadmap: Roadmap) -> Progress:
        return self._ensure_progress(roadmap)

    def generate_for_user(self, user: User, force_refresh: bool = False) -> RoadmapGenerationResult:
        profile = self._db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
        if profile is None:
            raise RoadmapValidationError("Complete onboarding before generating a roadmap.")

        context = self._build_generation_context(profile)
        existing = self.get_current_roadmap(user.id)
        if existing is not None and not force_refresh:
            progress = self._ensure_progress(existing)
            return RoadmapGenerationResult(roadmap=existing, progress=progress, created=False)

        proposal = self._generate_structured_proposal(context)

        try:
            if force_refresh:
                self._archive_existing_roadmaps(user.id)

            roadmap = Roadmap(
                user_id=user.id,
                title=proposal["title"],
                summary=proposal["summary"],
                status="ACTIVE",
            )
            self._db.add(roadmap)
            self._db.flush()

            for task_payload in proposal["tasks"]:
                self._db.add(RoadmapTask(roadmap_id=roadmap.id, **task_payload))

            self._db.flush()
            progress = self._ensure_progress(roadmap, created_at_event="Roadmap generated")
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

        persisted = self.get_current_roadmap(user.id)
        if persisted is None:
            raise RoadmapUnavailableError("Roadmap was generated but could not be reloaded.")
        persisted_progress = self._ensure_progress(persisted)
        return RoadmapGenerationResult(roadmap=persisted, progress=persisted_progress, created=True)

    def update_task_status(self, user_id: int, task_id: int, status: str) -> RoadmapGenerationResult:
        task = self.get_task_for_user(user_id, task_id)
        if task is None:
            raise RoadmapValidationError("Task not found.")

        normalized_status = str(status or "").upper()
        if normalized_status not in {"PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED"}:
            raise RoadmapValidationError("Invalid task status.")

        task.status = normalized_status
        task.updated_at = datetime.utcnow()
        progress = self._ensure_progress(
            task.roadmap,
            created_at_event=f"Task {task.id} marked {normalized_status}",
        )
        self._db.commit()
        roadmap = self.get_current_roadmap(user_id)
        if roadmap is None:
            raise RoadmapUnavailableError("Roadmap not found after task update.")
        return RoadmapGenerationResult(roadmap=roadmap, progress=progress, created=False)

    def _archive_existing_roadmaps(self, user_id: int) -> None:
        roadmaps = self._db.scalars(
            select(Roadmap).where(Roadmap.user_id == user_id, Roadmap.status != "ARCHIVED")
        ).all()
        for roadmap in roadmaps:
            roadmap.status = "ARCHIVED"

    def _build_generation_context(self, profile: UserProfile) -> dict[str, Any]:
        onboarding_data = profile.onboarding_data or {}
        goals = onboarding_data.get("goals")
        location = _location_from_profile(profile)
        situation = onboarding_data.get("situation")
        immediate_needs = {
            "legal_needs": onboarding_data.get("legalNeeds") or [],
            "healthcare_needs": onboarding_data.get("healthcareNeeds") or [],
            "financial_needs": onboarding_data.get("financialNeeds") or [],
            "career_needs": onboarding_data.get("careerNeeds") or [],
            "constraints": onboarding_data.get("constraints") or [],
            "safety_concern": onboarding_data.get("safetyConcern") or "",
        }

        if not location:
            raise RoadmapValidationError("Location is required before generating a roadmap.")
        if not isinstance(goals, list) or not [goal for goal in goals if str(goal).strip()]:
            raise RoadmapValidationError("At least one goal is required before generating a roadmap.")
        if not isinstance(situation, list) or not [item for item in situation if str(item).strip()]:
            raise RoadmapValidationError(
                "Current situation details are required before generating a roadmap."
            )

        return {
            "full_name": profile.full_name,
            "location": location,
            "language": profile.language,
            "goals": goals,
            "situation": situation,
            "employment_status": onboarding_data.get("employmentStatus") or "",
            "housing": onboarding_data.get("housing") or "",
            "dependents": onboarding_data.get("dependents") or "",
            "immediate_needs": immediate_needs,
            "communication_preference": onboarding_data.get("communicationPreference") or "",
        }

    def _generate_structured_proposal(self, context: dict[str, Any]) -> dict[str, Any]:
        if isinstance(self._llm, PlaceholderLLMProvider):
            raise RoadmapUnavailableError("Granite is unavailable for roadmap generation.")

        prompt = json.dumps(context, ensure_ascii=True, indent=2)
        try:
            raw = self._llm.generate(prompt, system=_SYSTEM_PROMPT)
        except Exception as exc:
            raise RoadmapUnavailableError("Granite is unavailable for roadmap generation.") from exc

        return _validate_roadmap_payload(_parse_json_object(raw))

    def _ensure_progress(self, roadmap: Roadmap, created_at_event: str | None = None) -> Progress:
        progress = next(iter(roadmap.progress_entries), None)
        if progress is None:
            progress = Progress(roadmap_id=roadmap.id, engagement_history=[])
            self._db.add(progress)
            roadmap.progress_entries.append(progress)

        completed_tasks = sum(1 for task in roadmap.tasks if task.status == "COMPLETED")
        blocked_tasks = sum(1 for task in roadmap.tasks if task.status == "BLOCKED")
        progress.completed_milestones = completed_tasks
        progress.missed_milestones = blocked_tasks
        progress.overdue_tasks = 0
        progress.status = "COMPLETED" if roadmap.tasks and completed_tasks == len(roadmap.tasks) else "ACTIVE"

        history = list(progress.engagement_history or [])
        if created_at_event:
            history.append(f"{datetime.utcnow().isoformat()}::{created_at_event}")
        progress.engagement_history = history[-20:]
        self._db.flush()
        return progress
