"""Agent API routes.

Exposes all implemented agent endpoints:
  POST /agents/government, /agents/supervisor, /agents/document,
  /agents/case_worker, /agents/employment, /agents/finance,
  /agents/healthcare, /agents/legal, /agents/mentor_matching,
  /agents/planning, /agents/progress, /agents/risk
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.agents.base import AgentRequest, AgentResponse
from backend.app.agents.case_worker.agent import CaseWorkerAgent
from backend.app.agents.document.agent import DocumentAgent
from backend.app.agents.employment.agent import EmploymentAgent
from backend.app.agents.finance.agent import FinanceAgent
from backend.app.agents.government.agent import GovernmentAgent
from backend.app.agents.healthcare.agent import HealthcareAgent
from backend.app.agents.legal.agent import LegalAgent
from backend.app.agents.mentor_matching.agent import MentorMatchingAgent
from backend.app.agents.planning.agent import PlanningAgent
from backend.app.agents.progress.agent import ProgressAgent
from backend.app.agents.risk.agent import RiskPredictionAgent
from backend.app.agents.supervisor.agent import SupervisorAgent
from backend.app.api.dependencies import get_current_user
from backend.app.api.placeholders import build_placeholder_router
from backend.app.config import get_settings
from backend.app.database.models.entities import User
from backend.app.database.session import get_db
from backend.app.rag.retrieval.hybrid import HybridRetriever
from backend.app.rag.retrieval.structured import SchemeStructuredRetriever
from backend.app.rag.vector_store.chroma_store import ChromaStore
from backend.app.rag.embeddings.provider import SentenceTransformerEmbeddingProvider
from backend.app.services.llm_provider import get_llm_provider

router = APIRouter(prefix="/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Lazy singletons (same pattern as rag.py to avoid re-loading the model)
# ---------------------------------------------------------------------------

_embedding_provider: SentenceTransformerEmbeddingProvider | None = None
_vector_store: ChromaStore | None = None


def _get_embedding_provider() -> SentenceTransformerEmbeddingProvider:
    global _embedding_provider  # noqa: PLW0603
    if _embedding_provider is None:
        settings = get_settings()
        _embedding_provider = SentenceTransformerEmbeddingProvider(
            model_name=settings.embedding_model
        )
    return _embedding_provider


def _get_vector_store() -> ChromaStore:
    global _vector_store  # noqa: PLW0603
    if _vector_store is None:
        settings = get_settings()
        _vector_store = ChromaStore(
            persist_directory=settings.chroma_persist_directory,
            collection_name=settings.chroma_collection_name,
            embedding_provider=_get_embedding_provider(),
        )
    return _vector_store


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class GovernmentAgentRequest(BaseModel):
    """Input to the Government Agent endpoint."""

    query: str = Field(..., description="Natural-language question from the user.")
    state: str | None = Field(default=None, description="Indian state of residence.")
    category: str | None = Field(default=None, description="Scheme category filter.")
    target_group: str | None = Field(default=None, description="Target demographic.")
    age: int | None = Field(default=None, ge=0, description="User's age in years.")
    income: int | None = Field(default=None, ge=0, description="Annual household income (INR).")
    vector_limit: int = Field(default=5, ge=1, le=20, description="Max document chunks to retrieve.")


class GovernmentAgentResponse(BaseModel):
    """Structured output from the Government Agent."""

    agent_name: str
    status: str
    answer: str
    recommended_schemes: list[dict[str, Any]]
    additional_context: str
    evidence_summary: dict[str, int]
    sources: list[str]


# ---------------------------------------------------------------------------
# Government Agent endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/government",
    response_model=GovernmentAgentResponse,
    summary="Government welfare scheme recommendation (Hybrid RAG + IBM Granite, JWT-protected)",
)
def government_agent(
    payload: GovernmentAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Government Agent pipeline.

    1. Filters eligible schemes from PostgreSQL using the supplied profile.
    2. Retrieves semantically relevant document chunks from ChromaDB.
    3. Passes the combined evidence to IBM Granite for grounded recommendation.

    If WATSONX credentials are not configured the response still contains full
    structured evidence; only the narrative answer will be a placeholder.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    # Build context dict for AgentRequest
    context: dict[str, Any] = {}
    for key in ("state", "category", "target_group", "age", "income"):
        val = getattr(payload, key, None)
        if val is not None:
            context[key] = val
    context["active_status"] = True  # always enforce active-only

    request = AgentRequest(query=payload.query, context=context)

    hybrid_retriever = HybridRetriever(
        structured_retriever=SchemeStructuredRetriever(db),
        vector_store=_get_vector_store(),
    )

    agent = GovernmentAgent(
        hybrid_retriever=hybrid_retriever,
        llm_provider=get_llm_provider(),
        vector_limit=payload.vector_limit,
    )

    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "recommended_schemes": response.data.get("recommended_schemes", []),
        "additional_context": response.data.get("additional_context", ""),
        "evidence_summary": response.data.get("evidence", {}),
        "sources": response.sources,
    }


# ---------------------------------------------------------------------------
# Supervisor Agent endpoint
# ---------------------------------------------------------------------------

class SupervisorRequest(BaseModel):
    """Input to the Supervisor Agent endpoint."""

    query: str = Field(..., description="Natural-language query from the user.")


class SupervisorResponse(BaseModel):
    """Structured output from the Supervisor Agent."""

    agent_name: str
    status: str
    summary: str
    routed_to: str | None
    intent: str
    method: str


@router.post(
    "/supervisor",
    response_model=SupervisorResponse,
    summary="Classify and route user query to a specialist agent (JWT-protected)",
)
def supervisor_agent(
    payload: SupervisorRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Run the Supervisor Agent pipeline.

    Classifies the user query using keyword rules (and Granite LLM as fallback)
    and returns the selected specialist agent name plus intent reasoning.
    The specialist agent is NOT executed — routing only.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
    )
    agent = SupervisorAgent(llm_provider=get_llm_provider())
    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "summary": response.summary,
        "routed_to": response.data.get("routed_to"),
        "intent": response.data.get("intent", ""),
        "method": response.data.get("method", ""),
    }


# ---------------------------------------------------------------------------
# Document Agent endpoint
# ---------------------------------------------------------------------------

class DocumentAgentRequest(BaseModel):
    """Input to the Document Agent endpoint."""

    query: str = Field(..., description="Natural-language question about documents.")
    vector_limit: int = Field(default=5, ge=1, le=20, description="Max chunks to retrieve.")


class DocumentAgentResponse(BaseModel):
    """Structured output from the Document Agent."""

    agent_name: str
    status: str
    answer: str
    guidance: list[dict[str, Any]]
    required_documents: list[str]
    evidence_summary: dict[str, Any]
    sources: list[str]


@router.post(
    "/document",
    response_model=DocumentAgentResponse,
    summary="Document guidance via RAG + IBM Granite (JWT-protected)",
)
def document_agent(
    payload: DocumentAgentRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Run the Document Agent pipeline.

    Retrieves relevant document excerpts from ChromaDB and uses IBM Granite
    to produce grounded document guidance.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
    )
    agent = DocumentAgent(
        vector_store=_get_vector_store(),
        llm_provider=get_llm_provider(),
        vector_limit=payload.vector_limit,
    )
    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "guidance": response.data.get("guidance", []),
        "required_documents": response.data.get("required_documents", []),
        "evidence_summary": response.data.get("evidence", {}),
        "sources": response.sources,
    }


# ---------------------------------------------------------------------------
# Case Worker Agent endpoint
# ---------------------------------------------------------------------------

class CaseWorkerRequest(BaseModel):
    """Input to the Case Worker Agent endpoint."""

    query: str = Field(..., description="Case management query or question.")


class CaseWorkerResponse(BaseModel):
    """Structured output from the Case Worker Agent."""

    agent_name: str
    status: str
    case_summary: str
    priority_actions: list[dict[str, Any]]
    document_gaps: list[str]
    roadmap_status: str
    risk_flags: list[str]
    case_meta: dict[str, Any]


@router.post(
    "/case_worker",
    response_model=CaseWorkerResponse,
    summary="Case management assistance using live DB records (JWT-protected)",
)
def case_worker_agent(
    payload: CaseWorkerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Case Worker Agent pipeline.

    Loads the authenticated user's profile, documents, roadmaps, and progress
    from the database, then uses IBM Granite to generate a grounded case
    assessment. No data is invented — gaps are reported explicitly.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
    )
    agent = CaseWorkerAgent(db=db, llm_provider=get_llm_provider())
    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "case_summary": response.summary,
        "priority_actions": response.data.get("priority_actions", []),
        "document_gaps": response.data.get("document_gaps", []),
        "roadmap_status": response.data.get("roadmap_status", "No roadmap found"),
        "risk_flags": response.data.get("risk_flags", []),
        "case_meta": response.data.get("case_meta", {}),
    }


# ---------------------------------------------------------------------------
# Employment Agent endpoint
# ---------------------------------------------------------------------------

class EmploymentAgentRequest(BaseModel):
    """Input to the Employment Agent endpoint."""

    query: str = Field(..., description="Natural-language employment or career question.")
    state: str | None = Field(default=None, description="Indian state of residence.")
    target_group: str | None = Field(default=None, description="Target demographic.")
    age: int | None = Field(default=None, ge=0, description="User's age in years.")
    vector_limit: int = Field(default=5, ge=1, le=20, description="Max document chunks to retrieve.")


class EmploymentAgentResponse(BaseModel):
    """Structured output from the Employment Agent."""

    agent_name: str
    status: str
    answer: str
    job_options: list[dict[str, Any]]
    skills_guidance: list[str]
    next_actions: list[str]
    evidence_summary: dict[str, Any]
    sources: list[str]


@router.post(
    "/employment",
    response_model=EmploymentAgentResponse,
    summary="Employment and career guidance via Hybrid RAG + IBM Granite (JWT-protected)",
)
def employment_agent(
    payload: EmploymentAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Employment Agent pipeline.

    Retrieves employment-related scheme records from PostgreSQL and relevant
    document chunks from ChromaDB, then uses IBM Granite to produce grounded
    career and job guidance. Never invents job listings or salary figures.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    context: dict[str, Any] = {}
    for key in ("state", "target_group", "age"):
        val = getattr(payload, key, None)
        if val is not None:
            context[key] = val

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
        context=context,
    )

    hybrid_retriever = HybridRetriever(
        structured_retriever=SchemeStructuredRetriever(db),
        vector_store=_get_vector_store(),
    )
    agent = EmploymentAgent(
        hybrid_retriever=hybrid_retriever,
        llm_provider=get_llm_provider(),
        vector_limit=payload.vector_limit,
    )
    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "job_options": response.data.get("job_options", []),
        "skills_guidance": response.data.get("skills_guidance", []),
        "next_actions": response.data.get("next_actions", []),
        "evidence_summary": response.data.get("evidence", {}),
        "sources": response.sources,
    }


# ---------------------------------------------------------------------------
# Finance Agent endpoint
# ---------------------------------------------------------------------------

class FinanceAgentRequest(BaseModel):
    """Input to the Finance Agent endpoint."""

    query: str = Field(..., description="Natural-language financial assistance question.")
    state: str | None = Field(default=None, description="Indian state of residence.")
    target_group: str | None = Field(default=None, description="Target demographic.")
    age: int | None = Field(default=None, ge=0, description="User's age in years.")
    income: int | None = Field(default=None, ge=0, description="Annual household income (INR).")
    vector_limit: int = Field(default=5, ge=1, le=20, description="Max document chunks to retrieve.")


class FinanceAgentResponse(BaseModel):
    """Structured output from the Finance Agent."""

    agent_name: str
    status: str
    answer: str
    financial_options: list[dict[str, Any]]
    budgeting_tips: list[str]
    next_actions: list[str]
    disclaimer: str
    evidence_summary: dict[str, Any]
    sources: list[str]


@router.post(
    "/finance",
    response_model=FinanceAgentResponse,
    summary="Financial assistance guidance via Hybrid RAG + IBM Granite (JWT-protected)",
)
def finance_agent(
    payload: FinanceAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Finance Agent pipeline.

    Retrieves finance-related scheme records from PostgreSQL and relevant
    document chunks from ChromaDB, then uses IBM Granite to produce grounded
    financial guidance. Never invents amounts, eligibility, or scheme details.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    context: dict[str, Any] = {}
    for key in ("state", "target_group", "age", "income"):
        val = getattr(payload, key, None)
        if val is not None:
            context[key] = val

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
        context=context,
    )

    hybrid_retriever = HybridRetriever(
        structured_retriever=SchemeStructuredRetriever(db),
        vector_store=_get_vector_store(),
    )
    agent = FinanceAgent(
        hybrid_retriever=hybrid_retriever,
        llm_provider=get_llm_provider(),
        vector_limit=payload.vector_limit,
    )
    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "financial_options": response.data.get("financial_options", []),
        "budgeting_tips": response.data.get("budgeting_tips", []),
        "next_actions": response.data.get("next_actions", []),
        "disclaimer": response.data.get(
            "disclaimer",
            "This is informational only. Verify all details with the relevant institution.",
        ),
        "evidence_summary": response.data.get("evidence", {}),
        "sources": response.sources,
    }


# ---------------------------------------------------------------------------
# Healthcare Agent endpoint
# ---------------------------------------------------------------------------

class HealthcareAgentRequest(BaseModel):
    """Input to the Healthcare Agent endpoint."""

    query: str = Field(..., description="Natural-language healthcare access question.")
    state: str | None = Field(default=None, description="Indian state of residence.")
    target_group: str | None = Field(default=None, description="Target demographic.")
    age: int | None = Field(default=None, ge=0, description="User's age in years.")
    income: int | None = Field(default=None, ge=0, description="Annual household income (INR).")
    vector_limit: int = Field(default=5, ge=1, le=20, description="Max document chunks to retrieve.")


class HealthcareAgentResponse(BaseModel):
    """Structured output from the Healthcare Agent."""

    agent_name: str
    status: str
    answer: str
    healthcare_schemes: list[dict[str, Any]]
    next_actions: list[str]
    medical_disclaimer: str
    evidence_summary: dict[str, Any]
    sources: list[str]


@router.post(
    "/healthcare",
    response_model=HealthcareAgentResponse,
    summary="Healthcare access guidance via Hybrid RAG + IBM Granite (JWT-protected)",
)
def healthcare_agent(
    payload: HealthcareAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Healthcare Agent pipeline.

    Retrieves healthcare-related scheme records from PostgreSQL and relevant
    document chunks from ChromaDB, then uses IBM Granite to produce grounded
    healthcare access guidance. Never diagnoses conditions or invents services.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    context: dict[str, Any] = {}
    for key in ("state", "target_group", "age", "income"):
        val = getattr(payload, key, None)
        if val is not None:
            context[key] = val

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
        context=context,
    )

    hybrid_retriever = HybridRetriever(
        structured_retriever=SchemeStructuredRetriever(db),
        vector_store=_get_vector_store(),
    )
    agent = HealthcareAgent(
        hybrid_retriever=hybrid_retriever,
        llm_provider=get_llm_provider(),
        vector_limit=payload.vector_limit,
    )
    response: AgentResponse = agent.handle(request)

    _disclaimer = (
        "This is informational guidance only. "
        "Please consult a qualified healthcare professional for medical decisions."
    )
    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "healthcare_schemes": response.data.get("healthcare_schemes", []),
        "next_actions": response.data.get("next_actions", []),
        "medical_disclaimer": response.data.get("medical_disclaimer", _disclaimer),
        "evidence_summary": response.data.get("evidence", {}),
        "sources": response.sources,
    }


# ---------------------------------------------------------------------------
# Legal Agent endpoint
# ---------------------------------------------------------------------------

class LegalAgentRequest(BaseModel):
    """Input to the Legal Agent endpoint."""

    query: str = Field(..., description="Natural-language legal information question.")
    state: str | None = Field(default=None, description="Indian state of residence.")
    target_group: str | None = Field(default=None, description="Target demographic.")
    vector_limit: int = Field(default=5, ge=1, le=20, description="Max document chunks to retrieve.")


class LegalAgentResponse(BaseModel):
    """Structured output from the Legal Agent."""

    agent_name: str
    status: str
    answer: str
    legal_information: list[dict[str, Any]]
    suggested_resources: list[str]
    next_actions: list[str]
    legal_disclaimer: str
    evidence_summary: dict[str, Any]
    sources: list[str]


@router.post(
    "/legal",
    response_model=LegalAgentResponse,
    summary="Legal information guidance via Hybrid RAG + IBM Granite (JWT-protected)",
)
def legal_agent(
    payload: LegalAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Legal Agent pipeline.

    Retrieves legal-aid scheme records from PostgreSQL and relevant document
    chunks from ChromaDB, then uses IBM Granite to produce grounded legal
    information. Never claims to be a lawyer or fabricates legal facts.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    context: dict[str, Any] = {}
    for key in ("state", "target_group"):
        val = getattr(payload, key, None)
        if val is not None:
            context[key] = val

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
        context=context,
    )

    hybrid_retriever = HybridRetriever(
        structured_retriever=SchemeStructuredRetriever(db),
        vector_store=_get_vector_store(),
    )
    agent = LegalAgent(
        hybrid_retriever=hybrid_retriever,
        llm_provider=get_llm_provider(),
        vector_limit=payload.vector_limit,
    )
    response: AgentResponse = agent.handle(request)

    _disclaimer = (
        "This is general informational guidance only and not legal advice. "
        "Please consult a qualified legal professional."
    )
    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "legal_information": response.data.get("legal_information", []),
        "suggested_resources": response.data.get("suggested_resources", []),
        "next_actions": response.data.get("next_actions", []),
        "legal_disclaimer": response.data.get("legal_disclaimer", _disclaimer),
        "evidence_summary": response.data.get("evidence", {}),
        "sources": response.sources,
    }


# ---------------------------------------------------------------------------
# Mentor Matching Agent endpoint
# ---------------------------------------------------------------------------

class MentorMatchingRequest(BaseModel):
    """Input to the Mentor Matching Agent endpoint."""

    query: str = Field(..., description="Natural-language mentorship question or goal.")


class MentorMatchingResponse(BaseModel):
    """Structured output from the Mentor Matching Agent."""

    agent_name: str
    status: str
    answer: str
    ideal_mentor_profile: dict[str, Any]
    recommended_channels: list[str]
    next_actions: list[str]
    disclaimer: str
    no_mentor_db: bool
    profile_used: dict[str, Any]


@router.post(
    "/mentor_matching",
    response_model=MentorMatchingResponse,
    summary="Profile-based mentor guidance via IBM Granite (JWT-protected)",
)
def mentor_matching_agent(
    payload: MentorMatchingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Mentor Matching Agent pipeline.

    Loads the authenticated user's profile, documents, and roadmaps.
    Uses IBM Granite to suggest ideal mentor criteria and channels.
    Does NOT have access to a real mentor database — no mentor is matched.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
    )
    agent = MentorMatchingAgent(db=db, llm_provider=get_llm_provider())
    response: AgentResponse = agent.handle(request)

    _disclaimer = (
        "Actual mentor matching requires registration and consent. "
        "No specific mentor has been identified."
    )
    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "ideal_mentor_profile": response.data.get("ideal_mentor_profile", {}),
        "recommended_channels": response.data.get("recommended_channels", []),
        "next_actions": response.data.get("next_actions", []),
        "disclaimer": response.data.get("disclaimer", _disclaimer),
        "no_mentor_db": response.data.get("no_mentor_db", True),
        "profile_used": response.data.get("profile_used", {}),
    }


# ---------------------------------------------------------------------------
# Planning Agent endpoint
# ---------------------------------------------------------------------------

class PlanningAgentRequest(BaseModel):
    """Input to the Planning Agent endpoint."""

    query: str = Field(..., description="Natural-language planning or goal question.")


class PlanningAgentResponse(BaseModel):
    """Structured output from the Planning Agent."""

    agent_name: str
    status: str
    answer: str
    existing_plan_summary: dict[str, Any]
    recommended_next_actions: list[dict[str, Any]]
    gaps_identified: list[str]
    disclaimer: str
    context_meta: dict[str, Any]


@router.post(
    "/planning",
    response_model=PlanningAgentResponse,
    summary="Personalized action planning from real DB data + IBM Granite (JWT-protected)",
)
def planning_agent(
    payload: PlanningAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Planning Agent pipeline.

    Loads the user's profile, roadmaps, tasks, and progress records.
    Uses IBM Granite to generate prioritized next-action recommendations.
    Does NOT write to the database. Recommendations are clearly flagged as
    AI-generated and not saved automatically.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
    )
    agent = PlanningAgent(db=db, llm_provider=get_llm_provider())
    response: AgentResponse = agent.handle(request)

    _disclaimer = (
        "These recommendations are AI-generated suggestions and have not been "
        "saved to your account."
    )
    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "existing_plan_summary": response.data.get("existing_plan_summary", {}),
        "recommended_next_actions": response.data.get("recommended_next_actions", []),
        "gaps_identified": response.data.get("gaps_identified", []),
        "disclaimer": response.data.get("disclaimer", _disclaimer),
        "context_meta": response.data.get("context_meta", {}),
    }


# ---------------------------------------------------------------------------
# Progress Agent endpoint
# ---------------------------------------------------------------------------

class ProgressAgentRequest(BaseModel):
    """Input to the Progress Agent endpoint."""

    query: str = Field(..., description="Natural-language progress tracking question.")


class ProgressAgentResponse(BaseModel):
    """Structured output from the Progress Agent."""

    agent_name: str
    status: str
    answer: str
    progress_summary: dict[str, Any]
    achievements: list[str]
    pending_actions: list[str]
    next_recommended_step: str
    context_meta: dict[str, Any]


@router.post(
    "/progress",
    response_model=ProgressAgentResponse,
    summary="Real progress analysis from DB records + IBM Granite (JWT-protected)",
)
def progress_agent(
    payload: ProgressAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Progress Agent pipeline.

    Calculates completion metrics deterministically from real Roadmap/Task/Progress
    records. Uses IBM Granite to interpret the data and recommend next steps.
    Never fabricates completion percentages or milestone counts.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
    )
    agent = ProgressAgent(db=db, llm_provider=get_llm_provider())
    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "progress_summary": response.data.get("progress_summary", {}),
        "achievements": response.data.get("achievements", []),
        "pending_actions": response.data.get("pending_actions", []),
        "next_recommended_step": response.data.get("next_recommended_step", ""),
        "context_meta": response.data.get("context_meta", {}),
    }


# ---------------------------------------------------------------------------
# Risk Prediction Agent endpoint
# ---------------------------------------------------------------------------

class RiskAgentRequest(BaseModel):
    """Input to the Risk Prediction Agent endpoint."""

    query: str = Field(..., description="Natural-language risk assessment question.")


class RiskAgentResponse(BaseModel):
    """Structured output from the Risk Prediction Agent."""

    agent_name: str
    status: str
    answer: str
    risk_level: str
    risk_score: float
    risk_flags: list[str]
    risk_interpretation: str
    observed_risk_factors: list[str]
    inferred_risk_factors: list[str]
    recommended_interventions: list[str]
    risk_features: dict[str, Any]
    context_meta: dict[str, Any]


@router.post(
    "/risk",
    response_model=RiskAgentResponse,
    summary="Rule-based risk assessment from real DB data + IBM Granite (JWT-protected)",
)
def risk_agent(
    payload: RiskAgentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the Risk Prediction Agent pipeline.

    Computes risk flags deterministically from real profile/document/roadmap data.
    Uses IBM Granite to interpret and recommend interventions.
    Risk level is always from the rule engine, never from the LLM.
    """
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    request = AgentRequest(
        user_id=str(current_user.id),
        query=payload.query,
    )
    agent = RiskPredictionAgent(db=db, llm_provider=get_llm_provider())
    response: AgentResponse = agent.handle(request)

    return {
        "agent_name": response.agent_name,
        "status": response.status,
        "answer": response.summary,
        "risk_level": response.data.get("risk_level", "UNKNOWN"),
        "risk_score": response.data.get("risk_score", 0.0),
        "risk_flags": response.data.get("risk_flags", []),
        "risk_interpretation": response.data.get("risk_interpretation", ""),
        "observed_risk_factors": response.data.get("observed_risk_factors", []),
        "inferred_risk_factors": response.data.get("inferred_risk_factors", []),
        "recommended_interventions": response.data.get("recommended_interventions", []),
        "risk_features": response.data.get("risk_features", {}),
        "context_meta": response.data.get("context_meta", {}),
    }


# ---------------------------------------------------------------------------
# Agent listing — all 12 agents now implemented
# ---------------------------------------------------------------------------

_placeholder = build_placeholder_router("agents", "agents")

@router.get("/", summary="List agents")
def list_agents() -> dict[str, object]:
    return {
        "implemented": [
            "government", "supervisor", "document", "case_worker",
            "employment", "finance", "healthcare", "legal",
            "mentor_matching", "planning", "progress", "risk",
        ],
        "placeholder": [],
    }
