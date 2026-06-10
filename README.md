# IF

A personal FastAPI agent service with planner-based routing, scoped specialist execution, durable memory, and runtime behavior directives. It receives messages from Discord, OpenWebUI, and an OpenAI-compatible HTTP API; routes through OpenRouter models and OpenCode workspaces; persists knowledge in LanceDB; and stores directives plus domain state in DynamoDB.

---

## What This Is

An architectural exercise and personal learning project — not a product. The goal is to build practical knowledge of multi-agent orchestration, runtime behavior shaping, specialist delegation, domain tool design, and operational observability by building something that actually runs.

It is deployed on a personal Kubernetes (k3s) cluster and used personally, which means real bugs surface and architectural decisions have real consequences.

**Current:** OpenRouter (LLM provider), OpenCode (planner and execution runtime), Discord + OpenWebUI + OpenAI-compatible HTTP (interaction layers), DynamoDB + LanceDB + SQLite (state), Prometheus + Loki + Grafana (observability), Kubernetes (k3s) (cluster runtime).

---

## How It Works

```text
User message (Discord / OpenWebUI / HTTP API)
  -> completions pipeline
    -> runtime context assembly
      -> OpenCode planner writes plan.md
        -> route:
             social    -> direct OpenRouter chat
             domain    -> specialist OpenCode run with scoped MCP tools
             technical -> OpenCode build run + review
        -> optional HANDOFF_REQUIRED specialist runs
      -> response.md / direct text
    -> FILES: parsing, attachment materialization, chunked delivery
```

The planner receives conversation history, core directives, runtime context, the specialist catalog, and eligible model IDs. It writes a small `plan.md` decision containing:

- interaction type: `social`, `domain`, or `technical`
- specialist slug
- thinking-mode flag
- concrete model ID from `models/model_ids.txt`

Planner failures are fail-closed. If the plan cannot be written or parsed, the service returns an explicit failure response rather than guessing a route.

### Scoped Specialist Execution

Domain requests run through a selected specialist. Each specialist receives only:

- its own Jinja2 prompt template
- directives filtered to its declared domain
- runtime context relevant to the request
- its declared local tools and MCP servers
- any active thinking-mode instructions

Before each domain run, the service writes a per-session `opencode.json` that exposes only the selected specialist's MCP categories and allowed tool names. This context scoping is the core architectural choice: it reduces hallucination risk from bloated prompts and keeps cost proportional to task complexity, not system size.

### Technical Workspaces

Technical requests run in a persistent per-conversation workspace. OpenCode performs the build task, writes `response.md`, and then a review pass writes `review.md`.

- `OK` on the first review line accepts the result.
- `RETRY` on the first review line triggers one retry with review context.

Generated files stay in the session workspace and are delivered back to Discord or HTTP clients through the `FILES:` attachment pipeline.

### Model Selection

The current flow selects concrete model IDs at planning time. Eligible execution models are maintained in `models/model_ids.txt`, while `storage/model_registry.py` keeps OpenRouter metadata in DynamoDB:

- context size
- maximum output
- pricing
- modalities
- tool support
- caching support
- zero-data-retention flag
- throughput and latency

Legacy tier and preset modules still exist for support paths, but the normal request flow is planner-selected model IDs plus specialist-scoped prompts.

### Runtime Directive System

Behavior rules are stored in DynamoDB, not baked into code. This inverts the typical agent workflow:

**Traditional:** Engineer a comprehensive system prompt upfront -> deploy -> discover gaps -> edit code -> redeploy.

**This system:** Start with a baseline -> use the agent -> reflection pipeline detects failure patterns -> agent proposes directive -> human reviews in proposals portal -> approved directive takes effect on the next request.

Directives are priority-tiered for conflict resolution. Specialists receive only directives matching their declared `directive_types`, so domain rules do not leak across contexts.

The agent can propose new directives, but nothing takes effect without human approval through the proposals portal.

### Behavioral Feedback Loop

After longer sessions, periodically, or on demand:

1. **Pattern Detection** — recurring behaviors and failure modes
2. **Capability Gap Analysis** — tracks what the agent could not do, scored by frequency, recency, and impact
3. **Opinion Formation** — logs where operator and agent positions differ
4. **Directive Proposals** — suggests behavioral changes for human review
5. **Growth Tracking** — follows operator development over time

High-frequency capability gaps are useful signals for where new tools, specialist changes, or prompt constraints would have the most impact.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Core | Python 3.12, FastAPI |
| Agent Runtime | OpenCode planner/build runs, per-conversation workspaces |
| LLM Routing | OpenRouter, DynamoDB-backed model registry |
| Vector Search | LanceDB user facts, all-MiniLM-L6-v2 embeddings |
| RAG | ChromaDB health docs with PDF extraction, chunking, and deduplication |
| Structured Storage | DynamoDB for directives, health, finance, diary, proposals, model registry |
| Relational Storage | SQLite with WAL for webhooks and activity |
| Tool Runtime | Python tool plugins exposed through scoped MCP servers |
| Observability | Prometheus, Loki, Grafana, Discord status embeds |
| Deployment | Kubernetes (k3s), Terraform, Docker images built via Packer |

---

## Specialists

Domain experts are discovered from `specialists/*/specialist.yaml`. Each is a YAML config plus a Jinja2 prompt template, so adding a specialist is primarily configuration and prompt work rather than routing code.

<details>
<summary><strong>Code &amp; Infrastructure (17 specialists)</strong></summary>

| Specialist | Purpose | Key Tools |
| --- | --- | --- |
| `coder` | General software engineering | terminal, read/write/search files |
| `scripter` | Quick command-oriented tasks | terminal, read/write files |
| `debugger` | Deep code debugging and error analysis | terminal, read/write/search files |
| `architect` | System design and architecture patterns | read/write/search files, AWS docs MCP |
| `secops` | Security operations and vulnerability analysis | terminal, read/search files |
| `devops` | Infrastructure and deployment automation | terminal, read/write files |
| `file_generator` | Structured file generation with syntax validation | terminal, write/read files |
| `git_ops` | Git operations, rebasing, conflicts, PR workflows | terminal, read/write/search files |
| `code_reviewer` | Structured code review | terminal, read/search files |
| `code_explorer` | Codebase navigation and dependency mapping | terminal, read/search files |
| `doc_generator` | READMEs, ADRs, RFCs, API docs, runbooks | terminal, read/write/search files |
| `test_writer` | Test generation and verification | terminal, read/write/search files |
| `refactorer` | Behavior-preserving code refactoring | terminal, read/write/search files |
| `api_designer` | REST, GraphQL, gRPC, and OpenAPI design | read/write/search files |
| `migration_planner` | Database and infrastructure migration planning | terminal, read/write/search files |
| `incident_responder` | Production incident triage and mitigation | terminal, read/search files |
| `performance_analyst` | Profiling, benchmarking, and optimization | terminal, read/search files |

</details>

<details>
<summary><strong>Reasoning, Planning &amp; Communication (15 specialists)</strong></summary>

| Specialist | Purpose |
| --- | --- |
| `planner` | Decomposes goals into sequenced, dependency-aware plans |
| `dialectic` | Structured adversarial reasoning |
| `decision_analyst` | Multi-criteria decision analysis |
| `project_manager` | Implementation verification against planned work |
| `product_manager` | Product discovery, user research, and strategy |
| `product_owner` | Requirements, acceptance criteria, and delivery definition |
| `todo_generator` | Extracts actionable task lists from conversations or documents |
| `proofreader` | Prose editing, grammar, clarity, and tone |
| `email_writer` | Professional email drafting |
| `jira_writer` | Structured Jira tickets and acceptance criteria |
| `constrained_writer` | Character-limited writing for short-form channels |
| `interviewer` | Requirements gathering through structured questioning |
| `summarizer` | Condensing long content into structured summaries |
| `meeting_prep` | Meeting preparation, talking points, and background notes |
| `negotiation_advisor` | Negotiation strategy, BATNA analysis, and concession planning |

</details>

<details>
<summary><strong>Documents, Analysis &amp; Learning (12 specialists)</strong></summary>

| Specialist | Purpose |
| --- | --- |
| `resume` | Resume tailoring via LaTeX, JD analysis, and PDF compilation |
| `cover_letter` | JD-specific cover letter generation |
| `workday` | ATS and Workday form input blocks |
| `pdf_generator` | Formatted PDF creation |
| `changelog_writer` | Release notes from git history |
| `data_analyst` | Data exploration, analysis, and visualization |
| `legal_reader` | Contract, ToS, and policy reading; not legal advice |
| `prompt_engineer` | Prompt writing, testing, and evaluation |
| `sql_analyst` | Query optimization and schema analysis |
| `math_tutor` | Mathematics instruction |
| `language_tutor` | Language learning support |
| `ml_tutor` | Machine learning and AI instruction |

</details>

<details>
<summary><strong>Domain-Specific &amp; Meta (10 specialists)</strong></summary>

| Specialist | Purpose | Key Integration |
| --- | --- | --- |
| `powerlifting_coach` | Training reads, coaching, analysis, and explicit health/training mutations | Health + supplement research MCPs |
| `health_write` | Specialized health mutation path retained for compatibility | Health DynamoDB tools |
| `finance_write` | Finance snapshot mutations | Finance DynamoDB tools |
| `financial_analyst` | Market research and financial analysis | Yahoo Finance + Alpha Vantage MCPs |
| `research_assistant` | Research-style synthesis and supplement corpus search | supplement research tools |
| `media_reader` | File and image analysis | vision-capable model path |
| `career_advisor` | Career strategy, skill gaps, and market positioning | user facts |
| `consensus_builder` | Multi-source synthesis across specialist outputs | handoff/synthesis flow |
| `self_improver` | Analyzes agent performance and proposes improvements | reflection/proposal tools |
| `tarot_reader` | Tarot card readings, meaning lookups, and spread information | tarot tools |

</details>

### Thinking Modes

Longer reasoning modes are implemented as skill packages loaded into prompts when requested:

- `deep_think`
- `sequential_plan`
- `parallel_analysis`

They modify the reasoning protocol for a request without requiring separate specialist implementations.

---

## Tools

Deterministic functions handle data access and domain operations so the model does not guess structured state.

Local tool plugins live under `tools/` and expose schemas plus async executors. The app-side MCP manager indexes tools at startup, and per-run OpenCode configs expose only the tools allowed for the selected specialist.

| Plugin | Purpose |
| --- | --- |
| `health` | Training program CRUD, sessions, competitions, imports, templates, analytics, glossary, health RAG |
| `finance` | Financial profile, goals, accounts, investments, cashflow, tax, insurance, net worth |
| `diary` | Diary entries and current signal computation |
| `proposals` | Directive proposals and implementation plans |
| `supplement_research` | Local supplement research corpus search |
| `tarot` | Tarot card draw, meaning lookup, and spread information |
| `temporal_*` | Date parsing, timezone conversion, duration calculation, age, city time, Unix timestamps |

Native OpenCode MCP tool names are server-prefixed, for example `if_health_health_get_session`. Prompts also expose a fallback shell bridge:

```bash
PYTHONPATH=<app-src:project-root> python -m mcp_runtime.invoke_tool <tool_name> '<json_args>'
```

---

## Memory

| Store | Tech | Purpose |
| --- | --- | --- |
| **User Facts** | LanceDB | Semantic search over operator context: preferences, projects, opinions, health, finance, skills, mental state, and similar categories |
| **Health Docs** | ChromaDB | RAG over health and powerlifting reference documents |
| **Legacy Memory** | ChromaDB | Older memory path still present for compatibility |
| **Conversation State** | Local workspace files | `history.md`, `history.json`, generated files, and run artifacts per conversation |

User facts accumulate over time. Facts carry sources, confidence, categories, and supersession metadata so old or corrected information can be handled explicitly.

---

## Channels

| Platform | Type | Status |
| --- | --- | --- |
| Discord | Bot (`discord.py`) | Active — slash commands, threads, status embeds, attachment delivery |
| OpenWebUI | Polling / chat integration | Active |
| HTTP API | OpenAI-compatible REST | Active |

Message flow: `listener/API -> debounce or request handling -> completions pipeline -> OpenCode planner -> route execution -> chunker -> delivery`.

Discord gets real-time status embeds showing planner failures, route/model/tool progress, specialist runs, and delivery failures.

---

## Utility Applications

Human collaboration layer — TypeScript/Node.js apps that provide visual interfaces to agent-managed data.

| App | Port | What It Does |
| --- | ---: | --- |
| **Hub** | 3000 | Central dashboard aggregating the local portals |
| **Finance Portal** | 3002 | Net worth, investments, accounts, goals, and cashflow |
| **Diary Portal** | 3003 | Journal entries and life-load signals injected into runtime context |
| **Proposals Portal** | 3004 | Kanban board for reviewing agent-proposed directives before they take effect |
| **Powerlifting App** | 3005 | Training sessions, program state, analytics, imports, and templates |
| **Directives Portal** | 3006 | Review, edit, and version the active directive set |

---

## AI Concepts Covered

This project exists to build applied knowledge. Here is what it exercises:

| Concept | Where It Lives |
| --- | --- |
| Multi-agent orchestration | OpenCode planner -> scoped specialist runs -> optional handoffs |
| RAG | Health document corpus and supplement research tooling |
| Vector semantic search | LanceDB user facts with sentence-transformer embeddings |
| Tool use / function calling | Local Python tool plugins exposed through scoped MCP servers |
| Model routing | Planner-selected concrete model IDs backed by an OpenRouter model registry |
| Context management | Per-conversation history, runtime context builders, specialist-scoped prompts |
| Prompt engineering | Jinja2 specialist templates, directive injection, tool protocol generation |
| Agentic execution | Domain/technical OpenCode runs with tool access and workspace artifacts |
| Runtime behavior shaping | DynamoDB directive system with human-reviewed proposals |
| Behavioral feedback loops | Reflection pipeline, pattern detection, capability gaps, directive proposals |
| Cost optimization | Scoped tools, cached AI reports, model metadata, and model allowlists |
| Plugin architecture | Local tool folders surfaced as filtered MCP categories |
| Multi-platform messaging | Discord, OpenWebUI, and HTTP converging into one completions pipeline |
| Observability | Prometheus metrics, Loki logs, Grafana dashboards, Discord status embeds |
| Infrastructure as Code | Terraform, Packer, Docker images, k3s deployment |

---

## Running Locally

```bash
cd app
pip install -r requirements.txt
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Runtime needs at least:

- `OPENROUTER_API_KEY`
- `opencode` on `PATH`
- configured AWS/DynamoDB access for production storage paths

---

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture Deep Dive](docs/ARCHITECTURE.md) | Current runtime, planner flow, scoped MCP configuration, storage, and routing |
| [Comparative Analysis](docs/COMPARATIVE_ANALYSIS.md) | Comparison with adjacent open-source agent systems |
| [Roadmap & Future Work](docs/THINGS_TO_EXPLORE.md) | Known gaps, planned features, and concepts to explore |

---

## License

MIT
