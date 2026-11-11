# Analytics and Rankings Rewrite in Rust: Full Plan

> **Step 0 (first actions after approval):**
> 1. `git checkout -b feat/analytics-rankings-rust` (the user explicitly allowed this; it is the only git write).
> 2. Copy this whole plan to `docs/plans/2026-11-11-analytics-rankings-rewrite.md`. Every subagent reads that file as its spec, and each phase ticks off its checklist there.
>
> The user makes the branch from the staged files. The pipeline (`.github/workflows/build-images.yml`) builds the images and applies Terraform and k8s. Nothing is applied by hand.

## 1. Context

Two pods do the analysis work today.

**`pl-analytics`** is a single pod that runs a Python FastAPI domain service and a Node "reports" sidecar on `127.0.0.1:8091`.
- Most `analytics.*` operations are relayed from Python (`handlers/analysis_reports/composite.py`) to Node (`src/backend/src/analyticsSidecar.ts` → `routes/analytics.ts`).
- Node then calls back into Python for the math, which lives in `src/services/handlers/analysis_reports/analytics.py` (5,291 lines).
- Node also contains `services/blockAnalytics.ts` (2,158), `analysisCache.ts`, `analysisRecords.ts` and `blockAnalysisExport.ts` (548).

**`pl-rankings`** (`src/services/lib/opl_dataset.py`) concatenates the whole OpenPowerlifting CSV (about 3M rows) into one pandas frame.
- The pod limit is 3Gi.
- It keeps an unbounded slice cache and copies frames on every request.
- It reports ready before the dataset has loaded, so callers get 503s.

**Lifetime Compare is broken.** `src/services/handlers/analysis/multi_block_comparison_analysis/core.py:17` has a bare import, which raises `ModuleNotFoundError`.

**Goal:**
- Rewrite these as lean, idiomatic, memory-efficient Rust services, built properly rather than translated line by line.
- Keep every operation name, input/output shape, HTTP route and MCP exposure the same.
- New service-to-service calls use gRPC.
- Isolate the AI parts.
- Keep caching working.
- Make Lifetime Compare a working, holistic all-blocks report that is saved to S3, so `template_evaluate` can read it from its codex workspace.

## 2. Constraints

1. Each service is a standalone Cargo crate. There is no shared library crate. Small pieces such as auth headers and the operation envelope are written per service.
2. Proto files are owned by the producing service. Consumers compile them by relative path in `build.rs`; that is a contract, not a library.
3. Use established crates. Do not hand-roll stats, AWS, Dynamo, Redis, gRPC, MCP, xlsx or OpenAPI.
4. RAM matters, CPU does not. Stream where possible, borrow instead of clone, and keep nothing resident unless it is small.
5. Rankings must not OOM and must scale horizontally (stateless replicas).
6. Code style follows the repo `CLAUDE.md`:
   - no comments
   - modules split by concern
   - no git writes
   - destructive kubectl and terraform are run by the operator
   - only the tests for the crate or module that changed are run, offline
   - deploys happen only through the pipeline
7. Keep Dynamo cost low. Snapshot the live data once, then test offline.
8. Sonnet subagents do the implementation. Opus orchestrates, reviews diffs and runs the scoped tests.
9. Directory names are domain names with no language suffix.

## 3. Target services

All are new directories under `src/services/`, next to the existing Python domain code.

| Domain / k8s Service | Directory | Replaces | Ops served | Mem limit |
|---|---|---|---|---|
| `analytics` → `pl-analytics` | `src/services/analytics/` | Python analytics math plus the whole Node sidecar | deterministic analysis and block compare (§4.1) | 256Mi |
| `rankings` → `pl-rankings` | `src/services/rankings/` | `lib/opl_dataset.py` plus 3 rankings handlers | `rankings.json` (unchanged) | 512Mi |
| `analytics-export` → `pl-analytics-export` | `src/services/analytics-export/` | `blockAnalysisExport.ts` | `analytics.export`, `analytics.lifetime_export` (new) | 128Mi |
| `analytics-ai` → `pl-analytics-ai` | `src/services/analytics-ai/` | 5 Python AI report ops plus the Node AI routes | AI ops (§4.3) | 128Mi |

`get_analysis_markdown` and `analytics.markdown` wrap Python's `build_program_markdown`. Their domain moves to the existing Python **`export`** service (`pl-export`), which already owns that code, so nothing is ported.

The Python image (`docker/powerlifting-services.pkr.hcl`) must exclude these four directories and `**/target`.

## 4. Operation mapping

The contract stays in `src/services/operations/*.json`. Op names, schemas and `execution` are unchanged; only `domain` changes and the ops move between files. Updates needed:
- the domain list at `src/backend/src/utils/operations.ts:12`
- the Python `src/services/contract.py` loader
- `permissions.json` only if it is keyed by domain

### 4.1 `analytics.json` → `pl-analytics` (Rust)

| Op | Notes |
|---|---|
| `analysis_section`, `weekly_analysis` | Section builders: overview, workload, fatigue_readiness, peaking, alerts |
| `analyze_progression`, `analyze_rpe_drift` | Theil-Sen slope, Kendall tau, r² |
| `health_suggest_e1rm_multipliers` | |
| `analytics.manifest`, `sections_queue`, `sections_get`, `sections_invalidate` | Valkey section records, `SET NX` running state, 15-minute stale → error |
| `analytics.weekly`, `analytics.bundle`, `analytics.regenerate` | `bundle` honours `refresh` (today it always recomputes) |
| `analytics.blocks_list`, `blocks_get`, `blocks_regenerate` | `blocks_regenerate` calls `pl-analytics-ai` over gRPC to regenerate the AI reports |
| `analytics.compare` | Deterministic comparison (`buildBlockComparison` port) |
| `analytics.lifetime` (new, deterministic) | Holistic all-blocks report (§6). Also exposed to MCP. |

### 4.2 `analytics-export.json` → `pl-analytics-export`

| Op | Notes |
|---|---|
| `analytics.export` | Block export in xlsx or markdown, returned as base64. The current-block 400 is kept. |
| `analytics.lifetime_export` (new) | Returns the saved lifetime report (md or xlsx) from S3, or 404 |

### 4.3 `analytics-ai.json` → `pl-analytics-ai`

`correlation_analysis`, `block_correlation_analysis`, `program_evaluation`, `block_program_evaluation`, `multi_block_comparison_analysis`, `analytics.block_evaluation`, `analytics.correlation`, `analytics.compare_ai`.

### 4.4 Moved to `export.json` (Python `pl-export`)

`get_analysis_markdown`, `analytics.markdown`.

The main backend's directly served routes in `src/backend/src/routes/analytics.ts` (correlation, program-evaluation, start-maxes, fatigue-profile, …) keep calling `callOperation`. They pick up the new domains automatically. The frontend does not change.

## 5. Communication

```
backend ──REST /operations, /mcp──▶ pl-analytics | pl-rankings | pl-analytics-export | pl-analytics-ai   (unchanged contract)
every service ──REST──▶ pl-profile /internal/access                                                       (existing, unchanged)
pl-analytics-ai ──REST jobs/executions──▶ pl-coach                                                        (existing coach protocol)
pl-analytics-ai     ──gRPC──▶ pl-analytics          (AnalyticsData)
pl-analytics-export ──gRPC──▶ pl-analytics          (AnalyticsData)
pl-analytics        ──gRPC──▶ pl-analytics-ai       (Reports.Regenerate)
pl-analytics-ai     ──gRPC──▶ pl-analytics-export   (Reports.SaveLifetimeReport)
```

Each Rust service listens on **8000** for HTTP and **50051** for gRPC.

**`src/services/analytics/proto/analytics.proto`**, `service AnalyticsData`:
- `GetSnapshot(AthleteRef)`: program, sessions, weight log, goals and competitions, already normalized
- `GetBlockBundle(BlockRef)`
- `ListBlocks(AthleteRef)`
- `Compare(BlockKeys)`
- `Lifetime(AthleteRef)`
- `CorrelationInputs(BlockRef)`: weekly e1RM series and accessory volume series, ported from `correlation_ai.py:71,110`

Messages carry typed scalars. Large nested report bodies are `google.protobuf.Struct` so the JSON shape stays identical to the HTTP output.

**`src/services/analytics-ai/proto/reports.proto`**, `service Reports`:
- `Regenerate(BlockRef)`

**`src/services/analytics-export/proto/export.proto`**, `service Exports`:
- `SaveLifetimeReport(LifetimeReport)`
- `RenderBlock(BlockRef, Format)`

Auth on gRPC: metadata `x-internal-token` plus `x-athlete-pk` and `x-person-pk`, checked by a tonic interceptor. The internal network uses plain h2c, the same trust level as the HTTP token today.

### Codex and subscription auth

`pl-analytics-ai` never runs Codex. It implements the existing domain-execution protocol from `src/services/execution.py` and `src/services/ai.py`:

1. `submit` reserves a generation and POSTs `IF_API_URL/v1/jobs` (`kind: domain`). It returns 202 `{job_id, generation_id, status}`.
2. The coach calls back to `POST /operations/{name}` with the job context.
3. `start` and `poll` run the handler. On a prompt-cache miss it returns `{status: needs_inference, execution_id, challenge_id, messages, tools, response_format, instruction}`.
4. The coach answers with `POST /executions/{id}`. The answer is validated against the tool schema (jsonschema), and execution resumes.
5. `GET /generations/{id}` returns status and results.

The ChatGPT subscription login stays only in `pl-coach`'s persistent `CODEX_HOME`. There is one login, it is never repeated, and the Codex memory risk stays in the coach pod.

In-flight executions are held in process. `pl-analytics-ai` runs 1 replica, the same as today, because the challenge/resume protocol is stateful.

## 6. Lifetime Compare (the key deliverable)

**Deterministic part: `pl-analytics`, module `lifetime`, op `analytics.lifetime`.**

Input: every block from `blocks_list`, whether completed or current-to-date, not only the selected keys.

Per block:
- **Exposure:** per lift and accessory category, weekly hard sets, tonnage, intensity-band distribution (relative intensity buckets), frequency per week, average RPE, INOL per lift and week, the 4-dimension fatigue profile (axial/neural/peripheral/systemic), ACWR peaks, monotony and strain, compliance, deload placement, specificity ratio.
- **Outcome:** Δe1RM per lift (start to end, using the existing e1RM and multiplier rules), ΔTotal, ΔDOTS, ΔIPF GL, competition result and projection accuracy where present, RPE drift.
- **Classification:** `improved`, `stalled` or `regressed` per lift and overall. Thresholds are set relative to the block's measurement noise and stored in the report.

Across blocks:
- Kendall tau and Spearman correlation of each exposure variable against each outcome, with `n`, `p` (from statrs), and a `low_n` flag below 5 blocks.
- Volume-tolerance bands per lift: the exposure range in which outcomes were positive, and where stalls began.
- Exercise ROI, consolidated ROI, lift dose-response, training-day response and pattern signals (port of `blockAnalytics.ts:1534-1986`).
- `worked` / `did_not_work` lists. Each entry is a signal tied to a variable, its evidence (blocks and values) and its strength.

**AI narrative: `pl-analytics-ai`.**
- `analytics.compare_ai` and `multi_block_comparison_analysis` fetch `Lifetime` over gRPC.
- They render the copied `multi_block_comparison_system.j2` with minijinja and run the coach protocol. The output schema is the same (`overall_summary`, `similarities`, `differences`, `what_works`, `roi`, …), so the frontend `LifetimeComparePanel` (`src/frontend/src/components/analysis/BlockAnalytics.tsx:876`) works unchanged.
- If the panel passes a subset of `blockKeys`, that subset is compared. The all-blocks run is the lifetime run and the one that gets saved.

**Saving.** When an all-blocks lifetime AI run succeeds, `pl-analytics-ai` calls `Exports.SaveLifetimeReport` over gRPC. `pl-analytics-export` renders markdown and xlsx (deterministic tables plus the AI narrative) and writes them to the dataset bucket `$POWERLIFTING_S3_BUCKET`:
- `lifetime/<athlete>/latest.md`
- `lifetime/<athlete>/latest.xlsx`
- `lifetime/<athlete>/<UTC timestamp>.md`
- `lifetime/<athlete>/<UTC timestamp>.xlsx`

**Template-evaluation hook.** This is a small Python change in `src/services/coach/runner.py`, near `workspace_for` at `runner.py:206`:
- For domain jobs whose operation is `template_evaluate`, get `lifetime/<athlete>/latest.md` with boto3.
- If it exists, write it into the job workspace as `lifetime_report.md`, and append one line to the instructions saying it is available.
- If it is missing, change nothing.

The coach pod needs S3 read access to that prefix. Verify the mounted `/secrets/aws` credentials allow it, or add an IAM policy line in the root Terraform; the pipeline's `terraform-apply` job applies that.

## 7. Per-service design

### 7.1 Common skeleton (written separately in each crate, about 150 lines)

```
src/
  main.rs          config from env (envy or plain std::env), tracing, start the axum and tonic servers
  config.rs
  auth.rs          X-Internal-Token constant-time compare (subtle), X-PL-Principal JWT verify (jsonwebtoken), athlete/person extraction
  operations.rs    include_str!("../../operations/<domain>.json"), jsonschema validation, name → handler dispatch
  http.rs          POST /operations/{name}, GET /health (readiness gated), GET /openapi.json, GET /docs (Swagger UI, spec generated from utoipa derives)
  mcp.rs           rmcp streamable-HTTP server at /mcp; tools generated from the operations JSON (internal_only excluded)
  error.rs         thiserror enum → {detail:{code,message}} with the same status codes as the Python OperationError
```

Crates: `axum`, `tokio`, `tower-http` (trace, compression, timeout), `tonic`, `prost`, `tonic-build`, `tonic-health`, `tonic-reflection`, `serde`, `serde_json`, `thiserror`, `tracing`, `tracing-subscriber` (json), `utoipa` (ToSchema derives + `#[utoipa::path]` per operation) with `utoipa-swagger-ui` (vendored), `rmcp`, `jsonschema`, `jsonwebtoken`, `subtle`.

Release profile: `lto = "thin"`, `codegen-units = 1`, `strip = true`. Allocator: `mimalloc`, which keeps fragmentation and RSS low for long-running pods.

### 7.2 `pl-analytics`

```
src/
  source/        mod.rs (trait Source), dynamo.rs (aws-sdk-dynamodb + serde_dynamo), fixture.rs (JSON dir)
  model.rs       Program, Session, Set, Exercise, Block, Competition, WeightEntry, Goal (serde, borrowed &str where possible)
  calc/          e1rm.rs, scoring.rs (DOTS, IPF GL), compliance.rs, progression.rs, fatigue.rs, inol.rs, acwr.rs,
                 banister.rs, peaking.rs, intensity.rs, landmarks.rs, readiness.rs, alerts.rs, deload.rs
  windows.rs     current, previous_1/2/4/8 and block windows from block-local weeks and week start day
  sections/      overview.rs, workload.rs, fatigue_readiness.rs, peaking.rs, alerts.rs, mod.rs (fan-out)
  blocks/        index.rs, bundle.rs, strength.rs, outcome.rs
  compare/       trends.rs, roi.rs, dose_response.rs, patterns.rs, tolerance.rs
  lifetime/      exposure.rs, outcome.rs, correlate.rs, signals.rs, mod.rs
  cache.rs       Valkey records and version counter
  grpc.rs        AnalyticsData server
  handlers.rs    op → function
```

Data access uses the same keys as `src/services/lib/program_store.py` and `session_store.py`:
- `if-health`: `pk=<athlete>`, `sk=program#current` → `program#vNNN`; glossary at `sk=glossary#v1`
- `if-sessions`: query by athlete
- competition entries merged as in `with_competition_entries`

Table names come from env `IF_HEALTH_TABLE_NAME` / `IF_SESSIONS_TABLE_NAME`, falling back to `DYNAMODB_TABLE`. The ConfigMap mismatch goes in `bug.md`.

The glossary region comes from the AWS config, not hardcoded.

Formulas: port faithfully from `analytics.py` and `blockAnalytics.ts`, with `docs/FORMULAS.md` as the reference.
- The RPE-percentage table is loaded from `src/services/calculation_constants.json` via `include_str!` (a data file, not a lib).
- Weights for fatigue dimensions, INOL thresholds and specificity bands come from the same constants.

Stats crates:
- `statrs`: medians, quantiles, distributions, p-values
- `kendalls`: Kendall tau
- `linregress`: OLS and r²
- Theil-Sen is the median of pairwise slopes, computed with statrs.

Memory: one snapshot per request, passed as `&Snapshot`. Sections take slices and iterators. There is no global cache in the process; Valkey is the cache.

Caching uses the same keys so the current Python write path keeps invalidating correctly:
- `pl:analysis:<athlete>:<record>`, with records `native_section#…`, `native_windows#…`, `native_block_view#5#…`, `native_block_index#5#2#…`, `native_block#5#<key>#<fp>`
- fingerprint `s4-v<version>-<start>-<end>`
- version counter `pl:analysis-version:<athlete>`, incremented by `src/services/analysis_version.py` after writes

Change: every record gets `EX 2592000` (30 days). Section running state uses `SET NX` and keeps the 15-minute stale rule. The `redis` crate is used with `tokio-comp` and `connection-manager`.

### 7.3 `pl-rankings`

```
src/
  dataset.rs     S3 sync, identity (sha256 of name, size, mtime → 16 hex), CSV → Parquet conversion, readiness flag
  query.rs       lazy plans: base filter, recent-best dedupe, percentile, stats
  categories.rs  boot-time distinct values and country/region/federation maps
  ops.rs         analyze_powerlifting_stats, powerlifting_filter_categories, powerlifting_ranking_percentile
  scoring.rs     DOTS
  classes.rs     IPF weight classes, ±1 band
```

**Boot:**
1. List `datasets/openpowerlifting-` in S3.
2. If `datasets/openpowerlifting-<identity>.parquet` exists, download it to an emptyDir at `/data`.
3. Otherwise download the CSV to `/data`, then run `LazyCsvReader` → select only the needed columns → cast to categoricals and f32 → derive `Year` → `sink_parquet`. This is the streaming engine with bounded memory. Upload the Parquet back to S3 so other replicas skip the conversion, then delete the CSV.
4. Compute categories with one streaming scan.
5. Set ready. The readiness probe is `/health`, which returns 503 until ready.

**Per request:** `LazyFrame::scan_parquet` with projection and predicate pushdown, run with the streaming engine.
- ranking: Event == "SBD", then sex, age_class, equipment, the weight-class band and the last 3 years; then `group_by(Name).agg(max TotalKg)`, scoped to national and regional; then count strictly below the user's value and `n`.
- stats: filtered quantiles, mean, max, and a strictly-below count per lift.
- No DataFrames are kept between requests.

Semantics kept exactly:
- percentile is strictly below and returns None when n < 10
- `top10_mean` is the top-25% mean quirk; preserve it and log it in `bug.md`
- the actual input fields of `analyze_powerlifting_stats` are read, even though its schema declares fewer

Cache: Valkey `pl:rankings:{identity}:{year}:{pk}:{sha256(inputs)}`, now with `EX 604800`.

Polars features: `lazy`, `streaming`, `parquet`, `csv`, `dtype-categorical`, `strings`. Nothing else.

Scaling: 2 replicas, `emptyDir` with `sizeLimit` about 1Gi, no shared state.

### 7.4 `pl-analytics-export`

```
src/  render/markdown.rs, render/xlsx.rs (rust_xlsxwriter, one sheet per topic like blockAnalysisExport.ts),
      lifetime.rs (S3 put and get via aws-sdk-s3), grpc.rs (Exports server), handlers.rs
```

Data comes from `AnalyticsData.GetBlockBundle` and `Lifetime` over gRPC. It returns the same `{content_base64, content_type, content_disposition}` envelope as today.

### 7.5 `pl-analytics-ai`

```
src/  execution.rs (submit/start/poll/resume state machine; tokio oneshot per challenge; 900 s deadline),
      generations.rs (Dynamo if-powerlifting-analysis-cache: pk=analysis#<athlete>, sk=native_generation#<sha256>,
                      80 KB result shards; same fingerprint inputs as generations.py so existing records stay readable),
      prompt_cache.rs (Valkey pl:ai-cache:exact:<athlete>:<op>:<sha256>, EX 30 d),
      prompts/ (copied .j2 files, minijinja), reports/{correlation, evaluation, comparison}.rs, grpc.rs (Reports server)
```

Generation sha256 identity must be byte-compatible with `generations.py:22,85`, which uses canonical JSON with sorted keys. This is tested against fixtures.

Set `expires_at` on new generation records (180 days); the table already has TTL on that attribute.

## 8. Testing and parity (offline, low Dynamo cost)

**Snapshot script.** `scripts/snapshot_operator_analytics.py` is written in phase 1 and **run once** (by Claude, before the cutover, against the current live services). It is read-only:
- One `GetItem` for the program pointer and version, one paginated `Query` of operator sessions, weight log, goals, glossary and competition entries. That is tens of read units.
- Calls to the current live deterministic ops through the backend as operator, each once:
  - `analytics.blocks_list`
  - `analytics.blocks_get` for each block
  - `analytics.manifest` and `analytics.sections_get` for every window × section at a fixed `asOfDate`
  - `analytics.weekly`
  - `analyze_progression` and `analyze_rpe_drift` for the main lifts
  - `analytics.compare` over all blocks
  - `analytics.export` md for one past block
  - the 3 rankings ops with the operator's maxes
- Writes to `fixtures/operator/{source,golden}/*.json` (added to `.gitignore`).
- The OPL CSV is copied into `fixtures/opl/` once (S3 read).

**Per-module parity.** Each Rust module has a test that loads `fixture.rs` and compares against its golden section, with tolerance `1e-6` relative or `1e-9` absolute, and exact matching for strings and enums.
- Run only that crate's test, for example `cargo test --manifest-path src/services/analytics/Cargo.toml workload`.
- Tests skip with a clear message if `fixtures/operator` is absent.
- No AWS credentials are used and nothing is written to live tables.

**Lifetime.** There is no golden, because it is new or broken today. Coverage:
- property tests (insta snapshot of the shape)
- correlation sanity on synthetic blocks: monotonic dose gives tau ≈ 1, noise gives |tau| small
- a check that `low_n` is set correctly

**Final full compare (phase 7).** A single run of all crates' parity tests plus `scripts/compare_operator_goldens.py`, which diffs a fresh Rust-generated set against the goldens. This needs the operator's explicit OK, per CLAUDE.md rule 11.

**Lint:** `cargo clippy -- -D warnings` and `cargo fmt --check` per crate.

## 9. Execution phases

Opus orchestrates each phase and sends Sonnet subagents a brief that points at this doc's section. Opus then reviews the diff, runs the scoped tests and ticks the checklist.

- [ ] **0.** Copy this plan to `docs/plans/2026-11-11-analytics-rankings-rewrite.md`. Save the feedback memories (no language suffixes in names; full plan as an md first).
- [ ] **1. Contracts:**
  - split `analytics.json` into `analytics.json`, `analytics-ai.json` and `analytics-export.json`, and move the 2 markdown ops to `export.json`
  - add the new op entries (`analytics.lifetime`, `analytics.lifetime_export`)
  - update the backend domain list and `contract.py`
  - write the snapshot script
  - add the `.gitignore` fixtures entry
  - **Run the snapshot script once.**
- [ ] **2a. Sonnet:** `src/services/rankings/`, complete, with parity tests.
- [ ] **2b. Sonnet:** `src/services/analytics/` skeleton, source, model, calc, windows and sections, with section parity tests. Parallel with 2a.
- [ ] **3. Sonnet:** `analytics` blocks, compare, lifetime, cache and the gRPC server, with parity and lifetime tests.
- [ ] **4a. Sonnet:** `src/services/analytics-export/`. Parallel with 4b.
- [ ] **4b. Sonnet:** `src/services/analytics-ai/`, including generation-id compatibility tests.
- [ ] **5. Sonnet:** coach `template_evaluate` hook plus a unit test (`src/services/coach` test file for the runner only).
- [ ] **6. Sonnet, deploy artifacts:**
  - Packer `docker/powerlifting-{analytics,rankings,analytics-export,analytics-ai}.pkr.hcl`: build in `rust:1-slim-bookworm`, run in `debian:bookworm-slim` with ca-certificates, non-root
  - exclude the Rust directories from the Python services image
  - CI in `.github/workflows/build-images.yml`:
    - add `build-analytics`, `build-rankings`, `build-analytics-export` and `build-analytics-ai` jobs, following the existing `build-services` Packer/ECR pattern
    - path filters for each Rust directory
    - add the new jobs to the `kubernetes-apply` `needs` and `if`, so the pipeline applies `terraform/k8s/app` with the new image tags
    - pass image repos and tags as Terraform vars, like the existing services image
  - Terraform:
    - `terraform/k8s/app/analytics.tf`: rewrite as a single container
    - `rankings.tf`: new, 2 replicas, emptyDir
    - `analytics_export.tf` and `analytics_ai.tf`: new
    - remove `rankings` from the `services.tf` for_each
    - add gRPC port 50051 to the Services
    - env vars as in §7
  - `terraform fmt` and `validate` only.
- [ ] **7.** Final full compare (with operator OK). Unrelated findings go into `bug.md`: read-only gaps in `analyticsService.ts:136,141`, the `block_program_evaluation/core.py:22` import, the `DYNAMODB_TABLE` env mismatch, and the `top10_mean` naming.

Any task stuck for more than about 4 rethink cycles goes to `HANDOFF.md` and the work moves on.

## 10. Cutover (pipeline)

1. The user branches from the staged work and merges it. On the push, the pipeline builds all images and applies the `terraform/k8s/{core,perms,network,app}` stacks (`kubernetes-apply` job).
2. Ordering inside the single `app` apply:
   - the new Deployments and Services (`pl-analytics-export`, `pl-analytics-ai`) carry no dependency on the backend
   - the backend Deployment gets `depends_on` those Services, so the split operations JSON never routes to a missing host
3. The Service names `pl-analytics` and `pl-rankings` do not change.
4. Rollback is a git revert, which the pipeline re-applies. The old images stay in ECR.
5. Python handler code for the moved ops is deleted only after a stable week. That deletion is a separate task.

## 11. Verification

- Per-crate parity tests are green against the operator goldens. Clippy and fmt are clean.
- Live, read-only checks after cutover:
  - `kubectl top pod -n <ns>`: rankings stays under 512Mi during a burst of about 50 percentile requests, and analytics stays under 256Mi on `analytics.bundle`.
  - `kubectl logs` show no errors.
- In the UI:
  - Analysis → Weekly sections load and invalidate after a session edit.
  - Past Blocks loads, and xlsx/md export downloads.
  - Rankings page loads.
  - Lifetime Compare → Run AI completes (coach login unchanged, no re-auth).
  - `lifetime/operator/latest.md` and `latest.xlsx` exist in S3.
- Run `template_evaluate` and confirm the coach job workspace contains `lifetime_report.md`, and that the evaluation cites it.
- `/docs` (Swagger UI) on each service shows every operation. gRPC reflection lists the services (`grpcurl -plaintext pl-analytics:50051 list`).
