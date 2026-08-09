"""Document Agent — answers document guidance queries using RAG + IBM Granite.

Workflow
--------
user query
    ↓
ChromaDB similarity search (vector-only, no structured arm needed)
    ↓
grounded prompt (evidence only — model must not invent document requirements)
    ↓
IBM Granite via local MLX
    ↓
structured response with answer, guidance, and sources

The LLM is explicitly instructed to base its answer solely on retrieved
evidence. If the evidence is insufficient it must say so clearly.
"""

from __future__ import annotations

from typing import Any

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider

# Sentinel returned when evidence is insufficient
_INSUFFICIENT = "I could not find sufficient verified information about that document."

_SYSTEM_PROMPT = """\
You are a helpful document guidance advisor for Astitva, a platform that \
helps marginalised women in India navigate document requirements.

Answer the user's question based ONLY on the document excerpts provided below. \
Do NOT use your own general knowledge or invent any document names, procedures, \
or office locations.

If the provided excerpts do not contain enough information to answer the question, \
respond with exactly: "I could not find sufficient verified information about that document."

When evidence is sufficient, respond in the following JSON format (no markdown fences):
{
  "answer": "<2–3 sentence direct answer>",
  "guidance": [
    {
      "step": "<action the user should take>",
      "details": "<extra detail or note, if any>"
    }
  ],
  "required_documents": ["<document name>", ...],
  "sources": ["<source label>", ...]
}
"""


def _build_document_prompt(query: str, documents: list[dict[str, Any]]) -> str:
    """Build the user-turn prompt from retrieved vector chunks."""
    lines: list[str] = [f"USER QUERY:\n{query}\n"]

    if documents:
        lines.append("=== RELEVANT DOCUMENT EXCERPTS ===")
        for i, d in enumerate(documents[:6], 1):
            meta = d.get("metadata") or {}
            src = meta.get("source") or d.get("source_id") or f"chunk-{i}"
            lines.append(f"\n[Excerpt {i} | source: {src}]")
            lines.append(d.get("content", ""))
    else:
        lines.append("=== RELEVANT DOCUMENT EXCERPTS ===\nNo relevant excerpts found.")

    lines.append("\nBased solely on the above excerpts, provide your guidance.")
    return "\n".join(lines)


def _parse_document_response(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output; return a safe fallback dict on failure."""
    import json

    text = raw.strip()
    if not text or text == _INSUFFICIENT:
        return {
            "answer": _INSUFFICIENT,
            "guidance": [],
            "required_documents": [],
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
        "guidance": [],
        "required_documents": [],
        "sources": [],
    }


class DocumentAgent(BaseAgent):
    """Document guidance agent using ChromaDB RAG + IBM Granite.

    Parameters
    ----------
    vector_store:
        ChromaStore instance for semantic document retrieval.
    llm_provider:
        LLM for generating grounded answers.
    vector_limit:
        Max vector chunks to retrieve.
    """

    name = "document"
    responsibilities = (
        "Identify required documents",
        "Check document availability",
        "Detect missing documents",
        "Guide users on obtaining documents",
        "Document RAG",
    )

    def __init__(
        self,
        vector_store: Any,
        llm_provider: BaseLLMProvider,
        vector_limit: int = 5,
    ) -> None:
        self._vector_store = vector_store
        self._llm = llm_provider
        self._vector_limit = vector_limit

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Run the document agent workflow."""
        from backend.app.rag.interfaces import RetrievalResult

        # ── 1. Retrieve relevant chunks from ChromaDB ─────────────────────
        documents: list[dict[str, Any]] = []
        sources: list[str] = []

        if self._vector_store is not None:
            raw: list[RetrievalResult] = self._vector_store.similarity_search(
                request.query, limit=self._vector_limit
            )
            for r in raw:
                meta = r.metadata.model_dump() if r.metadata else {}
                documents.append(
                    {
                        "content": r.content,
                        "score": r.score,
                        "source_id": r.source_id,
                        "metadata": meta,
                    }
                )
                label = meta.get("source") or r.source_id or "vector_store"
                if label not in sources:
                    sources.append(label)

        # ── 2. Build grounded prompt ──────────────────────────────────────
        user_prompt = _build_document_prompt(request.query, documents)

        # ── 3. Call LLM ───────────────────────────────────────────────────
        raw_response = self._llm.generate(user_prompt, system=_SYSTEM_PROMPT)

        # ── 4. Parse output ───────────────────────────────────────────────
        parsed = _parse_document_response(raw_response)

        # Merge sources
        llm_sources: list[str] = parsed.get("sources") or []
        merged_sources = list(dict.fromkeys(llm_sources + sources))

        insufficient = parsed.get("answer", "") == _INSUFFICIENT
        return AgentResponse(
            agent_name=self.name,
            status="insufficient_evidence" if insufficient else "ok",
            summary=parsed.get("answer", ""),
            data={
                "guidance": parsed.get("guidance", []),
                "required_documents": parsed.get("required_documents", []),
                "evidence": {
                    "documents_count": len(documents),
                    "insufficient_evidence": insufficient,
                },
            },
            sources=merged_sources,
        )
