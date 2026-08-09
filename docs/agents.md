# Agents

Status:
- `[PLACEHOLDER]` Agent directories, abstract interfaces, and route boundaries
- `[PLANNED]` LangGraph workflows and delegation logic

## Agent Map

- Supervisor Agent: intent understanding, routing, orchestration, synthesis
- Legal Agent: legal rights, aid, procedures, complaint mechanisms
- Finance Agent: assistance, loans, entrepreneurship, independence planning
- Employment Agent: jobs, training, career rebuilding
- Healthcare Agent: services, schemes, maternal and mental-health support
- Government Agent: welfare schemes, eligibility, documents, procedures
- Document Agent: required documents, gaps, acquisition guidance
- Planning Agent: prioritized next-best actions and roadmap generation
- Progress Agent: milestone tracking and roadmap updates
- Risk Prediction Agent: support-risk classification and intervention cues
- Case Worker Agent: case prioritization and human handoff summaries
- Mentor Matching Agent: consent-aware mentor pairing

## Coordination Model

```text
Supervisor
  |
  +--> One or more domain agents
  |
  v
Planning Agent
  |
  +--> Progress Agent
  `--> Risk Prediction Agent
```

