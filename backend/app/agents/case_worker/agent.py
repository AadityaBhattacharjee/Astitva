"""Case Worker Agent — structured case-management assistance.

Workflow
--------
authenticated user context
    ↓
DB query: User profile + Documents + Roadmaps + Progress
    ↓
grounded summary of current case status
    ↓
IBM Granite: prioritised action plan based ONLY on real DB data
    ↓
structured case response with status, actions, and gaps

The agent NEVER invents records, legal facts, or government entitlements.
If data is unavailable it reports that clearly instead of guessing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

_NO_DATA_MSG = "Insufficient case data available to provide recommendations."

_SYSTEM_PROMPT = """\
You are a case management assistant for Astitva, a platform that supports \
marginalised women in India. Your role is to help case workers understand \
the current status of a user's case and suggest concrete next steps.

Base your response ONLY on the case data provided below. Do NOT invent any \
records, entitlements, legal facts, or scheme names that are not present in \
the provided data.

If the data is insufficient to make meaningful recommendations, respond with \
exactly: "Insufficient case data available to provide recommendations."

When data is sufficient, respond in the following JSON format (no markdown fences):
{
  "case_summary": "<2–3 sentence overview of the user's current situation>",
  "priority_actions": [
    {
      "action": "<specific next step>",
      "reason": "<why this is important based on the data>"
    }
  ],
  "document_gaps": ["<missing document type>", ...],
  "roadmap_status": "<brief assessment of roadmap progress or 'No roadmap found'>",
  "risk_flags": ["<any concern flagged by the data>", ...]
}
"""


def _build_case_context(
    user_id: int,
    db: Session,
) -> dict[str, Any]:
    """Query DB for user profile, documents, roadmaps, and progress."""
    from sqlalchemy import select
    from backend.app.database.models.entities import (
        Document,
        Progress,
        Roadmap,
        RoadmapTask,
        UserProfile,
    )

    # User profile
    profile_row = db.scalar(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile: dict[str, Any] = {}
    if profile_row:
        profile = {
            "full_name": profile_row.full_name,
            "state": profile_row.state,
            "language": profile_row.language,
        }

    # Documents
    doc_rows = db.scalars(
        select(Document).where(Document.user_id == user_id)
    ).all()
    documents = [
        {
            "type": d.document_type,
            "status": d.status,
            "file_name": d.file_name,
            "notes": d.notes,
        }
        for d in doc_rows
    ]

    # Roadmaps
    roadmap_rows = db.scalars(
        select(Roadmap).where(Roadmap.user_id == user_id)
    ).all()
    roadmaps: list[dict[str, Any]] = []
    for rm in roadmap_rows:
        task_rows = db.scalars(
            select(RoadmapTask).where(RoadmapTask.roadmap_id == rm.id)
        ).all()
        progress_rows = db.scalars(
            select(Progress).where(Progress.roadmap_id == rm.id)
        ).all()
        roadmaps.append(
            {
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
            }
        )

    return {
        "profile": profile,
        "documents": documents,
        "roadmaps": roadmaps,
    }


def _build_case_prompt(query: str, case_data: dict[str, Any]) -> str:
    """Serialise case data into a compact prompt block."""
    import json

    lines: list[str] = [f"CASE WORKER QUERY:\n{query}\n"]

    profile = case_data.get("profile", {})
    if profile:
        lines.append("=== USER PROFILE ===")
        for k, v in profile.items():
            if v:
                lines.append(f"  {k}: {v}")
    else:
        lines.append("=== USER PROFILE ===\nNo profile on record.")

    documents = case_data.get("documents", [])
    lines.append("\n=== DOCUMENTS ON FILE ===")
    if documents:
        for d in documents:
            flag = " ⚠ MISSING" if d["status"] == "MISSING" else ""
            lines.append(f"  [{d['status']}]{flag} {d['type']}"
                         + (f" — {d['notes']}" if d.get("notes") else ""))
    else:
        lines.append("  No documents on file.")

    roadmaps = case_data.get("roadmaps", [])
    lines.append("\n=== ROADMAPS & PROGRESS ===")
    if roadmaps:
        for rm in roadmaps:
            lines.append(f"  Roadmap: {rm['title']} [{rm['status']}]")
            for t in rm.get("tasks", []):
                lines.append(f"    Task [{t['status']}|{t['priority']}]: {t['title']}")
            for p in rm.get("progress", []):
                lines.append(
                    f"    Progress: completed={p['completed_milestones']}, "
                    f"missed={p['missed_milestones']}, overdue={p['overdue_tasks']}"
                )
    else:
        lines.append("  No roadmaps found.")

    lines.append("\nBased solely on the above case data, provide your assessment.")
    return "\n".join(lines)


def _parse_case_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM; return safe fallback on failure."""
    import json

    text = raw.strip()
    if not text or text == _NO_DATA_MSG:
        return {
            "case_summary": _NO_DATA_MSG,
            "priority_actions": [],
            "document_gaps": [],
            "roadmap_status": "No roadmap found",
            "risk_flags": [],
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
        "case_summary": text,
        "priority_actions": [],
        "document_gaps": [],
        "roadmap_status": "Unknown",
        "risk_flags": [],
    }


class CaseWorkerAgent(BaseAgent):
    """Case management agent — summarises case data and recommends next steps.

    Parameters
    ----------
    db:
        Active SQLAlchemy Session used to load user/case records.
    llm_provider:
        LLM for generating grounded case assessments.
    """

    name = "case_worker"
    responsibilities = (
        "Identify high-risk cases",
        "Prioritize cases",
        "Provide case summaries",
        "Recommend interventions",
        "Provide case-worker dashboard data",
    )

    def __init__(self, db: Session, llm_provider: BaseLLMProvider) -> None:
        self._db = db
        self._llm = llm_provider

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Run the case worker agent workflow."""
        # ── 1. Determine which user's case to load ────────────────────────
        # user_id comes from the authenticated request context
        raw_uid = request.user_id or request.context.get("user_id")
        if raw_uid is None:
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="No user_id provided; cannot load case data.",
                data={"case_summary": _NO_DATA_MSG, "priority_actions": [],
                      "document_gaps": [], "roadmap_status": "Unknown",
                      "risk_flags": []},
            )

        try:
            user_id = int(raw_uid)
        except (ValueError, TypeError):
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="Invalid user_id.",
                data={"case_summary": _NO_DATA_MSG, "priority_actions": [],
                      "document_gaps": [], "roadmap_status": "Unknown",
                      "risk_flags": []},
            )

        # ── 2. Load case data from DB ─────────────────────────────────────
        case_data = _build_case_context(user_id, self._db)

        has_data = (
            case_data["profile"]
            or case_data["documents"]
            or case_data["roadmaps"]
        )

        # ── 3. Build grounded prompt ──────────────────────────────────────
        user_prompt = _build_case_prompt(request.query, case_data)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse and structure output ─────────────────────────────────
        parsed = _parse_case_response(raw_response)

        no_data = parsed.get("case_summary", "") == _NO_DATA_MSG
        return AgentResponse(
            agent_name=self.name,
            status="no_data" if (no_data or not has_data) else "ok",
            summary=parsed.get("case_summary", ""),
            data={
                "priority_actions": parsed.get("priority_actions", []),
                "document_gaps": parsed.get("document_gaps", []),
                "roadmap_status": parsed.get("roadmap_status", "No roadmap found"),
                "risk_flags": parsed.get("risk_flags", []),
                "case_meta": {
                    "documents_on_file": len(case_data["documents"]),
                    "roadmaps_count": len(case_data["roadmaps"]),
                    "has_profile": bool(case_data["profile"]),
                },
            },
        )
