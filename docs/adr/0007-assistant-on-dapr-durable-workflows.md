# ADR-0007: Assistant runs on Dapr durable workflows

## Decision

Conversational and agentic AI moves from `pl-coach` to a new Go service,
`src/services/assistant` (`pl-assistant`), built on Dapr Workflow via
`durabletask-go`. Every turn is a workflow; every LLM call, tool call,
proposal, and delegation is a checkpointed activity. Turns go directly to an
orchestrator that delegates to responder subagents (child workflows) on model
aliases chosen by task complexity and escalates when review fails. Tool scope
comes from the caller's live permissions, not from the opened surface.

State lives in a pgvector-enabled CNPG PostgreSQL cluster
(`assistant-postgres`): the Dapr actor/workflow state store plus the
assistant's own schema (conversations, turns, participants, embeddings,
proposals, audit). The service runs 3–4 stateless replicas capped at 2 GiB
each; an interrupted workflow resumes on another replica from the last
completed activity.

All model and MCP traffic goes through LiteLLM. The Python dapr-agents
framework was rejected to keep the service in Go; the agent loop is ours.

`pl-coach` remains only as the domain-job broker and Codex `needs_inference`
answerer for `execution:"ai"` operations (analytics reports, import parsing).
Its chat endpoints, surfaces, guard, and SQLite thread/binding state are
removed. Discord becomes one shared conversation per (athlete, channel).

## Consequences

A Dapr control plane (scheduler + placement) joins the cluster and its health
gates workflow starts; stuck-PENDING workflows indicate a scheduler problem.
Conversation state survives pod loss without PVCs or node pinning. The
`/v1/jobs` contract consumed by analytics-ai is unchanged. Old SQLite
conversations are not migrated.

## Update (2026-11-16)

Orchestration is direct: there is no classification step ahead of the
coordinator. The coordinator model (`pl-coordinator`) answers itself or calls
`delegate_subagent` with a complexity tier (low, medium, high) and `needs_web`,
reviews results (`review_delegation`) and escalates (`escalate_from`); a
conditional security subagent can only tighten. Decisions are recorded in
`orchestration_events`. Models are LiteLLM aliases only (`pl-coordinator`,
`pl-responder-fast`, `pl-strong`, `pl-web`, `pl-embed`, `pl-light`); concrete
models are tfvars configuration. Retrieval applies the authorization filter
before pgvector similarity ranking. Dapr control plane is 1.18.
