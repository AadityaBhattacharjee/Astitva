# Astitva

Tagline: "Rebuilding Lives. Restoring Identity."

Astitva is an AI-powered life orchestration platform for women navigating major life transitions such as domestic abuse, widowhood, financial dependency, abandonment, single parenthood, and career breaks. The platform is designed to intelligently coordinate existing support systems rather than pretending one chatbot can replace legal, financial, healthcare, employment, and welfare ecosystems.

This repository now includes a minimal Phase 1 backend foundation: FastAPI, PostgreSQL wiring, Alembic migrations, seed data, and basic CRUD for users, schemes, roadmaps, roadmap tasks, and progress. Agent orchestration, RAG, ML, mentor workflows, and frontend work are still intentionally deferred.

## Current Status

- `[IMPLEMENTED]` FastAPI app with `/health` and Phase 1 CRUD routes
- `[IMPLEMENTED]` PostgreSQL configuration, SQLAlchemy models, and Alembic migration scaffold
- `[IMPLEMENTED]` Demo seed data for users, schemes, roadmap tasks, and progress
- `[PLACEHOLDER]` Agent module structure and abstract interfaces
- `[PLACEHOLDER]` Hybrid RAG package boundaries and ingestion/retrieval interfaces
- `[PLACEHOLDER]` Security, mentor, and risk prediction interfaces
- `[PLANNED]` Agent logic, RAG pipelines, ML inference, and frontend UI
- `[TO IMPLEMENT]` Production business logic, persistence, verification pipelines, and deployment hardening

## Phase 1 Scope

Included in this phase:

- PostgreSQL via `DATABASE_URL`
- SQLAlchemy ORM models and relationships
- Alembic migration setup with an initial migration
- CRUD endpoints for users, schemes, roadmaps, roadmap tasks, and progress
- demo seed data
- basic health and database test coverage

Explicitly not included in this phase:

- agents or LangGraph workflows
- RAG, ChromaDB, or document retrieval pipelines
- ML or risk prediction logic
- mentor matching logic
- frontend implementation

## Phase 1 Quick Start

1. Copy `.env.example` to `.env` and adjust `DATABASE_URL` if needed.
2. Start PostgreSQL with Docker:

```bash
docker compose up -d db
```

3. Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

4. Run migrations:

```bash
alembic upgrade head
```

5. Seed demo data:

```bash
python -m scripts.seed_data
```

6. Start the API:

```bash
uvicorn backend.app.main:app --reload
```

7. Check the health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

## Phase 1 API Endpoints

- `POST /api/v1/users/`
- `GET /api/v1/users/`
- `POST /api/v1/schemes/`
- `GET /api/v1/schemes/`
- `POST /api/v1/roadmaps/`
- `GET /api/v1/roadmaps/`
- `POST /api/v1/roadmaps/tasks`
- `GET /api/v1/roadmaps/tasks`
- `POST /api/v1/progress/`
- `GET /api/v1/progress/`

## Problem Statement

Support systems already exist, but they are fragmented. Users often need legal aid, health services, employment pathways, welfare schemes, documentation help, and ongoing case support at the same time. The difficulty is navigating disconnected institutions while under stress, with incomplete documents, low trust, and rapidly changing personal circumstances.

## Proposed Solution

Astitva is designed as a coordinated orchestration platform that can:

- understand a user's situation
- route requests to domain-specific agents
- retrieve verified information from structured and unstructured sources
- generate a personalized roadmap
- track milestones and risk signals
- escalate high-risk cases to human case workers
- support opt-in peer mentoring for users who later want to help others

## Why Astitva Is Different From a Normal Chatbot

A normal chatbot mainly answers questions. Astitva is intended to become a source-backed orchestration layer with persistent state, domain routing, retrieval over verified materials, roadmap tracking, intervention prioritization, and consent-aware human escalation.

## System Architecture

```text
User
  |
  v
Supervisor Agent [PLANNED]
  |
  +--> Specialized Agents [PLANNED]
  |      |- Legal
  |      |- Finance
  |      |- Employment
  |      |- Healthcare
  |      |- Government
  |      |- Document
  |      |- Planning / Decision
  |      |- Progress
  |      |- Risk Prediction
  |      |- Case Worker
  |      `- Mentor Matching
  |
  +--> Hybrid Retrieval Layer [PLACEHOLDER]
  |      |- PostgreSQL / SQL structured retrieval
  |      `- ChromaDB semantic retrieval
  |
  v
Personalized Roadmap [PLANNED]
  |
  +--> Progress Tracking [PLANNED]
  `--> Risk Prediction [PLANNED]
          |
          v
    Case Worker Intervention [PLANNED]
          |
          v
    Opt-in Mentor Network [PLANNED]
```

## Multi-Agent Architecture

Every domain is modeled as its own future agent so responsibilities stay explicit and testable. The supervisor agent will eventually manage context, delegation, and result synthesis, while the planning agent will convert domain findings into user-facing next steps.

See [docs/agents.md](/Users/aadityabhattacharjee/Astitva/docs/agents.md) for the detailed agent map.

## Hybrid RAG

The retrieval layer is intentionally split:

- Structured retrieval for user state, schemes, jobs, eligibility, roadmap progress, mentor data, and case data
- Unstructured retrieval for legal PDFs, scheme documents, NGO guidance, healthcare documents, and application procedures

```text
User Query
  |
  v
Supervisor
  |
  v
Selected Agent
  |
  +--> Structured Retrieval --> PostgreSQL
  |
  `--> Semantic Retrieval --> ChromaDB
                                ^
                                |
                        Document Ingestion
  |
  v
Reranking / Validation [PLACEHOLDER]
  |
  v
LLM Provider Abstraction [PLACEHOLDER]
  |
  v
Source-backed Recommendation [PLANNED]
```

See [docs/hybrid-rag.md](/Users/aadityabhattacharjee/Astitva/docs/hybrid-rag.md) and [docs/document-ingestion.md](/Users/aadityabhattacharjee/Astitva/docs/document-ingestion.md).

## Structured vs Unstructured Data

Structured data will eventually cover:

- users and profiles
- cases
- schemes and eligibility rules
- jobs
- healthcare services
- roadmap tasks and progress
- mentor and consent data

Unstructured data will eventually cover:

- government PDFs
- legal documents
- scheme guidelines
- NGO documentation
- healthcare resource packs
- application procedure documents

## Document Ingestion Pipeline

```text
Documents
  |
  v
Loader [PLACEHOLDER]
  |
  v
Parsing [PLACEHOLDER]
  |
  v
Cleaning [PLACEHOLDER]
  |
  v
Chunking [PLACEHOLDER]
  |
  v
Metadata Extraction [PLACEHOLDER]
  |
  v
Embeddings [PLACEHOLDER]
  |
  v
ChromaDB [PLANNED]
  |
  v
Retrieval [PLANNED]
```

## Government Scheme Intelligence

The repository includes schema placeholders for government schemes, including category, eligibility, benefits, documentation, state targeting, official source URL, and verification metadata. No scraping is implemented in this phase.

## Risk Prediction

Risk prediction in Astitva is scoped as intervention prioritization, not diagnosis. The planned model will analyze milestone completion, overdue tasks, application status, financial constraints, engagement, and documentation readiness to produce low, medium, or high support-risk signals.

See [docs/risk-prediction.md](/Users/aadityabhattacharjee/Astitva/docs/risk-prediction.md).

## Case-Worker Intervention

High-risk or stalled journeys should eventually be surfaced to trained human case workers with concise case summaries, risk factors, and recommended next actions. The current repository contains only placeholder architecture for that handoff.

## Mentor Network

The mentor subsystem is designed to be opt-in, privacy-aware, and consent-based. Successful users may later create mentor profiles and be matched to similar users based on lived experience, domain fit, language, geography, and availability.

See [docs/mentor-system.md](/Users/aadityabhattacharjee/Astitva/docs/mentor-system.md).

## Privacy and Security

Security is treated as a first-class architectural concern:

- JWT authentication `[PLACEHOLDER]`
- role-based access control `[PLACEHOLDER]`
- consent management `[PLACEHOLDER]`
- audit logging `[PLACEHOLDER]`
- PII minimization `[PLACEHOLDER]`
- LLM context filtering `[PLACEHOLDER]`
- encryption-ready configuration `[PLANNED]`
- HTTPS deployment guidance `[PLANNED]`

See [docs/security.md](/Users/aadityabhattacharjee/Astitva/docs/security.md).

## Technology Stack

- Frontend: React, Tailwind CSS `[PLANNED]`
- Backend: FastAPI, Python `[PLACEHOLDER]`
- Agent orchestration: LangGraph `[PLANNED]`
- LLM: IBM Granite via provider abstraction `[PLACEHOLDER]`
- RAG: LangChain + ChromaDB + PostgreSQL `[PLACEHOLDER]`
- Document ingestion: Docling, PyPDF fallback `[PLACEHOLDER]`
- ML: XGBoost or Random Forest behind an interface `[PLACEHOLDER]`
- Auth/security: JWT, RBAC, audit logging `[PLACEHOLDER]`
- Deployment: Docker on a single VPS/cloud server `[PLACEHOLDER]`

## Deployment Architecture

Initial deployment is intentionally simple:

```text
Internet
  |
  v
HTTPS Reverse Proxy [PLANNED]
  |
  +--> FastAPI Application Container
  `--> PostgreSQL
```

No Kafka, Kubernetes, or multi-service orchestration is introduced in this phase.

## Future Scope

- implement supervisor and domain agent workflows
- add verified source ingestion pipelines
- connect PostgreSQL and ChromaDB retrieval
- implement roadmap generation
- add risk scoring and case worker dashboards
- build frontend experience for users, mentors, and admins
- add evaluation, observability, and compliance workflows

## Repository Layout

```text
backend/     FastAPI app, agent interfaces, RAG boundaries, security, models
docs/        Architecture and implementation planning documents
frontend/    Frontend placeholder and future UI notes
data/        Local placeholders for raw, processed, and domain datasets
scripts/     Setup and seed-data placeholder scripts
```

## What Is Ready

- repository structure for all planned major components
- working backend foundation for Phase 1 CRUD
- health endpoint with a database check
- Alembic migration scaffold and initial migration
- typed schemas and SQLAlchemy models for the Phase 1 entities
- demo seed data for local development
- documentation that marks planned vs placeholder components clearly

## What Remains To Implement

- real authentication and authorization flows
- agent workflows and orchestration
- RAG ingestion, indexing, retrieval, and reranking
- government scheme verification workflows
- roadmap generation and progress mutation logic
- risk model training/inference
- case worker prioritization logic
- mentor matching logic
- frontend product experience

## Recommended 36-Hour Hackathon Order

1. Wire PostgreSQL models, migrations, and a small verified seed dataset.
2. Implement auth, users, cases, and roadmap CRUD.
3. Build supervisor routing plus one strong domain agent first, preferably government or document.
4. Add basic document ingestion with metadata and ChromaDB indexing.
5. Implement hybrid retrieval for schemes and supporting PDFs.
6. Build roadmap generation and progress tracking.
7. Add a rules-first risk scoring baseline before any ML model.
8. Expose case-worker and mentor APIs last if time remains.

## Developer Notes

- The backend should start without API keys.
- Secrets are expected through environment variables.
- Placeholder modules include docstrings and TODOs to guide future work.
