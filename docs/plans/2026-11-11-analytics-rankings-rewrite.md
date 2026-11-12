# Analytics Migration and Rewrite: Revision 5

> Revision 5 replaces all earlier revisions.
>
> On approval, write this file to `docs/plans/2026-11-11-analytics-rankings-rewrite.md`, replacing its contents. Subagents read that file as their spec.
>
> Execution rules:
> - Sonnet subagents do all the work; Opus only orchestrates.
> - Builds are serialized and memory-capped: `flock /tmp/claude-1000/cargo-build.lock env CARGO_BUILD_JOBS=3 systemd-run --user --scope -p MemoryMax=7G -p MemorySwapMax=0 --quiet -- <cmd>`.
> - Only the pipeline applies changes. No git writes.
> - Tests are offline and scoped; nothing is ever written to prod.

## 1. Services (four in total, no further splitting)

| Service / dir | Lang | Scope |
|---|---|---|
| `pl-analytics` / `src/services/analytics/` | Rust (already built) | All analysis: the current-block sections, weekly, progression, RPE drift, e1RM multipliers, manifest/queue/sections records, the Past Blocks index/get/regenerate, compare, lifetime. Owns its own Dynamo reads, its Valkey cache (for the frontend), and the S3 snapshots of **past blocks only**. Serves the AnalyticsData gRPC. |
| `pl-rankings` / `src/services/rankings/` | Rust (done) | OpenPowerlifting dataset and ranking queries. |
| `pl-analytics-ai` / `src/services/analytics-ai/` | Go | The AI report ops (`analytics-ai.json`). Kept separate because Codex is an OOM risk. Uses the coach execution protocol, with the single coach login. |
| `pl-analytics-export` / `src/services/analytics-export/` | Go | Read-heavy rendering: `analytics.export`, `analytics.lifetime_export`, and saving the lifetime report to S3. |

**Separate scopes that are not part of these services and never call them:**
- export / program markdown
- program history
- program-evaluation metrics (`template_evaluate`)
- competition projection

Each of them keeps its own code.

**gRPC links:**

| From | To | Calls |
|---|---|---|
| `pl-analytics-ai` | `pl-analytics` | AnalyticsData |
| `pl-analytics-export` | `pl-analytics` | AnalyticsData |
| `pl-analytics` | `pl-analytics-ai` | `Reports.Regenerate` |
| `pl-analytics-ai` | `pl-analytics-export` | `Exports.SaveLifetimeReport` |

## 2. Auth and communication (all four services)

This is the mesh model. The Rust side is already ported.

**Inbound requests:**
- Headers: `X-Person-Pk`, `X-Athlete-Pk`, `X-PL-Source-Principal`, and the job and generation headers.
- Check order, ported from `app.py:call`:
  1. a generation without a job → 403
  2. unknown operation → 404
  3. reserved arguments → 403
  4. missing Person → 403
  5. `access_context` on pl-profile
  6. `internal_only` operations require the backend source account
  7. scope the arguments, validate the input, run the handler, validate the output

**gRPC on :50051:**
- Metadata carries the Person/Athlete. An interceptor checks the caller account against an allow list.
- The Service port is named `grpc` with `app_protocol = "grpc"`.
- There are no tokens.

**Go stack:**

| Purpose | Library |
|---|---|
| HTTP and OpenAPI | `huma/v2` on `chi`. Swagger UI at `/docs` is generated from types, with a test that every operation is documented. |
| gRPC | `grpc-go`, stubs generated with `buf` |
| JSON schema | `santhosh-tekuri/jsonschema/v6` |
| AWS | `aws-sdk-go-v2` |
| Valkey | `go-redis/v9` |
| Logging | `slog` |
| xlsx | `excelize/v2` |
| Prompts | `text/template` |

Other Go conventions: JSON-RPC at `POST /mcp`, distroless non-root images, `GOMEMLIMIT` set under the 128Mi limit.

## Part I: Finish the migration

- [x] Merge cleanup, offline goldens, Rust auth port, rankings, analytics core, phase 3 compute (compare, lifetime, gRPC tests).
- [x] **3. Analytics finish (Rust).** Fix the `blocks_get` parity failure (12/12), then clippy and fmt. Use the agent's notes in `look-at-the-analysis-dapper-creek-agent-a04092a82b498d0a6.md`.
- [x] **4a. `pl-analytics-export` (Go)** and **4b. `pl-analytics-ai` (Go)**, in parallel. (4b `pl-analytics-ai` done: `src/services/analytics-ai/`, tests green offline; 4a pending.)
  - [x] **export (done, `src/services/analytics-export/`):** renders xlsx/md from `GetBlockBundle`; saves and reads `lifetime/<athlete>/{latest,<ts>}.{md,xlsx}`.
  - [x] **ai:**
    - the coach protocol (submit / needs_inference / resume, 900 s, 1 replica), with only the Person/Athlete headers sent to the coach
    - generation sha256 byte-compatible with `generations.py`
    - the prompt cache `pl:ai-cache:exact:…`
    - the 4 prompts rewritten as `text/template`
    - `Reports.Regenerate`
    - `SaveLifetimeReport` after an all-past-blocks run
- [x] **5. Coach hook.** `template_evaluate` gets `lifetime_report.md` if `lifetime/<athlete>/latest.md` exists.
- [x] **6. Deploy artifacts.**
  - Packer:
    - the `powerlifting-analytics` template becomes the Rust build
    - new templates for rankings (Rust), and for ai and export (Go, distroless)
    - all use the single-tag pattern with the push step named `publish`
    - the services image excludes the Rust/Go directories
  - ECR repos, `var.repositories`, the CI matrices and the rollout list.
  - Terraform:
    - `analytics.tf` becomes a single container, 256Mi; the Node sidecar and `ANALYTICS_NODE_TOKEN` are dropped
    - `rankings.tf`: 512Mi, 2 replicas, emptyDir; rankings is removed from `services.tf` and `mesh_domains`
    - `analytics_ai.tf` and `analytics_export.tf`: 128Mi each
  - Mesh:
    - service accounts for `pl-analytics-ai` and `pl-analytics-export`
    - port lists that include 50051
    - `mesh_callers` per the gRPC table
    - `cache_callers` for Valkey
  - `fmt` and `validate` only.
- [ ] **7. Final offline compare** with `scripts/golden_harness`, plus the `bug.md` entries.
- [x] **D. Delete legacy code.**
  - **Carve-out first.** Export/markdown, program history, the `template_evaluate` metrics and the competition projection each take the few functions they use out of `analysis_reports/analytics.py` into a module in their own package. No new operations, and no calls to the analysis services.
  - **Python deletions:**
    - the rest of `analytics.py`
    - `handlers/analysis/**`
    - the analytics shims and `composite.py`
    - `suggest_e1rm_multipliers.py`
    - `lib/opl_dataset.py` and `generations.py`
    - the 4 analytics prompts
    - the rankings `warm_cache` and `/generations` in `app.py`
    - the REPORTS branches in `execution.py`
    - pandas, numpy and (if unused) scipy
    - the dead tests
  - `contract.py` `handler` becomes optional for the Rust/Go domains, and `test_handler_imports` skips them.
  - **Node:** delete the sidecar and its relay/paths files, `blockAnalytics.ts`, `blockAnalysisExport.ts`, `analysisRecords.ts`, `programRequestCache.ts`, `utils/calculations.ts`, `blockScope.ts`, and the dead tests and scripts. Trim `routes/analytics.ts` to the 10 main-backend routes, with `start-maxes` rewritten on `analytics.blocks_list`, and trim `analysisCache.ts` to the normalizers.
  - Run only the scoped tests.
- [ ] **C. Dynamo cleanup.**
  1. Enumerate read-only to a manifest and back it up: the `person_3a06…` copy, the September fixture partitions, `pk='test'`.
  2. Report the counts.
  3. Batch-delete only those keys, plus the video's S3 objects.
  4. Keep the Authentik `test` login rows and all `operator` data.

## Part II: Analysis rewrite (after the migration)

### R1. Calculation correctness (`pl-analytics`, Rust)

- **History across blocks.** ACWR, Banister, monotony and INOL baselines seed from the full history; the window limits display only.
- **Week and phase.** The current week comes from the window's end date. Phase lookup is scoped to the block.
- **Exercise names.** One normalizer. The main lift is resolved through glossary `lift_transfer`.
- **Planned overreach.** Only when the active phase of the current block is explicitly tagged (drop the RPE ≥ 9 rule). The suffix goes only on elevated zones.
- **INOL.** Remove the `[1, 2]` clamp. Coefficients are validated to `[0.5, 2.0]` and come from the matching profile. Thresholds are scaled the same way. Output: raw, adjusted, and the coefficient's source.
- **ACWR.** Missing dimensions are excluded and the weights renormalized. Acute and chronic values are exposed per dimension.
- **Fatigue dimensions.** Reported as a ratio to the athlete's chronic baseline (1.0 = a typical week), plus the raw value. The non-SBD intensity uses the glossary e1RM.
- **Monotony and strain.** Normalized load, restricted to the window, partial weeks flagged, at least 3 days for `high_monotony`.
- **Specificity and per-lift breakdown.** Both use transfer weights: lunges → squat, RDLs → deadlift, close-grip → bench. Computed server-side.
- **Muscle volume.** Sets per muscle compared against researched landmarks per muscle (`data/muscle_landmarks.json`, with sources cited), with a status for each muscle.
- **Glossary.** Parsed fully (muscles, archived, `lift_transfer`).
- **Docs and tests.** `FORMULAS.md` and `formulaDescriptions.ts` are synced to the code. Synthetic tests per metric; the re-baseline is reviewed.

### R2. Glossary `lift_transfer` (glossary and lift-profiles scope)

- An AI-estimated field `{squat, bench, deadlift: 0–1, source, reasoning}`, like `fatigue_profile`, with rule-based defaults.
- An editor field, and a backfill op that runs through the app.
- Audit the repeated 1.40 stimulus coefficient (`lib/lift_profile_ai.py:56-81` and its prompt).

### R3. Analysis UI (frontend)

- **Peaking timeline.** `PeakingTimeline.tsx:237-245`: the Scatter's own `data` hides `projected_tsb`. Merge the points into `chartData`.
- **`ChartHelp` on every chart:** a short description, the expected range from the backend thresholds, the units, how it relates to the other metrics on the same chart, and a link to the definition. Charts: TSB and peaking, INOL, ACWR, Fatigue Dimensions, Monotony & Strain, Specificity, the per-lift breakdown.
- **Muscle map.** Remove the duplicate "Avg Weekly by Muscle Group" chart. The body map shows average sets per muscle against that muscle's researched landmarks. Add the same map at the bottom of the Dashboard.
- **Dead client code.** Delete the client-side per-lift and muscle computation.

### R4. Past Blocks screen and Lifetime Compare

- **`pl-analytics` (Rust):**
  - stores **past blocks only** in S3 as immutable snapshots
  - `blocks_list` returns `stored` and `storedAt`, which replaces the never-set `cacheStatus` that left the list empty
- **Lifetime Compare:**
  - The user selects stored past blocks.
  - The run produces the same analysis as the main page, with those past blocks as historical context and reference points:
    - the deterministic part comes from `analytics.lifetime`
    - the narrative comes from `pl-analytics-ai`
  - An all-past-blocks run is saved through export for `template_evaluate`.
- This fixes the 500.

Order: R1 and R2, then R3, then R4.

## Verification

- **Part I:**
  - parity is 12/12, and the Go and Swagger-coverage tests pass
  - the harness diff matches the goldens
  - lint and `terraform validate` pass
  - after the pipeline deploys (read-only checks): pods are Running, within limits, no 403s
  - in the UI: Analysis, Past Blocks, export, Rankings and the Lifetime AI run all work
  - `lifetime_report.md` reaches the `template_evaluate` workspace
- **Phase D:** no imports of the deleted modules; the carved scopes' tests pass; backend and frontend `tsc` pass.
- **Part II:** per-metric tests, the re-baseline reviewed, and the R3/R4 UI checks.
- **Cleanup:** the manifest queries return 0, and operator counts are unchanged.
