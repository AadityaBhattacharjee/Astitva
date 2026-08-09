# Architecture

Status:
- `[PLACEHOLDER]` Repository boundaries and startup scaffold
- `[PLANNED]` End-to-end orchestration and production integrations

## Overview

Astitva is organized around a supervisor-driven orchestration model that can coordinate specialized agents, structured databases, semantic retrieval systems, roadmap generation, risk prioritization, and human support workflows.

## High-Level Diagram

```text
User
  |
  v
API Layer
  |
  v
Supervisor Agent
  |
  +--> Domain Agents
  +--> Retrieval Layer
  +--> Planning Layer
  +--> Progress Layer
  +--> Risk Layer
  `--> Human Escalation
```

## Design Principles

- keep provider boundaries abstract
- separate planning from retrieval
- make privacy controls explicit
- favor source-backed responses over free-form generation
- keep the first deployment simple

