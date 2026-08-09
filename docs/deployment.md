# Deployment

Status:
- `[PLACEHOLDER]` Docker-based single-server deployment scaffold
- `[TO IMPLEMENT]` Reverse proxy, HTTPS, secrets management, and monitoring

The initial deployment target is a single VPS or cloud server running:

- FastAPI application container
- PostgreSQL
- optional local ChromaDB persistence

Deliberately excluded from this phase:

- Kafka
- Kubernetes
- microservice decomposition

