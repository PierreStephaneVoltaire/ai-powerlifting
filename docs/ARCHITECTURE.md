# Architecture Deep Dive

Technical map of IF as it currently runs. For the human overview, read the [README](../README.md). For agent-facing implementation context, read [`.claude/CLAUDE.md`](../.claude/CLAUDE.md).

---

## Runtime Shape

IF is a FastAPI service that accepts OpenAI-compatible chat requests and channel events, routes them through an OpenCode-based execution flow, and delivers text/files back to the originating platform.

```text
Client
  Discord / OpenWebUI / HTTP
    -> listener or /v1/chat/completions
    -> command parsing + interceptor
    -> run_if_flow()
    -> session directory resolution
    -> runtime context assembly
    -> OpenCode planner
    -> route:
         social    -> direct OpenRouter chat
         domain    -> specialist OpenCode run
         technical -> OpenCode build run + review
    -> optional HANDOFF_REQUIRED child runs
    -> FILES: parsing + attachment materialization
    -> chunked delivery
```

The normal request path is `api/completions.py -> flow.runner.run_if_flow`. Older OpenHands SDK modules still exist in the repo, but they are not the primary chat execution path.

---

## Session Workspace

Every conversation gets a persistent local workspace under `OPENCODE_WORKSPACE_BASE`.

For Discord, the path is stable by guild/channel. For OpenWebUI and direct API calls, the path is derived from request identifiers or cache keys.

Important files:

| File | Owner | Purpose |
| --- | --- | --- |
| `history.md` | runner | Incremental conversation history, edit-aware for Discord |
| `history.json` | runner | Structured history backing file |
| `plan.md` | planner | YAML-front-matter route/model/specialist decision |
| `opencode.json` | runner | Per-run OpenCode MCP config |
| `response.md` | domain/technical run | Final user-facing output |
| `review.md` | technical reviewer | Retry signal for technical runs |
| `.if/status.log` | OpenCode run | Progress lines forwarded to Discord status embeds |

Generated deliverables stay inside the session directory. `FILES:` metadata in responses is stripped before delivery and converted into attachment records.

---

## Planning

The planner is an OpenCode `plan` agent run. It reads `history.md`, receives IF personality/core directives, runtime context, a specialist catalog, and eligible model IDs from `models/model_ids.txt`.

It must write `plan.md` with this front matter:

```yaml
---
intent_summary: "short summary"
interaction_type: "social|domain|technical"
specialist: "powerlifting_coach"
thinking_mode: false
selected_model: "provider/model-id"
---
```

Validation happens in `flow/plan.py`. The selected model must be present in the eligible model list and the specialist must be known.

Planner failure is fail-closed. `PlannerFailure` is caught in `run_if_flow`, a red Discord status is sent, and the user gets an explicit planner error. The runner does not fall back to a guessed social answer.

---

## Routing

### Social

Social traffic is answered through a direct OpenRouter chat call. It receives:

- IF personality prompt
- Core directives
- Runtime context
- Planner prompt

No domain MCP tools are loaded.

### Domain

Domain traffic runs the selected specialist through OpenCode. The runner builds a prompt with:

- Current IF personality
- Core directives
- Specialist prompt rendered from `specialists/<slug>/agent.j2`
- Directives filtered by the specialist's `directive_types`
- Runtime context, memory rules, media rules, and thinking-mode skills when active
- Tool protocol and allowed schemas

Before the run starts, `write_opencode_config()` writes `opencode.json` for that workspace. It includes only the selected specialist's MCP servers and only the declared tool names for that specialist.

If a domain run returns `HANDOFF_REQUIRED` blocks, the runner parses them, validates the targets, executes child domain runs in order, and then runs a synthesis pass.

### Technical

Technical traffic runs OpenCode `build` in the workspace. It must write `response.md`.

After build, the runner asks OpenCode `plan` to review the output and write `review.md`.

- `OK` on line 1 accepts the build.
- `RETRY` on line 1 triggers one retry with review context.

This path is for code, files, shell work, debugging, build/test work, and generated artifacts.

---

## Scoped MCP Configuration

Local tools live under `tools/<plugin>/`. Each folder with a `tool.py` can be exposed as a Python MCP server through `tools/mcp_server.py`.

`flow/opencode_config.py` groups allowed tool names by their backing category and writes an OpenCode config like:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "if_health": {
      "type": "local",
      "command": ["python", "/app/tools/mcp_server.py", "health"],
      "environment": {
        "IF_TOOLS_ROOT": "/app/tools",
        "IF_MCP_ALLOWED_TOOLS": "health_get_session,health_update_session",
        "PYTHONPATH": "/app/src:/app"
      },
      "enabled": true,
      "timeout": 60000
    }
  }
}
```

The server filters `list_tools` using `IF_MCP_ALLOWED_TOOLS`, so OpenCode cannot see the rest of the plugin just because it shares a folder.

External MCP servers are defined in `specialists/mcp_servers.yaml` and included only when a specialist declares them.

Native OpenCode MCP tool names are server-prefixed, such as `if_health_health_get_session`. Prompts also expose a shell fallback:

```bash
PYTHONPATH=<app-src:project-root> python -m mcp_runtime.invoke_tool <tool_name> '<json_args>'
```

The app also starts MCP managers at startup to build a tool index, power slash commands, and serve runtime calls.

---

## Specialists

Specialists are discovered from `specialists/*/specialist.yaml`.

Important fields:

| Field | Meaning |
| --- | --- |
| `description` | Planner-facing routing description |
| `preset` | Domain/model grouping metadata |
| `tools` | Exact local tool names allowed for this specialist |
| `mcp_servers` | Local/external MCP categories to attach |
| `directive_types` | Directive classes loaded into the prompt |
| `context_builder` | Optional prefetch hook for specialist-specific context |
| `skills` | AgentSkills packages referenced by the prompt/runtime |

Rendered specialist prompts come from `agent.specialists.render_specialist_prompt`.

Current important routing rules:

- `powerlifting_coach` handles training reads, coaching, analysis, and explicit health/training writes through scoped health MCP tools.
- `finance_write` handles explicit finance snapshot mutations.
- `financial_analyst` handles market/financial analysis with Yahoo Finance and Alpha Vantage MCPs.
- `research_assistant` can use supplement research and research-model behavior.
- `media_reader` handles image/file analysis when an attachment requires vision.

Specialists do not call SDK delegation tools in the OpenCode path. If another specialist is needed, they write `HANDOFF_REQUIRED`.

---

## Runtime Context

`flow/context.py` builds the compatibility block injected into planner and OpenCode prompts.

It can include:

- Current diary/training/finance signals
- LanceDB operator facts relevant to the latest message
- Upload manifests
- Runtime compatibility notes mapping old tool names to current protocols
- Runtime memory CLI commands
- Media protocol text
- Thinking-mode addenda and skills

Runtime memory CLI:

```bash
python -m flow.runtime_tool user_facts_search '<json>'
python -m flow.runtime_tool user_facts_add '<json>'
python -m flow.runtime_tool user_facts_supersede '<json>'
python -m flow.runtime_tool capability_gap_log '<json>'
```

These are intentionally narrow. They let OpenCode runs interact with durable operator memory without exposing the whole old SDK tool surface.

---

## Data Stores

| Store | Use |
| --- | --- |
| LanceDB | User facts, semantic search, context-scoped memory |
| ChromaDB | Legacy memory store and health-document RAG |
| DynamoDB `if-core` | Directives, proposals, model registry data |
| DynamoDB health/finance/diary tables | Domain state |
| SQLite | Webhook/channel registration and activity |
| Local workspace | Per-conversation history, plans, outputs, files |

DynamoDB writes must convert Python floats to `Decimal(str(value))`. Reuse existing conversion helpers in health/finance/model stores rather than writing raw floats.

---

## Directives And Reflection

Directives are versioned behavioral rules stored in DynamoDB. They are priority-tiered and filtered by `directive_types`.

The reflection system can run periodically, post-session, or on demand through slash commands. It tracks:

- Behavioral patterns
- Capability gaps
- Opinions and disagreements
- Session reflections
- Growth signals
- Directive proposals

Proposals are reviewed in the proposals portal before changing runtime behavior.

---

## Channels And Delivery

| Platform | Current role |
| --- | --- |
| Discord | Main interactive channel, slash commands, status embeds |
| OpenWebUI | Polling integration |
| HTTP | OpenAI-compatible API |

Dispatcher flow:

```text
listener -> debounce -> translator -> completions pipeline -> chunker -> delivery
```

Discord status embeds are emitted for model selection, domain/technical starts and completions, planner/domain failures, and tool progress lines from `.if/status.log`.

Messages are chunked to 1500 characters for Discord. Attachments are materialized from generated file references.

---

## Models

Model IDs live in `models/model_ids.txt`. The planner chooses the execution model from that list.

The model registry still stores OpenRouter metadata in DynamoDB: context size, max output, price, modalities, tool support, caching support, latency, and throughput.

Tier/preset managers still exist and are used by legacy paths and metadata flows, but the current request path relies on planner-selected concrete model IDs rather than the old `@preset/*` specialist router.

---

## Tool Plugins

Each local plugin is a folder under `tools/` with metadata and an async `execute(name, args)` entrypoint.

Common plugins:

| Plugin | Purpose |
| --- | --- |
| `health` | Training program CRUD, sessions, competitions, imports, templates, glossary, analytics, RAG, conversions |
| `finance` | Profile, goals, accounts, investments, cashflow, tax, insurance, net worth |
| `diary` | Diary entries and signal computation |
| `proposals` | Directive proposal CRUD and implementation plans |
| `supplement_research` | Supplement corpus search |
| `temporal_*` | Dates, durations, timezones, city time, ages, Unix timestamps |

Plugins can still expose schemas for direct app-side dispatch. The current OpenCode specialist path reaches them through scoped MCP servers or the shell bridge fallback.

---

## Deployment

The app is deployed to a personal k3s cluster.

- Terraform manages Kubernetes/AWS resources.
- Packer builds Docker images.
- Portals run as separate frontend/backend services.
- Prometheus, Loki, Grafana, and Discord status embeds cover observability.

Minimum local development requirements:

- Python 3.12
- `OPENROUTER_API_KEY`
- access to configured storage backends for production-like runs
- `opencode` on `PATH` for normal planner/domain/technical execution
