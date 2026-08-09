"""Planning Agent — personalized action planning using real DB data + IBM Granite.

Workflow
--------
authenticated user context
    ↓
DB query: UserProfile + Roadmaps + RoadmapTasks + Progress + Documents
    ↓
summarize existing plan state (existing tasks, pending/completed)
    ↓
IBM Granite: generate prioritized next actions and recommendations
    ↓
structured plan response

The agent:
- Uses existing roadmap/task data as the ground truth for current planning state.
- Generates AI recommendations for next steps on top of real data.
- Clearly separates existing DB facts from AI-generated recommendations.
- Does NOT write to the database.
- Does NOT pretend recommendations have been saved.
- Returns "no_data" status when the user has no profile or roadmap.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

_NO_DATA_MSG = "Insufficient data to generate a planning recommendation."

_SYSTEM_PROMPT = """\
You are a planning and goal-setting advisor for Astitva, a platform that \
helps marginalised women in India build practical action plans.

Your task is to help the user understand their current plan state and \
suggest concrete next steps.

RULES:
- Base your response ONLY on the roadmap, task, and profile data provided below.
- Do NOT invent completed tasks, milestones, or progress that is not in the data.
- Clearly distinguish existing tasks (from the database) from your AI-generated \
  recommendations.
- These recommendations are NOT automatically saved to the user's account.
- If data is insufficient to make meaningful recommendations, respond with exactly: \
  "Insufficient data to generate a planning recommendation."

When data is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence summary of the planning situation>",
  "existing_plan_summary": {
    "roadmaps_count": <int>,
    "total_tasks": <int>,
    "completed_tasks": <int>,
    "pending_tasks": <int>,
    "active_roadmap_title": "<title of most recent active roadmap or null>"
  },
  "recommended_next_actions": [
    {
      "action": "<specific next step>",
      "priority": "<HIGH / MEDIUM / LOW>",
      "reason": "<why this is important, grounded in the data>"
    }
  ],
  "gaps_identified": ["<gap in the current plan>", ...],
  "disclaimer": "These recommendations are AI-generated suggestions and have not been saved to your account.",
  "sources": []
}
"""


def _load_planning_context(user_id: int, db: Session) -> dict[str, Any]:
    """Load profile, roadmaps, tasks and progress for planning."""
    from backend.app.database.models.entities import (
        Document, Progress, Roadmap, RoadmapTask, UserProfile,
    )

    profile_row = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    profile: dict[str, Any] = {}
    if profile_row:
        profile = {
            "full_name": profile_row.full_name,
            "state": profile_row.state,
            "language": profile_row.language,
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
            "id": rm.id,
            "title": rm.title,
            "status": rm.status,
            "tasks": [
                {"title": t.title, "status": t.status, "priority": t.priority}
                for t in task_rows
            ],
            "progress": [
                {
                    "status": p.status,
                    "completed_milestones": p.completed_milestones,
                    "missed_milestones": p.missed_milestones,
                    "overdue_tasks": p.overdue_tasks,
                }
                for p in progress_rows
            ],
        })

    return {
        "profile": profile,
        "documents": documents,
        "roadmaps": roadmaps,
    }


def _build_planning_prompt(query: str, ctx: dict[str, Any]) -> str:
    """Serialise planning context into a compact prompt."""
    lines: list[str] = [f"PLANNING QUERY:\n{query}\n"]

    profile = ctx.get("profile", {})
    if profile:
        lines.append("=== USER PROFILE ===")
        for k, v in profile.items():
            if v:
                lines.append(f"  {k}: {v}")
    else:
        lines.append("=== USER PROFILE ===\nNo profile on record.")

    documents = ctx.get("documents", [])
    lines.append("\n=== DOCUMENTS ON FILE ===")
    if documents:
        for d in documents:
            lines.append(f"  [{d['status']}] {d['type']}")
    else:
        lines.append("  No documents on file.")

    roadmaps = ctx.get("roadmaps", [])
    lines.append("\n=== ROADMAPS & TASKS ===")
    if roadmaps:
        for rm in roadmaps:
            lines.append(f"  Roadmap: {rm['title']} [{rm['status']}]")
            for t in rm.get("tasks", []):
                lines.append(f"    [{t['status']}|{t['priority']}] {t['title']}")
            for p in rm.get("progress", []):
                lines.append(
                    f"    Progress: completed={p['completed_milestones']}, "
                    f"missed={p['missed_milestones']}, overdue={p['overdue_tasks']}"
                )
    else:
        lines.append("  No roadmaps on record.")

    lines.append(
        "\nBased solely on the above data, generate a planning assessment and "
        "recommended next actions. These recommendations will NOT be saved automatically."
    )
    return "\n".join(lines)


def _parse_planning_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM; return safe fallback on failure."""
    text = raw.strip()
    _disclaimer = (
        "These recommendations are AI-generated suggestions and have not been saved to your account."
    )
    if not text or text == _NO_DATA_MSG:
        return {
            "answer": _NO_DATA_MSG,
            "existing_plan_summary": {},
            "recommended_next_actions": [],
            "gaps_identified": [],
            "disclaimer": _disclaimer,
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
        "existing_plan_summary": {},
        "recommended_next_actions": [],
        "gaps_identified": [],
        "disclaimer": _disclaimer,
        "sources": [],
    }


class PlanningAgent(BaseAgent):
    """Action planning agent using existing DB data + IBM Granite.

    Loads real profile/roadmap/task/progress data and uses Granite to
    generate prioritized next-action recommendations. Does NOT write to
    the database.

    Parameters
    ----------
    db:
        Active SQLAlchemy Session.
    llm_provider:
        LLM for generating grounded planning recommendations.
    """

    name = "planning"
    responsibilities = (
        "Combine outputs from domain agents",
        "Prioritize actions",
        "Generate next-best actions",
        "Create personalized roadmap",
        "Adapt roadmap as user context changes",
    )

    def __init__(self, db: Session, llm_provider: BaseLLMProvider) -> None:
        self._db = db
        self._llm = llm_provider

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Run the planning agent workflow."""
        # ── 1. Determine user_id ──────────────────────────────────────────
        raw_uid = request.user_id or request.context.get("user_id")
        if raw_uid is None:
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="No user_id provided; cannot load planning context.",
                data={"existing_plan_summary": {}, "recommended_next_actions": [],
                      "gaps_identified": [], "disclaimer": "No user context."},
            )

        try:
            user_id = int(raw_uid)
        except (ValueError, TypeError):
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="Invalid user_id.",
                data={"existing_plan_summary": {}, "recommended_next_actions": [],
                      "gaps_identified": [], "disclaimer": "Invalid user context."},
            )

        # ── 2. Load context ───────────────────────────────────────────────
        ctx = _load_planning_context(user_id, self._db)

        has_data = bool(ctx["profile"] or ctx["documents"] or ctx["roadmaps"])

        # ── 3. Build prompt ───────────────────────────────────────────────
        user_prompt = _build_planning_prompt(request.query, ctx)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse output ───────────────────────────────────────────────
        parsed = _parse_planning_response(raw_response)

        # Compute quick plan summary from real data
        total_tasks = sum(len(rm["tasks"]) for rm in ctx["roadmaps"])
        completed_tasks = sum(
            1 for rm in ctx["roadmaps"]
            for t in rm["tasks"] if t["status"] == "COMPLETED"
        )
        pending_tasks = total_tasks - completed_tasks
        active_roadmaps = [rm for rm in ctx["roadmaps"] if rm["status"] == "ACTIVE"]
        active_title = active_roadmaps[0]["title"] if active_roadmaps else None

        plan_summary = parsed.get("existing_plan_summary") or {
            "roadmaps_count": len(ctx["roadmaps"]),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "active_roadmap_title": active_title,
        }

        no_data = not has_data or parsed.get("answer", "") == _NO_DATA_MSG
        return AgentResponse(
            agent_name=self.name,
            status="no_data" if no_data else "ok",
            summary=parsed.get("answer", ""),
            data={
                "existing_plan_summary": plan_summary,
                "recommended_next_actions": parsed.get("recommended_next_actions", []),
                "gaps_identified": parsed.get("gaps_identified", []),
                "disclaimer": parsed.get(
                    "disclaimer",
                    "These recommendations are AI-generated suggestions and have not been saved to your account.",
                ),
                "context_meta": {
                    "has_profile": bool(ctx["profile"]),
                    "documents_count": len(ctx["documents"]),
                    "roadmaps_count": len(ctx["roadmaps"]),
                },
            },
        )
