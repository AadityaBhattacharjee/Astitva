"""Mentor Matching Agent — profile-based mentor guidance using Granite.

Architecture note
-----------------
The Astitva database does not yet have a dedicated Mentor ORM table.
The schemas in database/schemas/mentors.py define the *future* shape.
Rather than fabricating a mentor database that does not exist, this agent:

1. Loads the authenticated user's own profile (language, state, goals).
2. Asks Granite to suggest the *types* of mentor profiles most suited to the
   user — e.g. "a woman in Maharashtra with experience in microfinance" —
   based only on what the profile data actually says.
3. Returns structured mentor-profile criteria plus actionable next steps
   (e.g. "contact your local SHG", "request a mentor via the district DWCD
   office") sourced from verified guidance where available via RAG.

If the user has no profile data the agent returns an explicit no-data
response and does not speculate.

The agent NEVER:
- invents real mentor names, contact details, or organisations.
- fabricates mentor availability or qualifications.
- pretends a mentor match has been made when no database record exists.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

_NO_DATA_MSG = (
    "Insufficient profile information to suggest mentor criteria. "
    "Please complete your profile first."
)

_SYSTEM_PROMPT = """\
You are a mentor-matching advisor for Astitva, a platform that supports \
marginalised women in India. Your role is to help users understand what \
kind of mentor would best support their goals.

IMPORTANT CONSTRAINTS:
- You do NOT have access to a real mentor database. Do NOT invent mentor names, \
  contact numbers, organisations, or availability.
- Base your response ONLY on the user profile data provided below.
- If the profile data is insufficient, say so clearly.
- Recommend the *types* of mentors and *channels* through which the user can \
  find mentorship (e.g. local SHGs, DWCD offices, NGOs), not specific individuals.
- Always remind the user that actual matching depends on real mentor availability \
  through official channels.

When data is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence summary of mentorship guidance>",
  "ideal_mentor_profile": {
    "experience_areas": ["<area relevant to user's needs>", ...],
    "language_match": "<preferred language based on user profile>",
    "location_relevance": "<state or region guidance>",
    "availability_note": "<general guidance on finding available mentors>"
  },
  "recommended_channels": ["<channel to find mentors, e.g. SHG, DWCD, NGO>", ...],
  "next_actions": ["<concrete step the user can take>", ...],
  "disclaimer": "Actual mentor matching requires registration and consent. No specific mentor has been identified.",
  "sources": []
}

If data is insufficient, respond with exactly: \
"Insufficient profile information to suggest mentor criteria. Please complete your profile first."
"""


def _load_user_profile(user_id: int, db: Session) -> dict[str, Any]:
    """Load user profile from DB."""
    from backend.app.database.models.entities import UserProfile, Document, Roadmap

    profile_row = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    profile: dict[str, Any] = {}
    if profile_row:
        profile = {
            "full_name": profile_row.full_name,
            "state": profile_row.state,
            "language": profile_row.language,
        }

    # Gather document types as a proxy for user's current situation
    doc_rows = db.scalars(select(Document).where(Document.user_id == user_id)).all()
    doc_types = [d.document_type for d in doc_rows]

    # Gather roadmap titles as a proxy for stated goals
    roadmap_rows = db.scalars(select(Roadmap).where(Roadmap.user_id == user_id)).all()
    roadmap_titles = [r.title for r in roadmap_rows]

    return {
        "profile": profile,
        "document_types": doc_types,
        "roadmap_titles": roadmap_titles,
    }


def _build_mentor_prompt(query: str, user_data: dict[str, Any]) -> str:
    """Build user-turn prompt from profile data."""
    lines: list[str] = [f"USER QUERY:\n{query}\n"]

    profile = user_data.get("profile", {})
    if profile:
        lines.append("=== USER PROFILE ===")
        if profile.get("full_name"):
            lines.append(f"  Name: {profile['full_name']}")
        if profile.get("state"):
            lines.append(f"  State: {profile['state']}")
        if profile.get("language"):
            lines.append(f"  Language: {profile['language']}")
    else:
        lines.append("=== USER PROFILE ===\nNo profile on record.")

    doc_types = user_data.get("document_types", [])
    if doc_types:
        lines.append(f"\n=== DOCUMENTS ON FILE ===\n  {', '.join(doc_types)}")

    roadmap_titles = user_data.get("roadmap_titles", [])
    if roadmap_titles:
        lines.append(f"\n=== STATED GOALS (roadmaps) ===")
        for t in roadmap_titles:
            lines.append(f"  - {t}")

    lines.append(
        "\nBased solely on the above profile, suggest the ideal mentor criteria "
        "and channels through which the user can find mentorship. "
        "Do NOT invent real mentors or organisations."
    )
    return "\n".join(lines)


def _parse_mentor_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM; return safe fallback on failure."""
    text = raw.strip()
    _disclaimer = (
        "Actual mentor matching requires registration and consent. "
        "No specific mentor has been identified."
    )
    if not text or text == _NO_DATA_MSG:
        return {
            "answer": _NO_DATA_MSG,
            "ideal_mentor_profile": {},
            "recommended_channels": [],
            "next_actions": [],
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
        "ideal_mentor_profile": {},
        "recommended_channels": [],
        "next_actions": [],
        "disclaimer": _disclaimer,
        "sources": [],
    }


class MentorMatchingAgent(BaseAgent):
    """Profile-based mentor guidance agent using IBM Granite.

    IMPORTANT: This agent does NOT have access to a real mentor database.
    It generates ideal-mentor criteria and official channels based on the
    user's profile and roadmap data. Actual matching is out-of-scope until
    a Mentor ORM model is introduced.

    Parameters
    ----------
    db:
        Active SQLAlchemy Session.
    llm_provider:
        LLM for generating grounded mentor guidance.
    """

    name = "mentor_matching"
    responsibilities = (
        "Identify successful users who opt in",
        "Create mentor profiles",
        "Match mentors with users",
        "Match based on relevant experience or domain",
        "Consider language, location, and availability",
        "Preserve privacy and consent",
    )

    def __init__(self, db: Session, llm_provider: BaseLLMProvider) -> None:
        self._db = db
        self._llm = llm_provider

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Run the mentor matching agent workflow."""
        # ── 1. Determine user_id ──────────────────────────────────────────
        raw_uid = request.user_id or request.context.get("user_id")
        if raw_uid is None:
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="No user_id provided; cannot load profile for mentor matching.",
                data={"ideal_mentor_profile": {}, "recommended_channels": [],
                      "next_actions": [], "disclaimer": "No user context.", "no_mentor_db": True},
            )

        try:
            user_id = int(raw_uid)
        except (ValueError, TypeError):
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="Invalid user_id.",
                data={"ideal_mentor_profile": {}, "recommended_channels": [],
                      "next_actions": [], "disclaimer": "Invalid user context.", "no_mentor_db": True},
            )

        # ── 2. Load user profile data ─────────────────────────────────────
        user_data = _load_user_profile(user_id, self._db)

        has_profile = bool(user_data.get("profile"))

        # ── 3. Build prompt ───────────────────────────────────────────────
        user_prompt = _build_mentor_prompt(request.query, user_data)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse output ───────────────────────────────────────────────
        parsed = _parse_mentor_response(raw_response)

        no_data = not has_profile or parsed.get("answer", "") == _NO_DATA_MSG
        return AgentResponse(
            agent_name=self.name,
            status="no_data" if no_data else "ok",
            summary=parsed.get("answer", ""),
            data={
                "ideal_mentor_profile": parsed.get("ideal_mentor_profile", {}),
                "recommended_channels": parsed.get("recommended_channels", []),
                "next_actions": parsed.get("next_actions", []),
                "disclaimer": parsed.get(
                    "disclaimer",
                    "Actual mentor matching requires registration and consent. "
                    "No specific mentor has been identified.",
                ),
                "no_mentor_db": True,  # transparent: no ORM mentor table yet
                "profile_used": {
                    "has_profile": has_profile,
                    "documents_count": len(user_data.get("document_types", [])),
                    "roadmaps_count": len(user_data.get("roadmap_titles", [])),
                },
            },
        )
