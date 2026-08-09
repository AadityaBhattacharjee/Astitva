# Hybrid RAG

Status:
- `[PLACEHOLDER]` Architectural model and interfaces
- `[TO IMPLEMENT]` Real structured queries, vector similarity search, and validation

## Structured Retrieval

Planned entities:

- user data
- scheme data
- eligibility data
- job data
- healthcare services
- progress data
- mentor data

## Unstructured Retrieval

Planned sources:

- government PDFs
- legal documents
- scheme guidelines
- NGO documents
- healthcare support documents
- application procedures

## Query Flow

```text
User Query
  |
  v
Supervisor
  |
  v
Selected Agent
  |
  +--> PostgreSQL retrieval
  `--> ChromaDB retrieval
          |
          v
  Reranking / validation
          |
          v
  LLM synthesis
```

