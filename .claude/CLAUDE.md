# IF — Intelligent Agent API

A personal FastAPI agent service with planner-based routing, specialist execution, scoped MCP tools, and durable operator memory. Routes through OpenRouter and OpenCode, persists knowledge in LanceDB, stores directives and domain state in DynamoDB, and delivers through Discord, OpenWebUI, and an OpenAI-compatible HTTP API.

## Tech Stack

- Python 3.12, FastAPI, OpenCode subprocess runtime
- LanceDB (user facts, all-MiniLM-L6-v2 embeddings), ChromaDB (health docs RAG)
- SQLite (webhooks, activity via SQLModel), DynamoDB (directives, health, finance, diary, proposals, models)
- Local per-conversation workspaces for history, plans, responses, files, and status logs
- Scoped MCP servers for local tools plus external capabilities (AWS docs, Yahoo Finance, Alpha Vantage)
- Kubernetes deployment via Terraform, Docker images via Packer

## DynamoDB Number Handling

- Boto3 DynamoDB writes reject Python `float` values. Before every DynamoDB `put_item`, `update_item`, batch write, or nested payload write from Python, recursively convert floats to `Decimal(str(value))`.
- Reuse existing helpers such as `ProgramStore._floats_to_decimals`, `tools/health/core.py::_floats_to_decimals`, or equivalent store-level conversion helpers. Do not write raw floats into DynamoDB.
- This applies to nested health, competition, session, analysis-cache, import, template, glossary, federation, finance, diary, proposal, and model-registry payloads.

## How to Run

```bash
cd app
pip install -r requirements.txt
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Requires `OPENROUTER_API_KEY`, `opencode` on `PATH`, and configured AWS/DynamoDB access for production storage paths. See `app/src/config.py` for full configuration.

## Test Environment and Deploy Workflow

- Use `if-portals-test` as the canonical private test namespace.
- Never run portal tests against the live `operator` PK. Test data must use `test`.
- Test API env must set `HEALTH_PROGRAM_PK=test` and `IF_USER_PK=test`.
- Test powerlifting backend env must set `POWERLIFTING_TEST_MAPPED_PK=test`, so authenticated and unauthenticated test requests resolve to `mapped_pk=test`.
- Test OpenRouter model envs must use `deepseek/deepseek-v4-flash`; the test planner allowlist is mounted through `MODELS_PATH` and contains only that model.
- For portal feature changes, local dev servers are not acceptance tests. Do not use local Vite, `npm run dev`, or a locally served frontend as proof that portal work is correct. Local runs are allowed only for quick harness debugging before the real pod verification.
- Before portal verification, refresh test data with `python scripts/copy_operator_health_to_test.py --replace` so `pk=test` matches the live operator data shape. Confirm the target remains `test`, never `operator`.
- If a portal change reads or writes a DynamoDB-backed data domain that is not already mirrored by the test-data tooling, update `scripts/copy_operator_health_to_test.py` and any related cleanup/restore script before verification. This includes new or previously omitted tables/entities such as videos, user settings, analysis caches, derived cache records, imports, templates, glossary data, federation data, competitions, goals, and session-adjacent metadata.
- The copy/cleanup tooling must keep `test` representative of live `operator` data for every touched feature. Do not accept tests that pass only because the test copy omitted the data type under test.
- Use `scripts/build-test-images.sh` for ad-hoc test image deploys. It builds only `if-agent-api`, `powerlifting-app-backend`, and `powerlifting-app-frontend`, tags them as `test`, pushes to ECR, and patches only `if-portals-test`.
- Do not use `terraform apply` for ad-hoc test deployments. For Terraform validation, run `terraform fmt`, `terraform validate`, and `terraform plan` only.
- Required portal verification sequence:
  1. Copy operator data to `test`.
  2. Build and deploy test images with `scripts/build-test-images.sh`.
  3. Wait for the `if-portals-test` pods to roll out.
  4. Port-forward the deployed test services with `kubectl -n if-portals-test port-forward`.
  5. Run browser/UI checks against the port-forwarded frontend service, not a local frontend.
  6. Inspect `if-portals-test` pod logs for frontend, backend, and API errors.
- The test environment stays private: no Cloudflare record, no tunnel ingress rule, and no public `HTTPRoute`. Access it only with `kubectl port-forward`.
- For touched portal features, verify with `if-portals-test` pod logs plus live API calls and browser/UI checks against port-forwarded pod services. Unit, typecheck, build, and local-browser runs are supporting evidence only, never the main proof.
- If an existing test script defaults to local Vite, pass its deployed-frontend option such as `POWERLIFTING_TEST_USE_DEPLOYED_FRONTEND=1`, or update the script so deployed pod services are the default and local mode requires an explicit opt-in.

## Project Layout

```
app/
├── src/
│   ├── main.py              # FastAPI app entry point, lifespan init
│   ├── config.py            # All env vars (plain module-level, os.getenv defaults)
│   ├── logging_config.py    # Centralized logging configuration
│   ├── api/                 # FastAPI routers
│   │   ├── completions.py   # POST /v1/chat/completions (OpenAI-compatible)
│   │   ├── models.py        # GET /v1/models
│   │   ├── files.py         # File serving from sandbox
│   │   ├── webhooks.py      # Channel registration
│   │   ├── directives.py    # Directive CRUD API
│   │   └── admin.py         # POST /admin/reload-tools (hot reload)
│   ├── flow/                # Current OpenCode planner/runner path
│   │   ├── runner.py        # run_if_flow(), route execution, handoffs, delivery
│   │   ├── plan.py          # plan.md front matter parsing/validation
│   │   ├── opencode.py      # OpenCode subprocess wrapper
│   │   ├── opencode_config.py # Per-run scoped MCP config writer
│   │   ├── context.py       # Runtime context assembly
│   │   ├── history.py       # history.md/history.json management
│   │   ├── direct_llm.py    # Social/direct OpenRouter response path
│   │   ├── model_catalog.py # Planner eligible-model catalog
│   │   ├── runtime_tool.py  # Runtime memory CLI for OpenCode runs
│   │   └── session_dirs.py  # Per-conversation workspace resolution
│   ├── mcp_runtime/         # App-side MCP manager and shell bridge
│   │   ├── manager.py       # Starts configured categories, indexes tool names
│   │   └── invoke_tool.py   # `python -m mcp_runtime.invoke_tool ...`
│   ├── agent/               # Shared prompts, specialists, legacy/support modules
│   │   ├── specialists.py   # YAML-based specialist auto-discovery + rendering
│   │   ├── tiering.py       # Legacy/support tier helpers
│   │   ├── condenser.py     # Conversation summarization
│   │   ├── commands.py      # Slash command definitions
│   │   ├── prompts/         # Jinja2 prompt fragments
│   │   ├── reflection/      # Metacognitive layer
│   │   │   ├── engine.py           # ReflectionEngine (periodic, post-session, on-demand)
│   │   │   ├── pattern_detector.py # Behavioral pattern detection
│   │   │   ├── opinion_formation.py
│   │   │   ├── meta_analysis.py
│   │   │   └── growth_tracker.py
│   │   └── specialist_context/ # Optional context prefetch hooks
│   ├── channels/            # Multi-platform message handling
│   │   ├── dispatcher.py    # Message flow bridge (translate → agent → chunk → deliver)
│   │   ├── delivery.py      # Send responses back to platforms
│   │   ├── chunker.py       # Split responses into 1500-char chunks
│   │   ├── debounce.py      # 5-second message batching window
│   │   ├── manager.py       # Listener lifecycle management
│   │   ├── context.py       # Platform context var for status embed threading
│   │   ├── status.py        # Discord status embed system
│   │   ├── slash_commands.py
│   │   ├── listeners/       # discord_listener.py, openwebui_listener.py
│   │   └── translators/     # discord_translator.py, openwebui_translator.py
│   ├── memory/              # Persistent memory
│   │   ├── user_facts.py    # UserFact dataclass + UserFactStore (LanceDB-backed)
│   │   ├── lancedb_store.py # LanceDB table management, context-scoped storage
│   │   ├── store.py         # Legacy ChromaDB MemoryStore
│   │   ├── embeddings.py    # Sentence transformer embedding generation
│   │   └── summarizer.py    # Conversation summarization (fire-and-forget)
│   ├── storage/             # Storage abstraction
│   │   ├── factory.py       # Backend factory (webhooks, directives, model registry)
│   │   ├── sqlite_backend.py    # SQLite (WAL mode) for webhooks
│   │   ├── dynamodb_backend.py  # DynamoDB stub
│   │   ├── directive_store.py   # DynamoDB directive storage + cache
│   │   └── model_registry.py    # DynamoDB model metadata registry + cache
│   ├── routing/             # Request routing
│   │   ├── interceptor.py   # Bypass routing
│   │   ├── cache.py         # Conversation cache
│   │   └── commands.py      # Command parsing (/reset, /pondering, /reflect, etc.)
│   ├── app_sandbox/         # Legacy LocalWorkspace manager
│   │   ├── __init__.py      # init_local_sandbox, exported entry point
│   │   └── local.py         # LocalSandboxManager, get_local_sandbox
│   ├── files/               # FILES: metadata parsing (strip from agent output)
│   │   └── __init__.py      # FileRef, FilesStripBuffer, strip_files_line
│   ├── mcp_servers/         # Legacy/support MCP config helpers
│   │   └── config.py        # PRESET_MCP_MAP, server resolution
│   ├── presets/             # Legacy/support OpenRouter preset definitions
│   │   └── loader.py        # PresetManager
│   ├── terminal/            # Terminal file helper utilities
│   │   └── files.py
│   ├── heartbeat/           # Proactive engagement
│   │   ├── runner.py        # Idle detection, cooldown, quiet hours
│   │   └── activity.py      # Activity log queries
├── docker/                  # Packer build files (.pkr.hcl)
├── terraform/               # Kubernetes, AWS infra
└── main_system_prompt.txt   # Agent personality base prompt
specialists/                 # One subdir per specialist (specialist.yaml + agent.j2)
├── mcp_servers.yaml         # MCP server command definitions
skills/                       # Prompt skill packages for thinking modes
└── {skill-name}/
    ├── SKILL.md              # YAML frontmatter + markdown body
    ├── scripts/              # optional: executables (run via uv/uvx/npx)
    ├── references/           # optional: on-demand reference docs
    └── assets/               # optional: templates/data
models/                       # Current planner model allowlist + legacy model config
└── model_ids.txt            # Execution model allowlist for OpenCode planner
tools/                       # External tool plugins (one subdir per plugin)
├── mcp_server.py            # Local plugin MCP wrapper used by OpenCode
├── health/                  # Training program management, analytics, imports, templates
├── finance/                 # Financial profile and investments (21 tools)
├── diary/                   # Write-only diary entries and signals
├── proposals/               # Agent-proposed directives (4 tools)
├── supplement_research/     # Supplement research corpus search
└── temporal_*/              # Date/time helper plugins
utils/                       # TypeScript/Node.js utility apps
├── main-portal/             # Hub dashboard (port 3000)
├── finance-portal/          # Net worth, investments (port 3002)
├── diary-portal/            # Mental health journaling (port 3003)
├── proposals-portal/        # Directive proposal kanban (port 3004)
├── powerlifting-app/        # Training tracking (port 3005)
└── video-lambda/            # Lambda function for video processing
```

## Architecture

```
Client (Discord / OpenWebUI / HTTP)
  → Channel Listener / POST /v1/chat/completions
    → Completions Pipeline
      → Command parsing (/reset, /pondering, /reflect, etc.)
      → Interceptor (bypass routing)
      → Runtime context assembly (signals, memories, uploads, compatibility notes)
      → Session workspace resolution
      → history.md/history.json write
      → OpenCode planner (plan.md)
        → route:
            social    → direct OpenRouter chat
            domain    → specialist OpenCode run with scoped MCP tools
            technical → OpenCode build run + review
        → optional HANDOFF_REQUIRED child specialist runs
      → Response extraction (FILES: metadata stripping)
    → Chunker (1500 char chunks)
  → Delivery (back to platform)
```

### Request Processing (completions.py)

`process_chat_completion_internal()` is the core pipeline:
1. Resolve `cache_key` (from webhook channel_id, chat_id, or content hash) and `context_id`
2. Parse slash commands (`/reset`, `/pondering`, `/reflect`, `/gaps`, `/patterns`, `/opinions`, `/growth`, `/meta`, `/tools`)
3. Run interceptor for bypass routing
4. Persist cache/conversation state
5. Call `flow.runner.run_if_flow()`
6. Build runtime context via `flow/context.py`
7. Write `history.md` and `history.json`
8. Run OpenCode planner and validate `plan.md`
9. Execute the selected route (`social`, `domain`, or `technical`)
10. Extract file attachments from `FILES:` metadata
11. Trigger async conversation summarization

Planner failures are fail-closed. If `plan.md` is missing, malformed, names an unknown specialist, or selects a model outside `models/model_ids.txt`, return an explicit planner failure. Do not reintroduce guessed fallback routing.

### Runtime Prompt Assembly

OpenCode planner/domain prompts are assembled in `flow/runner.py` and `flow/context.py` from:
1. Main personality prompt (`main_system_prompt.txt`)
2. Core directives from DynamoDB
3. Runtime context: current diary/training/finance signals, relevant LanceDB facts, uploads, compatibility notes
4. Conversation history from `history.md`
5. Specialist prompt from `specialists/<slug>/agent.j2` for domain routes
6. Directives filtered by specialist `directive_types`
7. Memory/media protocol text
8. Thinking-mode addenda and skills when requested
9. Allowed tool schemas from the scoped MCP configuration

## Model Router

Current execution model selection happens in the OpenCode planner. The planner must choose a concrete model ID from `models/model_ids.txt`; validation in `flow/plan.py` rejects anything outside that allowlist.

The older tier/preset router modules and YAML files still exist for legacy/support paths and historical model metadata work. Do not assume they are the primary runtime path unless the code path you are editing still calls them.

### Model Registry (`storage/model_registry.py`)

DynamoDB-backed registry (`if-models` table, PK=`MODEL`, SK=model_id) storing metadata for OpenRouter models. Populated from the OpenRouter API via the seed script.

**ModelInfo fields**: model_id, context_size, max_output_tokens, input/output pricing (per-provider), input/output modalities, tool_support, caching_support, zero_data_retention, throughput, latency.

**Seeding**: `python scripts/seed_models.py [--models-file models/model_ids.txt]` — fetches all models from OpenRouter, filters to the input list (skipping models without tool support), upserts to DynamoDB. Also fetches per-provider latency/throughput from `/api/v1/models/{id}/endpoints` (min p50 latency, max p50 throughput across providers). Runs automatically at startup to refresh metadata.

**Periodic stats refresh**: Background task in `main.py` calls `ModelRegistry.refresh_endpoint_stats()` every `MODEL_STATS_REFRESH_INTERVAL` seconds (default 1800 / 30 min) to keep latency/throughput data current. Updates both DynamoDB and the in-memory cache.

**Sorting strategies**: `price_asc`, `price_desc`, `latency_asc`, `context_size_desc`, `throughput_desc`.

### Current Selection

The current planner sees:

- conversation history
- runtime context
- specialist catalog
- eligible model IDs from `models/model_ids.txt`

It writes `selected_model` in `plan.md`. That value is then passed into the social, domain, or technical route.

### Legacy/Support Tiering

`agent/tiering.py` still implements context-aware preset tiering for support paths:
- **Air**: simple/short contexts
- **Standard**: normal conversations
- **Heavy**: large or complex contexts

Tier limits and preset slugs come from `app/src/config.py` environment variables (`TIER_AIR_LIMIT`, `TIER_STANDARD_LIMIT`, `TIER_HEAVY_LIMIT`, `TIER_*_PRESET`). Do not document this as the main OpenCode planner route.

## Agent System

### Specialists

Domain experts selected by the OpenCode planner. Each has its own `specialist.yaml` config and `agent.j2` prompt template. Auto-discovered from `specialists/*/specialist.yaml` at import time — no Python changes needed to add a specialist.

| Specialist | Purpose | Tools | Preset |
|------------|---------|-------|--------|
| `coder` | General software engineering | terminal_execute, read/write/search files | `@preset/code` |
| `scripter` | Quick tasks (3-5 commands), max 3 turns | terminal_execute, read/write files | `@preset/code` |
| `debugger` | Deep code debugging and error analysis | terminal_execute, read/write/search files | standard |
| `architect` | System design and architecture patterns | read/write/search files + AWS docs MCP | standard |
| `secops` | Security operations and vulnerability analysis | terminal_execute, read/search files | standard |
| `devops` | Infrastructure and deployment automation | terminal_execute, read/write files | standard |
| `file_generator` | Structured file generation with syntax validation — scripts, configs, IaC, code modules. `agentic: true` | terminal_execute, write/read files | `@preset/code` |
| `git_ops` | Git operations — rebasing, conflict resolution, PR workflows, history rewriting. `agentic: true` | terminal_execute, read/write/search files | `@preset/code` |
| `code_reviewer` | Structured code review — correctness, security, performance, maintainability. `agentic: true` | terminal_execute, read/search files | `@preset/code` |
| `code_explorer` | Codebase navigation, dependency mapping, "how does X work?". `agentic: true` | terminal_execute, read/search files | `@preset/code` |
| `doc_generator` | Technical documentation — READMEs, ADRs, RFCs, API docs, runbooks. `agentic: true` | terminal_execute, read/write/search files | `@preset/code` |
| `test_writer` | Test generation — unit, integration, edge cases. Agentic: GENERATE→RUN→FIX→VERIFY. `agentic: true` | terminal_execute, read/write/search files | `@preset/code` |
| `refactorer` | Code refactoring without behavior change — extract, rename, decouple. `agentic: true` | terminal_execute, read/write/search files | `@preset/code` |
| `api_designer` | REST/GraphQL/gRPC API design, OpenAPI specs | read/write/search files | `@preset/architecture` |
| `migration_planner` | Database/infrastructure migration planning with rollback strategies | terminal_execute, read/write/search files | `@preset/architecture` |
| `incident_responder` | Production incident triage — fast, action-first, no preamble | terminal_execute, read/search files | `@preset/code` |
| `performance_analyst` | Performance profiling, optimization, benchmarking — MEASURE→IDENTIFY→OPTIMIZE→VERIFY | terminal_execute, read/search files | `@preset/code` |
| `planner` | Decomposes goals into sequenced, dependency-aware plans. Produces plans; does not execute | read/write/search files | standard |
| `dialectic` | Structured adversarial reasoning — thesis-antithesis-synthesis | read_file | standard |
| `decision_analyst` | Multi-criteria decision analysis with weighted scoring and tradeoff matrices | write_file | standard |
| `project_manager` | Implementation verification — confirms planned work exists in codebase. `agentic: true` | terminal_execute, read/search files | `@preset/code` |
| `product_manager` | Product strategy — app ideation, user personas, competitive framing, go-to-market, success metrics, roadmap direction. Not for backlog decomposition (→ product_owner) or implementation (→ architect/coder). | read/write files | `@preset/architecture` |
| `product_owner` | Agile product ownership — breaks known product direction into user stories with acceptance criteria, backlog prioritization, scope trade-offs. Not for ideation (→ product_manager) or implementation. | read/write files | `@preset/architecture` |
| `todo_generator` | Extracts actionable task lists from conversations and documents | read/write files | standard |
| `proofreader` | Prose editing, grammar, clarity, tone | — | standard |
| `email_writer` | Professional email drafting | — | standard |
| `jira_writer` | Structured Jira tickets with acceptance criteria | — | standard |
| `constrained_writer` | Character-limited content (tweets, Discord, SMS) | — | standard |
| `interviewer` | Requirements gathering through structured questioning — asks, does not answer | — | `@preset/air` |
| `summarizer` | Condensing long content into structured summaries | read/write files | `@preset/air` |
| `meeting_prep` | Meeting preparation — talking points, background research, anticipated questions | read/write files, user facts | standard |
| `negotiation_advisor` | Negotiation strategy — BATNA analysis, concession planning | user facts | standard |
| `resume` | Resume tailoring via LaTeX, JD analysis, compile to PDF. `agentic: true` | terminal_execute, read/write/search files | `@preset/air` |
| `cover_letter` | Cover letter generation — JD-specific, one page max. `agentic: true` | terminal_execute, read/write files | `@preset/air` |
| `workday` | Workday/ATS application form input — copy-paste-ready text blocks | read/write files | `@preset/air` |
| `pdf_generator` | Formatted PDF creation via WeasyPrint/Pandoc/LaTeX. `agentic: true` | terminal_execute, read/write files | `@preset/code` |
| `changelog_writer` | Release notes and changelogs from git history | terminal_execute, read/write files | `@preset/code` |
| `data_analyst` | Data exploration, analysis, visualization — CSV, JSON, logs. `agentic: true` | terminal_execute, read/write/search files | `@preset/code` |
| `legal_reader` | Contract, ToS, and policy analysis — extracts obligations and risks. NOT legal advice | read_file | standard |
| `prompt_engineer` | Writing, refining, and testing prompts for LLMs — including IF's own | read/write/search files | standard |
| `sql_analyst` | Database query specialist — optimization, schema analysis, explain plans | terminal_execute, read/write files | `@preset/code` |
| `math_tutor` | Mathematics instruction — algebra, calculus, linear algebra, ML/AI math foundations | write_file | standard |
| `language_tutor` | Language learning — Japanese, Spanish, French. Vocabulary, grammar, conversation | write_file | standard |
| `ml_tutor` | ML/AI instruction — architectures, training, practical implementation | terminal_execute, read/write files | `@preset/code` |
| `career_advisor` | Career strategy — trajectory analysis, skill gaps, market positioning | write_file, user facts | standard |
| `consensus_builder` | Multi-source synthesis — coordinates specialist outputs and synthesizes | handoff/synthesis flow, write_file | standard |
| `self_improver` | Analyzes IF's own performance and proposes improvements to directives and prompts | read/write/search files | standard |
| `health_write` | Specialized health mutation path retained for compatibility. In the current routing model, normal explicit health/training writes are owned by `powerlifting_coach`. | health write tools + import/template/glossary tools, supplement_search | `@preset/health` |
| `powerlifting_coach` | Training reads, coaching, analysis, and explicit health/training mutations. It should fetch the current markdown export before answering training questions and use scoped health MCP tools for data it needs. | health tools, supplement_search, weekly_analysis, correlation_analysis, fatigue_profile_estimate, program_evaluation, get_analysis_markdown, regenerate_analysis, template_list/get/evaluate | `@preset/health` |
| `finance_write` | Finance snapshot mutations (balances, holdings, goals) | Finance DynamoDB tools | standard |
| `financial_analyst` | Market research and financial analysis | Yahoo Finance + Alpha Vantage MCPs | standard |
| `research_assistant` | Web research + Examine.com supplement corpus. Native web search via research model pool (Perplexity Sonar / :online suffix). | read/write files, supplement_search, plan_append, plan_read | `@preset/research` |
| `media_reader` | On-demand file and image analysis (vision model, single turn) | — | media preset |

**Current thinking skills**: `deep_think`, `sequential_plan`, and `parallel_analysis` are prompt packages loaded when requested.

`agentic: true` may appear in some YAML files as legacy metadata. In the current OpenCode path, specialist execution is controlled by `flow/runner.py` and scoped MCP configuration.

**Model routing for specialists**: The current planner chooses the concrete `selected_model` for the run. The specialist `preset` field remains useful metadata and may still be used by legacy/support code, but it is not the current primary execution selector.

### Skills System

Prompt skill packages loaded into OpenCode prompts when the runtime enables a thinking mode. Skills are **not** loaded globally into every request (context size concern).

**Directory layout**:
```
skills/                       # AgentSkills-compliant skill packages
└── {skill-name}/
    ├── SKILL.md              # YAML frontmatter + markdown body
    ├── scripts/              # optional: executables (run via uv/uvx/npx from the agent's bash tool)
    ├── references/           # optional: on-demand reference docs
    └── assets/               # optional: templates/data
```

**Configuration**: Specialists can declare referenced skills in their `specialist.yaml`, and the runtime can inject thinking-mode skills based on planner/request state.

```yaml
description: Code generation and debugging
tools: [terminal_execute, read_file, write_file]
preset: "@preset/code"
skills: [deep_think, sequential_plan]  # Skills this specialist can reference
```

**Current packages**: `deep_think`, `sequential_plan`, `parallel_analysis`.

If a skill provides scripts, prefer invoking them through the documented command in that skill package rather than retyping large logic into a prompt.

### Specialist Delegation

The OpenCode planner selects the first specialist by writing `specialist` in `plan.md`.

If that specialist needs another specialist, it emits a `HANDOFF_REQUIRED` block:

```text
HANDOFF_REQUIRED:
  target: specialist_slug
  task: "what the target should do"
  context: "needed context"
```

or:

```text
HANDOFF_REQUIRED:
  target: specialist_slug
  intended_change: "precise mutation/change"
  context: "needed context"
```

`flow/runner.py` parses handoffs, validates the target specialist, runs child domain requests in order, and synthesizes the result.

Directive injection happens automatically using the specialist's `directive_types` YAML field — no separate directive-fetching step required in the specialist prompt.

## Tools

Current domain tools are local Python plugins exposed to OpenCode through scoped MCP servers. The selected specialist sees only the MCP categories and exact tool names declared in its `specialist.yaml`.

### Current MCP Tool Path

`flow/opencode_config.py::write_opencode_config()` writes a per-run `opencode.json` in the session directory:

- maps selected specialist tool names to backing MCP categories
- includes only those categories in `opencode.json`
- passes `IF_MCP_ALLOWED_TOOLS`
- filters `list_tools` in `tools/mcp_server.py`

Native OpenCode MCP tool names are server-prefixed, for example:

```text
if_health_health_get_session
```

The prompt also exposes a shell fallback:

```bash
PYTHONPATH=<app-src:project-root> python -m mcp_runtime.invoke_tool <tool_name> '<json_args>'
```

Runtime memory is exposed through a narrow CLI, not the old SDK tool surface:

```bash
python -m flow.runtime_tool user_facts_search '<json>'
python -m flow.runtime_tool user_facts_add '<json>'
python -m flow.runtime_tool user_facts_supersede '<json>'
python -m flow.runtime_tool capability_gap_log '<json>'
```

### External Tool Plugins

Domain tools live in `tools/` as mountable plugins. Each plugin is a subdirectory with `tool.yaml` metadata and `tool.py`. Plugins should expose `get_schemas()` where applicable and `async execute(name, args)`.

The app-side MCP manager (`mcp_runtime/manager.py`) starts configured categories at startup and maintains a tool-name index for slash commands, schemas, and fallback calls.

| Plugin | Scope | Tools | Description |
|--------|-------|-------|-------------|
| `tools/health/` | specialist | 85+ | Training program CRUD, session logging, glossary management, goal/federation library CRUD, import pipeline, template CRUD, block analytics, lift-profile AI, muscle-group AI, multi-block comparison, stats analysis, unit conversions |
| `tools/finance/` | specialist | 21 | Financial profile, investments, goals, cashflow, holdings |
| `tools/diary/` | specialist | 2 | Write-only diary entries, signal computation |
| `tools/proposals/` | specialist | 4 | Proposal CRUD, implementation plan generation |
| `tools/supplement_research/` | specialist | 1+ | Local supplement research corpus search |
| `tools/temporal_resolve/` | main | 1 | Parse natural language date/time phrases into concrete dates |
| `tools/temporal_timezone/` | main | 1 | Convert datetime between IANA timezones |
| `tools/temporal_duration/` | main | 1 | Calculate duration between two dates |
| `tools/temporal_age/` | main | 1 | Calculate age and birthday info from a birth date |
| `tools/temporal_city_time/` | main | 1 | Current date/time for major cities worldwide |
| `tools/temporal_to_unix/` | main | 1 | Parse datetime string into Unix timestamp |
| `tools/temporal_from_unix/` | main | 1 | Convert Unix timestamp to structured datetime |

**Adding a new in-process plugin:**
1. Create `tools/{name}/tool.yaml` with name, description, version, scope, `mode: in_process`
2. Create `tools/{name}/tool.py` exporting `get_schemas()` and `async execute(name, args)`
3. Optionally add `requirements.txt` for pip dependencies
4. Add the tool names to the appropriate specialist `specialist.yaml`
5. App picks it up on next startup; the MCP manager indexes it for schemas/fallback calls

**Adding a new subprocess plugin:**
1. Create `tools/{name}/tool.yaml` with name, description, version, scope, `mode: subprocess`
2. Create `tools/{name}/pyproject.toml` with `[project]` name, version, requires-python, dependencies
3. Create `tools/{name}/tool_meta.yaml` with static schema (tools → tool_name → description + parameters)
4. Create `tools/{name}/tool.py` with only `async execute(name, args)` and helpers
5. Copy `tools/_plugin_runner.py` into the plugin directory as `_plugin_runner.py`

### Tool Authoring

**DynamoDB rule**: Boto3 rejects Python `float` values. Every Python DynamoDB write path must recursively convert floats to `Decimal(str(value))` before `put_item`, `update_item`, batch writes, or nested payload writes.

Reuse helpers such as `health.program_store.ProgramStore._floats_to_decimals`, `tools/health/core.py::_floats_to_decimals`, or equivalent store-level helpers.


## Channels

| Platform | Type | Description |
|----------|------|-------------|
| Discord | Bot (discord.py) | Listens to registered channels, slash commands, thread support, status embeds |
| OpenWebUI | Polling | Chat interface integration (5s poll interval) |
| HTTP API | REST | Direct OpenAI-compatible API access |

Flow: listener → debounce (5s) → dispatcher (set platform context) → translator → completions pipeline → OpenCode planner/runtime → chunker (1500 chars) → delivery.

### Discord Status Embeds

Lightweight, color-coded embeds sent to Discord channels for operational visibility. Only active for Discord platform — no-ops for API/OpenWebUI.

**Status types** (sent as separate small embeds per event):
| Status | Color | When |
|--------|-------|------|
| Message Received | Blue | Dispatcher receives batch |
| Model Selected | Green | Planner/model routing selects a concrete model |
| Subagent Spawning | Yellow | Specialist/domain run starts with model info |
| Subagent Completed | Green | Specialist/domain run finishes |
| Subagent Failed | Red | Specialist/domain run errors |
| Tool Started | Purple | Tool call/status line detected |
| Tool Completed | Green | Tool execution succeeds |
| Tool Failed | Red | Tool execution errors |

**Implementation**: `channels/context.py` stores platform context (channel_ref, discord_loop) in a `contextvars.ContextVar`. `channels/status.py` reads this context to send embeds via `asyncio.run_coroutine_threadsafe()`. Context is propagated through `ThreadPoolExecutor` paths via `contextvars.copy_context()`.

### Attachment Handling

Discord attachments are downloaded by the dispatcher, materialized for the runtime, and referenced via upload manifests / `FILES:` metadata. The `FilesStripBuffer` strips `FILES:` lines from responses delivered to users.

### Discord History

The dispatcher fetches up to 100 historical messages from Discord for context enrichment.

## Memory System

### User Facts (LanceDB)

`UserFact` dataclass with: id, context_id, username, content, category, source, confidence, cache_key, timestamps, metadata.

**Categories** (22): personal, preference, opinion, skill, life_event, future_direction, project_direction, mental_state, interest_area, conversation_summary, topic_log, model_assessment, agent_identity, agent_opinion, agent_principle, capability_gap, tool_suggestion, opinion_pair, misconception, session_reflection, health, finance.

**Sources**: user_stated, model_observed, model_assessed, conversation_derived.

Context-scoped: each context_id gets its own LanceDB table. Supports semantic search within context, supersession for fact updates, and capability gap logging with priority scoring.

### Legacy Memory (ChromaDB)

`MemoryStore` in `store.py` — older RAG-backed semantic search. Categories: preference, personal, skill_level, opinion, life_event, future_plan, mental_state.

### Conversation Summarization

Fire-and-forget summarization in `summarizer.py` after conversations end.

## Directives

Versioned behavioral rules stored in DynamoDB (`if-core` table). Tiered by priority (0-5):

| Tier | Label | Purpose |
|------|-------|---------|
| 0 | Core Identity | Fundamental personality traits |
| 1 | Behavioral Rules | How to respond/act |
| 2 | Style & Tone | Voice adjustments |
| 3 | Domain Knowledge | Topic-specific guidance |
| 4 | Situational | Context-dependent rules |
| 5 | Temporary | Time-limited adjustments |

Content is cached in memory with periodic refresh. Core directives are injected into planner/runtime prompts; specialist runs receive directives filtered by their `directive_types` config.

Directive APIs live under `app/src/api/directives.py`, and proposal review happens through the proposals portal. Do not run directive seed scripts unless explicitly asked; they mutate DynamoDB.

## Reflection Engine

Metacognitive layer in `agent/reflection/`. Analyzes interactions for self-improvement.

**Triggers**: post-session (>5 turns), periodic (6h), on-demand (`/reflect`), threshold-based (uncategorized facts, gaps, opinions).

**Cycle**: Pattern Detection → Opinion Formation → Capability Gap Analysis → Meta-Analysis → Growth Tracking.

**Capability gaps**: logged with priority score `(frequency * 0.4) + (recency * 0.3) + (impact * 0.3)`. High-frequency gaps are promoted to tool suggestions via `CAPABILITY_GAP_PROMOTION_THRESHOLD` (default 3).

## OpenCode Runner

The active multi-step execution layer is `flow/runner.py`:

- **Planner**: OpenCode `plan` writes `plan.md`.
- **Domain route**: OpenCode runs the selected specialist with scoped MCPs and writes `response.md`.
- **Technical route**: OpenCode `build` writes `response.md`, then OpenCode `plan` reviews and writes `review.md`.
- **Handoffs**: `HANDOFF_REQUIRED` blocks trigger child specialist runs and final synthesis.

## Session Workspace

Per-conversation workspace resolution lives in `flow/session_dirs.py`. Workspaces hold runtime state and generated artifacts.

Important files:

- `history.md`: incremental user/assistant history
- `history.json`: structured history
- `plan.md`: planner output
- `opencode.json`: per-run MCP config
- `response.md`: final user-facing output for domain/technical routes
- `review.md`: technical review output
- `.if/status.log`: progress lines sent to Discord status embeds

Do not treat these as deliverable artifacts. `config.IF_TECHNICAL_ARTIFACT_EXCLUDES` excludes them from file attachments.

`FILES:` lines in agent output reference generated files for artifact tracking and attachment delivery. Parsing and stripping are handled by `files/__init__.py` (`FileRef`, `FilesStripBuffer`, `strip_files_line`).

## Health Module

Training program management with DynamoDB storage (`if-health` table) and ChromaDB RAG for PDF documents (IPF rulebook, anti-doping list, supplement PDFs).

Core health functionality now lives primarily under `tools/health/` and is exposed through the health MCP category. Tools cover program CRUD, session logging, competition management, imports, templates, glossary, analytics, RAG search, and unit conversions. Any health DynamoDB write must recursively convert floats to `Decimal(str(value))`.

## Heartbeat

Proactive engagement system. Monitors channel activity, initiates pondering conversations after idle threshold.

Config: idle 6h, cooldown 6h, quiet hours 23:00-07:00 UTC. Opening message uses stored user facts. Integrates with pondering preset.

## MCP Servers

Local plugin folders under `tools/` can be exposed as MCP categories through `tools/mcp_server.py`. External capabilities are defined in `specialists/mcp_servers.yaml`.

| Server | Purpose |
|--------|---------|
| `if_health` / health category | Health plugin tools filtered by `IF_MCP_ALLOWED_TOOLS` |
| `if_finance` / finance category | Finance plugin tools filtered by `IF_MCP_ALLOWED_TOOLS` |
| `aws_docs` | AWS documentation lookup |
| `yahoo_finance` | Stock quotes |
| `alpha_vantage` | Financial indicators |

Server assignment per specialist is configured in each `specialist.yaml` under `mcp_servers`. Tool visibility is additionally filtered by the exact tool names in the specialist `tools` list.

## Storage

| Store | Backend | Purpose |
|-------|---------|---------|
| User Facts | LanceDB | Operator context with semantic search |
| Webhooks | SQLite (WAL) | Channel registration and activity |
| Directives | DynamoDB (`if-core`) | Behavioral rules with versioning |
| Models | DynamoDB (`if-models`) | OpenRouter model metadata registry |
| Health | DynamoDB (`if-health`) | Training programs |
| Finance | DynamoDB (`if-finance`) | Financial snapshots |
| Diary | DynamoDB (`if-diary-entries`, `if-diary-signals`) | Journaling + distilled signals |
| Proposals | DynamoDB (`if-proposals`) | Agent-proposed directives |

## Utility Applications

TypeScript/Node.js apps in `utils/`:

| App | Port | Purpose | DynamoDB Table |
|-----|------|---------|----------------|
| Hub | 3000 | Central dashboard aggregating all portals | — |
| Finance | 3002 | Net worth, investments, cashflow | `if-finance` |
| Diary | 3003 | Mental health journaling and signals | `if-diary-entries`, `if-diary-signals` |
| Proposals | 3004 | Kanban for agent-proposed directives | `if-proposals` |
| Powerlifting | 3005 | Training tracking, analytics, block comparison, rankings, maxes history | `if-health` |

## Commands

Discord guild slash commands (autocomplete) and plain text messages:

| Command | Action |
|---------|--------|
| `/end_convo` | Clear conversation state and force reclassification |
| `/clear [amount]` | Delete recent messages from channel (default 100, requires Manage Messages) |
| `/pondering` | Enter reflective conversation mode (heavy tier) |
| `/reflect` | Trigger manual reflection cycle |
| `/gaps [min_triggers]` | List capability gaps ranked by priority |
| `/patterns` | Show detected behavioral patterns |
| `/opinions` | Show opinion pairs (operator vs agent positions) |
| `/growth [days]` | Show operator growth report (default 30 days) |
| `/meta` | Show store health metrics and category suggestions |
| `/tools` | Show tool suggestions from capability gaps |

## Environment Variables

Key configuration (see `app/src/config.py` for full list):

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
| `OPENCODE_BIN` | "" | Optional explicit OpenCode binary path |
| `OPENCODE_PLANNER_MODEL` | `deepseek/deepseek-v4-flash` | OpenCode planner model fallback/default |
| `OPENCODE_TIMEOUT_SECONDS` | 900 | OpenCode subprocess timeout |
| `OPENCODE_WORKSPACE_BASE` | `WORKSPACE_BASE` or `/app/src/data/conversations` | Base path for per-conversation OpenCode workspaces |
| `WORKSPACE_BASE` | `/app/src/data/conversations` | Legacy/default workspace base fallback |
| `TOOL_OUTPUT_CHAR_LIMIT` | 200000 | Legacy SDK tool output char limit |
| `EXTERNAL_TOOLS_PATH` | "" | Override path for external tool plugins |
| `EXTERNAL_TOOLS_FALLBACK` | `project_root/tools/` | Fallback path if EXTERNAL_TOOLS_PATH is empty |
| `SPECIALISTS_PATH` | `project_root/specialists/` | Path to specialists directory |
| `SKILLS_PATH` | `project_root/skills/` | Path to AgentSkills directory |
| `IF_MODELS_TABLE_NAME` | `if-models` | DynamoDB table for model registry |
| `MODELS_PATH` | `project_root/models/` | Path to model preset YAML configs |
| `MODEL_ROUTER_MODEL` | `anthropic/claude-haiku-4.5` | Legacy/support fast model for older specialist model selection |
| `MODEL_ROUTER_ENABLED` | true | Enable legacy/support LLM-based model routing |
| `MODEL_SEED_INTERVAL` | 3600 | Seconds between full model metadata re-seeds from OpenRouter API |
| `LLM_REASONING_EFFORT` | high | Reasoning effort for legacy/support paths (`high`/`medium`/`low`; silently ignored for non-supporting models) |
| `SPECIALIST_REASONING_EFFORT` | (inherits `LLM_REASONING_EFFORT`) | Legacy/support specialist reasoning effort |
| `MODEL_STATS_REFRESH_INTERVAL` | 1800 | Seconds between per-provider latency/throughput refreshes |

## Operational Rules

- **Build before declaring done**: Always run `npm run build` in both `frontend/` and `backend/` of any portal before declaring work complete. A successful build is the minimum verification bar — no exceptions.
- **k3s debugging**: The app is hosted on a k3s cluster. When debugging runtime issues, use `kubectl logs`, `kubectl describe`, and `kubectl get events` to inspect pod state. Do not guess at runtime behavior from code alone.
- **Terraform**: Never run `terraform apply` or `terraform destroy`. Targeted low-blast-radius `terraform apply -target=...` is the only exception, and only after explicit user approval via AskUserQuestion.
- **AWS resources**: Never delete AWS resources (CLI, SDK, console). Provide the command for the user to run manually.
- **kubectl mutations**: Never run `kubectl delete/apply/patch/edit/replace/scale/rollout/cordon/drain`. Provide the command for the user to run manually. Read-only commands (`get`, `describe`, `logs`, `events`, `top`) are fine.
- **No git writes**: Never run `git commit`, `git push`, `git merge`, `git rebase`, `git reset --hard`, or any mutating git command. No write privileges. Provide the command for the user to run manually.

## Key Patterns

- **Specialist auto-discovery**: `specialists.py` scans `SPECIALISTS_PATH` at import time — no code changes needed to add specialists
- **OpenCode planner path**: `api/completions.py -> flow.runner.run_if_flow()` is the primary request path. Planner output is validated by `flow/plan.py`.
- **Session workspace pattern**: `flow/session_dirs.py` resolves per-conversation workspaces; `history.md`, `plan.md`, `opencode.json`, `response.md`, and `review.md` are runtime artifacts, not deliverables.
- **Scoped MCP pattern**: `flow/opencode_config.py` writes per-run MCP config; `tools/mcp_server.py` filters tools by `IF_MCP_ALLOWED_TOOLS`.
- **Model allowlist**: `models/model_ids.txt` is the current planner execution allowlist. YAML presets/tiers are legacy/support metadata.
- **Model registry**: `storage/model_registry.py` mirrors DirectiveStore pattern (PK/SK, boto3, cache). Seeded from OpenRouter API at startup.
- **Tool plugin structure**: local plugins under `tools/` expose `tool.yaml`, `tool.py`, optional `get_schemas()`, and `async execute(name, args)`.
- **Specialist handoffs**: domain runs request other specialists by emitting `HANDOFF_REQUIRED`; `flow/runner.py` validates and executes child runs.
- **Context/signal injection**: `flow/context.py` injects diary/training/finance signals, relevant LanceDB facts, uploads, compatibility notes, and protocol text.
- **FILES metadata pattern**: `FILES:` lines in agent output are stripped by `FilesStripBuffer` for artifact tracking
- **Channel message flow**: listener → debounce → dispatcher → translator → completions → OpenCode planner/runtime → chunker → delivery
- **Directive injection**: System prompt includes directives from DynamoDB, filtered by specialist type for subagents
- **MCP server config**: `mcp_servers.yaml` defines servers; specialist `specialist.yaml` lists which servers each specialist gets
- **Discord status embeds**: `channels/status.py` sends color-coded embeds via `contextvars` propagation — no-ops for non-Discord platforms