# NoLift A powerlifting meet-prep portal

Powerlifting is just a hobby for me. I got frustrated with my lack of progress,
so I decided to pull together all my historical training data and actually look
at what works.

Over six years of lifting I've had mixed experiences with coaches some really
great, some providing cookie-cutter coaching. I came to the conclusion that my
bad experiences came down to a lack of communication. But it's hard to explain
six years of training history to someone over a couple of sessions. This
platform exists to fix that: it aggregates everything past workouts, fatigue
profile, budget, even past competition performance and lift videos into one
place an athlete can share with their coach so they can collaborate on training.

This is a **competition-geared** notebook, not a free-form workout tracker. The
assumption is that the athlete is preparing for a meet, because meets provide the
guidelines and standards an athlete must adhere to a much better anchor for a
training app than open-ended logging.

> This is not meant to replace coaching. It's a notebook where coaches and
> athletes can use formulas and AI to collaborate on their meet-prep journey.

---

## Why I'm building it

I'm testing the app by being its first user. I use it for my own training and
comp prep and adjust it based on perceived needs or bugs I run into.

### My numbers

My last completed meet (data pulled straight from the app's DynamoDB store):

|                                               | Squat  | Bench  | Deadlift | **Total**  | Bodyweight |
| --------------------------------------------- | ------ | ------ | -------- | ---------- | ---------- |
| **Ottawa Open & Bench Press** CPU, 2025-10-04 | 185 kg | 115 kg | 220 kg   | **520 kg** | 78.2 kg    |

The projection at T‑1 week had me at 546.4 kg (total Projection-to-Result Ratio
of 0.952). My own notes from that day: _"sandbagged deadlifts: had at least
10 kg in me."_ That gap between projected and actual is exactly what the
projection-calibration math is designed to close over future meets.

My goal for 2026 is a **550 kg total** and to explore different federations. I
haven't locked down which meet I'm running yet, so the current program targets
aren't shown here they shift as I decide.

### A learning tool, too

I'm also using this project as a learning tool to play with AI prompting
techniques, tools, and AI-specific architecture, and to keep my software-design
skills fresh. Expect the AI side to evolve fast.

---

## Features

The portal is split into athlete-facing features today, with social features on
the roadmap.

### Training

- **Dashboard** the main hub summarizing the current program state.
- **Sessions** calendar (Month / Agenda / Compact views), full session editor
  with planned vs logged work, per-set statuses, failure reasons, RPE, wellness,
  pain log, and video attachments.
- **Analysis** the analytics hub with four tabs:
  - **Weekly** current maxes, compliance, fatigue, readiness, peaking,
    workload, alerts, and AI correlation + program evaluation.
  - **Blocks** per-block deterministic analytics, AI evaluation, and exports.
  - **Compare** cross-block and lifetime comparison (deterministic + AI).
  - **Maxes** all-time and windowed max history.
- **Designer** phase CRUD, drag-and-drop session design, goals, federations,
  competitions, glossary.
- **Templates** library, creation, block-to-template conversion, AI
  evaluation, import jobs.
- **Import wizard** AI-assisted spreadsheet import (classification → parse →
  glossary resolution → apply).
- **Glossary** canonical exercise definitions, muscle mapping, generated
  exercise text, fatigue profiles, accessory e1RM estimates.
- **Lift profiles** per-lift (squat/bench/deadlift) style notes, sticking
  points, stimulus coefficient, INOL thresholds, e1RM multiplier.
- **Tools** DOTS calculator, attempt selector, unit converter, percent table,
  plate calculator, weight tracker.
- **Videos** S3-backed lift video library with auto-generated thumbnails.
- **Rankings** compare your totals/DOTS against the OpenPowerlifting dataset.
- **Profiles** public lifter profile search and your own profile management.
- **Budget** comp-prep budget tracking (equipment, supplements, memberships,
  meet entry) with a purchase timeline.
- **Supplements / Biometrics / Notes** supplement phases, diet & recovery
  notes, dated program notes.

### The UI is just one interface

The portal is one way in. The same training data is available through the
**Discord bot**, which relays your messages to the Coach, and through **MCP**:
every domain operation is a typed tool. The backend is a thin transport layer
over those same operations, so nothing is locked behind the UI.

---

## Calculations

The deterministic analytics are the backbone. None of it is textbook-generic
every formula was customized for meet prep on real (noisy) training logs.

Highlights (full math and reasoning in [`docs/FORMULAS.md`](docs/FORMULAS.md)):

- **Conservative e1RM** RPE-table / conservative-percent estimate, 90th
  percentile of executed sets over 6 weeks. No Epley/Brzycki.
- **Progression rate** Theil-Sen regression on best weekly e1RM, deload-aware
  effective-week indexing.
- **Meet projection** diminishing-returns curve, DOTS-gated decay & peak
  factors, taper- and deload-aware, clamped ceiling.
- **Projection calibration (PRR)** post-meet re-tuning of the decay factor
  from actual-vs-projected ratios.
- **4-dimensional fatigue** axial / neural / peripheral / systemic, nonlinear
  per-set load scaling.
- **Fatigue index** failures, acute spikes, RPE, intensity density, monotony,
  and decaying reservoirs; skip-rate isn't allowed to dilute real fatigue.
- **Stimulus-adjusted INOL** INOL modulated by per-lift stimulus coefficient.
- **Phase-aware RPE drift & readiness** residual against phase target midpoint,
  missing-data-aware re-weighted readiness score.
- **Volume landmarks** MV / MEV / MAV / MRV from whole-program history.
- **Specificity ratio** narrow & broad SBD specificity with weeks-to-comp
  bands.
- **Banister CTL/ATL/TSB**, taper quality, **DOTS** and **IPF GL** scoring.

## AI components

The AI is narrow and tool-scoped. The browser never talks to a model, and
neither do the domain services. Every AI request goes through the **Coach**, a
small worker that uses OpenAI's **Codex** as its agent harness. Codex runs
locked down: no shell, no file writes, no plugins, and no access to secrets.

Right now the Coach runs on my ChatGPT subscription, but the harness and the
model are separate. Each AI feature has its own provider, model and reasoning
effort in the coach Terraform vars, so moving a feature to OpenRouter or API
pricing is a config change, not a rewrite. The heavier reviews (program
evaluation, multi-block comparison, template evaluation) run at high effort;
everything else runs at medium.

Where the AI shows up:

- Exercise **ROI correlation** analysis
- **Program evaluation** (full-block, structured stance/strengths/strategy)
- **Multi-block lifetime comparison**
- **Template evaluation** against what the program is meant to do
- **Lift-profile** option suggestions and stimulus-coefficient estimation
- **Accessory e1RM backfill**
- **Spreadsheet import** (classify / parse / glossary-resolve)
- **Glossary text generation**, muscle-group and fatigue-profile estimation
- **Budget** advice and purchase timeline
- **Session note drafting**, **auto-regulation** suggestions, and the
  **Discord** coach chat

### How a request runs

The domain code does the real work. It loads the data, computes the numbers,
and only stops when it needs the model to interpret them. At that point it
hands the Coach a prompt and the exact JSON shape it expects back, waits for
the answer, then picks up where it left off. The frontend just polls until the
job is done.

```mermaid
sequenceDiagram
  participant UI as Browser
  participant OP as oauth2-proxy
  participant BE as powerlifting-app-backend
  participant SVC as pl-glossary (any domain service)
  participant C as pl-coach (Codex)
  participant L as litellm
  participant P as ChatGPT subscription / OpenRouter
  UI->>OP: request an AI feature
  OP->>BE: verified identity
  BE->>SVC: run the operation
  SVC->>C: start a job
  SVC-->>C: needs the model (prompt + JSON shape)
  C->>L: Responses API, model alias (pl-standard)
  L->>P: routed deployment, fallback alias on failure
  P-->>L: completion
  L-->>C: JSON
  C->>C: validate, retry up to 3 times
  C->>SVC: resume with the answer
  SVC-->>C: result
  BE->>C: poll for the result
  C-->>BE: result
  BE-->>UI: result
```

The analysis reports are cached. If nothing about the data changed, you get
the stored report, and two people opening the same report share one job.

### Keeping it honest

Every answer is checked against its JSON schema before anything uses it. A bad
answer is sent back to the model with the error, and after three misses the
job fails instead of passing on something half-valid.

The shape being right doesn't make the content right, so the rest of the
guard rails are about keeping the model away from making things up:

- **Numbers come from the app, not the model.** Specificity, fatigue trends,
  sets per muscle and % of max are all computed in code and handed over.
- **Closed answers where possible.** Lift-profile suggestions can only pick
  from the form's options, and muscle estimates can only name known muscles.
- **Ranges are clamped in code**, like the 1.0–2.0 stimulus coefficient.
  Fatigue estimates aren't bounded yet.
- **Nothing is saved without you.** Suggestions pre-fill the form, imports are
  staged for review, and the Discord coach only writes when asked.
- **No silent retries.** If a job is interrupted, it's flagged so you can
  check what happened instead of being re-run.

What's not checked is whether a valid answer is a _good_ one. The reports are
advice, they cite the numbers they were given, and you can regenerate them.

### Running things in parallel

Each provider has its own limit on how many calls run at once; extra jobs
just wait their turn. The ChatGPT subscription throttles at about two
concurrent requests per account, so it stays at 2 and the Coach stays at one
pod while it's in use. API-key providers can go higher.

---

## Architecture

The stack runs on a **bare-metal k3s** node behind a Cloudflare tunnel. There
are **20 typed HTTP/MCP domain services**, each with its own Deployment and
operation manifest in [`src/services/operations/`](src/services/operations/).
The diagrams below separate incoming traffic, the service inventory, and the
supporting infrastructure so each component stays visible.

### Every service and how they connect

```mermaid
flowchart TB
  UI["Browser<br/>React PWA"]
  DiscordApp["Discord"]
  CF["Cloudflare<br/>DNS + tunnel"]
  ChatGPT["ChatGPT subscription"]
  OpenRouter["OpenRouter"]

  subgraph Cluster["k3s · powerlifting namespace · Istio ambient mesh"]
    subgraph Edge["Edge"]
      Tunnel["cloudflared"]
      Gateway["edge-powerlifting<br/>NGINX Gateway Fabric"]
      Waypoint["nolift-waypoint<br/>mTLS + caller allow-lists"]
    end

    subgraph Identity["Identity"]
      Proxy["oauth2-proxy<br/>browser session"]
      Auth["authentik-server<br/>OIDC"]
      AuthWorker["authentik-worker"]
      AuthPG[("authentik-postgres<br/>CNPG")]
    end

    subgraph Portal["Portal"]
      FE["powerlifting-app-frontend<br/>static PWA"]
      BE["powerlifting-app-backend<br/>Express API"]
    end

    subgraph Domains["Domain services · Python"]
      Program["pl-program"]
      Sessions["pl-sessions"]
      Templates["pl-templates"]
      Glossary["pl-glossary"]
      LiftProfiles["pl-lift-profiles"]
      Competition["pl-competition"]
      Federation["pl-federation"]
      Goals["pl-goals"]
      Budget["pl-budget"]
      WeightLog["pl-weight-log"]
      Performance["pl-performance"]
      Calculations["pl-calculations"]
      Profile["pl-profile<br/>identity + access_context"]
      Videos["pl-videos"]
      Imports["pl-imports"]
      Export["pl-export"]
    end

    subgraph Analysis["Analysis"]
      Analytics["pl-analytics<br/>Rust"]
      AnalyticsAI["pl-analytics-ai<br/>Go"]
      AnalyticsExport["pl-analytics-export<br/>Go"]
      Rankings["pl-rankings<br/>Rust"]
    end

    subgraph AI["AI runtime"]
      Coach["pl-coach<br/>Codex worker"]
      Bot["pl-coach-discord<br/>gateway bot"]
      CacheMCP["pl-prompt-cache-mcp"]
      Qdrant[("pl-prompt-cache<br/>Qdrant")]
    end

    subgraph LLM["LiteLLM layer · llm.nolift.training"]
      LiteLLM["litellm<br/>providers + model aliases + fallbacks"]
      LLMPG[("litellm-postgres<br/>CNPG · UI users")]
    end

    Valkey[("pl-valkey<br/>sessions + caches")]
  end

  UI --> CF --> Tunnel --> Gateway
  Gateway -->|"/"| FE
  Gateway -->|"/api, /oauth2"| Proxy
  Gateway -->|"auth host"| Auth
  Gateway -->|"llm host"| LiteLLM

  Proxy -->|"authenticated API"| BE
  Proxy <-->|"OIDC"| Auth
  Proxy -->|"sessions"| Valkey
  Auth <-->|"identity source"| DiscordApp
  Auth & AuthWorker --> AuthPG

  BE -->|"HTTP operations"| Domains
  BE --> Analytics & AnalyticsAI & AnalyticsExport & Rankings
  BE -->|"AI jobs + polling"| Coach
  BE -->|"cache"| Valkey

  Domains -->|"access_context"| Profile
  Program & Competition & Templates & Export & Profile -->|"analysis reads"| Analytics
  Domains -->|"AI operations"| Coach
  Domains -->|"cache"| Valkey

  Analytics -->|"domain reads"| Domains
  Analytics -->|"gRPC Reports"| AnalyticsAI
  AnalyticsAI -->|"gRPC AnalyticsData"| Analytics
  AnalyticsAI -->|"gRPC Exports"| AnalyticsExport
  AnalyticsExport -->|"gRPC AnalyticsData"| Analytics
  Analytics --> Rankings
  AnalyticsAI -->|"AI jobs"| Coach
  Analytics & AnalyticsAI & Rankings -->|"cache"| Valkey

  DiscordApp <-->|"websocket"| Bot
  Bot -->|"chat"| Coach
  Coach -->|"MCP tools"| Domains
  Coach --> Analytics & AnalyticsAI & Rankings
  Coach -->|"exact reply cache"| Valkey
  Coach -->|"semantic lookup"| CacheMCP --> Qdrant
  Coach -->|"Responses API · aliases pl-standard, pl-light, pl-documents"| LiteLLM

  LiteLLM -->|"chatgpt/ deployments"| ChatGPT
  LiteLLM -->|"openrouter/ deployments"| OpenRouter
  LiteLLM -->|"admin UI SSO"| Auth
  LiteLLM --> LLMPG
```

Authentik is the only login authority; Discord is its identity source.
OAuth2 Proxy owns the Valkey-backed browser session and forwards the verified
identity to Express. Express no longer holds a Passport session or a direct
Discord OAuth callback. Both public hostnames pass through NGINX.

### Every domain service

Each box below is a separate service, with typed HTTP operations for the
backend and MCP tools for the Coach. The four frames organize the inventory
by purpose; they are not shared processes or extra routing layers.

```mermaid
flowchart TB
  BE["Express backend<br/>HTTP operations"]
  Coach["pl-coach<br/>MCP tools"]

  subgraph Training["Training"]
    direction TB
    Program["pl-program<br/>programs, blocks, phases, notes"]
    Sessions["pl-sessions<br/>planned and logged training"]
    Templates["pl-templates<br/>reusable programs + evaluation"]
    Glossary["pl-glossary<br/>exercises, muscles, fatigue profiles"]
    LiftProfiles["pl-lift-profiles<br/>technique + stimulus tuning"]
    Program ~~~ Sessions ~~~ Templates ~~~ Glossary ~~~ LiftProfiles
  end

  subgraph MeetPrep["Meet preparation"]
    direction TB
    Competition["pl-competition<br/>entries, attempts, results"]
    Federation["pl-federation<br/>master directory + user library"]
    Goals["pl-goals<br/>athlete goals"]
    Budget["pl-budget<br/>expenses, advice, purchase timeline"]
    WeightLog["pl-weight-log<br/>dated bodyweight entries"]
    Competition ~~~ Federation ~~~ Goals ~~~ Budget ~~~ WeightLog
  end

  subgraph Analysis["Analysis and performance"]
    direction TB
    Analytics["pl-analytics<br/>deterministic analysis · Rust"]
    AnalyticsAI["pl-analytics-ai<br/>AI report workflows · Go"]
    AnalyticsExport["pl-analytics-export<br/>block + lifetime exports · Go"]
    Performance["pl-performance<br/>current maxes, history, targets"]
    Calculations["pl-calculations<br/>e1RM, DOTS, units, percentages"]
    Rankings["pl-rankings<br/>OpenPowerlifting comparisons · Rust"]
    Analytics ~~~ AnalyticsAI ~~~ AnalyticsExport ~~~ Performance ~~~ Calculations ~~~ Rankings
  end

  subgraph Records["Profiles and data exchange"]
    direction TB
    Profile["pl-profile<br/>identity, grants, relationships, notes"]
    Videos["pl-videos<br/>lift library + media metadata"]
    Imports["pl-imports<br/>parse, review, apply spreadsheets"]
    Export["pl-export<br/>program history + Markdown"]
    Profile ~~~ Videos ~~~ Imports ~~~ Export
  end
  BE --> Training & MeetPrep & Analysis & Records
  Coach --> Training & MeetPrep & Analysis & Records
```

The sixteen Python services share the `if-powerlifting-fns` image. Analytics
and Rankings have their own Rust images; Analytics AI and Analytics Export
have their own Go images. The old analytics reports sidecar has been replaced
by these separate services.

Every service checks application permissions at its HTTP/MCP boundary using
the current grants and publication settings. `pl-profile` manages those
records; it is not a central authorization hop for every operation.

### Analytics, AI and caches

All model traffic goes through the **LiteLLM layer** at `llm.nolift.training`.
LiteLLM holds the provider credentials (from SSM Parameter Store) and the
ChatGPT subscription login, once. Apps only name **model aliases**
(`pl-standard`, `pl-light`, `pl-documents`); each alias groups one or more
provider deployments and can fall back to another alias. The admin UI signs in
through Authentik, limited to the users in `litellm_admins`.

```mermaid
flowchart LR
  Analytics["pl-analytics"]
  AI["pl-analytics-ai"]
  Export["pl-analytics-export"]
  Features["AI-enabled domain operations<br/>pl-templates, pl-glossary, pl-imports,<br/>pl-lift-profiles, pl-budget"]
  Coach["pl-coach<br/>Codex runtime"]
  Valkey[("pl-valkey<br/>analysis + reply caches")]
  CacheMCP["pl-prompt-cache-mcp<br/>semantic cache tools"]
  Qdrant[("pl-prompt-cache<br/>Qdrant vectors")]
  State[("pl-coach-state PVC<br/>jobs + Codex state")]

  subgraph LLM["LiteLLM layer"]
    direction TB
    Aliases["model aliases<br/>pl-standard · pl-light · pl-documents"]
    Router["router<br/>load balancing + alias fallbacks"]
    Creds["provider credentials<br/>SSM /powerlifting/litellm/*"]
    Token[("litellm-chatgpt-token PVC<br/>subscription login")]
    Aliases --> Router --> Creds
    Router --> Token
  end

  ChatGPT["ChatGPT subscription"]
  OpenRouter["OpenRouter"]
  Compat["OpenAI-compatible providers"]

  Analytics -->|"gRPC: generate reports"| AI
  AI -->|"gRPC: analysis data"| Analytics
  AI -->|"gRPC: export context"| Export
  Export -->|"gRPC: analysis data"| Analytics
  AI -->|"inference jobs"| Coach
  Features -->|"inference jobs"| Coach
  Coach -->|"Responses API"| Aliases
  Router --> ChatGPT & OpenRouter & Compat
  Analytics --> Valkey
  AI --> Valkey
  Coach -->|"exact reply cache"| Valkey
  Coach -->|"semantic reply lookup"| CacheMCP --> Qdrant
  Coach --> State
```

AI-capable operations hand inference to the Coach and resume with its
validated response. The analytics services also exchange computed data over
gRPC; report generation and export run outside the deterministic analytics
process. Valkey stores cached results, while Qdrant supports semantic prompt
and reply lookup through its own MCP service.

### Storage and media

```mermaid
flowchart LR
  subgraph Services["Domain + analysis services"]
    direction TB
    SvcList["pl-program · pl-sessions · pl-templates · pl-glossary<br/>pl-lift-profiles · pl-competition · pl-federation · pl-goals<br/>pl-budget · pl-weight-log · pl-performance · pl-calculations<br/>pl-profile · pl-videos · pl-imports · pl-export<br/>pl-analytics · pl-analytics-ai · pl-analytics-export"]
  end
  BE["Express backend"]
  Rankings["pl-rankings"]
  UI["Browser"]

  subgraph AWS["AWS"]
    DDB[("DynamoDB<br/>profiles, training, grants,<br/>competitions, budgets")]
    Master[("DynamoDB<br/>master competitions + federations")]
    S3[("S3<br/>videos, thumbnails, media,<br/>reports + OpenPowerlifting dataset")]
    CDN["CloudFront<br/>private S3 origin"]
    Sync["master-sync Lambda"]
    Thumbs["video-thumbnail Lambda<br/>FFmpeg"]
  end

  Services -->|"domain records"| DDB
  Services -->|"files and reports"| S3
  Rankings -->|"load dataset"| S3
  UI -->|"video upload"| BE -->|"bounded multipart upload"| S3
  BE -->|"authorize video, redirect to signed URL"| UI
  S3 -->|"media delivery"| CDN --> UI
  S3 -->|"videos/ upload event"| Thumbs
  Thumbs -->|"thumbnail file"| S3
  Thumbs -->|"video metadata"| DDB
  Master -->|"DynamoDB Streams"| Sync -->|"update athlete directories"| DDB
```

Application data stays in DynamoDB and S3; Postgres is for Authentik.
Thumbnails are served unsigned through CloudFront. Full videos require an
authorized redirect to a signed CDN URL; budget media and avatars retain
their authorized API endpoints. The two retained AWS Lambdas generate video
thumbnails and copy master competition/federation updates to athlete directories.
See [ADR 0004](docs/adr/0004-media-delivery-through-cdn.md) for media access
and signed-URL expiry.

### Mesh, monitoring and deployment

Istio Ambient supplies workload identity and strict mTLS through `ztunnel`.
The `nolift-waypoint` enforces service caller policies; each service still
checks the acting Person's permissions. `istiod` manages the mesh and the
Istio CNI enrolls workloads. These transport controls apply across the service
diagrams above; see [ADR 0006](docs/adr/0006-ambient-mesh-and-authentik-only-login.md).

```mermaid
flowchart LR
  subgraph Monitoring["monitoring namespace"]
    Node["node-exporter<br/>host metrics"]
    Containers["cAdvisor<br/>container metrics"]
    Kube["kube-state-metrics<br/>Kubernetes object state"]
    Events["event-exporter<br/>Kubernetes events"]
    Prometheus["Prometheus"]
    Promtail["Promtail<br/>container logs"]
    Loki["Loki"]
    Grafana["Grafana"]
    Node & Containers & Kube & Events --> Prometheus
    Events -->|"event records"| Loki
    Promtail --> Loki
    Grafana -->|"query metrics"| Prometheus
    Grafana -->|"query logs"| Loki
  end

  CI["GitHub Actions"] -->|"build and publish images"| ECR["AWS ECR"]
  CI -->|"kubernetes-apply job"| Runner["In-cluster Actions runner"]
  Runner -->|"Terraform stacks"| Workloads["k3s workloads"]
  Workloads -->|"pull images"| ECR
  Workloads -->|"container logs"| Promtail
```

Grafana is reached by port-forward on `localhost:3000`. Infrastructure is
Terraform, with separate states for each scope:

| Location | Scope |
| --- | --- |
| `terraform/` | AWS and Cloudflare resources, applied by CI |
| `terraform/k8s/core` | Namespaces, secrets, runner, Authentik, CNPG Postgres, monitoring |
| `terraform/k8s/perms` | Kubernetes service accounts and RBAC |
| `terraform/k8s/network` | NGINX Gateway, HTTP routes, Cloudflare tunnel |
| `terraform/k8s/mesh` | Istio control plane, CNI and ztunnel |
| `terraform/k8s/app` | Portal, domain services, caches, OAuth2 Proxy, waypoint and service policies |
| `terraform/coach` | Coach, Discord bot and persistent state |

The in-cluster runner applies the Kubernetes stacks and the separate Coach
state after their images are published. See
[`terraform/k8s/README.md`](terraform/k8s/README.md) for the deployment flow.

For more on the request flow, data model and caching, see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Target release form

A **PWA** for quick validation and testing installable, offline-capable, and
fast to iterate on.

---

## Roadmap

Right now the focus is **athlete-specific features**. Planned social features:

```mermaid
erDiagram
  ATHLETE ||--o{ GOAL : "sets"
  ATHLETE ||--|| COACH : "has at most 1"
  ATHLETE ||--|| HANDLER : "has at most 1"
  COACH ||--o{ ATHLETE : "coaches (1-to-many)"
  HANDLER ||--o{ ATHLETE : "handles (1-to-many)"
  ATHLETE ||--o{ SESSION : "logs"
  ATHLETE ||--o{ COMPETITION : "prepares for"
  COACH ||--o{ PROGRAM_NOTE : "collaborates on"
  ATHLETE ||--o{ PROGRAM_NOTE : "collaborates on"
```

- **Profiles** for athletes, handlers, and coaches.
- **Coach / athlete relationships** one-to-many: a coach can have multiple
  athletes; to avoid complexity, an athlete can only have **one coach** and
  **one handler**.
- **Handler matching** same one-to-many rule for handlers.
- **Forums** for like-minded lifters.
- More **cloud portability** (NFS-backed cross-cloud workloads) and additional
  typed service operations.

This isn't meant to replace coaching it's a shared notebook where coaches and
athletes use the formulas and AI above to collaborate on the meet-prep journey.

---

## Repository map

```
powerlifting-app/
├── src/
│   ├── backend/              Express API (thin transport → typed services)
│   ├── frontend/             React 19 + Vite PWA
│   ├── services/             One folder per typed HTTP/MCP domain service, shared `runtime/`, and operation manifests
│   ├── lambda/               Retained AWS Lambdas: master-sync and video-thumbnail
│   └── dependencies/types/   Shared TypeScript types
├── docker/         Container build context
├── terraform/      AWS + Cloudflare (main), k8s/ stacks (core, perms, network, app), coach/
└── docs/           Architecture, formulas, and the implementation reference
```

See [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) for the annotated tree and
[`AGENTS.md`](AGENTS.md) for the guidelines agents and contributors must follow
when working in this repo.
