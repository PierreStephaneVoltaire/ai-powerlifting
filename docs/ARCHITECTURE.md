# Architecture

Software and technical deep-dive for the powerlifting portal. For the math, see
[`FORMULAS.md`](./FORMULAS.md). 

## Current request flow

Powerlifting runs in the `powerlifting` namespace as nineteen domain
Services/Deployments, one per operation manifest in
`src/services/operations/*.json`. Each manifest defines typed HTTP and MCP
operations. The Express gateway calls them over the cluster network, and the
Assistant (`pl-assistant`) runs conversational turns and calls them as tools.
The Assistant also serves the `/v1/jobs` domain job contract for analytics
reports and imports. DynamoDB and S3 hold the training data.

The AI workflow (use cases, models, request flow, concurrency, output
validation and hallucination controls) is in the README's
[AI components](../README.md#ai-components) section.

Export, imports, templates and videos share the `if-powerlifting-fns` image.
Lift profiles and the other native domain services use their own images.

```mermaid
flowchart LR
  Browser["Browser"] --> Gateway["Express gateway"]
  Gateway --> Service["19 typed HTTP/MCP services"]
  Gateway --> Assistant["pl-assistant"]
  Service <-->|"inference continuations"| Assistant
  Assistant -->|"MCP tools via LiteLLM"| Service
  Bot["pl-coach-discord"] --> Assistant
  Assistant --> AssistantDB[("assistant-postgres")]
  Service --> Store[("DynamoDB and S3")]
  Gateway --> Profile["Profile permission evaluator"]
  Service --> Profile
```

Browser authentication uses OAuth2 Proxy with the existing Authentik OIDC
provider; Discord is an Authentik source. The gateway holds no login session; it
reads the user from the ID token OAuth2 Proxy forwards and resolves the Person
through Profile. Dedicated ServiceAccounts identify workloads through Istio
Ambient mTLS, and per-service AuthorizationPolicies on the shared waypoint decide
which workloads may call which services. Callers state the acting Person in a
header; each domain service enforces current grants at HTTP/MCP boundaries,
including through Profile's access checks. See ADR-0006.

Video upload keeps the existing multipart gateway endpoint. A single request
spools the file with a 500 MiB bound; the backend sends bytes to S3 and confirms
through the existing storage operations. Media reads go through CloudFront (ADR 0004):
thumbnails unsigned, full videos via 72-hour signed URLs issued by `/api`. There is no browser S3 upload, chunk
protocol, second environment or second inference host.

## Service map

### Entry points and identity

```mermaid
flowchart TB
  UI["Browser<br/>React PWA · Vite + Mantine"]
  DiscordApp["Discord"]
  CF["Cloudflare<br/>DNS + tunnel"]

  subgraph Cluster["k3s · powerlifting namespace"]
    Tunnel["cloudflared"]
    Gateway["NGINX Gateway Fabric"]
    FE["powerlifting-app-frontend<br/>static PWA"]
    Proxy["oauth2-proxy<br/>browser login + session"]
    BE["powerlifting-app-backend<br/>Express API"]
    Valkey[("pl-valkey<br/>sessions + application cache")]
    Auth["authentik-server<br/>OIDC identity authority"]
    AuthWorker["authentik-worker<br/>background tasks"]
    Postgres[("CNPG Postgres<br/>Authentik data")]
    Assistant["pl-assistant<br/>Dapr workflows"]
    AssistantDB[("assistant-postgres<br/>CNPG + pgvector")]
    Bot["pl-coach-discord<br/>gateway bot"]
    LiteLLM["litellm<br/>model aliases"]
  end

  UI --> CF --> Tunnel --> Gateway
  Gateway -->|"/"| FE
  Gateway -->|"/api and /oauth2"| Proxy
  Gateway -->|"auth hostname"| Auth
  Proxy -->|"authenticated API requests"| BE
  Proxy <-->|"OIDC"| Auth
  Auth <-->|"Discord identity source"| DiscordApp
  Auth --> Postgres
  AuthWorker --> Postgres
  Proxy -->|"login sessions"| Valkey
  BE -->|"application cache"| Valkey
  DiscordApp <-->|"websocket"| Bot
  BE -->|"chat and jobs"| Assistant
  Bot -->|"chat"| Assistant
  Assistant --> AssistantDB
  Gateway -->|"llm hostname"| LiteLLM
  Assistant -->|"model calls + MCP"| LiteLLM
```

Authentik is the only login authority; Discord is its identity source.
OAuth2 Proxy owns the Valkey-backed browser session and forwards the verified
identity to Express. Express no longer holds a Passport session or a direct
Discord OAuth callback. Both public hostnames pass through NGINX.

### Every domain service

Each box below is a separate service, with typed HTTP operations for the
backend and MCP tools for the Assistant. The four frames organize the inventory
by purpose; they are not shared processes or extra routing layers.

```mermaid
flowchart TB
  BE["Express backend<br/>HTTP operations"]
  Coach["pl-assistant<br/>MCP tools"]

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
    WeightLog["pl-weight-log<br/>dated bodyweight entries"]
    Competition ~~~ Federation ~~~ Goals ~~~ WeightLog
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

The remaining Python domain services share the `if-powerlifting-fns` image.
Lift profiles, Analytics AI and Analytics Export have Go images; Analytics and
Rankings have Rust images.

Every service checks application permissions at its HTTP/MCP boundary using
current grants and publication settings. `pl-profile` manages those records
and supplies access checks to native services.

### Analytics, AI and caches

All model traffic goes through the **LiteLLM layer** at `llm.nolift.training`.
LiteLLM holds the provider credentials (from SSM Parameter Store) and the
ChatGPT subscription login, once. Apps only name **model aliases**
(for example `pl-coordinator`, `pl-responder-fast`, `pl-strong`, `pl-web`,
`pl-embed`, `pl-light`); each alias groups one or more
provider deployments and can fall back to another alias. The admin UI signs in
through Authentik, limited to the users in `litellm_admins`.

```mermaid
flowchart LR
  Analytics["pl-analytics"]
  AI["pl-analytics-ai"]
  Export["pl-analytics-export"]
  Features["AI-enabled domain operations<br/>pl-templates, pl-glossary, pl-imports,<br/>pl-lift-profiles"]
  Jobs["pl-assistant<br/>Dapr domain jobs"]
  Valkey[("pl-valkey<br/>analysis, report pointers,<br/>prompt cache entries")]
  PromptCache["pl-prompt-cache-api<br/>exact + semantic lookup"]
  CacheMCP["pl-prompt-cache-mcp<br/>semantic cache tools"]
  Decisions["OpenAI Decisions API<br/>gpt-6-luna"]
  Reports[("S3 analysis-reports/<br/>finished AI reports")]
  Qdrant[("pl-prompt-cache<br/>Qdrant vectors")]
  State[("assistant-postgres<br/>jobs + checkpoints")]

  subgraph LLM["LiteLLM layer"]
    direction TB
    Aliases["model aliases<br/>pl-coordinator · pl-responder-fast · pl-strong · pl-web · pl-embed · pl-light"]
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
  AI -->|"inference jobs"| Jobs
  Features -->|"inference jobs"| Jobs
  Jobs -->|"model calls"| Aliases
  Router --> ChatGPT & OpenRouter & Compat
  Analytics --> Valkey
  AI -->|"report pointer + reservation"| Valkey
  AI -->|"finished reports"| Reports
  AI -->|"lookup before inference,<br/>store after"| PromptCache
  Features -->|"lookup before inference,<br/>store after"| PromptCache
  PromptCache -->|"exact key + entries"| Valkey
  PromptCache -->|"top 3 candidates"| CacheMCP --> Qdrant
  PromptCache -->|"same / contextual /<br/>temporal / none"| Decisions
  Jobs --> State
```

AI-capable operations hand inference to the Dapr workflow and resume with its
validated response. The analytics services also exchange computed data over
gRPC; report generation and export run outside the deterministic analytics
process. Every domain AI call, from the Python runtime and from pl-analytics-ai,
asks `pl-prompt-cache-api` before it starts inference and tells it after
inference. I made one service own this so the cache logic exists once and the
callers stay thin. The service checks Valkey for an exact match first. If that
misses, it asks `pl-prompt-cache-mcp` for the top three Qdrant candidates for
that Athlete and operation, then sends them in one request to the OpenAI
Decisions API (`POST /v1/decisions`, model `gpt-6-luna`) so a small model
judges whether a stored answer still holds. Valkey keeps the entries and the
fast report pointers, Qdrant only holds the search index, and S3 holds
finished AI reports. A cache service error never fails an operation; it is
just a miss. Assistant conversations are separate and do not use this cache;
only domain AI operations go through `pl-prompt-cache-api`.

### Storage and media

```mermaid
flowchart LR
  subgraph Services["Domain + analysis services"]
    direction TB
    SvcList["pl-program · pl-sessions · pl-templates · pl-glossary<br/>pl-lift-profiles · pl-competition · pl-federation · pl-goals<br/>pl-weight-log · pl-performance · pl-calculations<br/>pl-profile · pl-videos · pl-imports · pl-export<br/>pl-analytics · pl-analytics-ai · pl-analytics-export"]
  end
  BE["Express backend"]
  Rankings["pl-rankings"]
  UI["Browser"]

  subgraph AWS["AWS"]
    DDB[("DynamoDB<br/>profiles, training, grants,<br/>competitions")]
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
authorized redirect to a signed CDN URL; avatars retain their authorized
API endpoints. The two retained AWS Lambdas generate video
thumbnails and copy master competition/federation updates to athlete directories.

### AWS workload identity

k3s signs the service-account tokens that NoLift pods use to access AWS. The
issuer is the regional HTTPS endpoint of a dedicated S3 bucket in
`ca-central-1`. The bucket exposes the OIDC discovery document at
`/.well-known/openid-configuration` and the JSON Web Key Set
(JWKS) at `/openid/v1/jwks`. The signing key stays on the cluster.

1. Kubernetes projects a rotating, one-hour token into each AWS-using workload
   at `/secrets/aws/web-identity-token`. Its audience is `sts.amazonaws.com`.
2. The AWS SDK reads `AWS_WEB_IDENTITY_TOKEN_FILE` and `AWS_ROLE_ARN` and calls
   regional STS `AssumeRoleWithWebIdentity`. IAM trusts the registered issuer
   and requires an exact match on both the audience and the subject
   `system:serviceaccount:<namespace>:<service-account>`.
3. STS returns temporary credentials for `nolift-<service-account>`. The
   role's policy determines which AWS calls succeed. For example,
   `pl-templates` can query `if-sessions` when evaluating an athlete's draft.
   The SDK refreshes credentials while the workload runs.

Authentik identifies the Person signing in to the portal. Istio mTLS identifies
the caller on service-to-service requests. GitHub Actions uses GitHub-issued
OIDC tokens for its AWS CI roles. Registry image pulls use the `ecr-registry`
Secret, which the `ecr-refresher` service account renews using its own AWS role.

The deployment pipeline publishes the k3s public signing keys and discovery
document and provisions the IAM provider and roles. The in-cluster runner
configures the issuer and deploys the workloads with projected tokens. After
rollout, CI verifies that STS accepts the `pl-rankings` service account and
rejects a wrong audience or an unrelated service account. See the
[deployment workflow](../.github/workflows/build-images.yml),
[IAM policy definitions](../terraform/workload_identity.tf), the
[shared workload settings](../terraform/k8s/modules/workload-aws/main.tf) and
[ADR 0010](adr/0010-aws-workload-identity-and-network-hardening.md).

### Workload delivery

Each Argo Application reads one manifest directory on the release branch.
Owner releases from `feature/*` use GitHub's `stage` environment and publish
`latest` to ECR. A release from `master` selects the golden branch again.
The in-cluster runner scans those files for ECR names, private values and workload
identity markers. Terraform owns the resulting Kustomize patches. Image Updater
owns the digest overrides and reads the refreshed ECR pull secret. The pinned
updater can overwrite concurrent Application changes, so the runner pauses it
for the Argo Terraform apply. Kustomize preserves the repository and digest
when the updater adds a redundant `:latest` tag. This keeps sibling pod
templates stable when one service gets a new digest. Authentik
grants console access through the `argocd-admins` group. The release environment
supplies `ARGOCD_DOMAIN`. Its `K8S_TFVARS` contains the matching
`argocd_domain` and the Authentik usernames in `argocd_admins`.

After Terraform updates the Application specs, Argo CD reconciles the selected
branch automatically and Image Updater reconciles the ECR digests.

The home node and private EC2 Spot workers communicate over Tailscale. Workers
have no public IPs or direct inbound access; one ARM64 fck-nat instance in a
dedicated public subnet provides IPv4 egress. Workers use a restricted instance role for bootstrap; pod AWS access uses the existing
projected workload identity. Spot workers are tainted, so existing workloads
remain on the home node unless explicitly configured otherwise. Argo manages
the termination handler, which drains workers on interruption or scale-in, and
a CronJob that removes stale worker records. Terraform keeps the desired worker
count at zero by default.

[ADR 0011](adr/0011-argocd-mutation-injection-and-spot-workers.md)

### Mesh, monitoring and deployment

Istio Ambient supplies workload identity and strict mTLS through `ztunnel`.
The `nolift-waypoint` enforces service caller policies; each service still
checks the acting Person's permissions. `istiod` manages the mesh and the
Istio CNI enrolls workloads. These transport controls apply across the service
diagrams above.

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
  Runner -->|"Terraform installs and configures"| Argo["Argo CD"]
  Master["master manifests"] --> Argo
  ECR -->|"digest of latest"| Updater["Image Updater"]
  Updater -->|"Application image overrides"| Argo
  Argo -->|"server-side apply"| Workloads["k3s workloads"]
  Workloads -->|"pull images"| ECR
  Workloads -->|"container logs"| Promtail
```

Grafana is reached by port-forward on `localhost:3000`. Each Terraform scope
has its own state. The Git manifests live alongside those stacks.

| Location | Scope |
| --- | --- |
| `terraform/` | AWS and Cloudflare resources, including the public k3s issuer documents, IAM OIDC provider and workload roles |
| `terraform/ci-access` | Permissions the existing CI role needs to manage AWS resources, including workload identity |
| `terraform/k8s/core` | Namespaces, secrets, runner, Authentik, CNPG Postgres, monitoring |
| `terraform/k8s/perms` | Kubernetes service accounts and RBAC |
| `terraform/k8s/network` | NGINX Gateway, Gateway API and tunnel credential checksum |
| `terraform/k8s/argocd` | Argo CD, Authentik SSO settings, ECR Image Updater and Application patches |
| `terraform/k8s/nodes` | Tailscale, k3s bootstrap parameters and generated credentials |
| `deploy/argocd/nodes` | Worker termination handler and reaper CronJob |
| `deploy/argocd/{app,coach,network}` | Namespaced workloads, workload policies, waypoint and HTTP routes |
| `terraform/k8s/mesh` | Istio control plane, CNI and ztunnel |
| `terraform/k8s/app` | Application secrets, private configuration, persistent volumes, registry refresh and LiteLLM key registration |
| `terraform/coach` | Coach credentials and persistent state |

The in-cluster runner applies the platform, Argo CD, node and Coach states through the deployment pipeline.

## Analysis page: the four computation paths

`AnalysisPage.tsx` is the analytics hub. It has four top-level section tabs
(Weekly, Blocks, Compare, Maxes) toggled via `?type=`. The Weekly tab alone has
four distinct computation paths:

```mermaid
flowchart TB
  subgraph P1[1. Backend deterministic sections]
    Sec[analysis_section] --> Cache[analysisCache.ts\nper section/window cache]
  end
  subgraph P2[2. Frontend-local derivations]
    Prog[program data] --> Fe[local e1RM/DOTS/IPF GL trends]
    Gloss[glossary + weight log] --> Fe
  end
  subgraph P3[3. Cache-only AI reports]
    Cor[correlation?cacheOnly=true] --> CorCache[cache hit → show]
    Cor2[correlation?refresh=true] --> GenCor[generate new AI]
    Ev[program-evaluation?cacheOnly=true] --> EvCache[cache hit → show]
    Ev2[program-evaluation?refresh=true] --> GenEv[generate new AI]
  end
  subgraph P4[4. Block / lifetime analytics]
    BA[blockAnalytics.ts] --> Past[Past Blocks tab]
    BA --> Cmp[Compare tab]
  end
```

1. **Backend deterministic sections** — `analysis_section`, queued and cached per
   section/window by `analysisCache.ts`. Current section keys: `overview`,
   `fatigue_readiness`, `peaking`, `workload`, `alerts`.
2. **Frontend-local derivations** — computed in-browser from program data,
   glossary, and the weight log (e.g. local e1RM/DOTS/IPF GL trend cards).
3. **Cache-only-by-default AI reports** — correlation analysis and full-block
   program evaluation load saved references; explicit Generate/Refresh actions
   produce new AI output. Read-only misses return a missing-cache response.
4. **Block / lifetime analytics** — `blockAnalytics.ts` powers the Past Blocks and
   Lifetime Compare tabs.

Max comparisons must use the same method and date range. Historical window
maxima and current Estimated 1RMs have different meanings; for an identical
method and range, the shared lift calculations are authoritative.

## Data model

```mermaid
erDiagram
  PROGRAM ||--o{ SESSION : "versioned"
  PROGRAM ||--|| META : "has"
  PROGRAM ||--o{ PHASE : "defines"
  PROGRAM ||--o{ BLOCK_NOTE : "carries"
  PROGRAM ||--o{ CHANGE_LOG : "records"
  SESSION ||--o{ EXERCISE : "logged"
  SESSION ||--o{ PLANNED_EXERCISE : "planned"
  SESSION ||--o{ SESSION_VIDEO : "has"
  SESSION ||--|| WELLNESS : "optional"
  EXERCISE ||--o{ SET_STATUS : "per set"
  GLOSSARY ||--o{ GLOSSARY_EXERCISE : "defines"
  GLOSSARY_EXERCISE ||--|| FATIGUE_PROFILE : "carries"
  LIFT_PROFILE ||--|| STIMULUS_COEFFICIENT : "tuned by AI"
  PERSON ||--o| ATHLETE : "has role"
  PERSON ||--o{ GRANT : "receives"
  ATHLETE ||--o{ COMPETITION_ENTRY : "owns"
  COMPETITION_EVENT ||--o{ COMPETITION_ENTRY : "anchors"
  COMPETITION_ENTRY ||--o{ ATTEMPT : "records"
  COMPETITION_ENTRY ||--o| LIFT_RESULTS : "completed with"
  WEIGHT_LOG ||--o{ WEIGHT_ENTRY : "stores"
  MAX_HISTORY ||--o{ MAX_ENTRY : "stores"
```

### Storage

| Store | Backend | Purpose |
|-------|---------|---------|
| `if-health` | DynamoDB | Program document, glossary, max history, weight log |
| `if-sessions` | DynamoDB | Sessions (separate from program; merged by version in `programController.getProgram()`) |
| `if-supplements` | DynamoDB | Supplements and supplement phases, stored by Athlete and Program version |
| `if-user` | DynamoDB | Verified provider-subject pointers, Person/profile settings and Athlete mapping |
| `if-powerlifting-analysis-cache` | DynamoDB | Legacy and no longer used. It held AI generation records before they moved to S3 and Valkey. The operator deletes it; nothing may read or write it |
| `analysis-reports/{athlete}/{generation_id}.json` | S3 (powerlifting bucket) | Finished AI reports (correlation / ROI, program evaluation, block comparison and any other generation), saved after the calculations. Valkey holds the pointer |
| `pl-valkey` | Valkey | Deterministic analysis sections, block bundles and markdown exports (30-day TTL), ranking percentiles (7-day TTL), and prompt cache keys and entries (`pl:ai-cache:*`, 30-day TTL). AI report pointers (`pl:report:{athlete}:{generation_id}`) have no TTL once complete; in-flight reservations expire after one hour. Also holds the per-Athlete `pl:analysis-version` and `pl:analysis-build` marker |
| `pl-prompt-cache-api` | Go service | Owns the domain AI prompt cache: exact Valkey lookup, Qdrant candidates through the MCP service, one Decisions API call, store after inference |
| `pl-prompt-cache` / `pl-prompt-cache-mcp` | Qdrant (emptyDir) + mcp-server-qdrant | Semantic search index only. Domain AI prompts use one collection per Athlete and operation. Each domain AI point carries an entry id and the entry itself lives in Valkey at `pl:ai-cache:entry:{entry_id}`. Losing it costs semantic hits, never answers |
| `if-powerlifting-user-competitions` | DynamoDB | Independent Athlete-owned Competition Entries and Attempts |
| `if-powerlifting-master-competitions` | DynamoDB | Master competition directory |
| `if-powerlifting-master-federations` | DynamoDB | Federation library + qualification standards |
| `if-powerlifting-tags` | DynamoDB | Global operator-reviewed vocabulary |
| `if-powerlifting-notifications` | DynamoDB | Durable Person inbox and event deduplication |
| `if-powerlifting-requests` | DynamoDB | Relationships, role slots, favorites, indexed inbox/roster |
| `if-powerlifting-goals` | DynamoDB | Athlete goals |
| `powerlifting-session-videos` | S3 | Lift videos (+ thumbnails, + processed) |
| `video-thumbnail-generator` | Lambda | S3-triggered ffmpeg thumbnail generation |

### Person and selected Athlete

The guest landing page presents both Discord and Authentik sign-in actions.
Search and About remain separate public pages with navigation back to Home and
Sign in. Discord uses the existing application client and configured
`DISCORD_REDIRECT_URI` at `/api/auth/discord/callback`; Authentik uses its separate
OIDC flow and `/api/auth/authentik/callback`. The Discord button must not be
rerouted through Authentik's Discord source. Both use verified provider subjects
and the shared server-side session store.

Passport and openid-client verify Authentik's issuer and subject. Direct Discord
login obtains its verified subject from Discord's authenticated user API. Valkey stores
server-side login sessions. The identity pointer resolves a stable Person in
`if-user`; `mapped_pk` preserves that Person's existing Athlete partition.
`X-Selected-Athlete-Pk` changes the requested Athlete, never the acting Person.
The Profile service recomputes effective permissions for each HTTP/MCP operation.
Anonymous requests have only explicitly published access; the default operator
selector grants nothing by itself.

Read-only notices follow the current route's domain permissions and are absent
from informational/public navigation pages. Existing navigation carries Athlete
context; the operator rejected a duplicated top context strip. Browser Back from
another Athlete's view must restore the previous context, including on small screens.

### Storage conventions

- Dates are `YYYY-MM-DD`; timestamps are ISO8601.
- Weights are stored in **kilograms**; frontend unit switching is display-only.
- Powerlifting weeks are program/block-defined, not calendar weeks — analysis
  uses the block record's `week_start_day` plus the caller's `asOfDate`.

### Program meta

`Program.meta` carries identity/versioning, timeline, training-week boundaries,
federation/class context, bodyweight, targets, attempt defaults, anthropometrics,
manual maxes, block records (dates, week start and start maxes), program history, template lineage, and
`sex` for DOTS/IPF GL.

### Block and version publication

Blocks have stable identities and editable names. Each block record carries its
start date, week-start day and start maxes. Complete, Start next and the
combined transition are plain writes. Completing a Block preserves unfinished Session statuses. A new Block captures
its dates, week-start preference and confirmed start maxes, with weeks reset to
one. Template targets preserve logged work and independent Competition Entries.

Setup and version changes stage a unique unpublished Program and its Sessions
before an atomic pointer/publication transaction. Failed staging remains hidden;
retries publish one complete result. Conditional revisions reject stale edits.
Template items and their shared index update atomically, with actor-bound retry
records. Known ownership migrations and fixture copies are additive, conditional
and repeatable; copied operator media references remain read-only.

### Sessions and sets

`Session` holds date/day/week/phase/block, status, planned vs logged exercises,
subjective context (notes, RPE, bodyweight, wellness, pain log), and videos.

`set_statuses[]` is the per-set execution state: `pending | completed | failed |
skipped`. `completed` and `failed` count as executed sets; `skipped` and
`pending` do not contribute to volume, fatigue, INOL, specificity, or muscle-set
totals. `failed_set_reasons[][]` align to `set_statuses[]` (strength/technical/
command/grip/depth/pause/lockout/balance/pain/fatigue/misload tags).

### Lift profiles

The Go lift-profile service exposes the same HTTP and MCP operations and
performs per-Athlete access checks. It updates the profile field conditionally,
preserving stored form videos and rejecting concurrent profile changes.

Per lift (squat/bench/deadlift): style notes, sticking points, primary muscle,
volume tolerance, `e1rm_multiplier`, `stimulus_coefficient` (with confidence +
reasoning), and INOL low/high thresholds. Used two ways:

1. **Deterministically** — `stimulus_coefficient` modifies INOL.
2. **As AI context** — for lift-profile review/rewrite, stimulus estimation,
   fatigue-profile estimation, correlation, program evaluation, accessory e1RM
   backfill, template evaluation, and import.

## Caching strategy

```mermaid
flowchart TB
  Req[Analytics request] --> Manifest[GET analysis/manifest\nsection status, no payloads]
  Manifest --> Need{Section cached?}
  Need -- yes --> Read[read from\npl-valkey]
  Need -- no --> Queue[queue analysis_section]
  Queue --> Write[write pl-valkey, 30-day TTL]
  Read --> FE[frontend renders]
  Write --> FE
  Regen[POST analysis/regenerate\nor Regenerate button] --> Inv[invalidate + requeue\nselected window only]
```

- Section API keys are window-scoped (`current`, `previous_1/2/4/8`, `block`).
- The legacy `weekly-bundle` endpoint still exists for compatibility/export
  tooling; the Weekly tab reads sections instead.
- AI correlation, program-evaluation and block-comparison reports cache
  separately and only regenerate on explicit refresh (never via the main
  regenerate endpoint). Their IDs are stable for the Athlete, report inputs,
  block and access scope: training-data versions, today's date and prompt
  revisions never invalidate a finished report. The current block's start date
  distinguishes it from a later current block. Data changes can make a report
  stale; the Analysis UI's explicit refresh replaces it. This is separate from
  input-sensitive prompt caching for glossary and profile AI features.
  After the calculations, the finished report is saved to
  S3 at `analysis-reports/{athlete}/{generation_id}.json`. Valkey holds a small
  pointer at `pl:report:{athlete}:{generation_id}` and the in-flight
  reservation (`SET NX` with a one-hour TTL). Finished reports and their pointers
  have no TTL. Explicit regeneration replaces the report at the same S3 key;
  bucket versioning can retain previous object versions. If the pointer is gone,
  the read goes to S3 at the known key and restores the pointer. DynamoDB is not
  involved.
- Section and block keys contain the per-Athlete analysis version (plus the
  as-of date for current-block windows). Unchanged data is always a hit; an
  analysis-input write bumps the version, so older entries become unreachable
  and expire after 30 days or are evicted under LRU. When the build id changes,
  analytics sweeps `pl:analysis:*` once on startup.
- Ranking percentiles key on the OpenPowerlifting file identity (name, size,
  mtime), the comparison year, the Athlete, their numbers and the filter.
- Domain AI calls go through `pl-prompt-cache-api` (key from the LiteLLM
  provider keys, `openai`). The lookup order is fixed. First an exact Valkey
  key of Athlete, operation, analysis version and request hash. Then, on a
  miss, the top three Qdrant candidates for that Athlete and operation via
  `pl-prompt-cache-mcp`. Then one OpenAI Decisions API call (`POST
  /v1/decisions`, `gpt-6-luna`) that answers each candidate with one choice:
  `same` (reuse as is), `contextual` (the ask or its data differs, so the
  answer would change), `temporal` (the answer depends on the date and the
  date moved) or `none`. A hit is the first candidate that answers `same` with
  confidence of at least 0.8. Any error, refusal, timeout or missing key is a
  miss, and the caller then runs inference and stores the result. The decision
  is a single bounded call inside the cache service, not a Specialist run with
  tools, so the cache can never block or fail an operation. The old Luna
  Specialist design is gone; do not bring it back.
- Writes to analysis inputs (an allowlist in `services/analysis_version.py`)
  bump a per-Athlete version in Valkey from `dispatch`. The bump targets the
  Athlete the call runs under, not the raw `pk` argument, because a
  person-scoped write such as settings would otherwise bump the Person and
  leave the Athlete's analysis stale. Deterministic section, manifest,
  block and markdown lookups key on that version. Saved AI reports do not:
  only explicit regeneration replaces them. Persisted requirements
  record the source domains and Competition Entry scope; every reference/job
  read checks them against current permissions. Legacy results without source
  requirements are readable only by the Athlete until regenerated.
- Filtered empty source fields remain empty during generation; handlers cannot
  reload private data as a fallback. Read-only cache misses never start inference.
- Historical exports preserve archived Program/Session data and merge independent
  Competition Entries through the same read projection. Exporting does not
  generate a missing AI report.

### Cache design rules

These are rules, not preferences. I keep seeing designs that break them, so
they are written down here.

- Caches live only in Valkey or S3. Never DynamoDB. DynamoDB holds the data
  the caches are computed from, and a cache table there only adds cost and a
  second source of truth.
- Saved Analysis AI reports persist until explicit regeneration, even when
  inputs, dates, prompts or builds change. Reads return the saved report and
  never start inference. A miss means no report exists for that report scope.
  Glossary and profile AI features retain input-sensitive caching.
- Deterministic and prompt caches invalidate outdated entries. They are never
  versioned by a hand-bumped constant in a key or path. Data changes
  invalidate through the Athlete's `pl:analysis-version`, which is bumped on an
  analysis-input write for the Athlete the call runs under. Code changes
  invalidate by build: analytics reads `BUILD_ID` on startup, and when it
  differs from `pl:analysis-build` it sweeps its own `pl:analysis:*` keys once
  (one replica, guarded by a lock) and records the new build. Snapshots carry
  the build id in their body, and a snapshot from another build is treated as
  missing. API fields such as `schemaVersion` stay as response values for the
  frontend; they never appear in a key or path.
- Person to Athlete resolution uses the `mapped_pk` from
  `access_store.current_context`. No ad-hoc user lookups or scans to find an
  Athlete.
- Visitor (signed-out) views read cached results only and never start
  inference. A miss for a visitor stays a miss until the owner generates it.

## Assistant

`pl-assistant` (`src/services/assistant`) is a Go service on Dapr durable
workflows (`durabletask-go`, Dapr 1.18 control plane). Each conversation turn
is a `ConversationTurn` workflow. Every model call, tool call, proposal and
delivery is a checkpointed activity, stored in the pgvector-enabled CNPG
cluster `assistant-postgres`, next to the assistant's own schema
(conversations, turns, participants, embeddings, proposals, audit,
orchestration events). The same Dapr worker executes domain jobs using the
service-issued inference challenge and the existing LiteLLM client. Discord
uses the Assistant's conversation endpoint. See ADR-0007 and ADR-0008.

Models are only ever named by LiteLLM alias, with providers registered once:
`pl-coordinator` (ChatGPT subscription, OpenRouter fallback),
`pl-responder-fast` and `pl-strong` (the low and higher delegation tiers),
`pl-web` (OpenRouter web plugin, web research subagent only), `pl-embed` and
`pl-light` (security). The concrete models are tfvars configuration.

### Turn flow

The client only sends the new message; history is held on the server. The
workflow resolves who is asking, screens the message, builds context, then
runs the coordinator model. The coordinator either answers or delegates to
child workflows; there is no classifier gate in front of it. Writes can only
be proposals, which wait for a person.

```mermaid
sequenceDiagram
  participant C as Drawer or Discord
  participant BE as Express backend
  participant A as pl-assistant HTTP
  participant W as ConversationTurn workflow
  participant P as Profile
  participant DB as assistant-postgres
  participant L as LiteLLM
  participant G as LiteLLM MCP gateway
  participant S as Domain services

  C->>BE: new message (surface + context)
  BE->>A: POST /v1/conversations/{id}/turns
  A->>DB: store turn, schedule workflow
  A-->>C: job id
  W->>P: ResolveIdentity (access_context, fail closed)
  W->>W: Guard (length, injection, rate, risk signals)
  opt guard signals
    W->>W: SecurityAssessment child workflow (pl-light)
  end
  W->>DB: Retrieve snippets (authorization filter, then pgvector ranking)
  W->>DB: Load recent turns (permission-filtered)
  W->>W: MintToken (scope from live permissions)
  W->>G: list tools (job token)
  loop agent loop on pl-coordinator
    W->>L: ModelCall (streams text into progress buffer)
    L-->>W: reply or tool calls
    alt delegate_subagent
      W->>W: SubagentTask child workflow (tier, or pl-web if needs_web)
      W->>L: ModelCall for the subagent
      W->>G: tool calls (fresh job token each call)
      G->>S: tools/call with token
      W->>W: review_delegation, escalate_from if failed
    else read tool
      W->>G: tool call (fresh job token)
      G->>S: tools/call with token
    else propose_change
      W->>W: validate arguments against the operation's MCP input schema
      W->>G: read the target (captures version)
      W->>DB: store proposal with structured diff
      Note over W: WaitForExternalEvent, 24 h timeout
      C->>A: approve or reject
      A->>W: RaiseEvent
      W->>P: re-check requester and approver permissions
      W->>G: re-read target, compare version
      W->>G: apply the write (fresh job token)
    end
  end
  W->>P: Deliver gate (every participant's live permissions, shared channels)
  W->>DB: complete turn, store embeddings
  C->>A: poll job (progress text, then result)
  A-->>C: reply or withheld notice
```

The order inside the workflow is fixed: identity, guard, optional security
assessment, retrieval, history, then the agent loop (`internal/workflow/turn.go`
and `agent.go`). A delegation is a child workflow at the chosen tier; a failed
or empty result is recorded as a failed review and the coordinator can retry
with `escalate_from` on a stronger tier. Model text is streamed into a per-turn
progress buffer in Postgres, which the drawer polls alongside the job status.
Stop terminates the workflow and its children.

### Security

No step trusts the model to say who it is acting for. Identity is resolved
outside the model, narrowed to a scope, and checked again by every service the
tools reach.

```mermaid
flowchart TB
  User["User session<br/>oauth2-proxy + Authentik"] --> BE["Express backend"]
  Discord["Discord sender"] --> Bot["pl-coach-discord"]
  BE -->|"mesh headers:<br/>person, athlete, SPIFFE source principal"| API["pl-assistant HTTP<br/>caller must be an allowed ServiceAccount"]
  Bot -->|"mesh headers"| API
  API --> Access["Profile access_context<br/>no permissions = deny, error = fail closed"]
  Access --> Scope["Scope = operations the live<br/>permissions allow"]
  Scope --> Mint["Per-call ES256 job token<br/>person, athlete, conversation, workflow, scope<br/>aud pl-domain-mcp, 5 min exp, jti"]
  Mint --> Key["LiteLLM virtual key<br/>models + object_permission.mcp_servers"]
  Key --> Gateway["LiteLLM MCP gateway<br/>forwards the token header per server"]
  Gateway --> Verify["Domain service verifies<br/>signature, issuer, audience, expiry,<br/>operation in scope"]
  Verify --> Reject["Bearer plus identity headers = rejected"]
  Verify --> Same["Then the same access_context and<br/>argument scoping as a human caller"]
  Same --> Audit[("Append-only audit<br/>+ orchestration_events<br/>+ LiteLLM metadata and tags")]
```

- **Default deny.** No permissions, no scope, an unmapped operation or an
  unverifiable token all end in a denial. A mutating operation is never callable
  from the agent loop; it only runs through an approved proposal.
- **The model never chooses identity or scope.** Person, athlete and scope come
  from Profile; the model only picks among tools already in scope.
- **The security subagent can only tighten.** Its verdict is merged with the
  existing floor (allow, require approval, block) and never grants access.
- **Shared channels.** A result is delivered to a shared Discord conversation
  only if every participant's live permissions cover everything it used;
  otherwise a withheld notice is posted and the event is audited.
- **Approval is re-checked.** Commit re-validates both requester and approver
  permissions, re-reads the target, and refuses a stale version.
- **Audit.** Access decisions, token scope, tool calls, proposals, commits and
  visibility decisions go to the append-only audit table; delegation, review,
  escalation and security decisions go to `orchestration_events`; LiteLLM
  carries per-request metadata and tags. The mesh-header path for non-AI
  callers is unchanged.

### High availability and durability

The service keeps no state of its own. Replicas can be killed, rescheduled or
rolled without losing a turn.

```mermaid
flowchart LR
  Client["Client polls the job"] --> Svc["pl-assistant Service"]
  Svc --> R1["replica 1"] & R2["replica 2"] & R3["replica 3"]
  R1 & R2 & R3 <--> Dapr["Dapr 1.18 control plane<br/>scheduler + placement"]
  R1 & R2 & R3 -->|"workflow history,<br/>one row per completed activity"| PG[("assistant-postgres<br/>CNPG + pgvector")]
  PG --- Data["conversations, turns, proposals,<br/>audit, orchestration_events, embeddings"]
```

- **Three stateless replicas**, no PVC and no node pinning (2 GiB limit each,
  with a Dapr sidecar).
- **Checkpointed activities.** Each activity result is written to the workflow
  history in Postgres. If a replica is killed or OOMs mid-turn, another replica
  picks the workflow up and replays it to the last completed activity; a model
  call in flight is repeated. This was verified by killing a replica during a
  model call.
- **Durable approvals.** A pending proposal is a `WaitForExternalEvent` with a
  24 hour timeout, so waiting survives restarts and deploys. On timeout the
  proposal expires and nothing is changed.
- **Dapr control plane.** The scheduler and placement services coordinate where
  workflows run. If they are unhealthy, workflows sit in PENDING.
- **One database.** Workflow state and the assistant's own tables share the
  CNPG cluster, so a conversation, its proposals and its audit trail survive
  pod loss together.
- **Tokens are never stored.** A job token is minted inside the activity that
  uses it and lives for five minutes; workflow history holds only the subject
  (person, athlete, scope), not the token.

## AI execution model

This section covers domain AI jobs (analytics reports, imports); chat is the
Assistant above.

The gateway calls the typed domain operation. AI operations submit a domain job
through `/v1/jobs`. The Assistant schedules a Dapr workflow with the job ID.
PostgreSQL holds payloads and checkpoints, including large imports. The domain
service yields a structured inference challenge, the workflow calls LiteLLM,
and `domain_resume` validates the answer before the handler continues. A replay
uses the saved checkpoint. An ambiguous domain-write outcome becomes `uncertain`.

```mermaid
flowchart LR
  Browser --> Gateway
  Gateway --> Domain[Typed domain operation]
  Domain --> Job[Domain job API]
  Job --> Worker[Assistant Dapr workflow]
  Worker --> Model[LiteLLM model alias]
  Model --> Resume[Validated domain continuation]
  Resume --> Result[Persisted result and reference]
  Result --> Gateway
```

The acting Person and selected Athlete remain distinct throughout submission,
continuation and result reads. The Profile service checks current grants; saved
job results also require access to the domains and competition ties used in
their source. Report deduplication and import review/apply retain their existing
native contracts. Environment variables left in retained AI helpers do not
select a separate inference provider.

## Authentication and publication

Authentik remains available alongside direct Discord login. Application permissions use the Profile
service's PyCasbin evaluator, independent of Authentik's internal RBAC. Every
operation has an explicit permission map and an operation-bound signed principal.
Verified provider subjects preserve existing Person/Athlete mappings; names and
email cannot link accounts. Only an Athlete administers their grants.

Profiles are private by default. Public baseline fields are display name, avatar,
federations and currently approved tags. The Athlete explicitly publishes other
domains through revisioned publication settings. Program, Session, export and
media reads apply current domain permissions. A browser role selector does not
issue grants. Browser caches and drafts use Person/Athlete partitions; online
cached reads contact the service and observed access changes clear the partition.

The selected role determines the current view: Athlete dashboard, Coach roster
or Handler competition-day roster. Multiple memberships do not combine those
screens. Profile/privacy, relationships and inbox are grouped in Settings;
page/display preferences stay in their separate drawer. Tag selection uses
approved pills and one plus-modal search/request field. Pending requests retain
their association and show submission feedback; a pill appears after approval.

Ordinary Program reads fetch current domain state. They do not use the gateway's
former seven-day GET cache, so native domain mutations appear at the same portal
URL immediately. Deterministic caches retain their source fingerprints and write
invalidation. Saved Analysis AI reports retain current permission checks and
change only on explicit regeneration; offline drafts remain in IndexedDB.

## Video pipeline

The browser sends one multipart request to the existing
`POST /api/videos/:version/:date` route. The backend spools the file with bounded
memory, transfers bytes to S3 and confirms the stored allocation. Storage upload
URLs never reach the browser. Interrupted transfers retry the ordinary request.

The existing S3-triggered worker transcodes and thumbnails videos. Media registry
records bind Athlete, Program version, Session ID, media ID and processing
revision. Generated objects include the revision so stale workers cannot overwrite
newer bytes. The browser loads thumbnails directly from CloudFront and plays videos
through signed CloudFront URLs that `/api` issues after authorization (ADR 0004).

The video limit remains 500 MiB. Lift demonstrations additionally allow at most
three minutes. Cloudflare's request allowance must be upgraded before accepting
the full file size; chunking and browser-direct fallback are excluded.

## Current rough edges

Deliberate or temporary mismatches to be aware of (not all are bugs to fix):

1. Max cards need an explicit method and date range when comparing historical
   achieved loads with current estimates.
2. `attempt_selection` is computed but not rendered on the Analysis page.
3. Program-evaluation gating differs between frontend (≥4 completed sessions)
   and backend (≥4 completed weeks).
4. Template evaluation still passes mocked, minimal athlete context
   (`dots_score=350`, `weeks_to_comp=12`).
5. `TimelinePage.tsx` and `DietNotesPage.tsx` have no registered route.

When you encounter a possible bug, note it in `bug.md` and stay on task — see
[`AGENTS.md`](../AGENTS.md).
