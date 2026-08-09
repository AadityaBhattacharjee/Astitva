"""Employment Agent — career, job, and skills guidance using RAG + IBM Granite.

Workflow
--------
user query
    ↓
ChromaDB similarity search for verified employment/skills information
    ↓
Scheme-DB filter for employment-related schemes (category = "employment")
    ↓
grounded prompt (evidence only — model must not invent job listings or salaries)
    ↓
IBM Granite via local MLX
    ↓
structured response with guidance, skills gaps, next actions, and sources

The LLM is explicitly instructed:
- Never invent job listings, salary figures, or employer names.
- Never fabricate training programs or eligibility criteria.
- Report clearly when evidence is insufficient.
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

# Sentinel returned when evidence is insufficient
_INSUFFICIENT = "I could not find sufficient verified information about employment opportunities."

_SYSTEM_PROMPT = """\
You are an employment and career guidance advisor for Astitva, a platform that \
helps marginalised women in India find work and rebuild their careers.

Answer the user's question based ONLY on the scheme records and document excerpts \
provided below. Do NOT invent job listings, employer names, salary figures, or \
training programme details that are not in the provided evidence.

If the provided evidence does not contain enough information to answer the question, \
respond with exactly: \
"I could not find sufficient verified information about employment opportunities."

When evidence is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence direct guidance>",
  "job_options": [
    {
      "title": "<role or scheme>",
      "description": "<brief description from evidence>",
      "eligibility": "<eligibility from evidence>",
      "how_to_apply": "<application steps from evidence>"
    }
  ],
  "skills_guidance": ["<skill or training suggestion from evidence>", ...],
  "next_actions": ["<concrete step>", ...],
  "sources": ["<source label>", ...]
}
"""


def _build_employment_evidence(evidence: dict[str, Any]) -> str:
    """Serialise hybrid-retrieval evidence for the employment prompt."""
    lines: list[str] = []

    schemes: list[dict[str, Any]] = evidence.get("schemes", [])
    documents: list[dict[str, Any]] = evidence.get("documents", [])

    if schemes:
        lines.append("=== EMPLOYMENT-RELATED SCHEMES (from database) ===")
        for s in schemes:
            lines.append(f"\nScheme: {s.get('name', 'Unknown')}")
            if s.get("category"):
                lines.append(f"  Category: {s['category']}")
            if s.get("state"):
                lines.append(f"  State: {s['state']}")
            if s.get("target_group"):
                lines.append(f"  Target group: {s['target_group']}")
            if s.get("benefits"):
                lines.append(f"  Benefits: {', '.join(s['benefits'])}")
            if s.get("eligibility"):
                lines.append(f"  Eligibility: {s['eligibility']}")
            if s.get("application_process"):
                lines.append(f"  How to apply: {s['application_process']}")
            lines.append(f"  Source: {s.get('source', 'structured_db')}")
    else:
        lines.append("=== EMPLOYMENT-RELATED SCHEMES ===\nNo matching employment schemes found in database.")

    if documents:
        lines.append("\n=== RELEVANT EMPLOYMENT DOCUMENT EXCERPTS (from knowledge base) ===")
        for i, d in enumerate(documents[:6], 1):
            meta = d.get("metadata") or {}
            src = meta.get("source") or d.get("source_id") or f"chunk-{i}"
            lines.append(f"\n[Excerpt {i} | source: {src}]")
            lines.append(d.get("content", ""))
    else:
        lines.append("\n=== RELEVANT DOCUMENT EXCERPTS ===\nNo relevant document excerpts found.")

    return "\n".join(lines)


def _build_employment_prompt(query: str, profile: dict[str, Any], evidence_block: str) -> str:
    """Build the user-turn prompt for the employment agent."""
    profile_lines: list[str] = []
    if profile.get("state"):
        profile_lines.append(f"State: {profile['state']}")
    if profile.get("age") is not None:
        profile_lines.append(f"Age: {profile['age']}")
    if profile.get("target_group"):
        profile_lines.append(f"Target group: {profile['target_group']}")

    profile_section = "\n".join(profile_lines) if profile_lines else "No profile provided."

    return (
        f"USER QUERY:\n{query}\n\n"
        f"USER PROFILE:\n{profile_section}\n\n"
        f"{evidence_block}\n\n"
        "Based solely on the above evidence, provide your employment guidance."
    )


def _parse_employment_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output; return a safe fallback dict on failure."""
    text = raw.strip()
    if not text or text == _INSUFFICIENT:
        return {
            "answer": _INSUFFICIENT,
            "job_options": [],
            "skills_guidance": [],
            "next_actions": [],
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
        "job_options": [],
        "skills_guidance": [],
        "next_actions": [],
        "sources": [],
    }


class EmploymentAgent(BaseAgent):
    """Employment and career guidance agent using Hybrid RAG + IBM Granite.

    Combines employment-related scheme records (PostgreSQL) with ChromaDB
    document retrieval to produce grounded career guidance. Never invents
    job listings, salaries, or employer names.

    Parameters
    ----------
    hybrid_retriever:
        Pre-configured HybridRetriever (structured + vector arms).
    llm_provider:
        A BaseLLMProvider implementation.
    vector_limit:
        Number of vector chunks to retrieve per query.
    """

    name = "employment"
    responsibilities = (
        "Job opportunities",
        "Skill development",
        "Vocational training",
        "Career rebuilding",
        "Employment RAG",
    )

    def __init__(
        self,
        hybrid_retriever: Any,
        llm_provider: BaseLLMProvider,
        vector_limit: int = 5,
    ) -> None:
        self._retriever = hybrid_retriever
        self._llm = llm_provider
        self._vector_limit = vector_limit

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Run the employment agent workflow."""
        # ── 1. Extract profile filters ────────────────────────────────────
        ctx = request.context
        filters: dict[str, Any] = {"active_status": True}
        profile: dict[str, Any] = {}
        for key in ("state", "target_group", "age"):
            if ctx.get(key) is not None:
                filters[key] = ctx[key]
                profile[key] = ctx[key]
        # Restrict structured retrieval to employment category
        filters["category"] = ctx.get("category", "employment")

        # ── 2. Retrieve evidence ──────────────────────────────────────────
        evidence = self._retriever.search(
            query=request.query,
            filters=filters,
            vector_limit=self._vector_limit,
        )

        # ── 3. Build grounded prompt ──────────────────────────────────────
        evidence_block = _build_employment_evidence(evidence)
        user_prompt = _build_employment_prompt(request.query, profile, evidence_block)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse and structure output ─────────────────────────────────
        parsed = _parse_employment_response(raw_response)

        retrieval_sources: list[str] = evidence.get("sources", [])
        llm_sources: list[str] = parsed.get("sources") or []
        merged_sources = list(dict.fromkeys(llm_sources + retrieval_sources))

        insufficient = parsed.get("answer", "") == _INSUFFICIENT
        return AgentResponse(
            agent_name=self.name,
            status="insufficient_evidence" if insufficient else "ok",
            summary=parsed.get("answer", ""),
            data={
                "job_options": parsed.get("job_options", []),
                "skills_guidance": parsed.get("skills_guidance", []),
                "next_actions": parsed.get("next_actions", []),
                "evidence": {
                    "schemes_count": len(evidence.get("schemes", [])),
                    "documents_count": len(evidence.get("documents", [])),
                    "insufficient_evidence": insufficient,
                },
            },
            sources=merged_sources,
        )
