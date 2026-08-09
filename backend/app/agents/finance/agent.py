"""Finance Agent — financial assistance, loans, and budget guidance using RAG + IBM Granite.

Workflow
--------
user query
    ↓
ChromaDB similarity search for verified financial/scheme information
    ↓
Scheme-DB filter for finance-related schemes (category = "finance")
    ↓
grounded prompt (evidence only — model must not invent amounts, eligibility, or schemes)
    ↓
IBM Granite via local MLX
    ↓
structured response with guidance, eligible schemes, and next steps

The LLM is explicitly instructed:
- Never invent loan amounts, interest rates, or benefit figures.
- Never fabricate scheme names, eligibility criteria, or financial records.
- Clearly distinguish verified scheme data from general guidance.
- Report insufficient evidence explicitly.
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

# Sentinel returned when evidence is insufficient
_INSUFFICIENT = "I could not find sufficient verified financial information."

_SYSTEM_PROMPT = """\
You are a financial guidance advisor for Astitva, a platform that helps marginalised \
women in India access financial assistance and plan their economic independence.

Answer the user's question based ONLY on the scheme records and document excerpts \
provided below. Do NOT invent loan amounts, interest rates, benefit figures, scheme \
names, or eligibility criteria that are not present in the provided evidence.

Important: this is informational guidance only, not financial advice. \
Always recommend users verify details with the relevant government or financial institution.

If the provided evidence does not contain enough information to answer the question, \
respond with exactly: "I could not find sufficient verified financial information."

When evidence is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence direct guidance>",
  "financial_options": [
    {
      "name": "<scheme or programme name>",
      "type": "<loan / grant / subsidy / insurance>",
      "eligibility": "<eligibility criteria from evidence>",
      "benefits": ["<benefit from evidence>", ...],
      "how_to_apply": "<application process from evidence>",
      "source": "<source label>"
    }
  ],
  "budgeting_tips": ["<tip grounded in evidence if any>", ...],
  "next_actions": ["<concrete step>", ...],
  "disclaimer": "This is informational only. Verify all details with the relevant institution.",
  "sources": ["<source label>", ...]
}
"""


def _build_finance_evidence(evidence: dict[str, Any]) -> str:
    """Serialise hybrid-retrieval evidence for the finance prompt."""
    lines: list[str] = []

    schemes: list[dict[str, Any]] = evidence.get("schemes", [])
    documents: list[dict[str, Any]] = evidence.get("documents", [])

    if schemes:
        lines.append("=== FINANCIAL SCHEMES / PROGRAMMES (from database) ===")
        for s in schemes:
            lines.append(f"\nScheme: {s.get('name', 'Unknown')}")
            if s.get("category"):
                lines.append(f"  Category: {s['category']}")
            if s.get("state"):
                lines.append(f"  State: {s['state']}")
            if s.get("target_group"):
                lines.append(f"  Target group: {s['target_group']}")
            if s.get("income_limit"):
                lines.append(f"  Income limit: ₹{s['income_limit']:,}/year")
            if s.get("benefits"):
                lines.append(f"  Benefits: {', '.join(s['benefits'])}")
            if s.get("eligibility"):
                lines.append(f"  Eligibility: {s['eligibility']}")
            if s.get("application_process"):
                lines.append(f"  How to apply: {s['application_process']}")
            if s.get("official_url"):
                lines.append(f"  Official URL: {s['official_url']}")
            lines.append(f"  Source: {s.get('source', 'structured_db')}")
    else:
        lines.append("=== FINANCIAL SCHEMES ===\nNo matching financial schemes found in database.")

    if documents:
        lines.append("\n=== RELEVANT FINANCIAL DOCUMENT EXCERPTS (from knowledge base) ===")
        for i, d in enumerate(documents[:6], 1):
            meta = d.get("metadata") or {}
            src = meta.get("source") or d.get("source_id") or f"chunk-{i}"
            lines.append(f"\n[Excerpt {i} | source: {src}]")
            lines.append(d.get("content", ""))
    else:
        lines.append("\n=== RELEVANT DOCUMENT EXCERPTS ===\nNo relevant document excerpts found.")

    return "\n".join(lines)


def _build_finance_prompt(query: str, profile: dict[str, Any], evidence_block: str) -> str:
    """Build the user-turn prompt for the finance agent."""
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
        "Based solely on the above evidence, provide your financial guidance."
    )


def _parse_finance_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output; return a safe fallback dict on failure."""
    text = raw.strip()
    if not text or text == _INSUFFICIENT:
        return {
            "answer": _INSUFFICIENT,
            "financial_options": [],
            "budgeting_tips": [],
            "next_actions": [],
            "disclaimer": "This is informational only. Verify all details with the relevant institution.",
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
        "financial_options": [],
        "budgeting_tips": [],
        "next_actions": [],
        "disclaimer": "This is informational only. Verify all details with the relevant institution.",
        "sources": [],
    }


class FinanceAgent(BaseAgent):
    """Financial assistance guidance agent using Hybrid RAG + IBM Granite.

    Combines finance-related scheme records (PostgreSQL) with ChromaDB
    document retrieval to produce grounded financial guidance. Never invents
    amounts, eligibility criteria, or scheme details.

    Parameters
    ----------
    hybrid_retriever:
        Pre-configured HybridRetriever (structured + vector arms).
    llm_provider:
        A BaseLLMProvider implementation.
    vector_limit:
        Number of vector chunks to retrieve per query.
    """

    name = "finance"
    responsibilities = (
        "Financial assistance",
        "Loans and support programs",
        "Entrepreneurship opportunities",
        "Financial independence planning",
        "Finance RAG",
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
        """Run the finance agent workflow."""
        # ── 1. Extract profile filters ────────────────────────────────────
        ctx = request.context
        filters: dict[str, Any] = {"active_status": True}
        profile: dict[str, Any] = {}
        for key in ("state", "target_group", "age", "income"):
            if ctx.get(key) is not None:
                filters[key] = ctx[key]
                profile[key] = ctx[key]
        # Restrict structured retrieval to finance category
        filters["category"] = ctx.get("category", "finance")

        # ── 2. Retrieve evidence ──────────────────────────────────────────
        evidence = self._retriever.search(
            query=request.query,
            filters=filters,
            vector_limit=self._vector_limit,
        )

        # ── 3. Build grounded prompt ──────────────────────────────────────
        evidence_block = _build_finance_evidence(evidence)
        user_prompt = _build_finance_prompt(request.query, profile, evidence_block)

        # ── 4. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 5. Parse and structure output ─────────────────────────────────
        parsed = _parse_finance_response(raw_response)

        retrieval_sources: list[str] = evidence.get("sources", [])
        llm_sources: list[str] = parsed.get("sources") or []
        merged_sources = list(dict.fromkeys(llm_sources + retrieval_sources))

        insufficient = parsed.get("answer", "") == _INSUFFICIENT
        return AgentResponse(
            agent_name=self.name,
            status="insufficient_evidence" if insufficient else "ok",
            summary=parsed.get("answer", ""),
            data={
                "financial_options": parsed.get("financial_options", []),
                "budgeting_tips": parsed.get("budgeting_tips", []),
                "next_actions": parsed.get("next_actions", []),
                "disclaimer": parsed.get(
                    "disclaimer",
                    "This is informational only. Verify all details with the relevant institution.",
                ),
                "evidence": {
                    "schemes_count": len(evidence.get("schemes", [])),
                    "documents_count": len(evidence.get("documents", [])),
                    "insufficient_evidence": insufficient,
                },
            },
            sources=merged_sources,
        )
