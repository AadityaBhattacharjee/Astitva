"""Legal Agent — legal information and guidance using RAG + IBM Granite.

Workflow
--------
user query
    ↓
ChromaDB similarity search for verified legal information
    ↓
Scheme-DB filter for legal-aid-related schemes (category = "legal")
    ↓
grounded prompt (evidence only — model must not claim to be a lawyer or fabricate law)
    ↓
IBM Granite via local MLX
    ↓
structured response with guidance, relevant legal information, next steps, and sources

The LLM is explicitly instructed:
- NEVER claim to be a lawyer or provide legal advice.
- Never fabricate laws, sections, case procedures, or legal facts.
- Clearly state when evidence is insufficient.
- Always recommend consulting a qualified legal professional.
- Provide only general informational guidance based on retrieved evidence.
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

# Sentinel returned when evidence is insufficient
_INSUFFICIENT = "I could not find sufficient verified legal information."

_SYSTEM_PROMPT = """\
You are a legal information advisor for Astitva, a platform that helps marginalised \
women in India understand their legal rights and access legal support.

Answer the user's question based ONLY on the scheme records and document excerpts \
provided below. Do NOT claim to be a lawyer, do NOT provide legal advice, do NOT \
invent laws, sections, case procedures, or legal facts that are not in the evidence.

This is general informational guidance only. Always recommend the user consult a \
qualified legal professional or contact a legal aid organisation.

If the provided evidence does not contain enough information to answer the question, \
respond with exactly: "I could not find sufficient verified legal information."

When evidence is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence informational guidance>",
  "legal_information": [
    {
      "topic": "<legal topic from evidence>",
      "summary": "<summary from evidence>",
      "relevant_law_or_scheme": "<law/scheme name from evidence if present>",
      "next_step": "<what the user should do>",
      "source": "<source label>"
    }
  ],
  "suggested_resources": ["<legal aid organisation or resource from evidence>", ...],
  "next_actions": ["<concrete step>", ...],
  "legal_disclaimer": "This is general informational guidance only and not legal advice. Please consult a qualified legal professional.",
  "sources": ["<source label>", ...]
}
"""


def _build_legal_evidence(evidence: dict[str, Any]) -> str:
    """Serialise hybrid-retrieval evidence for the legal prompt."""
    lines: list[str] = []

    schemes: list[dict[str, Any]] = evidence.get("schemes", [])
    documents: list[dict[str, Any]] = evidence.get("documents", [])

    if schemes:
        lines.append("=== LEGAL AID SCHEMES (from database) ===")
        for s in schemes:
            lines.append(f"\nScheme: {s.get('name', 'Unknown')}")
            if s.get("category"):
                lines.append(f"  Category: {s['category']}")
            if s.get("state"):
                lines.append(f"  State: {s['state']}")
            if s.get("target_group"):
                lines.append(f"  Target group: {s['target_group']}")
            if s.get("benefits"):
                lines.append(f"  Support provided: {', '.join(s['benefits'])}")
            if s.get("eligibility"):
                lines.append(f"  Eligibility: {s['eligibility']}")
            if s.get("application_process"):
                lines.append(f"  How to access: {s['application_process']}")
            if s.get("official_url"):
                lines.append(f"  Official URL: {s['official_url']}")
            lines.append(f"  Source: {s.get('source', 'structured_db')}")
    else:
        lines.append("=== LEGAL AID SCHEMES ===\nNo matching legal schemes found in database.")

    if documents:
        lines.append("\n=== RELEVANT LEGAL DOCUMENT EXCERPTS (from knowledge base) ===")
        for i, d in enumerate(documents[:6], 1):
            meta = d.get("metadata") or {}
            src = meta.get("source") or d.get("source_id") or f"chunk-{i}"
            lines.append(f"\n[Excerpt {i} | source: {src}]")
            lines.append(d.get("content", ""))
    else:
        lines.append("\n=== RELEVANT DOCUMENT EXCERPTS ===\nNo relevant document excerpts found.")

    return "\n".join(lines)


def _build_legal_prompt(query: str, profile: dict[str, Any], evidence_block: str) -> str:
    """Build the user-turn prompt for the legal agent."""
    profile_lines: list[str] = []
    if profile.get("state"):
        profile_lines.append(f"State: {profile['state']}")
    if profile.get("target_group"):
        profile_lines.append(f"Target group: {profile['target_group']}")

    profile_section = "\n".join(profile_lines) if profile_lines else "No profile provided."

    return (
        f"USER QUERY:\n{query}\n\n"
        f"USER PROFILE:\n{profile_section}\n\n"
        f"{evidence_block}\n\n"
        "Based solely on the above evidence, provide your legal information guidance."
    )


def _parse_legal_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output; return a safe fallback dict on failure."""
    text = raw.strip()
    _disclaimer = (
        "This is general informational guidance only and not legal advice. "
        "Please consult a qualified legal professional."
    )
    if not text or text == _INSUFFICIENT:
        return {
            "answer": _INSUFFICIENT,
            "legal_information": [],
            "suggested_resources": [],
            "next_actions": [],
            "legal_disclaimer": _disclaimer,
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
        "legal_information": [],
        "suggested_resources": [],
        "next_actions": [],
        "legal_disclaimer": _disclaimer,
        "sources": [],
    }


class LegalAgent(BaseAgent):
    """Legal information and guidance agent using Hybrid RAG + IBM Granite.

    Combines legal-aid scheme records (PostgreSQL) with ChromaDB document
    retrieval to produce grounded legal information. Never claims to be a
    lawyer or fabricates laws, sections, or case procedures.

    Parameters
    ----------
    hybrid_retriever:
        Pre-configured HybridRetriever (structured + vector arms).
    llm_provider:
        A BaseLLMProvider implementation.
    vector_limit:
        Number of vector chunks to retrieve per query.
    """

    name = "legal"
    responsibilities = (
        "Legal aid services",
        "Legal rights and procedures",
        "Relevant laws and guidelines",
        "Complaint and support mechanisms",
        "Legal RAG",
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
        """Run the legal agent workflow."""
        # ── 1. Extract profile filters ────────────────────────────────────
        ctx = request.context
        filters: dict[str, Any] = {"active_status": True}
        profile: dict[str, Any] = {}
        for key in ("state", "target_group"):
            if ctx.get(key) is not None:
                filters[key] = ctx[key]
                profile[key] = ctx[key]
        # Restrict structured retrieval to legal category
        filters["category"] = ctx.get("category", "legal")

        # ── 2. Retrieve evidence ──────────────────────────────────────────
        evidence = self._retriever.search(
            query=request.query,
            filters=filters,
            vector_limit=self._vector_limit,
        )

        # ── 3. Build grounded prompt ──────────────────────────────────────
        evidence_block = _build_legal_evidence(evidence)
        user_prompt = _build_legal_prompt(request.query, profile, evidence_block)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse and structure output ─────────────────────────────────
        parsed = _parse_legal_response(raw_response)

        retrieval_sources: list[str] = evidence.get("sources", [])
        llm_sources: list[str] = parsed.get("sources") or []
        merged_sources = list(dict.fromkeys(llm_sources + retrieval_sources))

        insufficient = parsed.get("answer", "") == _INSUFFICIENT
        _disclaimer = (
            "This is general informational guidance only and not legal advice. "
            "Please consult a qualified legal professional."
        )
        return AgentResponse(
            agent_name=self.name,
            status="insufficient_evidence" if insufficient else "ok",
            summary=parsed.get("answer", ""),
            data={
                "legal_information": parsed.get("legal_information", []),
                "suggested_resources": parsed.get("suggested_resources", []),
                "next_actions": parsed.get("next_actions", []),
                "legal_disclaimer": parsed.get("legal_disclaimer", _disclaimer),
                "evidence": {
                    "schemes_count": len(evidence.get("schemes", [])),
                    "documents_count": len(evidence.get("documents", [])),
                    "insufficient_evidence": insufficient,
                },
            },
            sources=merged_sources,
        )
