# ADR 0001 — Every feature is a nano function (uniform scale-to-zero)

Date: 2026-07-02

## Status

Accepted

## Context

The portal runs on a bare-metal k3s cluster with limited resources. A minority
of features are compute-intensive — the OpenPowerlifting stats / ranking /
percentile tools pull in pandas, numpy, and scipy and do heavy work. These
cannot run as long-running pods with multiple replicas: the cluster cannot size
for peak compute, and a warm pandas pod sitting idle between calls wastes scarce
memory.

Fission (scale 0 → 1 → 0 within ~60s of idle) solved this for the
compute-intensive features: each expensive capability is a nano function that
scales up only when called and scales down when done.

The question was whether to extend this pattern to **all** features — including
the many that are thin CRUD (`health_get_session`, `budget_list_items`,
`template_list`) or pure stdlib math (`kg_to_lb`, `calculate_dots`,
`estimate_1rm`) — or to keep a two-tier architecture where only the expensive
few are nano functions and the cheap ones live in a shared long-running process.

## Decision

**Every feature is a nano function.** All capabilities — analytics, CRUD,
math utilities, AI — follow the same pattern: one function per capability,
scale-to-zero, exposed as both an HTTP endpoint (called by the portal backend
via `invokeLambda`) and an MCP tool (called by the Discord agent). The one
documented exception is `health_rag_search`, which needs local ChromaDB state
on the IF Agent pod and goes through `invokeToolDirect` instead.

The resource constraint forced the first (compute-intensive) functions into this
shape. Uniformity was then extended to all features for four reasons:

1. **Free feature parity.** If every capability is a function exposed as both
   endpoint and MCP, the portal reaches it via HTTP and the Discord agent
   reaches it via MCP automatically. "Is this feature reachable from Discord?"
   never has to be asked — parity is a property of the substrate, not a
   per-feature effort.
2. **Migration insulation.** A planned DynamoDB → Postgres migration will make
   the storage client heavier than a simple SDK HTTP call. Per-function HTTP
   boundaries insulate each capability from the storage swap; a shared-process
   architecture would couple more code to the client change.
3. **MCP call reliability.** Grouping several capabilities into one function
   means one tool with branching input shapes, which risks the model
   mis-calling it through MCP. One function = one stable input schema = reliable
   agent tool calls.
4. **One architecture, not four.** A single deploy / routing / parity story
   across all features avoids maintaining separate substrates for cheap vs
   expensive vs AI vs CRUD capabilities.

## Consequences

- **Cold-start latency on trivial functions.** `kg_to_lb` pays a scale-from-zero
  cost it does not strictly need. Accepted for uniformity.
- **Operational overhead.** ~94 functions + `pl_authorizer` + `tool_registry`
  + master-sync + video-thumbnail to deploy and observe, instead of one process.
  Mitigated by uniform tooling (same `resources.yaml` / `resources.json` shape
  per function, shared layers).
- **One documented stateful carve-out.** `health_rag_search` needs local
  ChromaDB and cannot follow the stateless nano-function pattern. Any future
  feature needing local pod state (model weights, persistent caches) must
  declare itself explicitly and follow the `invokeToolDirect` carve-out rather
  than silently routing through a function.
- **Every new feature is born multi-interface.** Adding a feature means adding a
  function; it is automatically reachable from both the portal and the agent.
  A feature that is not callable through the agent's MCP tools is incomplete by
  definition.

## Alternatives considered

**Two-tier (nano only for the spicy few).** Keep compute-intensive features as
scale-to-zero nano functions; run thin CRUD and stdlib math in a shared
long-running backend process. Rejected: breaks uniform parity (shared-process
features would need a separate path to the agent), couples cheap features to the
DynamoDB→Postgres client migration, and introduces a second architecture to
maintain.

**Grouped functions (one pod, several capabilities, routed by a param).**
Rejected for the MCP reliability reason in (3) above: branching input shapes per
capability would make agent tool calls less reliable.
