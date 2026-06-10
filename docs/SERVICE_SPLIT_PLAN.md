# Service Split Plan

**Status:** Planning document — feasibility and packaging analysis for splitting the current monolithic `if-agent-api` pod into smaller services and pods.

This document inventories every feature the current API server (`if-agent-api`, FastAPI on port 8000) does today, beyond the OpenAI-style chat completion responses, so we can plan how to break it apart. It does not commit to a particular split — it's the input to that decision.

---

## What the API server does today

The current `if-agent-api` pod (built by `docker/build.pkr.hcl` from `app/`, deployed to the `if-portals` namespace as a single `replicas=1` Deployment with three PVCs — `data-storage`, `sandbox-storage`, `conversations-storage`) handles the following in one Python process:

1. Accepts OpenAI-compatible `/v1/chat/completions` and `/v1/models` HTTP traffic.
2. Runs the **Discord gateway**: a long-lived `discord.py` client that opens a WebSocket to Discord, receives events, and dispatches them through the channel coordinator.
3. Runs the **OpenWebUI poller**: an `httpx` polling loop that fetches new chat messages on a 5-second interval.
4. Runs the **Discord channel coordinator** (45-second classifier debounce + 300-second max-wait) and per-channel state machines in the `if-agent-execution-registry` DynamoDB table.
5. Runs the **batch classifier** (planner-style LLM call) and **decision applier** (per-decision handler dispatching to social-response vs. task-worker).
6. Runs the **task worker**, which calls `flow/runner.py::execute_route()` to drive `social`/`domain`/`technical` runs.
7. Spawns the **OpenCode subprocess** (`asyncio.create_subprocess_exec("opencode", ...)`) for planner/domain/technical runs — the heavy, blocking thing.
8. Spawns **MCP stdio server subprocesses** (one per category: `health`, `finance`, `diary`, `proposals`, `supplement_research`, `temporal_*`, `tarot`) and holds the persistent stdio sessions in the `mcp_runtime/manager.py` in-process manager.
9. Serves the **OpenAI-compatible models list** (`/v1/models`) and a parallel `/api/v1/models` route from the `storage/model_registry.py` cache.
10. Serves **static file delivery** for the agent sandbox (`/files/sandbox/{conversation_id}/{filepath:path}`) and per-workspace files (`/files/workspace/{chat_id}/{filepath:path}`).
11. Hosts the **webhook registration REST API** (`/v1/webhooks/*`) and the **directives REST API** (`/v1/directives/*`), the **template-imports REST API** (`/v1/health/template-imports/*`), and the **admin tool-reload endpoint** (`POST /admin/reload-tools`).
12. Owns the **slash command tree** (`/end_convo`, `/clear`, `/pondering`, `/chat_history`, `/reflect`, `/gaps`, `/patterns`, `/opinions`, `/growth`, `/meta`, `/tools`, `/import`, `/template`, `/program_archive`, plus dynamic per-MCP-tool and per-specialist commands up to Discord's 100-command cap).
13. Runs the **heartbeat runner** — a background thread that scans channel activity and posts proactive "pondering" messages after the configured idle window.
14. Runs the **reflection engine** — periodic (default 6h), post-session, and on-demand reflection cycles that drive `pattern_detector` → `opinion_formation` → `_analyze_capability_gaps` → `meta_analyzer` → `growth_tracker`.
15. Runs the **model registry** — periodic `_periodic_stats_refresh()` (default 1800s) and `_periodic_model_seed()` (default 3600s) that re-fetch OpenRouter `/api/v1/models/{id}/endpoints` and `seed_models.py` runs.
16. Runs the **conversation summarizer** (`memory/summarizer.py`) as a fire-and-forget background task after each request.
17. Owns the **LanceDB user-fact store**, including the per-context_id table creation, the embedding model warmup, the in-memory cache, and the `agentic_search()` path.
18. Owns the **outbound queue** (`channels/outbound_queue.py`) — a per-channel lock-protected outbox that drains the `if-agent-execution-registry` table to `deliver_to_channel` for Discord.
19. Owns the **Discord status embed system** (`channels/status.py`) — `contextvars`-propagated embeds that fire on every model selection, classifier, intent, task, subagent, tool, and enqueue event.
20. Hosts the **app sandbox manager** (`app_sandbox/local.py`) which is mostly a no-op now (`LocalSandbox` only initialises the workspace dir).

### External services it already talks to

- **OpenRouter** (`https://openrouter.ai/api/v1`) for LLM chat and per-model endpoint stats.
- **OpenCode binary** on `$PATH` (the actual planner and execution engine).
- **AWS DynamoDB** for 13 tables (`if-core`, `if-models`, `if-webhooks`, `if-proposals`, `if-health`, `if-health-templates`, `if-sessions`, `if-finance`, `if-diary-entries`, `if-diary-signals`, `if-agent-execution-registry`, `if-powerlifting-analysis-cache`, plus the directives tier-table).
- **AWS S3** for health video buckets and the supplement research PDF corpus.
- **LanceDB** (filesystem under `MEMORY_DB_PATH`) for the user-fact store and embeddings.
- **SQLite** (WAL, SQLModel under `STORAGE_DB_PATH`) for routing cache, activity log, and the legacy webhook records.
- **ChromaDB** (legacy) under `MEMORY_DB_PATH` for the deprecated RAG and the health-document RAG corpus.
- **Discord Gateway** (WebSocket) for the bot.
- **OpenWebUI** (HTTP polling).
- **uvx-launched MCP servers**: `mcp-server-time`, `awslabs.aws-documentation-mcp-server`, `mcp-yahoo-finance`, `alphavantage-mcp`.

---

## Feature inventory and split potential

Each row is one feature that could be lifted out. The "Split?" column says whether it makes sense, with the reason.

| # | Feature | Today | Code | Split? | If split, it would look like |
|---|---------|-------|------|--------|------------------------------|
| 1 | **OpenAI chat completions** | `POST /v1/chat/completions` | `api/completions.py` | Keep in the main pod, but its body should call into the runner/orchestrator over HTTP once those are split. | No new service — this is the public entry point. Becomes a thin shim that forwards to `runner-service` and `task-service`. |
| 2 | **OpenAI `/v1/models` list** | `GET /v1/models` | `api/models.py` reads `ModelRegistry._cache` | **Yes — trivial** | Stand up a `models-service` that exposes `GET /v1/models` from the `if-models` DynamoDB table (or a Redis cache). No LLM, no Discord, no OpenCode. Tiny memory, scales to 0 easily. |
| 3 | **Files API** (sandbox + workspace) | `GET /files/sandbox/...`, `GET /files/workspace/...` | `api/files.py` | **Yes** | A `files-service` that serves files from the same PVCs (or from S3 once uploads move). Pure static-serving, scales to 0. |
| 4 | **Webhooks CRUD** | `POST /v1/webhooks/register`, `GET /v1/webhooks`, `DELETE /v1/webhooks/{id}`, `POST /v1/webhooks/{id}/restart` | `api/webhooks.py` | **Yes — easy** | `webhooks-service` owns the `if-webhooks` DynamoDB table and exposes the full CRUD surface. The Discord listener and the OpenWebUI poller call it over HTTP for `list_active()`. Keeps the existing `WebhookStore` protocol. |
| 5 | **Directives CRUD** | `/v1/directives/*` (10 endpoints) | `api/directives.py` | **Yes — but careful** | `directives-service` owning `if-core`. Already has a sibling UI in `utils/directives-portal/` that consumes it. The "in-flight" directive list is loaded into every API pod at startup, so the runtime prompt path needs to keep using a local cache (or a `directives` Redis stream). |
| 6 | **Template imports** | `POST /v1/health/template-imports`, `GET /v1/health/template-imports/{job_id}` | `api/template_imports.py` | **Yes — but coupled to the agent runtime** | The current `template_imports.py` calls `run_specialist_flow` to drive a domain run. If the agent runtime is split out (see #11), this service needs to POST a job into it and poll a status endpoint. Otherwise, leave it on the main pod. |
| 7 | **Admin tool reload** | `POST /admin/reload-tools` | `api/admin.py` | **No — keep in main** | This reloads the in-process MCP manager. Once MCP servers are split out, this becomes a no-op or a per-service restart signal. |
| 8 | **Discord gateway** (`discord.py` client, WebSocket, slash command tree, message/edit events) | Long-lived task started in `lifespan` | `channels/listeners/discord_listener.py`, `channels/manager.py`, `channels/slash_commands.py` | **Yes — high value** | A standalone `discord-gateway` pod running the `discord.py` client, exposing a small internal API for the agent runtime to look up `channel_id → conversation_id`. The WebSocket + slash command tree are independent of LLM execution and can run on a tiny pod. |
| 9 | **OpenWebUI poller** | 5s polling loop | `channels/listeners/openwebui_listener.py` | **Yes — high value** | A standalone `openwebui-gateway` pod, also a thin process. Same idea as the Discord gateway. |
| 10 | **Channel coordinator** (45s debounce, 300s max-wait, classifier-lock state machine) | Started in `lifespan`, per-channel state in `if-agent-execution-registry` | `channels/channel_coordinator.py`, `channels/execution_store.py` | **Yes — careful** | Standalone `classifier-orchestrator` pod. The "real" per-channel state already lives in DynamoDB so a single instance is fine, but if we want HA then the `_active_classifier_owners` lock has to move to DynamoDB or Redis too. Would own `init_channel_coordinator` and the per-event scheduling loop. |
| 11 | **Agent runtime** (planner + routes + handoffs + FILES extraction) | Called from `process_chat_completion_internal` and `task_worker` | `flow/runner.py`, `flow/plan.py`, `flow/opencode.py`, `flow/context.py`, `flow/direct_llm.py` | **Yes — central target** | Standalone `agent-runtime` pod. Receives a `run_if_flow` request over HTTP, runs the planner, picks the route, runs it, and returns the response + file refs. The OpenCode subprocess call (currently `asyncio.create_subprocess_exec("opencode", ...)`) would be replaced with an HTTP call to `opencode-runner` (see #12). |
| 12 | **OpenCode subprocess execution** | One subprocess per planner/domain/technical run, default 900s timeout | `flow/opencode.py` calls `asyncio.create_subprocess_exec(...)` | **Yes — already started** | The `utils/opencode-runner/` Rust binary already implements this as a Fission one-shot job. The `run_opencode` Python wrapper needs an HTTP-client mode. The pod scales to zero between requests. |
| 13 | **Outbound queue** | `outbound_queue.schedule_drain` writes to `if-agent-execution-registry`, drains to `deliver_to_channel` | `channels/outbound_queue.py` | **Yes — but coupled to delivery** | Standalone `outbound-dispatcher` pod. Owns the outbox table scan loop. The delivery function is the part that touches Discord, so this service needs either the `discord.py` client (couples it back to the gateway) or a callback to the gateway. Cleanest: outbound service calls the gateway's internal `POST /internal/deliver` endpoint. |
| 14 | **Slash command handling** | Decorated `@app_commands` registered on a `CommandTree` per Discord client | `channels/slash_commands.py` (567 lines) | **Yes — moves with the gateway** | The slash command tree is owned by the `discord.py` client, so it stays in the `discord-gateway` pod. The actual command logic (e.g. `/reflect` calls `reflection_engine`, `/end_convo` calls `routing.cache.reset`) becomes an HTTP call back to the `agent-runtime` or to a small `commands-service`. |
| 15 | **Status embeds** (17 `StatusType` events) | `channels/status.py` reads `ContextVar` and `asyncio.run_coroutine_threadsafe` to send | `channels/status.py` | **Partially** | The embed-sender must run in a process that has the Discord client. So it stays in the `discord-gateway` pod. The trigger side (`send_status(...)`) is everywhere; if anything, normalise the calls into a thin HTTP POST so off-process callers (e.g. `agent-runtime`, `outbound-dispatcher`) can fire them. |
| 16 | **Storage backends** (DynamoDB stores, LanceDB, SQLite, ChromaDB) | Multiple modules under `storage/`, `memory/`, `routing/` | `storage/dynamodb_backend.py`, `memory/user_facts.py`, `routing/cache.py`, etc. | **Yes — but high effort** | This is the biggest cross-cutting concern. Each DynamoDB table has its own access patterns (transactions, GSIs, scan vs. query). Splitting this requires either a) per-domain "data services" that own their table and expose a typed API, or b) keeping direct DynamoDB access in each pod. Option (a) is the textbook microservice split but doubles the latency and the code. (b) is the "modular monolith on multiple pods" pattern. |
| 17 | **MCP plugin servers** (one stdio subprocess per category: `health`, `finance`, `diary`, `proposals`, `supplement_research`, `temporal_*`, `tarot`) | Started by `mcp_runtime/manager.py::start_all`; each is `python tools/mcp_server.py <category>` | `mcp_runtime/manager.py`, `tools/mcp_server.py` | **Yes — natural target** | Each plugin is a folder with `tool.py` + `get_schemas()`. Today it's invoked as a stdio subprocess inside the API pod. The natural split is: (a) keep them as stdio but run as sidecars in the same pod, (b) repackage each as an HTTP MCP server and deploy each one as its own pod, (c) do per-domain (e.g. one `mcp-health` pod, one `mcp-finance` pod). Option (c) gives independent scaling — the 65+ health tools have a very different load profile from the 2 diary tools. |
| 18 | **External MCP servers** (`time`, `aws_docs`, `yahoo_finance`, `alpha_vantage`) | uvx-launched from `specialists/mcp_servers.yaml` | `mcp_runtime/manager.py` reads the yaml | **Yes — already separate** | These are independent processes today (spawned by uvx). Move them to their own pods. The MCP config still names them, but with an HTTP transport instead of stdio. |
| 19 | **User facts (LanceDB)** | `memory/user_facts.py`, `memory/lancedb_store.py`, `memory/embeddings.py` | `memory/` | **Yes — careful** | The user-fact store is read by the agent runtime (semantic search) and written by the CLI/runtime tool. The `runtime_tool.py` CLI path is the only safe way to add/supersede facts. A standalone `memory-service` exposing `POST /facts/search`, `POST /facts/add`, `POST /facts/supersede` is clean. Embedding model warmup happens there. |
| 20 | **Legacy memory (ChromaDB)** | `memory/store.py` | `memory/store.py` | **No — keep until removed** | Currently a parallel store to LanceDB. Don't split until the migration is done. |
| 21 | **Health-document RAG (ChromaDB)** | `tools/health/rag.py` | `tools/health/rag.py` | **Yes — natural target** | One process, one corpus, one lifecycle. Either keep it as a sidecar to the `mcp-health` pod or stand up a `health-rag` service. The corpus is on disk under `tools/health/docs`. |
| 22 | **Heartbeat runner** | Background thread started in `lifespan` | `heartbeat/runner.py` (333 lines) | **Yes — high value** | A `heartbeat-service` pod that polls `ActivityTracker` and posts messages through the `discord-gateway`. Currently it calls `_deliver_heartbeat` directly via `asyncio.run_coroutine_threadsafe` to the same event loop as the Discord client. If the gateway is split, this becomes an HTTP POST. |
| 23 | **Reflection engine** | Background thread started in `lifespan`, also invoked from `process_chat_completion_internal` and from slash commands | `agent/reflection/engine.py` (526 lines) + 5 sibling modules | **Yes — high value** | A `reflection-service` pod. Owns the periodic scheduler, the post-session trigger, the `/reflect`/`/gaps`/`/patterns`/`/opinions`/`/growth`/`/meta`/`/tools` command logic. Currently shares the user-fact store and httpx client with the API pod. The CLI callers (`/reflect`) would POST to it. The background engine reads the user-fact store over HTTP. |
| 24 | **Model registry / seed** | `_periodic_stats_refresh()` + `_periodic_model_seed()` background tasks | `main.py` lifespan, `scripts/seed_models.py`, `storage/model_registry.py` | **Yes — easy** | A `model-registry-service` pod. Owns `if-models`. Periodic refresh + seed run here. `/v1/models` reads from a cache it exposes. |
| 25 | **Conversation summarizer** | Fire-and-forget after each request, uses LanceDB | `memory/summarizer.py` | **Yes — easy** | A `summarizer-service` pod. Receives conversation messages, returns a summary, writes to user facts. Currently invoked as `asyncio.create_task(...)` from `process_chat_completion_internal`. |
| 26 | **Slash command execution** | `/reflect` calls `reflection_engine.run_reflection_cycle`, etc. | `channels/slash_commands.py` | **Partially** | The slash command tree (registration, autocomplete) stays in the Discord gateway. The handler bodies move to whichever service owns the feature (reflection → `reflection-service`, `/end_convo` → `routing-service`, `/import` → `health-service`). |
| 27 | **Routing cache** | Per-conversation cache_key → preset, tier, pin state | `routing/cache.py` | **Yes — easy** | A `routing-service` pod owning the SQLite cache. Tiny pod, scales to 0. |
| 28 | **App sandbox manager** | `app_sandbox/local.py` is mostly a no-op now | `app_sandbox/local.py` | **No — keep in main** | Currently just initialises the workspace dir. No real work to do. |
| 29 | **Legacy `mcp_servers/config.py`** | `PRESET_MCP_MAP` | `mcp_servers/config.py` | **No — deprecate** | This is a support module. Don't split, just remove over time. |
| 30 | **Legacy `presets/loader.py`** | OpenRouter preset manager | `presets/loader.py` | **No — keep in main** | Loads preset YAMLs at startup. Used by the OpenCode config writer. Trivial, no need to split. |
| 31 | **Main `_deliver_heartbeat`** | Inline in `main.py` | `main.py:34-83` | **No — moves with the gateway** | Once the Discord gateway is split, the heartbeats are delivered over HTTP. |
| 32 | **Periodic config / model checksum annotations** | `checksum/config` and `checksum/model-config` pod annotations | `terraform/k8s-deployments.tf` | **No — k3s lifecycle** | This is a Terraform concern, not a service concern. |

---

## Already-standalone pieces

These are already in their own pod or Lambda and are NOT in the scope of this split:

- `utils/opencode-runner/` — Rust Fission one-shot HTTP server (`POST /v1/opencode/execute`, `GET /health`). Currently NOT wired into the agent runtime (the Python `flow/opencode.py` still spawns OpenCode as a subprocess). **This is the easy first split.**
- `utils/video-lambda/` — Python AWS Lambda. S3 trigger for video thumbnail generation against the `if-health` and `if-sessions` tables.
- `utils/main-portal/`, `finance-portal/`, `diary-portal/`, `proposals-portal/`, `powerlifting-app/`, `directives-portal/` — six TypeScript/Node.js portals, each its own frontend+backend Deployment.
- `terraform/k8s-observability.tf` — Prometheus, Loki, Promtail, Grafana.

---

## Suggested first-move splits

If you want to start carving things out without changing behaviour, these are the lowest-risk wins:

### Tier 0 — already-built, just not wired in

- **Wire `opencode-runner` into the Python agent runtime.** Add an HTTP transport to `flow/opencode.py::run_opencode`. The Rust pod already exists; the only work is the Python side. Saves 900s of subprocess holding inside the API pod.

### Tier 1 — extract a stateful worker with no API surface today

- **Heartbeat service.** Take `heartbeat/runner.py` out as-is. The only coupling is `_deliver_heartbeat` which currently calls into the in-process Discord event loop. Replace with an HTTP POST to the (future) Discord gateway. The activity tracker, user facts store, conversation cache, webhook store are all DynamoDB/SQLite, so the service can run on its own.
- **Reflection service.** Take `agent/reflection/engine.py` and its five sibling modules. The only API surface is the slash command handlers — which can move to the Discord gateway and call the new service over HTTP.
- **Model registry service.** Move the periodic refresh + seed into its own pod. Expose `GET /v1/models` from it and let the API pod forward. (Or replace the API pod's `/v1/models` route with a direct call to the registry service.)

### Tier 2 — extract the gateway pods

- **Discord gateway.** Take `channels/listeners/discord_listener.py`, `channels/manager.py`, and the slash command tree registration. The gateway owns the WebSocket connection and the slash command tree; the handler bodies call back into `agent-runtime` and `reflection-service` over HTTP. Saves the long-lived WS connection from the API pod.
- **OpenWebUI gateway.** Take `channels/listeners/openwebui_listener.py`. Same shape as the Discord gateway, much simpler.

### Tier 3 — extract the orchestration

- **Channel coordinator service.** The classifier-debounce + max-wait state machine. Already serialised to DynamoDB. Single replica is fine, but the active-classifier lock needs to move to DynamoDB conditional writes.
- **Outbound dispatcher service.** Owns the per-channel outbox. Calls back to the Discord gateway to deliver.

### Tier 4 — extract the MCP plugin servers

- One HTTP MCP server per plugin folder, each in its own pod, gated by `IF_MCP_ALLOWED_TOOLS`. The Python agent runtime becomes an MCP *client* that talks to them over HTTP instead of stdio.

### Tier 5 — extract the data layer (highest cost)

- Per-table or per-domain data services. Don't do this unless the rest of the split is in place.

---

## What the API pod does after a full split

After a clean cut, the `if-agent-api` pod shrinks to:

- A thin shim that exposes `/v1/chat/completions` (and `/v1/models` as a forward) and nothing else.
- Calls into the `agent-runtime` service to do the actual work.
- Optionally, the agent runtime runs in the same pod for very-low-latency social replies and forks to `opencode-runner` for the heavy work.

This is a long path and most of the value is in Tier 0-2.

---

## Open questions

1. **Where do conversation histories live?** Per-conversation directories under `OPENCODE_WORKSPACE_BASE` are mounted as a PVC in the current pod. If the agent runtime moves to a different pod, that PVC must be readable+writable from the new pod (NFS, ReadWriteMany, or a copy-on-write overlay).
2. **How are status events fired cross-pod?** `send_status(...)` currently runs `asyncio.run_coroutine_threadsafe` against the in-process Discord client loop. Once Discord is split, this becomes an HTTP POST. The status payload is small; a per-channel event stream (NATS, Redis pubsub, or a webhook) would work.
3. **Pinned-specialist channels and other webhook settings** are stored in `if-webhooks` per channel_id. A `webhooks-service` owns the table; the gateway reads it on startup to know which channels to listen on. Already correct shape; just need the service split.
4. **Discord library version drift.** If the gateway is split, the rest of the system doesn't need to ship `discord.py`. Smaller image for `agent-runtime`.
5. **Cancelling in-flight OpenCode runs.** The `cancellable_executor.py` is in-process today. Cross-pod cancellation needs a control channel (Redis pubsub, NATS, or a DynamoDB poll). `task_worker.py` already polls `OPENCODE_CANCEL_POLL_INTERVAL_SECONDS`; the same loop can run in a different pod.
