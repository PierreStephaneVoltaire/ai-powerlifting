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
  participant BE as Express backend
  participant SVC as Domain service
  participant C as Coach
  participant M as Model
  UI->>BE: request an AI feature
  BE->>SVC: run the operation
  SVC->>C: start a job
  SVC-->>C: needs the model (prompt + JSON shape)
  C->>M: prompt
  M-->>C: JSON
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

What's not checked is whether a valid answer is a *good* one. The reports are
advice, they cite the numbers they were given, and you can regenerate them.

### Running things in parallel

Each provider has its own limit on how many calls run at once; extra jobs
just wait their turn. The ChatGPT subscription throttles at about two
concurrent requests per account, so it stays at 2 and the Coach stays at one
pod while it's in use. API-key providers can go higher.

---

## Architecture

```mermaid
flowchart LR
  subgraph Clients["Clients"]
    UI["React PWA<br/>Vite + Mantine"]
    DiscordApp["Discord"]
  end

  subgraph Edge["Edge"]
    CF["Cloudflare<br/>DNS + tunnel"]
  end

  subgraph Cluster["k3s cluster"]
    Tunnel["cloudflared"]
    Gateway["NGINX Gateway Fabric"]
    FE["Frontend<br/>static PWA"]
    BE["Express API<br/>sessions, auth, cache"]
    Valkey[("Valkey<br/>cache + sessions")]
    Services["18 typed domain services<br/>HTTP + MCP"]
    Analytics["pl-analytics<br/>+ reports sidecar"]
    Rankings["pl-rankings<br/>OpenPowerlifting data"]
    Coach["pl-coach<br/>Codex worker"]
    Bot["pl-coach-discord<br/>gateway bot"]
    Runner["Actions runner<br/>applies k8s stacks"]
    Auth["Authentik + Discord OAuth"]
    Postgres[("Postgres<br/>CNPG, Authentik data")]
    Monitoring["Prometheus, Loki,<br/>Grafana"]
  end

  subgraph AWS["AWS"]
    DDB[("DynamoDB")]
    S3[("S3<br/>videos, media, dataset")]
    CDN["CloudFront<br/>signed media"]
    Sync["Lambda<br/>master-sync"]
    Thumbs["Lambda<br/>video thumbnails"]
  end

  UI --> CF --> Tunnel --> Gateway
  Tunnel -->|"auth host"| Auth
  Auth --> Postgres
  Gateway -->|"/"| FE
  Gateway -->|"/api"| BE
  BE --> Valkey
  BE -->|"typed operations"| Services
  BE -->|"AI jobs"| Coach
  BE --> Auth
  Services --- Analytics
  Services --- Rankings
  Services -->|"inference steps"| Coach
  Coach -->|"tools"| Services
  DiscordApp <-->|"websocket"| Bot
  Bot --> Coach
  Services --> DDB
  Services --> S3
  Rankings --> S3
  S3 --> CDN --> UI
  S3 -->|"upload event"| Thumbs --> DDB
  DDB -->|"stream"| Sync --> DDB
  Runner -.->|"terraform"| Cluster
```

The stack runs on a **bare-metal k3s** node to keep costs down, behind a
Cloudflare tunnel so nothing is exposed directly. Each domain (sessions,
program, templates, analytics, rankings and so on) is its own small service, so
something heavy like loading the OpenPowerlifting dataset for rankings can't
take the rest down with it. AWS holds the data, plus two Lambdas that are still
around: master-sync, which copies the competition directory to every athlete,
and video thumbnails.

Logins go through Authentik with Discord as the identity source, backed by a
CNPG Postgres cluster in the same k3s node. Prometheus, Loki and Grafana watch
the cluster; Grafana is reached by port-forward on `localhost:3000`.

Infrastructure is Terraform, split into a few stacks: AWS and Cloudflare in
`terraform/` (applied by CI), the Kubernetes pieces under `terraform/k8s/`
(applied by a runner inside the cluster; `core` holds namespaces, secrets, the
Actions runner, Authentik, Postgres and monitoring),
and the Coach in `terraform/coach`. See
[`terraform/k8s/README.md`](terraform/k8s/README.md).

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
│   ├── services/             Typed HTTP/MCP domain services, handlers, shared libraries, and operation manifests
│   ├── lambda/               Retained AWS Lambdas: master-sync and video-thumbnail
│   └── dependencies/types/   Shared TypeScript types
├── docker/         Container build context
├── terraform/      AWS + Cloudflare (main), k8s/ stacks (core, perms, network, app), coach/
└── docs/           Architecture, formulas, and the implementation reference
```

See [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) for the annotated tree and
[`AGENTS.md`](AGENTS.md) for the guidelines agents and contributors must follow
when working in this repo.

## Image rollout

Every push builds the images in `docker/` with Packer and pushes them to ECR.
When I'm the one pushing, a runner in the cluster then applies the Kubernetes
stacks, which picks up the new images and rolls the workloads.
