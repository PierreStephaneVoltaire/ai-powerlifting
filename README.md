# IF

A single main agent with context-aware tiering and specialist subagent delegation. Built on the OpenHands SDK, routes through OpenRouter, persists knowledge in LanceDB. Behavior evolves through runtime directives stored in DynamoDB.

---

## What This Is

An architectural exercise and personal learning project — not a product. The goal is to build practical knowledge of multi-agent orchestration, runtime behavior shaping, specialist delegation, and operational observability by building something that actually runs.

It is deployed on a personal Kubernetes (k3s) cluster and used personally, which means real bugs surface and architectural decisions have real consequences.

**Current:** OpenRouter (LLM provider), Discord + OpenWebUI (interaction layers), Prometheus + Loki + Grafana (observability) + Rancher (cluster managment).

---

## How It Works

```
User message (Discord / OpenWebUI / HTTP API)
  → Channel Listener → Debounce (5s batching) → Dispatcher
    → Orchestrator (lightweight: sees specialist list + user intent, not full domain context)
      → condense_intent (strips noise, rewrites as focused task)
        → Specialist (scoped: only its tools, directives, skills, and MCP servers)
          → Tool execution (deterministic functions — DynamoDB CRUD, date parsing, file validation)
          → Agentic loop (multi-turn tool use with stuck detection, for complex tasks)
      → Response → Chunker → Delivery back to platform
```

The orchestrator never sees all specialist domains at once. It classifies intent, picks a specialist, condenses the context, and hands off. Each specialist receives only:

- Its own system prompt template
- Directives filtered to its domain (health specialist gets health directives, not finance ones)
- Its declared tools and MCP servers
- Any applicable AgentSkills

This context scoping is the core architectural choice: it reduces hallucination risk from bloated prompts and keeps token costs proportional to task complexity, not system complexity.

### Tiered Model Selection

Models hallucinate more as their context window fills up. The orchestrator auto-upgrades to larger models as conversation context grows:

| Tier         | When          | Why                                                    |
| ------------ | ------------- | ------------------------------------------------------ |
| **Air**      | < 100K tokens | Fast, cheap — most single-turn tasks                   |
| **Standard** | < 200K tokens | Mid-range — multi-turn conversations                   |
| **Heavy**    | ≥ 200K tokens | Large context window — complex sessions, deep analysis |

Upgrade triggers at 65% capacity. The concrete model for each tier is resolved from a YAML-configured pool sorted by strategy (price, latency, throughput, context size).

### Smart Model Routing for Specialists

Each specialist has a model preset (e.g., `@preset/code`, `@preset/architecture`). At spawn time, a fast LLM selects the best concrete model from the preset's candidate pool using:

- The condensed task intent
- Model metadata (latency, price, context size, throughput)
- The preset's sorting strategy

A proofreading task gets a cheap, fast model. A health programming task gets a model ranked highly for that domain. This happens per-request with no code changes — presets are YAML.

### Runtime Directive System

Behavior rules are stored in DynamoDB, not baked into code. This inverts the typical agent workflow:

**Traditional:** Engineer a comprehensive system prompt upfront → deploy → discover gaps → edit code → redeploy.

**IF:** Start with a blank slate → use the agent → reflection pipeline detects failure patterns → agent proposes directive → human reviews in proposals portal → approved directive takes effect on next request.

Directives are priority-tiered (0–5) for conflict resolution. When two directives contradict, the higher-priority one wins deterministically. Specialists receive only directives matching their declared `directive_types`, so domain rules don't leak across contexts.

The agent can propose new directives (`directive_add`), but nothing takes effect without human approval through the proposals portal.

### Behavioral Feedback Loop

After sessions (>5 turns), periodically (every 6h), or on demand (`/reflect`):

1. **Pattern Detection** — recurring behaviors, failure modes
2. **Capability Gap Analysis** — tracks what the agent couldn't do, scores by frequency × recency × impact
3. **Opinion Formation** — logs where operator and agent positions differ
4. **Directive Proposals** — suggests behavioral changes for human review
5. **Growth Tracking** — operator development over time

High-frequency capability gaps are auto-promoted to tool suggestions. Gaps that keep appearing signal where new tools or specialist improvements would have the most impact.

---

## Tech Stack

| Layer              | Technology                                                                                     |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| Core               | Python 3.12, FastAPI, OpenHands SDK 1.11.4                                                     |
| LLM Routing        | OpenRouter (dynamic model registry, per-provider latency/throughput tracking)                  |
| Vector Search      | LanceDB (user facts, all-MiniLM-L6-v2 embeddings)                                              |
| RAG                | ChromaDB (health docs — Tika PDF extraction, 500-token chunks, 50-token overlap, SHA256 dedup) |
| Structured Storage | DynamoDB (directives, health, finance, diary, proposals, model registry)                       |
| Relational         | SQLite with WAL (webhooks, activity)                                                           |
| Observability      | Prometheus + Loki + Grafana                                                                    |
| Deployment         | Kubernetes (k3s), Terraform, Docker via Packer                                                 |
| Shell Access       | OpenHands SDK LocalWorkspace (per-conversation isolated directories)                           |

---

## Specialists

Domain experts spawned by the orchestrator. Each is a YAML config + Jinja2 prompt template — adding one requires no code changes.

<details>
<summary><strong>Code & Infrastructure (17 specialists)</strong></summary>

| Specialist            | Purpose                                                       | Key Tools                             |
| --------------------- | ------------------------------------------------------------- | ------------------------------------- |
| `coder`               | General software engineering                                  | terminal, read/write/search files     |
| `scripter`            | Quick tasks (3-5 commands, max 3 turns)                       | terminal, read/write files            |
| `debugger`            | Deep code debugging and error analysis                        | terminal, read/write/search files     |
| `architect`           | System design and architecture patterns                       | read/write/search files, AWS docs MCP |
| `secops`              | Security operations and vulnerability analysis                | terminal, read/search files           |
| `devops`              | Infrastructure and deployment automation                      | terminal, read/write files            |
| `file_generator`      | Structured file generation with syntax validation             | terminal, write/read files            |
| `git_ops`             | Git operations — rebasing, conflicts, PR workflows            | terminal, read/write/search files     |
| `code_reviewer`       | Structured code review                                        | terminal, read/search files           |
| `code_explorer`       | Codebase navigation, dependency mapping                       | terminal, read/search files           |
| `doc_generator`       | Technical documentation — READMEs, ADRs, RFCs, runbooks       | terminal, read/write/search files     |
| `test_writer`         | Test generation (GENERATE→RUN→FIX→VERIFY loop)                | terminal, read/write/search files     |
| `refactorer`          | Code refactoring without behavior change                      | terminal, read/write/search files     |
| `api_designer`        | REST/GraphQL/gRPC API design, OpenAPI specs                   | read/write/search files               |
| `migration_planner`   | Database/infra migration planning with rollback               | terminal, read/write/search files     |
| `incident_responder`  | Production incident triage — action-first                     | terminal, read/search files           |
| `performance_analyst` | Profiling and optimization (MEASURE→IDENTIFY→OPTIMIZE→VERIFY) | terminal, read/search files           |

</details>

<details>
<summary><strong>Reasoning, Planning & Communication (13 specialists)</strong></summary>

| Specialist            | Purpose                                                                |
| --------------------- | ---------------------------------------------------------------------- |
| `planner`             | Decomposes goals into sequenced, dependency-aware plans                |
| `dialectic`           | Structured adversarial reasoning — thesis-antithesis-synthesis         |
| `decision_analyst`    | Multi-criteria decision analysis with weighted scoring                 |
| `project_manager`     | Implementation verification — confirms planned work exists in codebase |
| `todo_generator`      | Extracts actionable task lists from conversations/documents            |
| `proofreader`         | Prose editing, grammar, clarity, tone                                  |
| `email_writer`        | Professional email drafting                                            |
| `jira_writer`         | Structured Jira tickets with acceptance criteria                       |
| `constrained_writer`  | Character-limited content (tweets, Discord, SMS)                       |
| `interviewer`         | Requirements gathering through structured questioning                  |
| `summarizer`          | Condensing long content into structured summaries                      |
| `meeting_prep`        | Meeting preparation — talking points, background research              |
| `negotiation_advisor` | Negotiation strategy — BATNA analysis, concession planning             |

</details>

<details>
<summary><strong>Documents, Analysis & Learning (11 specialists)</strong></summary>

| Specialist         | Purpose                                                     |
| ------------------ | ----------------------------------------------------------- |
| `resume`           | Resume tailoring via LaTeX, JD analysis, compile to PDF     |
| `cover_letter`     | Cover letter generation — JD-specific, one page max         |
| `workday`          | Workday/ATS form input — copy-paste-ready blocks            |
| `pdf_generator`    | Formatted PDF creation via WeasyPrint/Pandoc/LaTeX          |
| `changelog_writer` | Release notes from git history                              |
| `data_analyst`     | Data exploration, analysis, visualization                   |
| `legal_reader`     | Contract/ToS analysis — NOT legal advice                    |
| `prompt_engineer`  | Writing and testing prompts for LLMs                        |
| `sql_analyst`      | Database query optimization, schema analysis                |
| `math_tutor`       | Mathematics instruction — algebra through ML/AI math        |
| `language_tutor`   | Language learning — Japanese, Spanish, French               |
| `ml_tutor`         | ML/AI instruction — architectures, training, implementation |

</details>

<details>
<summary><strong>Domain-Specific & Meta (8 specialists)</strong></summary>

| Specialist           | Purpose                                                                         | Key Integration                                           |
| -------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `health_write`       | Training program mutations (log sessions, RPE, body weight)                     | Health DynamoDB tools (35 tools)                          |
| `finance_write`      | Finance snapshot mutations (balances, holdings, goals)                          | Finance DynamoDB tools (21 tools)                         |
| `financial_analyst`  | Market research and financial analysis                                          | Yahoo Finance + Alpha Vantage MCPs                        |
| `research_assistant` | Up-to-date research via native web search + local Examine.com supplement corpus | `supplement_search`, `plan_append/read`, read/write files |
| `media_reader`       | File and image analysis                                                         | Vision model (single turn)                                |
| `career_advisor`     | Career strategy — trajectory, skill gaps, market positioning                    | User facts                                                |
| `consensus_builder`  | Multi-source synthesis — spawns 2-3 specialists, collects, synthesizes          | Nested specialist spawning                                |
| `self_improver`      | Analyzes IF's performance, proposes directive/prompt improvements               | Read/write/search files                                   |

</details>

### Skill Modes

Specialists can be invoked with a skill modifier that shifts their perspective. A single system prompt injection — no separate agent.

`red_team` · `blue_team` · `pro_con` · `steelman` · `devils_advocate` · `backcast` · `rubber_duck` · `eli5` · `formal` · `speed` · `teach`

Example: `spawn_specialist(specialist_type="architect", skill="red_team")` → adversarial architecture review.

---

## Tools

Deterministic functions the agent calls instead of guessing. Two categories:

**System tools** (loaded in orchestrator): user fact CRUD, directive management, capability gap tracking, opinion logging, context/signal retrieval, specialist delegation (list_specialists, condense_intent, deep_think, spawn_specialist, spawn_specialists), media reading, orchestration.

**External tool plugins** (loaded per specialist): self-contained packages in `tools/` with `tool.yaml` + `tool.py`. Auto-discovered at startup, hot-reloadable via `POST /admin/reload-tools`.

| Plugin                   | Tools | Purpose                                                                                  |
| ------------------------ | ----- | ---------------------------------------------------------------------------------------- |
| `health`                 | 35    | Training program CRUD, session logging, RAG search, unit conversions                     |
| `finance`                | 21    | Financial profile, investments, goals, cashflow                                          |
| `diary`                  | 2     | Write-only diary entries, signal computation                                             |
| `proposals`              | 4     | Proposal CRUD, implementation plan generation                                            |
| `temporal_*` (7 plugins) | 7     | Date parsing, timezone conversion, duration calculation, age, city time, Unix timestamps |

Plugins support two execution modes:

- **In-process** — imported directly (heavy plugins already in main venv)
- **Subprocess** — isolated `uv` venv per plugin, invoked as a subprocess (clean dependency isolation)

All tools follow the OpenHands SDK `Action → Observation → Executor → ToolDefinition` pattern.

---

## Memory

| Store                      | Tech                       | Purpose                                                                                                                                                                |
| -------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **User Facts**             | LanceDB (all-MiniLM-L6-v2) | Semantic search over 22 categories of operator context — personal, preferences, opinions, skills, health, finance, mental state, etc. Context-scoped per conversation. |
| **Health Docs**            | ChromaDB                   | RAG over PDF documents (IPF rulebook, supplements, anti-doping). Tika extraction, 500-token chunks, 50-token overlap, SHA256 dedup for incremental indexing.           |
| **Conversation Summaries** | Fire-and-forget            | Async summarization after conversations end.                                                                                                                           |

User facts accumulate over time — the agent learns preferences, tracks life events, builds project context. Facts have sources (user-stated, model-observed, conversation-derived) and confidence scores.

---

## Channels

| Platform  | Type                     | Status                                          |
| --------- | ------------------------ | ----------------------------------------------- |
| Discord   | Bot (discord.py)         | Active — slash commands, threads, status embeds |
| OpenWebUI | Polling (5s)             | Active                                          |
| HTTP API  | REST (OpenAI-compatible) | Active                                          |

Message flow: `listener → debounce (5s) → dispatcher → translator → completions pipeline → chunker (1500 chars) → delivery`

Discord gets real-time status embeds (color-coded) showing: message received, model selected, subagent spawning/completed/failed, tool started/completed/failed.

---

## Utility Applications

Human collaboration layer — TypeScript/Node.js apps that give visual interfaces to agent-managed data.

| App                  | Port | What It Does                                                                       |
| -------------------- | ---- | ---------------------------------------------------------------------------------- |
| **Hub**              | 3000 | Central dashboard aggregating all portals                                          |
| **Finance Portal**   | 3002 | Net worth, investments, cashflow — data managed by `finance_write` specialist      |
| **Diary Portal**     | 3003 | Mental health journaling and signals — distilled into context injected per request |
| **Proposals Portal** | 3004 | Kanban board for reviewing agent-proposed directives before they take effect       |
| **Powerlifting App** | 3005 | Training tracking and analytics — data managed by `health_write` specialist        |

---

## AI Concepts Covered

This project exists to build applied knowledge. Here's what it exercises:

| Concept                              | Where It Lives                                                                          |
| ------------------------------------ | --------------------------------------------------------------------------------------- |
| Multi-agent orchestration            | Orchestrator → specialist delegation with context scoping                               |
| RAG (Retrieval-Augmented Generation) | ChromaDB health docs pipeline — extraction, chunking, dedup, retrieval                  |
| Vector semantic search               | LanceDB user facts with all-MiniLM-L6-v2 embeddings                                     |
| Embedding models                     | Sentence transformers for fact/query encoding                                           |
| Tool use / function calling          | 70+ deterministic tools via OpenHands SDK pattern                                       |
| Dynamic model routing                | Task-aware model selection from candidate pools using fast LLM                          |
| Context window management            | Tiered models, conversation summarization, directive scoping per specialist             |
| Prompt engineering                   | Jinja2 templates, directive injection, skill modifiers, system prompt assembly pipeline |
| Agentic loops                        | Multi-turn tool execution with stuck detection for complex specialists                  |
| Runtime behavior shaping             | DynamoDB directive system with priority-based conflict resolution                       |
| Behavioral feedback loops            | Reflection pipeline — pattern detection, gap analysis, directive proposals              |
| Cost optimization                    | Tier-based model selection, context condensation, per-provider price/latency tracking   |
| Plugin architecture                  | Hot-reloadable tool plugins with auto-discovery (YAML + Python)                         |
| AgentSkills compliance               | Skills portable across 30+ compliant agents (GitHub Copilot, Claude Code, Cursor, etc.) |
| Multi-platform messaging             | Listener/translator/dispatcher pattern across Discord, OpenWebUI, HTTP                  |
| Observability                        | Prometheus metrics, Loki logs, Grafana dashboards                                       |
| Infrastructure as Code               | Terraform (K8s + AWS), Packer (Docker images), k3s deployment                           |

---

## Documentation

| Document                                             | Contents                                                                                           |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| [Architecture Deep Dive](docs/ARCHITECTURE.md)       | System prompt assembly, tool authoring, channel internals, storage details, model router mechanics |
| [Comparative Analysis](docs/COMPARATIVE_ANALYSIS.md) | Detailed comparison with OpenHands, Claude Cowork, OpenClaw, Hermes Agent                          |
| [Roadmap & Future Work](docs/THINGS_TO_EXPLORE.md)   | Known gaps, planned features, AI concepts to add                                                   |

---

## License

MIT
