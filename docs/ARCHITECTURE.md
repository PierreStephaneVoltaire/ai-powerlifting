# IF Architecture

IF is a FastAPI service that accepts Discord, OpenWebUI, and OpenAI-compatible HTTP chat traffic. The current runtime uses an opencode planning stage, direct OpenRouter calls for social/domain responses, opencode build mode for technical work, and Python MCP servers for deterministic tools.

## Request Flow

```text
Client (Discord / OpenWebUI / HTTP)
  -> Channel listener
  -> Debounce
  -> Dispatcher
  -> /v1/chat/completions pipeline
  -> Plan
     - write {mount}/{guild_id}/{channel_id}/history.md
     - run opencode plan mode with deepseek/deepseek-v4-flash
     - inject specialists and models/model_ids.txt
     - parse plan.md
  -> Route
     - social: direct OpenRouter call with IF personality + core directives
     - domain: direct OpenRouter tool loop with specialist directives + MCP tools
     - technical: opencode build mode, opencode plan reviewer, one retry on RETRY
  -> Deliver
     - chunk response
     - send Discord/OpenWebUI/API response
     - upload generated technical artifacts from the session directory
```

Discord status embeds are preserved around message receipt, route/model selection, tool calls, and technical build/review execution.

## Planning

The planner writes `plan.md` with YAML front matter:

```yaml
intent_summary: "short summary"
interaction_type: "social|domain|technical"
specialist: "powerlifting_coach"
thinking_mode: false
selected_model: "provider/model-id-from-model_ids.txt"
```

The body of `plan.md` is the self-contained prompt for the next stage. The parser rejects unknown interaction types, unknown specialists, empty prompts, and selected models not present in `models/model_ids.txt`.

## Model Selection

There is no separate model router. The planning prompt injects the eligible model IDs from `models/model_ids.txt`; the planner chooses the concrete model for the next stage.

`deepseek/deepseek-v4-flash` is fixed for planning and review. It does not need to be in `model_ids.txt` unless it should also be eligible for normal execution.

## Specialists

Specialists remain data-driven:

```text
specialists/{slug}/specialist.yaml
specialists/{slug}/agent.j2
```

`scripts/generate_opencode_agents.py` renders these into `.opencode/agent/{slug}.md`. Generated agents include IF personality, specialist posture, directives/tool metadata, and no router preset instructions.

Domain responses render the specialist prompt directly and expose only the specialist's declared MCP tools.

## MCP Tools

Each tool category runs as a subprocess MCP server:

- `health`
- `finance`
- `diary`
- `proposals`
- `temporal`
- `supplement_research`

`tools/mcp_server.py` is the generic server wrapper. It loads tool schemas from `get_schemas()` or `tool_meta.yaml` and dispatches calls to the existing async `execute(name, args)` functions.

The app-side `mcp_runtime.MCPToolManager` starts all configured servers at startup, indexes tools by name, dispatches tool calls, and reloads servers through:

```text
POST /admin/reload-tools
POST /admin/reload-tools?category=health
```

## Powerlifting Critical Path

The Powerlifting App depends on the health MCP server for:

- `powerlifting_filter_categories`
- `analyze_powerlifting_stats`
- `export_program_history`
- template list/get/apply/evaluate tools

FastAPI stats endpoints call the MCP manager directly:

```text
GET  /api/health/stats/categories
POST /api/health/stats/analyze
```

The TypeScript backend still uses IF's HTTP API. `X-Direct-Tool-Invoke: true` now dispatches through MCP instead of direct Python imports.

## Storage

- LanceDB stores user facts and operator context.
- ChromaDB stores health-document RAG content.
- SQLite stores webhook and activity state.
- DynamoDB stores directives, health, finance, diary, proposals, and model metadata.

All DynamoDB writes that include numeric payloads must recursively convert Python floats to `Decimal(str(value))`.

## Preserved Channel Behavior

The channel layer is unchanged in shape:

- Discord listener and slash command registration.
- OpenWebUI listener.
- Debounce batching.
- Platform context for Discord status embeds.
- Chunking and delivery.

Slash commands still route through the completions pipeline or direct command handlers, but tool execution is MCP-backed.

