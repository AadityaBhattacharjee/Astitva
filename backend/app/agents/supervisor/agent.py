"""Supervisor Agent — classifies user queries and routes to specialist agents.

Routing strategy
----------------
1. Rule-based keyword matching (deterministic, fast, no LLM call).
2. LLM fallback via Granite for genuinely ambiguous queries.

The agent returns the selected agent name and intent reasoning without
executing the specialist agent.
"""

from __future__ import annotations

from backend.app.agents.base import AgentRequest, AgentResponse, BaseAgent
from backend.app.services.llm_provider import BaseLLMProvider, PlaceholderLLMProvider

# ---------------------------------------------------------------------------
# Keyword rules — map agent name → trigger keywords (lower-cased)
# ---------------------------------------------------------------------------

KEYWORD_RULES: dict[str, list[str]] = {
    "government": [
        "scheme", "yojana", "benefit", "subsidy", "welfare", "government",
        "entitlement", "allowance", "pm ", "pradhan mantri", "central scheme",
        "state scheme", "ration", "bpl", "apl",
    ],
    "employment": [
        "job", "employment", "work", "career", "salary", "hiring", "recruit",
        "internship", "apprentice", "mgnrega", "labour", "labor", "skill",
        "vocational", "resume", "cv ", "interview",
    ],
    "legal": [
        "legal", "law", "court", "rights", "complaint", "fir", "police",
        "domestic violence", "divorce", "custody", "alimony", "property",
        "inheritance", "advocate", "lawyer", "judge", "tribunal", "petition",
        "harassment", "assault",
    ],
    "finance": [
        "loan", "credit", "bank", "finance", "money", "savings", "investment",
        "insurance", "microfinance", "mudra", "interest rate", "emi",
        "debt", "financial", "budget", "income tax",
    ],
    "healthcare": [
        "health", "doctor", "hospital", "medicine", "clinic", "medical",
        "pregnancy", "antenatal", "postnatal", "nutrition", "vaccine",
        "immunisation", "immunization", "disease", "treatment", "ayushman",
        "janani", "mental health", "counsell",
    ],
    "document": [
        "document", "certificate", "aadhaar", "aadhar", "pan card",
        "ration card", "birth certificate", "caste certificate", "id proof",
        "voter id", "passport", "form fill", "application form",
    ],
    "case_worker": [
        "case worker", "caseworker", "social worker", "field officer",
        "assign", "case assign", "support worker",
    ],
    "mentor_matching": [
        "mentor", "mentorship", "coach", "guidance", "tutor", "role model",
        "mentor match",
    ],
    "planning": [
        "plan", "goal", "milestone", "roadmap", "strategy", "future",
        "timeline", "next step",
    ],
    "progress": [
        "progress", "track", "status", "update", "history", "report",
        "achievement", "completed", "pending task",
    ],
    "risk": [
        "risk", "danger", "threat", "safety", "abuse", "violence",
        "trafficking", "exploitation", "unsafe", "emergency",
    ],
}

# Ordered list of agent names (deterministic iteration)
_AGENT_NAMES: list[str] = list(KEYWORD_RULES.keys())

# Classification prompt template — kept short to minimise token cost
_CLASSIFY_SYSTEM = (
    "You are a routing classifier for a women's welfare platform. "
    "Classify the user query into exactly one of these agent names: "
    + ", ".join(_AGENT_NAMES)
    + ". Reply with only the agent name, nothing else."
)


# ---------------------------------------------------------------------------
# Pure routing helpers (module-level, easily unit-testable)
# ---------------------------------------------------------------------------

def _rule_based_route(query: str) -> str | None:
    """Return the best matching agent name or None if ambiguous/no match.

    Scores each agent by counting keyword hits in the lower-cased query.
    Returns the winner only when a single agent leads by at least one point.
    """
    q = query.lower()
    scores: dict[str, int] = {}
    for agent, keywords in KEYWORD_RULES.items():
        hits = sum(1 for kw in keywords if kw in q)
        if hits:
            scores[agent] = hits

    if not scores:
        return None

    top = max(scores.values())
    winners = [a for a, s in scores.items() if s == top]
    return winners[0] if len(winners) == 1 else None


def _llm_route(query: str, llm: BaseLLMProvider) -> str:
    """Ask the LLM to classify the query; return a valid agent name or 'unknown'."""
    response = llm.generate(query, system=_CLASSIFY_SYSTEM)
    candidate = response.strip().lower().split()[0] if response.strip() else ""
    # Sanitise: accept only known agent names
    return candidate if candidate in _AGENT_NAMES else "unknown"


# ---------------------------------------------------------------------------
# SupervisorAgent
# ---------------------------------------------------------------------------

class SupervisorAgent(BaseAgent):
    """Classifies user intent and selects the appropriate specialist agent.

    Parameters
    ----------
    llm_provider:
        LLM used only for ambiguous queries that keyword rules cannot resolve.
        Defaults to PlaceholderLLMProvider (no network calls in tests).
    """

    name = "supervisor"
    responsibilities = (
        "Understand user intent",
        "Maintain context",
        "Route tasks",
        "Coordinate multiple agents",
        "Combine agent outputs",
    )

    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self._llm = llm_provider or PlaceholderLLMProvider()

    def handle(self, request: AgentRequest) -> AgentResponse:
        query = request.query.strip()

        if not query:
            return AgentResponse(
                agent_name=self.name,
                status="error",
                summary="Query must not be empty.",
                data={"routed_to": None, "intent": "empty query", "method": "rule"},
            )

        routed_to = _rule_based_route(query)
        method = "rule"

        if routed_to is None:
            routed_to = _llm_route(query, self._llm)
            method = "llm"

        return AgentResponse(
            agent_name=self.name,
            status="routed",
            summary=f"Query routed to '{routed_to}' agent via {method}-based classification.",
            data={
                "routed_to": routed_to,
                "intent": f"Classified as '{routed_to}' using {method} routing.",
                "method": method,
            },
        )
