"""Risk Prediction Agent — rule-based risk assessment + IBM Granite interpretation.

Workflow
--------
authenticated user context
    ↓
DB query: UserProfile + Documents + Roadmaps + RoadmapTasks + Progress
    ↓
deterministic rule-based risk flag computation from real records
    ↓
populate RiskFeatures (from existing risk schema)
    ↓
IBM Granite: interpret risk situation and recommend interventions
    ↓
structured response with severity-tagged risk flags and recommendations

Design principles
-----------------
- Risk flags are derived ONLY from real observed data (missing docs, overdue
  tasks, missed milestones, no profile, etc.).
- Granite interprets and explains risk — it does NOT determine risk levels.
  Risk levels are computed deterministically by the rule engine.
- Speculative risk is clearly labelled as "inference" vs "observed".
- If there is insufficient data, an explicit insufficient-data response is returned.
- The existing RiskFeatures / RiskLevel / RiskPredictionSchema from
  database/schemas/risk.py are used directly.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.database.schemas.risk import RiskFeatures, RiskLevel
from backend.app.services.llm_provider import BaseLLMProvider

_NO_DATA_MSG = "Insufficient case data to perform a meaningful risk assessment."

_SYSTEM_PROMPT = """\
You are a risk assessment advisor for Astitva, a platform that helps \
marginalised women in India. Your role is to help case workers understand \
the risk level of a user's case and recommend appropriate interventions.

RULES:
- Base your response ONLY on the risk data and case information provided below.
- Do NOT invent missing documents, deadlines, eligibility, or case history.
- Clearly distinguish "observed" risk factors (from actual data) from \
  "inferred" risk factors (your interpretations).
- Do NOT present speculative risks as confirmed facts.
- Use the pre-calculated risk level (LOW / MEDIUM / HIGH) provided — do not \
  change it.
- If data is insufficient, respond with exactly: \
  "Insufficient case data to perform a meaningful risk assessment."

When data is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence honest risk summary>",
  "risk_interpretation": "<explanation of why the risk level was determined>",
  "observed_risk_factors": ["<factor directly visible in the data>", ...],
  "inferred_risk_factors": ["<factor inferred from patterns — label as inference>", ...],
  "recommended_interventions": ["<specific action for a case worker>", ...],
  "sources": []
}
"""

# ---------------------------------------------------------------------------
# Rule-based risk engine
# ---------------------------------------------------------------------------

def _compute_risk_flags(ctx: dict[str, Any]) -> tuple[list[str], RiskLevel, RiskFeatures]:
    """Derive risk flags and level from real observed data.

    Returns (flags, level, features).
    Flags are always sourced from actual data — never speculative.
    """
    flags: list[str] = []
    score = 0  # additive integer score — thresholds: 0-1=LOW, 2-3=MEDIUM, 4+=HIGH

    profile = ctx.get("profile", {})
    documents = ctx.get("documents", [])
    roadmaps = ctx.get("roadmaps", [])

    # ── Profile gaps ──────────────────────────────────────────────────────
    if not profile:
        flags.append("[OBSERVED] No user profile on record — case cannot be fully assessed")
        score += 1

    # ── Document gaps ─────────────────────────────────────────────────────
    missing_docs = [d for d in documents if d.get("status") == "MISSING"]
    if missing_docs:
        types = ", ".join(d["type"] for d in missing_docs[:3])
        flags.append(f"[OBSERVED] {len(missing_docs)} missing document(s): {types}")
        score += len(missing_docs)

    doc_completion = len([d for d in documents if d.get("status") == "VERIFIED"]) / max(len(documents), 1)

    # ── Roadmap / task gaps ───────────────────────────────────────────────
    total_overdue = 0
    total_missed = 0
    total_tasks = 0
    completed_tasks = 0

    for rm in roadmaps:
        total_tasks += len(rm.get("tasks", []))
        completed_tasks += sum(1 for t in rm.get("tasks", []) if t["status"] == "COMPLETED")
        for p in rm.get("progress_records", []):
            total_overdue += p.get("overdue_tasks", 0)
            total_missed += p.get("missed_milestones", 0)

    if total_overdue > 0:
        flags.append(f"[OBSERVED] {total_overdue} overdue task(s) across roadmaps")
        score += total_overdue

    if total_missed > 0:
        flags.append(f"[OBSERVED] {total_missed} missed milestone(s)")
        score += total_missed

    if total_tasks > 0 and completed_tasks == 0:
        flags.append("[OBSERVED] No tasks completed — engagement not started")
        score += 1

    if not roadmaps:
        flags.append("[OBSERVED] No roadmap on record — goal planning has not begun")
        score += 1

    # ── Determine level ───────────────────────────────────────────────────
    if score >= 4:
        level = RiskLevel.HIGH
    elif score >= 2:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    # ── Build RiskFeatures from existing schema ───────────────────────────
    features = RiskFeatures(
        missed_milestones=total_missed,
        completed_milestones=sum(
            p.get("completed_milestones", 0)
            for rm in roadmaps for p in rm.get("progress_records", [])
        ),
        overdue_tasks=total_overdue,
        document_completion=round(doc_completion, 2),
        engagement_progress_history=[
            entry
            for rm in roadmaps
            for p in rm.get("progress_records", [])
            for entry in p.get("engagement_history", [])
        ][:10],
    )

    return flags, level, features


def _load_risk_context(user_id: int, db: Session) -> dict[str, Any]:
    """Load all relevant data for risk assessment."""
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
    documents = [
        {"type": d.document_type, "status": d.status, "notes": d.notes}
        for d in doc_rows
    ]

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


def _build_risk_prompt(
    query: str,
    ctx: dict[str, Any],
    flags: list[str],
    level: RiskLevel,
    features: RiskFeatures,
) -> str:
    """Build prompt with pre-computed risk flags and features."""
    lines: list[str] = [f"RISK ASSESSMENT QUERY:\n{query}\n"]

    profile = ctx.get("profile", {})
    if profile:
        lines.append("=== USER PROFILE ===")
        for k, v in profile.items():
            if v:
                lines.append(f"  {k}: {v}")
    else:
        lines.append("=== USER PROFILE ===\nNo profile on record.")

    lines.append(f"\n=== PRE-CALCULATED RISK LEVEL: {level.value} ===")
    lines.append("(Do not change this risk level. It was calculated deterministically.)")

    lines.append("\n=== OBSERVED RISK FLAGS (from real data) ===")
    if flags:
        for f in flags:
            lines.append(f"  {f}")
    else:
        lines.append("  No risk flags observed in the available data.")

    lines.append("\n=== RISK FEATURES (calculated) ===")
    lines.append(f"  Missed milestones: {features.missed_milestones}")
    lines.append(f"  Completed milestones: {features.completed_milestones}")
    lines.append(f"  Overdue tasks: {features.overdue_tasks}")
    lines.append(f"  Document completion: {features.document_completion * 100:.0f}%")

    roadmaps = ctx.get("roadmaps", [])
    if roadmaps:
        lines.append("\n=== ROADMAPS ===")
        for rm in roadmaps:
            lines.append(f"  [{rm['status']}] {rm['title']}")
            for t in rm.get("tasks", [])[:5]:
                lines.append(f"    [{t['status']}|{t['priority']}] {t['title']}")

    lines.append(
        "\nBased solely on the above data and pre-calculated risk level, provide your "
        "risk interpretation. Clearly label observed vs inferred factors."
    )
    return "\n".join(lines)


def _parse_risk_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM; return safe fallback on failure."""
    text = raw.strip()
    if not text or text == _NO_DATA_MSG:
        return {
            "answer": _NO_DATA_MSG,
            "risk_interpretation": "",
            "observed_risk_factors": [],
            "inferred_risk_factors": [],
            "recommended_interventions": [],
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
        "risk_interpretation": "",
        "observed_risk_factors": [],
        "inferred_risk_factors": [],
        "recommended_interventions": [],
        "sources": [],
    }


class RiskPredictionAgent(BaseAgent):
    """Rule-based risk assessment agent with IBM Granite interpretation.

    Risk flags and levels are calculated deterministically from real DB data.
    Granite is used only for explanation and intervention recommendations.
    Never speculates beyond observed facts.

    Parameters
    ----------
    db:
        Active SQLAlchemy Session.
    llm_provider:
        LLM for interpreting pre-computed risk flags.
    """

    name = "risk_prediction"
    responsibilities = (
        "Analyze progress and user-state features",
        "Detect missed milestones",
        "Predict low, medium, or high intervention risk",
        "Explain risk factors",
        "Recommend case-worker intervention",
    )

    def __init__(self, db: Session, llm_provider: BaseLLMProvider) -> None:
        self._db = db
        self._llm = llm_provider

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Run the risk prediction agent workflow."""
        # ── 1. Determine user_id ──────────────────────────────────────────
        raw_uid = request.user_id or request.context.get("user_id")
        if raw_uid is None:
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="No user_id provided; cannot perform risk assessment.",
                data={"risk_level": "UNKNOWN", "risk_flags": [],
                      "observed_risk_factors": [], "inferred_risk_factors": [],
                      "recommended_interventions": []},
            )

        try:
            user_id = int(raw_uid)
        except (ValueError, TypeError):
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="Invalid user_id.",
                data={"risk_level": "UNKNOWN", "risk_flags": [],
                      "observed_risk_factors": [], "inferred_risk_factors": [],
                      "recommended_interventions": []},
            )

        # ── 2. Load context ───────────────────────────────────────────────
        ctx = _load_risk_context(user_id, self._db)

        has_data = bool(ctx["profile"] or ctx["documents"] or ctx["roadmaps"])

        # ── 3. Compute risk deterministically ─────────────────────────────
        flags, level, features = _compute_risk_flags(ctx)

        # ── 4. Build prompt ───────────────────────────────────────────────
        user_prompt = _build_risk_prompt(request.query, ctx, flags, level, features)

        # ── 5. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 6. Parse output ───────────────────────────────────────────────
        parsed = _parse_risk_response(raw_response)

        no_data = not has_data or parsed.get("answer", "") == _NO_DATA_MSG
        return AgentResponse(
            agent_name=self.name,
            status="no_data" if no_data else "ok",
            summary=parsed.get("answer", ""),
            data={
                "risk_level": level.value,       # always from deterministic engine
                "risk_score": float(           # normalised 0-1 proxy
                    min(features.missed_milestones + features.overdue_tasks, 10) / 10
                ),
                "risk_flags": flags,            # observed facts only
                "risk_interpretation": parsed.get("risk_interpretation", ""),
                "observed_risk_factors": parsed.get("observed_risk_factors", flags),
                "inferred_risk_factors": parsed.get("inferred_risk_factors", []),
                "recommended_interventions": parsed.get("recommended_interventions", []),
                "risk_features": {
                    "missed_milestones": features.missed_milestones,
                    "completed_milestones": features.completed_milestones,
                    "overdue_tasks": features.overdue_tasks,
                    "document_completion": features.document_completion,
                },
                "context_meta": {
                    "has_profile": bool(ctx["profile"]),
                    "documents_count": len(ctx["documents"]),
                    "roadmaps_count": len(ctx["roadmaps"]),
                },
            },
        )
