# Architecture Deep Dive

Technical details on how IF's internals work. For a high-level overview, see the [README](../README.md).

---

## Project Layout

```
app/
├── src/
│   ├── main.py              # FastAPI entry point, lifespan init
│   ├── config.py            # All env vars (module-level, os.getenv defaults)
│   ├── logging_config.py    # Centralized logging
│   ├── api/                 # FastAPI routers
│   │   ├── completions.py   # POST /v1/chat/completions (OpenAI-compatible)
│   │   ├── models.py        # GET /v1/models
│   │   ├── files.py         # File serving from sandbox
│   │   ├── webhooks.py      # Channel registration
│   │   ├── directives.py    # Directive CRUD API
│   │   └── admin.py         # POST /admin/reload-tools (hot reload)
│   ├── agent/               # Core agent system
│   │   ├── session.py       # AgentSession, system prompt assembly, execute_agent()
│   │   ├── tool_registry.py # External tool plugin discovery, loading, indexing
│   │   ├── specialists.py   # YAML-based specialist auto-discovery + rendering
│   │   ├── tiering.py       # Context-aware model selection (air/standard/heavy)
│   │   ├── condenser.py     # Conversation summarization
│   │   ├── commands.py      # Slash command definitions
│   │   ├── memory_tools.py  # ChromaDB memory search/add/remove/list
│   │   ├── plugin_runner.py # Subprocess plugin runner helper
│   │   ├── skills.py        # AgentSkills loader (load_skills_from_dir)
│   │   ├── prompts/         # Jinja2 templates + specialist definitions
│   │   │   ├── system_prompt.j2
│   │   │   └── mcp_servers.yaml
│   │   ├── reflection/      # Behavioral feedback loop
│   │   │   ├── engine.py           # ReflectionEngine (periodic, post-session, on-demand)
│   │   │   ├── pattern_detector.py # Behavioral pattern detection
│   │   │   ├── opinion_formation.py
│   │   │   ├── meta_analysis.py
│   │   │   └── growth_tracker.py
│   │   └── tools/           # OpenHands SDK tools
│   │       ├── base.py               # TextObservation base class
│   │       ├── capability_tracker.py # log_gap, list_gaps
│   │       ├── context_tools.py      # get_signals, get_financial_context, get_context_snapshot, get_current_date
│   │       ├── directive_tools.py    # add, revise, deactivate, list
│   │       ├── discovery_tools.py    # discover_tools + use_tool
│   │       ├── file_tools.py         # File read/write/search tools
│   │       ├── media_tools.py        # read_media
│   │       ├── opinion_tools.py      # log_opinion_pair, log_misconception
│   │       ├── session_reflection.py # store_session_reflection
│   │       ├── subagent_sdk.py       # run_subagent_sdk (agentic SDK loop)
│   │       ├── subagents.py          # list_specialists, condense_intent, deep_think, spawn_specialist
│   │       ├── terminal_tools.py     # terminal_execute, terminal_read_file, etc.
│   │       ├── tool_schemas.py       # Registry-backed schema resolution
│   │       └── user_facts.py         # search, add, update, list, remove
│   ├── models/              # Dynamic model routing
│   │   ├── loader.py        # ModelPresetManager + TierConfigManager
│   │   └── router.py        # Smart model selection via fast LLM
│   ├── channels/            # Multi-platform message handling
│   │   ├── dispatcher.py    # translate → agent → chunk → deliver
│   │   ├── delivery.py      # Platform-specific response delivery
│   │   ├── chunker.py       # 1500-char chunk splitting
│   │   ├── debounce.py      # 5-second message batching window
│   │   ├── manager.py       # Listener lifecycle management
│   │   ├── context.py       # Platform context var for status embed threading
│   │   ├── status.py        # Discord status embed system
│   │   ├── slash_commands.py
│   │   ├── listeners/       # discord_listener.py, openwebui_listener.py
│   │   └── translators/     # discord_translator.py, openwebui_translator.py
│   ├── memory/              # Persistent memory
│   │   ├── user_facts.py    # UserFact dataclass + UserFactStore (LanceDB)
│   │   ├── lancedb_store.py # Table management, context-scoped storage
│   │   ├── store.py         # Legacy ChromaDB MemoryStore
│   │   ├── embeddings.py    # Sentence transformer embedding generation
│   │   └── summarizer.py    # Fire-and-forget conversation summarization
│   ├── storage/             # Storage abstraction
│   │   ├── factory.py       # Backend factory
│   │   ├── sqlite_backend.py
│   │   ├── dynamodb_backend.py
│   │   ├── directive_store.py   # DynamoDB directives + cache
│   │   └── model_registry.py   # DynamoDB model metadata + cache
│   ├── routing/             # Request routing
│   │   ├── interceptor.py   # Bypass routing
│   │   ├── cache.py         # Conversation cache
│   │   └── commands.py      # Command parsing
│   ├── app_sandbox/         # Per-conversation shell access
│   │   ├── __init__.py      # init_local_sandbox entry point
│   │   └── local.py         # LocalSandboxManager
│   ├── files/               # FILES: metadata parsing
│   │   └── __init__.py      # FileRef, FilesStripBuffer
│   ├── orchestrator/        # Multi-step execution
│   │   ├── executor.py      # execute_plan (sequential steps)
│   │   ├── analyzer.py      # analyze_parallel (multiple perspectives)
│   │   └── prompts/         # Jinja2 templates for orchestrator subagents
│   ├── presets/             # Legacy preset definitions
│   │   └── loader.py
│   ├── mcp_servers/
│   │   └── config.py
│   ├── heartbeat/           # Proactive engagement
│   │   ├── runner.py        # Idle detection, cooldown, quiet hours
│   │   └── activity.py
│   └── health/              # Fitness/training module
│       ├── program_store.py # DynamoDB program storage
│       ├── rag.py           # ChromaDB RAG for PDFs
│       ├── renderer.py
│       └── tools.py
├── docker/                  # Packer build files
├── terraform/               # Kubernetes + AWS infra
└── main_system_prompt.txt   # Agent personality base prompt
specialists/                 # One subdir per specialist (specialist.yaml + agent.j2)
skills/                      # AgentSkills-compliant packages
models/                      # Dynamic model routing config
├── presets.yaml             # Subagent preset definitions
├── tiers.yaml               # Tier config (air/standard/heavy + media)
└── model_ids.txt            # Model IDs to track
tools/                       # External tool plugins
utils/                       # TypeScript/Node.js utility apps
```

---

## Request Processing Pipeline

`completions.py → process_chat_completion_internal()`:

1. Resolve `cache_key` (from webhook channel_id, chat_id, or content hash) and `context_id`
2. Parse slash commands (`/reset`, `/pondering`, `/reflect`, `/gaps`, `/patterns`, `/opinions`, `/growth`, `/meta`, `/tools`)
3. Run interceptor for bypass routing
4. Track tier with context token estimation
5. Resolve concrete model for the tier via `select_model_for_tier()` (first model in tier's sorted list)
6. Create session with `model_override` and signals injection
7. Execute agent via OpenHands SDK
8. Extract file attachments from `FILES:` metadata
9. Trigger async conversation summarization

---

## System Prompt Assembly

`session.py → assemble_system_prompt()` builds the complete prompt from:

1. **Signals** — current mental health, life load, training status (from `context_tools.py`)
2. **Base personality** — `main_system_prompt.txt`
3. **Operator context** — user facts from LanceDB (semantic search results relevant to conversation)
4. **Conversation history**
5. **Directives** — from DynamoDB DirectiveStore, priority-ordered
6. **Memory protocol** — instructions for fact management
7. **Media protocol** — instructions for handling attachments
8. **Terminal environment** — workspace path, available commands
9. **Pondering addendum** — if in reflective mode

For specialists, the assembly is different:
- Specialist's own Jinja2 template instead of base personality
- Only directives matching the specialist's `directive_types`
- Only the specialist's declared tools and MCP servers
- AgentSkills loaded per the specialist's `skills` config

---

## Model Router

### Model Registry (`storage/model_registry.py`)

DynamoDB-backed registry (`if-models` table) storing metadata for OpenRouter models.

**Fields**: model_id, context_size, max_output_tokens, input/output pricing (per-provider), input/output modalities, tool_support, caching_support, zero_data_retention, throughput, latency.

**Seeding**: `python scripts/seed_models.py` fetches models from OpenRouter API, filters to those in `models/model_ids.txt` with tool support, upserts to DynamoDB. Also fetches per-provider latency/throughput from `/api/v1/models/{id}/endpoints`. Runs at startup.

**Periodic refresh**: Background task refreshes latency/throughput stats every 30 minutes (configurable via `MODEL_STATS_REFRESH_INTERVAL`).

**Sorting strategies**: `price_asc`, `price_desc`, `latency_asc`, `context_size_desc`, `throughput_desc`.

### Presets (`models/presets.yaml`)

Subagent model pools. Each preset defines candidate models and a sorting strategy:

```yaml
presets:
  code:
    models: [anthropic/claude-sonnet-4, google/gemini-2.5-pro]
    sort_by: price_asc
    when: "Code generation, debugging, code review"
```

### Tiers (`models/tiers.yaml`)

Orchestrator model pools. Separate from subagent presets:

```yaml
tiers:
  air:
    models: [openai/gpt-5.4-nano, google/gemma-4-26b-a4b-it]
    sort_by: throughput_desc
    context_limit: 150000
  standard:
    models: [anthropic/claude-sonnet-4.6, google/gemini-3.1-pro-preview]
    sort_by: latency_asc
    context_limit: 200000
  heavy:
    models: [anthropic/claude-opus-4.6, openai/gpt-5.4]
    sort_by: price_asc
    context_limit: 1000000
```

Media tiers (vision-capable) are defined separately under `media_tiers`.

### Selection Paths

| Path | Target | Method |
|------|--------|--------|
| Main agent | `select_model_for_tier()` | Maps tier (0/1/2) → tier config → first model in sorted list. No LLM call. |
| Specialists | `select_model_for_specialist()` | Maps `@preset/X` → YAML preset → fast LLM picks best model from candidates using task intent + metadata. |
| Media | `get_media_tier()` | Picks vision-capable model from media tier pool. |

Fast router model: `anthropic/claude-haiku-4.5` (configurable). Falls back to first-sorted if router disabled or fails. If no YAML preset exists, original `@preset/X` reference passes through to OpenRouter (backward compatible).

---

## Tool System

### OpenHands SDK Pattern

All tools follow `Action` (params) → `Observation` (result) → `Executor` (logic) → `ToolDefinition` (metadata), registered via `register_tool()`.

**TextObservation fix**: All system tool Observations inherit from `TextObservation` (`agent/tools/base.py`) instead of raw SDK `Observation`. This fixes an SDK bug where `to_llm_content` returns empty content because custom Observations store results in named fields but don't override `to_llm_content`. `TextObservation` wires through `visualize.plain` so subclasses only need a correct `visualize` implementation.

**Output limit**: `TOOL_OUTPUT_CHAR_LIMIT` is 200K chars (SDK default 50K causes silent clipping).

### External Tool Plugins

Self-contained packages in `tools/` with `tool.yaml` (metadata) + `tool.py` (exports `execute()`). Two execution modes:

**In-process** (`mode: in_process`): `tool.py` imported directly; `execute()` called in the main process. For heavy plugins with dependencies already in the main venv.

**Subprocess** (`mode: subprocess`): Each plugin ships `pyproject.toml`, `tool_meta.yaml` (static schema), and `_plugin_runner.py`. Registry creates a dedicated `uv` venv on first use and invokes the runner as a subprocess, passing `{"name": ..., "args": ...}` on stdin.

### Adding a Plugin

**In-process:**
1. Create `tools/{name}/tool.yaml` — name, description, version, scope, `mode: in_process`
2. Create `tools/{name}/tool.py` — exports `get_tools()`, `get_schemas()`, `async execute(name, args)`
3. App picks it up on next startup, or `POST /admin/reload-tools` for hot reload

**Subprocess:**
1. Create `tools/{name}/tool.yaml` with `mode: subprocess`
2. Create `tools/{name}/pyproject.toml` with dependencies
3. Create `tools/{name}/tool_meta.yaml` with static schema
4. Create `tools/{name}/tool.py` with `async execute(name, args)`
5. Copy `tools/_plugin_runner.py` into the plugin directory

### Two Agent-Facing Execution Paths

- **SDK path** (agentic specialists): Tools registered via `register_tool()` at import. SDK resolves by PascalCase name.
- **JSON schema path** (non-agentic specialists): `tool_schemas.py` delegates to registry for schema resolution and dispatch. Uses snake_case names.

---

## Specialist System

### Auto-Discovery

`specialists.py` scans `SPECIALISTS_PATH` at import time. Each specialist directory contains:

```
specialists/{name}/
├── specialist.yaml   # Config: description, tools, preset, directive_types, mcp_servers, skills, agentic flag
└── agent.j2          # Jinja2 system prompt template
```

### Delegation Flow

1. `list_specialists` — orchestrator sees all available slugs + descriptions
2. `condense_intent` — fast LLM rewrites user message as focused task for chosen specialist
3. `spawn_specialist` — spawns with:
   - System prompt from `agent.j2`
   - Tools from `specialist.yaml` `tools` field
   - Directives filtered by `directive_types`
   - MCP servers from `mcp_servers` field
   - AgentSkills from `skills` field
   - Model selected via `select_model_for_specialist()`

### Agentic vs Non-Agentic

Specialists with `agentic: true` route to `run_subagent_sdk()` — full OpenHands SDK loop with multi-turn tool dispatch, stuck detection, and event-based iteration via `Conversation.run()`.

Non-agentic specialists use a raw OpenRouter call loop.

### Skills System

AgentSkills-compliant packages loaded per-specialist at spawn time (not globally — context size concern).

```
skills/{skill-name}/
├── SKILL.md       # YAML frontmatter + markdown body
├── scripts/       # Executables (run via uv/uvx/npx)
├── references/    # On-demand reference docs
└── assets/        # Templates/data
```

Loaded via `openhands.sdk.load_skills_from_dir`. Skill scripts run in isolated uv-managed venvs.

---

## Channel Internals

### Message Flow

```
Platform listener → Debounce (5s batching) → Dispatcher
  → Set platform context (contextvars.ContextVar)
  → Translate to ChatCompletionRequest
  → Completions pipeline
  → Chunker (1500 char chunks)
  → Delivery (platform-specific)
```

### Discord Specifics

**Status embeds**: Color-coded embeds sent per event — message received (blue), model selected (green), subagent spawning (yellow), subagent completed (green), subagent/tool failed (red), tool started (purple), tool completed (green). Context propagated through `ThreadPoolExecutor` via `contextvars.copy_context()`. No-ops for non-Discord platforms.

**Attachments**: Downloaded by dispatcher, uploaded to terminal filesystem, referenced via `FILES:` metadata in agent output. `FilesStripBuffer` strips these lines from user-facing responses.

**History**: Dispatcher fetches up to 100 historical messages for context enrichment.

---

## Directive System

DynamoDB `if-core` table. Priority tiers:

| Tier | Label | Purpose |
|------|-------|---------|
| 0 | Core Identity | Fundamental personality traits |
| 1 | Behavioral Rules | How to respond/act |
| 2 | Style & Tone | Voice adjustments |
| 3 | Domain Knowledge | Topic-specific guidance |
| 4 | Situational | Context-dependent rules |
| 5 | Temporary | Time-limited adjustments |

Content is rewritten through LLM for consistent voice. Cached in memory with periodic refresh.

Agent tools: `directive_add`, `directive_revise`, `directive_deactivate`, `directive_list`.

---

## Reflection Engine

`agent/reflection/` — triggers post-session (>5 turns), periodically (6h), on-demand (`/reflect`), or threshold-based (uncategorized facts, gaps, opinions accumulate).

**Cycle**: Pattern Detection → Opinion Formation → Capability Gap Analysis → Meta-Analysis → Growth Tracking.

**Capability gap scoring**: `(frequency × 0.4) + (recency × 0.3) + (impact × 0.3)`. Gaps exceeding `CAPABILITY_GAP_PROMOTION_THRESHOLD` (default 3) are promoted to tool suggestions.

---

## Orchestrator

Multi-step execution in `orchestrator/`:

- **`execute_plan`**: Sequential steps with subagents. Each step sees filesystem state from previous steps.
- **`analyze_parallel`**: Parallel analysis across perspectives (security, performance, architecture, testing, documentation). Each writes to `/home/user/workspace/findings/{perspective}.md`. Synthesizer combines into prioritized report.

---

## Sandbox

Per-conversation shell access via OpenHands SDK `LocalWorkspace`. Each conversation gets an isolated working directory at `WORKSPACE_BASE/{conversation_id}/`.

`LocalSandboxManager` manages lifecycle: `init_local_sandbox(conversation_id)` creates directory + returns `LocalWorkspace`; `get_local_sandbox(conversation_id)` retrieves existing.

`FILES:` lines in agent output reference sandbox files for artifact tracking. Parsed/stripped by `files/__init__.py`.

---

## Heartbeat

Proactive engagement after idle periods. Config: idle 6h, cooldown 6h, quiet hours 23:00-07:00 UTC. Uses stored user facts for opening message. Integrates with pondering mode for reflective conversations.

---

## MCP Servers

Defined in `specialists/mcp_servers.yaml`:

| Server | Purpose |
|--------|---------|
| `time` | Current date/time |
| `aws_docs` | AWS documentation lookup |
| `yahoo_finance` | Stock quotes |
| `alpha_vantage` | Financial indicators |

Assignment per specialist via `specialist.yaml` `mcp_servers` field.

---

## Storage

| Store | Backend | Table | Purpose |
|-------|---------|-------|---------|
| User Facts | LanceDB | per-context | Operator context with semantic search |
| Webhooks | SQLite (WAL) | — | Channel registration and activity |
| Directives | DynamoDB | `if-core` | Behavioral rules with versioning |
| Models | DynamoDB | `if-models` | OpenRouter model metadata |
| Health | DynamoDB | `if-health` | Training programs |
| Finance | DynamoDB | `if-finance` | Financial snapshots |
| Diary | DynamoDB | `if-diary-entries`, `if-diary-signals` | Journaling + distilled signals |
| Proposals | DynamoDB | `if-proposals` | Agent-proposed directives |

---

## Commands

| Command | Action |
|---------|--------|
| `/end_convo` | Clear conversation state and force reclassification |
| `/clear [amount]` | Delete recent messages (default 100) |
| `/pondering` | Enter reflective conversation mode (heavy tier) |
| `/reflect` | Trigger manual reflection cycle |
| `/gaps [min_triggers]` | List capability gaps by priority |
| `/patterns` | Show detected behavioral patterns |
| `/opinions` | Show opinion pairs (operator vs agent positions) |
| `/growth [days]` | Operator growth report (default 30 days) |
| `/meta` | Store health metrics and category suggestions |
| `/tools` | Tool suggestions from capability gaps |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | required | API key for model access |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | LLM endpoint |
| `TIER_UPGRADE_THRESHOLD` | 0.65 | Context fraction before tier upgrade |
| `TIER_AIR_LIMIT` | 100000 | Air tier token limit |
| `TIER_STANDARD_LIMIT` | 200000 | Standard tier token limit |
| `TIER_HEAVY_LIMIT` | 1000000 | Heavy tier token limit |
| `HEARTBEAT_ENABLED` | true | Enable proactive engagement |
| `HEARTBEAT_IDLE_HOURS` | 6.0 | Hours idle before heartbeat |
| `DIRECTIVE_STORE_ENABLED` | true | Enable DynamoDB directives |
| `REFLECTION_ENABLED` | true | Enable reflection engine |
| `WORKSPACE_BASE` | `/app/src/data/conversations` | Per-conversation working directories |
| `TOOL_OUTPUT_CHAR_LIMIT` | 200000 | Max tool output chars |
| `EXTERNAL_TOOLS_PATH` | `""` | Override for external tool plugins path |
| `EXTERNAL_TOOLS_FALLBACK` | `project_root/tools/` | Fallback path if EXTERNAL_TOOLS_PATH is empty |
| `SPECIALISTS_PATH` | `project_root/specialists/` | Specialists directory |
| `SKILLS_PATH` | `project_root/skills/` | AgentSkills directory |
| `IF_MODELS_TABLE_NAME` | `if-models` | DynamoDB table for model registry |
| `MODELS_PATH` | `project_root/models/` | Model preset YAML configs |
| `MODEL_ROUTER_MODEL` | `anthropic/claude-haiku-4.5` | Fast model for subagent routing |
| `MODEL_ROUTER_ENABLED` | true | Enable LLM-based model routing |
| `MODEL_STATS_REFRESH_INTERVAL` | 1800 | Seconds between stats refreshes |
| `MODEL_SEED_INTERVAL` | 3600 | Seconds between full model metadata re-seeds from OpenRouter |
| `LLM_REASONING_EFFORT` | `high` | Reasoning effort for main agent (`high`/`medium`/`low`; ignored for non-supporting models) |
| `SPECIALIST_REASONING_EFFORT` | (same as LLM_REASONING_EFFORT) | Reasoning effort for specialist subagents |

---
