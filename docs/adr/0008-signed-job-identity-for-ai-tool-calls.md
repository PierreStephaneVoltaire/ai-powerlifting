# ADR-0008: Signed job identity for AI tool calls

## Decision

Every durable AI job is bound at turn start to a short-lived asymmetric JWT
minted by the assistant after resolving the requester through Profile
`access_context`. Claims: `person_pk`, `athlete_pk`, `conversation_id`,
`workflow_id`, allowed operation scope, `aud`, `exp`, `jti`. Nothing supplied
by a model — subjects, headers, roles, paths — is ever trusted.

Tool calls reach domain services only through the LiteLLM MCP gateway, which
forwards the job token per server (`x-mcp-{alias}-{header}`) while
authenticating to LiteLLM with the caller's own virtual key. Domain services
verify signature, audience, expiry, and operation scope, then run the
existing `access_context` and argument-scoping checks. Unmapped operations
and unverifiable tokens are denied. The mesh-header path for existing
service callers is unchanged.

LiteLLM virtual keys replace master-key use by workloads; gateway credentials
and upstream MCP authorization stay separate. Access decisions, tool calls,
proposals, approvals, and mutations are written to an append-only audit table.

## Consequences

Object-level authorization is enforced by the services independently of agent
decisions, so a compromised or confused agent cannot widen its scope.
Revocation applies on the next call because grants are evaluated live.
Signing keys live in SSM; rotation invalidates outstanding jobs.

## Update (2026-11-16)

Tokens are ES256 and minted per tool call. The only write path is
`propose_change`: arguments are validated against the operation's MCP input
schema at propose time, a structured diff and target version are captured, and
commit follows explicit approval with a version re-check and idempotency key.
Commit failures are surfaced to the user and on the proposal card. LiteLLM
virtual keys are per consumer and limited with `object_permission.mcp_servers`.
Audit also includes `orchestration_events` and LiteLLM request metadata/tags.
