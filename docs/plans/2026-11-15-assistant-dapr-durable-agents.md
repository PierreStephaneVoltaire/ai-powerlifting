# Plan: Migrate `ai-powerlifting` conversational AI to Dapr Durable Agents

## Context

The powerlifting Coach (`pl-coach`) holds conversation state in SQLite on a
single-replica PVC with no durable resume (restart ⇒ jobs marked `uncertain`),
runs Codex in-process, and trusts mesh headers for MCP auth. The operator wants
the conversational/agentic side rebuilt on Dapr durable workflows: 3–4 headless
replicas (≤2 GB each), PostgreSQL/pgvector durable sessions that resume on
another replica after OOM, all model and MCP traffic through LiteLLM, short-lived
signed job identities end-to-end, server-side structured change approval, and a
frontend assistant opened from the session AI menu. Codex-based complex analysis
(analytics-ai reports) and import parsing stay on the existing path. Budget and
private notes are being removed — not in scope. **No migration/backfill code**:
old SQLite conversations are not carried over.

Operator decisions (confirmed):
- **Go** service on `durabletask-go` + Dapr Workflow (not Python dapr-agents).
  Agent loop, tool dispatch, nested subagents are our code. Service name encodes
  no language/framework.
- **pl-coach survives slimmed**: keeps `/v1/jobs` domain-job broker +
  `needs_inference` Codex answering for `execution:"ai"` operations (analysis
  reports, `import_parse_file`). Loses chat, surfaces, guard, threads/bindings.
- **Discord**: one shared durable conversation per (athlete, channel); athlete +
  granted coach/handler share history; results filtered per participant's
  authorization.

## Verified research (2026-11-15)

- **Dapr Workflow**: stable since 1.15; Go authoring stable; as of go-sdk v1.16
  use `durabletask-go` directly (client wrapper removed). Every activity result
  is checkpointed to the state store; after crash/OOM any replica resumes from
  the last completed step (actor placement). PostgreSQL state store supports
  actors ⇒ valid workflow backend. Known failure mode: workflows stuck PENDING
  when the Scheduler service is unhealthy ⇒ monitor dapr-scheduler.
- **LiteLLM MCP gateway**: two auth layers — client→LiteLLM virtual key;
  LiteLLM→MCP server static creds **plus per-request client headers** forwarded
  per server as `x-mcp-{server_alias}-{header}` (global `x-mcp-auth` deprecated;
  `extra_headers` controls forwarding). This carries our signed job token
  through LiteLLM while LiteLLM's own credential stays separate. Deployed
  `v1.108.8` should include this; verify at implementation, bump pin if needed.
- **Model routing (OpenRouter via LiteLLM aliases, providers registered once)**:
  frontier reasoning tier for coordination/program design; cheap-fast tier
  (gpt-6-luna / Haiku-class / DeepSeek V4.1 Flash) for classification, routing,
  summaries; DeepSeek V4.x tier for structured outputs/background. Exact models
  chosen in tfvars at cutover; aliases + fallback groups per existing scheme.

## Current state (explored)

**Infra**: no Dapr anywhere. CNPG operator runs `authentik-postgres`,
`litellm-postgres`; no pgvector (Qdrant backs prompt-cache). Istio Ambient
1.32, namespace-wide STRICT mTLS, `nolift-waypoint`, per-service SA
AuthorizationPolicy allow-lists (`TF/k8s/app/mesh.tf`, `TF/coach/mesh.tf`); no
NetworkPolicy. LiteLLM at `litellm:4000` — tfvars-driven aliases `pl-analysis`
(gpt-6-sol), `pl-standard` (gpt-5.6-terra), `pl-light` (gpt-6-luna),
`pl-documents`, `pl-background` (openrouter deepseek-v4-flash); master-key auth
only, **no MCP block, no virtual keys**; CNPG-backed DB already attached.
CI: `.github/workflows/build-images.yml` (Packer→ECR; ARC runner applies
core/perms/network/mesh/app then coach stacks; hard-coded `rollout status`
list must gain new Deployments).

**Coach** (`src/services/coach/`): FastAPI. (1) Domain-job broker `POST /v1/jobs`
→ domain service; `needs_inference` challenge answered via `inference.py`
(schema-checked, ≤3 retries), resumed at `POST /executions/{id}` —
**analytics-ai depends on this contract** (`internal/coach/coach.go`). (2) Chat
`POST /v1/conversations/{id}/turns`: `guard.check_rules` (length/injection/rate)
→ `guard.classify` LLM router → template surface w/ preview-hash confirm →
Valkey+Qdrant chat cache → `CodexModel.converse` (pinned `openai-codex==0.154.0`,
provider = litellm w/ **master key**, max_concurrent 4). State: SQLite
jobs/threads/bindings on `pl-coach-state` PVC + Codex home; Recreate, 1 replica
forced, node-pinned. Per-job MCP at `/v1/jobs/{id}/mcp` guarded by in-memory
HMAC token.

**AuthZ contract (reuse, do not fork)**: callers send `X-Person-Pk`,
`X-Athlete-Pk`; Istio adds `X-PL-Source-Principal` (SPIFFE SA). Services fetch
context from Profile `access_context` (Go: `internal/auth/access.go` per
service; Python: `runtime/access_store.current_context`) — fail closed, grants
checked live (revocation/tied-competition expiry in `access.py::grant_permissions`
/ Go `GrantPermissions`). `permissions.json` maps operation→permission,
`internal_only`, `cache_read`; unmapped fails closed. Argument scoping rejects
`_person_pk`/`_access`/`_if_job_id`, forces `pk` to the authorized athlete
(`runtime/dispatch.py::authorize`, Go `internal/auth/scope.go`). Two evaluator
copies exist (Go Profile = authority, Python runtime) — **do not add a third;
call `access_context`**.

**Frontend**: no session-level AI menu exists; closest is per-exercise
"Auto-regulation" (Bot icon menu in `components/sessions/SessionDrawer.tsx` →
`AutoRegulationModal.tsx`, client-held history, client-side apply) and the notes
Wand (`SessionNotesHelperModal`). Backend template-chat routes exist with no
frontend caller. No SSE/WebSocket — axios + polling (`resolveReport`,
`pollJob`). No server-side proposal/approval records anywhere.

**Discord**: `coach_discord` resolves users via DynamoDB `if-user`
(`Identity#sha256("https://discord.com\0" + id)` → `mapped_pk` → Person;
`DISCORD_PERSONS` env is dead config). Conversation
`powerlifting:{athlete}:discord:{channel}`; today each person gets a private
thread. Bot registrations in `if-webhooks` (these are config, not session
tracking — they stay in DynamoDB).

**Luna / Decision API**: OpenAI `POST /v1/decisions` used by prompt-cache
(`internal/decision/`, default model `gpt-6-luna`, min confidence 0.8). Not an
internal service. Old "Luna Specialist" design is retired — not revived; "Luna
decision" below = a light-model classification step.

## Target architecture

New Go service **`src/services/assistant`** → Deployment `pl-assistant`
(namespace `powerlifting`), 3 replicas (burst 4), requests 512Mi / limit 2Gi,
`GOMEMLIMIT` ~1.7GiB, no PVC, no node pin, RollingUpdate, Dapr-enabled pod
(`dapr.io/enabled`, `app-id: pl-assistant`). Follows existing conventions
(port 8000 `http`, `/health`, own SA, ambient label, waypoint policies).

```
web (oauth2-proxy→backend) ─┐                        ┌─> LiteLLM /v1 (models, virtual key)
discord (pl-coach-discord) ─┼─> pl-assistant ────────┤
                            │   Dapr Workflow        └─> LiteLLM MCP gateway ──> pl-<domain> /mcp
                            │   (durabletask-go)          (job token forwarded)   (token verified)
                            │        │
                            │   assistant-postgres (CNPG + pgvector):
                            │   workflow state store (actor) · conversations/turns
                            │   · embeddings · proposals · audit
                            └─> pl-profile access_context (authz, fail closed)

pl-coach (slim, unchanged contract): /v1/jobs + needs_inference Codex answering
for analytics-ai reports and import_parse_file. analytics-ai, prompt-cache,
Qdrant untouched.
```

### Durable workflow design (in `src/services/assistant`)

- **ConversationTurn workflow** (one per turn, keyed to the shared
  conversation): activities =
  1. `resolve_identity` — requester → Person/Athlete/role/relationship/channel
     via `access_context`; reject revoked/missing membership; mint job token.
  2. `decide` (Luna) — light-model classification of the latest request +
     relevant history: interface scope, unrelated-historical-change,
     destructive intent. Output routes only; **never grants permissions**.
     Implemented against the Decisions API through a LiteLLM passthrough route
     if supported by the pinned version, else structured-output call on
     `pl-light`. Deterministic guards (length, rate, injection regexes) ported
     from `guard.check_rules` run before it.
  3. `retrieve` — cross-session history: SQL `WHERE` on athlete scope +
     participant visibility **before** pgvector `ORDER BY distance`
     (embeddings via new `pl-embed` alias). Only conversations the requesting
     participant may see.
  4. `coordinate` — the agent loop: coordinator model (reasoning alias) picks
     the responder model per task (LiteLLM aliases incl. OpenRouter-backed
     tiers) and either answers, calls tools, or delegates.
  5. `tool_call` — via LiteLLM MCP gateway with the job token in the
     per-server forwarded header. No direct domain-service calls from the loop.
  6. `propose` / `commit` — mutations become proposal rows (structured diff,
     target object id + version); workflow waits on an **external event**
     (approve/reject). Commit revalidates `access_context` + object version,
     uses an idempotency key; destructive operations require target-specific
     approval.
  7. `deliver` — reply to web (poll endpoint) or Discord (relay).
- **Nested subagents**: child workflows (`CallChildWorkflow`) — task-scoped
  agents (template-phase, session-design, goals, supplements, biometrics,
  research) each with a restricted toolset and their own model alias;
  subagents may spawn further child workflows. Delegations are checkpointed
  steps ⇒ full durable trace, resume after OOM on any replica.
- Every LLM call and tool call is an activity ⇒ checkpointed in Postgres;
  retry policies on activities; concurrency capped per replica to respect 2Gi.

### Identity & security

- **Job token**: short-lived (minutes) asymmetric JWT (key pair in SSM, public
  key distributed via Secret/ConfigMap). Claims: `person_pk`, `athlete_pk`,
  `conversation_id`, `workflow_id`, allowed operation scope, `aud`
  (`pl-domain-mcp`), `exp`, `jti`. Minted server-side at turn start only —
  never from model output; model-supplied subjects/headers/paths ignored.
- **Verification in domain services (default deny)**: Go middleware added to
  the shared `internal/auth` pattern + Python `runtime/app.py` `/mcp` path:
  signature, audience, expiry, operation ∈ scope, then the **existing**
  `access_context` + argument-scoping checks (object-level, membership,
  revocation) run as today — authorization is enforced independently of any
  agent decision. Mesh-header path for existing callers (backend,
  pl-analytics, pl-coach) unchanged.
- **LiteLLM credential separation**: enable virtual keys (DB already present);
  `pl-assistant` and `pl-coach` each get their own key; retire master-key use
  in `TF/coach/provider-keys.tf`. LiteLLM's MCP-server config holds no user
  credentials — user scope travels only in the forwarded job token.
- **No user storage mounts / no direct data creds in workers**: pl-assistant
  gets no AWS credentials secret and no PVC; all data access is via MCP tools
  or `access_context`. Mesh: STRICT mTLS; allowed-callers =
  {backend, pl-coach-discord} → pl-assistant; pl-assistant → {litellm,
  pl-profile}; litellm → pl-<domain> (new, for the MCP gateway). ztunnel/
  waypoint entries per the existing checklist; dapr-system namespace excluded
  from ambient or explicitly allowed (decide at implementation — flagged).
- **Audit**: append-only Postgres table — access decisions, tool calls,
  proposals, approvals, commits (who/what/when/token jti).

### Runtime & storage

- New CNPG cluster `assistant-postgres` (pgvector-enabled image), 2 instances
  if single-node resources allow else 1, `postgres-local-path`. Databases:
  `dapr` (workflow/actor state store component, v2, `actorStateStore: true`)
  and `assistant` (conversations, turns, participants, embeddings
  `vector` column, proposals, audit) accessed via pgx.
- Dapr control plane via Helm (`TF/k8s/core/dapr.tf`): dapr 1.16.x with
  Scheduler + Placement (required for workflows); monitor scheduler health
  (known PENDING-stuck failure mode).
- SQLite threads/bindings and chat endpoints removed from pl-coach;
  conversation state lives only in Postgres. DynamoDB gains no new tables;
  `if-webhooks` registrations remain (not session state).

### Frontend

- New **AssistantDrawer** component (existing components untouched; one-line
  ASD-STE100 labels), opened from a new "Assistant" item in the existing
  session menus in `SessionDrawer.tsx` (next to Auto-regulation), passing the
  selected session + exercise as context. Auto-regulation modal stays as-is.
- Compact, expandable history (collapsed turn summaries → expand), rendered
  from the new history endpoint; polling transport (matches existing
  `pollJob`/`resolveReport` pattern; no SSE).
- **Structured change approval UI**: proposal cards with structured diffs,
  Approve/Reject per proposal; destructive ops show the named target and
  require its explicit confirmation. Backend relays approval → assistant
  raises the workflow event. Discord approvals = explicit confirm reply by an
  authorized participant.
- Surfaces at launch: session design, template phases, goals, supplements,
  biometrics; research tasks supported via a research subagent. **Deferred**:
  analysis chat, global chat. **Removed scope**: budget, private notes.

## Implementation steps (order)


Domain MCP tool calls carry the signed job token as
`x-mcp-<alias>-authorization` (aliases use underscores, for example
`x-mcp-lift_profiles-authorization`).

## Addendum 2026-11-15: direct orchestration

Supersedes the Luna routing gate, surface allow-lists and per-surface subagent
toolsets above.

- **No classification gate.** The `Decide` activity is removed. After identity
  resolution and the deterministic guard (length, rate, injection), the turn goes
  straight to the orchestrator on the coordinator alias. Retrieval runs once; a
  failure or empty result is handled as a history gap (below).
- **Surfaces are context profiles.** `surface` from the frontend selects a prompt
  hint and a default delegate kind only. It never restricts tools. Discord sends
  no surface and gets the `general` profile with the full catalog; identity and
  permissions are resolved per sender on every message.
- **Permission-driven scope.** The job-token `scope` claim is every catalog
  operation whose permission the caller holds (`tools.Scope(permissions)`).
  Writes stay proposal-gated; mutating operations never run directly.
- **Model selection and review.** The orchestrator picks a `complexity`
  (low/medium/high) per delegation: fast, coordinator or strong alias
  (`PL_MODEL_RESPONDER_FAST`, `PL_MODEL_COORDINATOR`, `PL_MODEL_STRONG`).
  Delegates carry a `delegation_id`; the orchestrator records a verdict with
  `review_delegation`, and a failed or empty result is auto-reviewed as failed.
  `delegate_subagent` with `escalate_from` retries one tier up; there is no tier
  above strong. Provider fallback stays in LiteLLM.
- **Security subagent.** Child workflow `SecurityAssessment` on
  `PL_MODEL_SECURITY` (default `pl-light`, falls back to the coordinator alias).
  Triggers: a high-risk guard signal (other-person reference, approval bypass, or
  bulk plus destructive language), an orchestrator `flag_suspicious` call, a
  destructive proposal, or a history-dependent mutation while history is
  unavailable. The verdict (`allow`, `require_approval`, `block`) can only
  tighten: it is merged with `Tighten`, floors per trigger cannot be lowered by
  the model, and it never grants access or widens scope. The assessment is
  attached to the proposal diff.
- **Shared-channel visibility gate.** In `Deliver`, for shared (Discord)
  conversations, the permissions required by the used operations and retrieved
  snippets are checked against every current participant's live permissions. If
  anyone lacks one (or cannot be resolved), the reply is replaced by a short
  notice, the withheld content is not stored or embedded, and the event is
  audited.
- **History fallback.** Retrieval failure, or no authorized result for a message
  that references earlier conversation, continues from the immediate messages,
  tells the Person history was unavailable, and routes history-dependent
  mutations through a security assessment before the proposal.
- **Observability.** LiteLLM requests carry `user`, `metadata` (tags, trace_id,
  session_id, spend_logs_metadata with user, conversation, workflow and turn ids)
  and matching `x-litellm-*` headers. Orchestration decisions, escalations,
  reviews, security assessments, history gaps and visibility withholds are written
  to the `orchestration_events` table.
- Unchanged: structured diffs, explicit approval, version re-checks, idempotency.

## Crash-resume verification note (2026-11-15)

Local docker check: a turn killed mid-ModelCall resumed on restart and
succeeded without resubmission (one activity replay, no duplicate turn); a kill
during Deliver re-ran only the in-flight embedding. Dapr control plane and
daprd must be >= 1.18 — 1.16.x/1.17.3 fail `CompleteWorkflowTask` with
durabletask-go v0.15.1 (chart pin is 1.18.10).

## Operator actions

1. Add the new aliases to `litellm_models` in the `K8S_TFVARS` CI secret, using
   the values in `terraform/k8s/k8s.tfvars.example`: `pl-coordinator`,
   `pl-responder-fast`, `pl-embed`, `pl-strong`.
2. After the pipeline finishes, verify on the cluster:
   - Repeat the kill test with `kubectl delete pod` mid-turn.
   - Confirm the Dapr scheduler PVC persists.
   - Confirm LiteLLM `/mcp/` returns a tools list (a 404 there fails turns).
   - Note `/v1/jobs/{id}/result` can report succeeded a few seconds before
     history embeddings finish writing.
