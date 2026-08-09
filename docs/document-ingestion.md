# Document Ingestion

Status:
- `[PLACEHOLDER]` Pipeline interfaces and metadata schema
- `[TO IMPLEMENT]` Loaders, parsing, chunking, indexing, and verification

## Planned Pipeline

```text
Documents
  |
  v
Document Loader
  |
  v
Parsing
  |
  v
Cleaning
  |
  v
Chunking
  |
  v
Metadata Extraction
  |
  v
Embedding
  |
  v
ChromaDB
```

## Metadata Fields

- source
- document_type
- organization
- category
- state
- publication_date
- last_verified_date
- url
- trust_level

