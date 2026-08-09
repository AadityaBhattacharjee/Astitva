"""Government scheme discovery and eligibility agent.

Workflow
--------
user query + profile filters
    ↓
HybridRetriever (PostgreSQL structured + ChromaDB semantic)
    ↓
grounded prompt (evidence only, no invented facts)
    ↓
IBM Granite via watsonx.ai
    ↓
structured recommendation with sources

The LLM is explicitly instructed to base its answer solely on the
retrieved evidence. If the evidence is insufficient it must reply with
the standard insufficiency message rather than drawing on model knowledge.
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

# Sentinel returned by the LLM when evidence is insufficient
_INSUFFICIENT = "I could not find sufficient verified information."

# System prompt — instructs the model to stay grounded
_SYSTEM_PROMPT = """\
You are a knowledgeable and empathetic government welfare advisor for Astitva, \
a platform that helps marginalised women in India access government support schemes.

Your task is to advise the user based ONLY on the structured scheme records and \
document excerpts provided in the user message. Do NOT use your own general knowledge \
or invent any scheme names, URLs, or benefit amounts.

If the provided evidence does not contain enough information to answer the question, \
respond with exactly: "I could not find sufficient verified information."

When evidence is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence summary of the recommendation>",
  "recommended_schemes": [
    {
      "name": "<scheme name>",
      "eligibility_reasoning": "<why this user qualifies>",
      "benefits": ["<benefit 1>", ...],
      "required_documents": ["<doc 1>", ...],
      "application_process": "<how to apply>",
      "official_url": "<url or null>",
      "source": "<source label>"
    }
  ],
  "additional_context": "<any relevant notes from the document chunks>",
  "sources": ["<source 1>", ...]
}
"""


def _build_evidence_block(evidence: dict[str, Any]) -> str:
    """Serialise hybrid-retrieval evidence into a compact prompt block."""
    lines: list[str] = []

    schemes: list[dict[str, Any]] = evidence.get("schemes", [])
    documents: list[dict[str, Any]] = evidence.get("documents", [])

    if schemes:
        lines.append("=== ELIGIBLE GOVERNMENT SCHEMES (from database) ===")
        for s in schemes:
            lines.append(f"\nScheme: {s.get('name', 'Unknown')}")
            lines.append(f"  Category: {s.get('category', '-')}")
            lines.append(f"  State: {s.get('state', '-')}")
            lines.append(f"  Target group: {s.get('target_group', '-')}")
            if s.get("income_limit"):
                lines.append(f"  Income limit: ₹{s['income_limit']:,}/year")
            if s.get("min_age") or s.get("max_age"):
                lines.append(f"  Age range: {s.get('min_age', 'any')}–{s.get('max_age', 'any')}")
            if s.get("benefits"):
                lines.append(f"  Benefits: {', '.join(s['benefits'])}")
            if s.get("required_documents"):
                lines.append(f"  Required documents: {', '.join(s['required_documents'])}")
            if s.get("application_process"):
                lines.append(f"  Application: {s['application_process']}")
            if s.get("official_url"):
                lines.append(f"  Official URL: {s['official_url']}")
            if s.get("eligibility"):
                lines.append(f"  Eligibility notes: {s['eligibility']}")
            lines.append(f"  Source: {s.get('source', 'structured_db')}")
    else:
        lines.append("=== ELIGIBLE GOVERNMENT SCHEMES ===\nNo matching schemes found in database.")

    if documents:
        lines.append("\n=== RELEVANT DOCUMENT EXCERPTS (from knowledge base) ===")
        for i, d in enumerate(documents[:5], 1):   # cap at 5 chunks to control prompt size
            meta = d.get("metadata") or {}
            src = meta.get("source") or d.get("source_id") or f"chunk-{i}"
            lines.append(f"\n[Excerpt {i} | source: {src}]")
            lines.append(d.get("content", ""))
    else:
        lines.append("\n=== RELEVANT DOCUMENT EXCERPTS ===\nNo relevant document excerpts found.")

    return "\n".join(lines)


def _build_user_prompt(query: str, profile: dict[str, Any], evidence_block: str) -> str:
    """Build the user-turn prompt containing query, profile, and evidence."""
    profile_lines: list[str] = []
    if profile.get("state"):
        profile_lines.append(f"State: {profile['state']}")
    if profile.get("age") is not None:
        profile_lines.append(f"Age: {profile['age']}")
    if profile.get("income") is not None:
        profile_lines.append(f"Annual income: ₹{profile['income']:,}")
    if profile.get("target_group"):
        profile_lines.append(f"Target group: {profile['target_group']}")

    profile_section = "\n".join(profile_lines) if profile_lines else "No profile provided."

    return (
        f"USER QUERY:\n{query}\n\n"
        f"USER PROFILE:\n{profile_section}\n\n"
        f"{evidence_block}\n\n"
        "Based solely on the above evidence, provide your recommendation."
    )


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output; return a safe fallback dict on failure."""
    text = raw.strip()
    if not text or text == _INSUFFICIENT:
        return {
            "answer": _INSUFFICIENT,
            "recommended_schemes": [],
            "additional_context": "",
            "sources": [],
        }
    # Attempt JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract a JSON object if wrapped in prose
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    # Return raw text as the answer when JSON parsing completely fails
    return {
        "answer": text,
        "recommended_schemes": [],
        "additional_context": "",
        "sources": [],
    }


class GovernmentAgent(BaseAgent):
    """Government welfare scheme discovery and eligibility agent.

    Combines HybridRetriever evidence with IBM Granite to produce grounded
    scheme recommendations. The LLM never determines eligibility independently —
    only schemes that pass the PostgreSQL eligibility filters are surfaced.

    Parameters
    ----------
    hybrid_retriever:
        Pre-configured HybridRetriever (structured + vector arms).
    llm_provider:
        A BaseLLMProvider implementation (GraniteLLMProvider in production,
        or any mock/stub for tests).
    vector_limit:
        Number of vector chunks to retrieve per query.
    """

    name = "government"
    responsibilities = (
        "Government welfare schemes",
        "Scheme eligibility",
        "Benefits",
        "Required documents",
        "Application procedures",
        "Central and state schemes",
        "Government RAG",
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
        """Run the full government agent workflow."""
        # ── 1. Extract profile filters from context ───────────────────────
        ctx = request.context
        filters: dict[str, Any] = {}
        profile: dict[str, Any] = {}
        for key in ("state", "category", "target_group", "age", "income", "active_status"):
            if ctx.get(key) is not None:
                filters[key] = ctx[key]
                profile[key] = ctx[key]

        # ── 2. Retrieve evidence via HybridRetriever ──────────────────────
        evidence = self._retriever.search(
            query=request.query,
            filters=filters,
            vector_limit=self._vector_limit,
        )

        # ── 3. Build grounded prompt ──────────────────────────────────────
        evidence_block = _build_evidence_block(evidence)
        user_prompt = _build_user_prompt(request.query, profile, evidence_block)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse and structure output ─────────────────────────────────
        parsed = _parse_llm_response(raw_response)

        # Merge retrieval sources into the parsed source list
        retrieval_sources: list[str] = evidence.get("sources", [])
        llm_sources: list[str] = parsed.get("sources") or []
        merged_sources = list(dict.fromkeys(llm_sources + retrieval_sources))  # dedupe, order-preserving

        return AgentResponse(
            agent_name=self.name,
            status="ok",
            summary=parsed.get("answer", ""),
            data={
                "recommended_schemes": parsed.get("recommended_schemes", []),
                "additional_context": parsed.get("additional_context", ""),
                "evidence": {
                    "schemes_count": len(evidence.get("schemes", [])),
                    "documents_count": len(evidence.get("documents", [])),
                },
            },
            sources=merged_sources,
        )
