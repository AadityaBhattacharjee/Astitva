"""Progress Agent — analyze real user progress from DB records + IBM Granite.

Workflow
--------
authenticated user context
    ↓
DB query: UserProfile + Roadmaps + RoadmapTasks + Progress records + Documents
    ↓
deterministic calculation of progress metrics from real records
    ↓
IBM Granite: summarize situation and recommend next actions
    ↓
structured response with real metrics and AI interpretation

The agent:
- Calculates all metrics deterministically from real DB records.
- Never fabricates completion percentages or milestone counts.
- Uses Granite ONLY for interpretation, summary, and recommendations.
- Returns a "no_data" status when the user has no roadmap or progress data.
- Does NOT write to the database.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

_NO_DATA_MSG = "No progress data found for this user."

_SYSTEM_PROMPT = """\
You are a progress tracking advisor for Astitva, a platform that \
helps marginalised women in India track their journey and stay on course.

Your task is to interpret the user's actual progress data and provide \
an encouraging, honest assessment with concrete next steps.

RULES:
- Base your response ONLY on the progress data provided below.
- Do NOT invent completion percentages, milestone counts, or task statuses.
- All numbers you use must come directly from the data provided.
- If the data shows no progress, say so honestly and recommend starting with \
  the highest-priority pending task.
- If there is no progress data at all, respond with exactly: \
  "No progress data found for this user."

When data is available, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence honest assessment of progress>",
  "progress_summary": {
    "overall_completion_pct": <float 0-100, calculated from completed/total tasks>,
    "completed_tasks": <int>,
    "pending_tasks": <int>,
    "overdue_tasks": <int>,
    "missed_milestones": <int>,
    "completed_milestones": <int>
  },
  "achievements": ["<task or milestone that is completed, from data>", ...],
  "pending_actions": ["<pending or overdue task, from data>", ...],
  "next_recommended_step": "<single most important next step based on the data>",
  "sources": []
}
"""


def _load_progress_context(user_id: int, db: Session) -> dict[str, Any]:
    """Load roadmaps, tasks, progress records and documents for the user."""
    from backend.app.database.models.entities import (
        Document, Progress, Roadmap, RoadmapTask, UserProfile,
    )

    profile_row = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    profile: dict[str, Any] = {}
    if profile_row:
        profile = {
            "full_name": profile_row.full_name,
            "state": profile_row.state,
        }

    doc_rows = db.scalars(select(Document).where(Document.user_id == user_id)).all()
    documents = [{"type": d.document_type, "status": d.status} for d in doc_rows]

    roadmap_rows = db.scalars(select(Roadmap).where(Roadmap.user_id == user_id)).all()
    roadmaps: list[dict[str, Any]] = []
    for rm in roadmap_rows:
        task_rows = db.scalars(
            select(RoadmapTask).where(RoadmapTask.roadmap_id == rm.id)
        ).all()
        progress_rows = db.scalars(
            select(Progress).where(Progress.roadmap_id == rm.id)
        ).all()
        roadmaps.append({
            "title": rm.title,
            "status": rm.status,
            "tasks": [
                {"title": t.title, "status": t.status, "priority": t.priority}
                for t in task_rows
            ],
            "progress_records": [
                {
                    "status": p.status,
                    "completed_milestones": p.completed_milestones,
                    "missed_milestones": p.missed_milestones,
                    "overdue_tasks": p.overdue_tasks,
                    "engagement_history": p.engagement_history,
                }
                for p in progress_rows
            ],
        })

    return {
        "profile": profile,
        "documents": documents,
        "roadmaps": roadmaps,
    }


def _compute_progress_metrics(ctx: dict[str, Any]) -> dict[str, Any]:
    """Compute deterministic progress metrics from real records."""
    total_tasks = 0
    completed_tasks = 0
    pending_tasks = 0
    total_overdue = 0
    total_missed = 0
    total_completed_milestones = 0
    completed_task_titles: list[str] = []
    pending_task_titles: list[str] = []

    for rm in ctx.get("roadmaps", []):
        for t in rm.get("tasks", []):
            total_tasks += 1
            if t["status"] == "COMPLETED":
                completed_tasks += 1
                completed_task_titles.append(t["title"])
            else:
                pending_tasks += 1
                pending_task_titles.append(f"[{t['priority']}] {t['title']}")
        for p in rm.get("progress_records", []):
            total_overdue += p.get("overdue_tasks", 0)
            total_missed += p.get("missed_milestones", 0)
            total_completed_milestones += p.get("completed_milestones", 0)

    completion_pct = (completed_tasks / total_tasks * 100.0) if total_tasks > 0 else 0.0

    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "overdue_tasks": total_overdue,
        "missed_milestones": total_missed,
        "completed_milestones": total_completed_milestones,
        "overall_completion_pct": round(completion_pct, 1),
        "completed_task_titles": completed_task_titles,
        "pending_task_titles": pending_task_titles,
    }


def _build_progress_prompt(query: str, ctx: dict[str, Any], metrics: dict[str, Any]) -> str:
    """Build the user-turn prompt from real progress data."""
    lines: list[str] = [f"PROGRESS QUERY:\n{query}\n"]

    profile = ctx.get("profile", {})
    if profile:
        lines.append("=== USER PROFILE ===")
        for k, v in profile.items():
            if v:
                lines.append(f"  {k}: {v}")
    else:
        lines.append("=== USER PROFILE ===\nNo profile on record.")

    lines.append("\n=== CALCULATED PROGRESS METRICS (from database — do not modify these numbers) ===")
    lines.append(f"  Total tasks: {metrics['total_tasks']}")
    lines.append(f"  Completed tasks: {metrics['completed_tasks']}")
    lines.append(f"  Pending tasks: {metrics['pending_tasks']}")
    lines.append(f"  Overdue tasks: {metrics['overdue_tasks']}")
    lines.append(f"  Missed milestones: {metrics['missed_milestones']}")
    lines.append(f"  Completed milestones: {metrics['completed_milestones']}")
    lines.append(f"  Overall completion: {metrics['overall_completion_pct']}%")

    if metrics["completed_task_titles"]:
        lines.append(f"\n  Completed tasks: {', '.join(metrics['completed_task_titles'])}")
    if metrics["pending_task_titles"]:
        lines.append(f"  Pending/overdue tasks: {', '.join(metrics['pending_task_titles'][:5])}")

    roadmaps = ctx.get("roadmaps", [])
    lines.append("\n=== ROADMAPS ===")
    if roadmaps:
        for rm in roadmaps:
            lines.append(f"  [{rm['status']}] {rm['title']}")
    else:
        lines.append("  No roadmaps on file.")

    documents = ctx.get("documents", [])
    if documents:
        lines.append("\n=== DOCUMENTS ON FILE ===")
        for d in documents:
            lines.append(f"  [{d['status']}] {d['type']}")

    lines.append(
        "\nUsing ONLY the above metrics and data, provide an honest progress assessment "
        "and recommend the most important next step."
    )
    return "\n".join(lines)


def _parse_progress_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM; return safe fallback on failure."""
    text = raw.strip()
    if not text or text == _NO_DATA_MSG:
        return {
            "answer": _NO_DATA_MSG,
            "progress_summary": {},
            "achievements": [],
            "pending_actions": [],
            "next_recommended_step": "",
            "sources": [],
        }
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {
        "answer": text,
        "progress_summary": {},
        "achievements": [],
        "pending_actions": [],
        "next_recommended_step": "",
        "sources": [],
    }


class ProgressAgent(BaseAgent):
    """Progress tracking agent using real DB data + IBM Granite interpretation.

    Calculates all metrics deterministically from Roadmap/RoadmapTask/Progress
    records. Uses Granite only to summarize and recommend next steps. Never
    fabricates numbers or milestone counts.

    Parameters
    ----------
    db:
        Active SQLAlchemy Session.
    llm_provider:
        LLM for interpreting and summarizing real progress data.
    """

    name = "progress"
    responsibilities = (
        "Track milestones",
        "Track completed and pending tasks",
        "Maintain roadmap state",
        "Update user progress",
        "Trigger recommendation updates",
    )

    def __init__(self, db: Session, llm_provider: BaseLLMProvider) -> None:
        self._db = db
        self._llm = llm_provider

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Run the progress agent workflow."""
        # ── 1. Determine user_id ──────────────────────────────────────────
        raw_uid = request.user_id or request.context.get("user_id")
        if raw_uid is None:
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="No user_id provided; cannot load progress data.",
                data={"progress_summary": {}, "achievements": [],
                      "pending_actions": [], "next_recommended_step": ""},
            )

        try:
            user_id = int(raw_uid)
        except (ValueError, TypeError):
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="Invalid user_id.",
                data={"progress_summary": {}, "achievements": [],
                      "pending_actions": [], "next_recommended_step": ""},
            )

        # ── 2. Load and compute ───────────────────────────────────────────
        ctx = _load_progress_context(user_id, self._db)
        metrics = _compute_progress_metrics(ctx)

        has_data = bool(ctx["roadmaps"] or ctx["documents"])

        # ── 3. Build prompt ───────────────────────────────────────────────
        user_prompt = _build_progress_prompt(request.query, ctx, metrics)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse output ───────────────────────────────────────────────
        parsed = _parse_progress_response(raw_response)

        # Always use real calculated metrics for progress_summary, not LLM's version
        real_summary = {
            "overall_completion_pct": metrics["overall_completion_pct"],
            "completed_tasks": metrics["completed_tasks"],
            "pending_tasks": metrics["pending_tasks"],
            "overdue_tasks": metrics["overdue_tasks"],
            "missed_milestones": metrics["missed_milestones"],
            "completed_milestones": metrics["completed_milestones"],
        }

        no_data = not has_data or parsed.get("answer", "") == _NO_DATA_MSG
        return AgentResponse(
            agent_name=self.name,
            status="no_data" if no_data else "ok",
            summary=parsed.get("answer", ""),
            data={
                "progress_summary": real_summary,  # always from real DB data
                "achievements": parsed.get("achievements", metrics["completed_task_titles"]),
                "pending_actions": parsed.get("pending_actions", metrics["pending_task_titles"]),
                "next_recommended_step": parsed.get("next_recommended_step", ""),
                "context_meta": {
                    "has_profile": bool(ctx["profile"]),
                    "roadmaps_count": len(ctx["roadmaps"]),
                    "documents_count": len(ctx["documents"]),
                    "total_tasks": metrics["total_tasks"],
                },
            },
        )
