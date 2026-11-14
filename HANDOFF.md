# Handoff — 2026-11-13 (branch `feat/analytics-rankings-rust`, HEAD 0e270441)

## Where we are

- The analytics/rankings rewrite is deployed: four services (pl-analytics Rust, pl-rankings Rust, pl-analytics-ai Go, pl-analytics-export Go). The pipeline passes, and 34/34 deployments are ready. Spec: `docs/plans/2026-11-11-analytics-rankings-rewrite.md`.
- AI ops were verified live from the backend pod; all succeeded end to end:
  - fatigue / muscle / lift-transfer estimate, lift-profile suggest
  - correlation queue → generation result
- **ChatGPT subscription quota is exhausted until Nov 14 2026 12:29 AM.** Every AI call fails until then with `execution_failed: You've hit your usage limit`. This is not a code bug.
- Disk: 78% used (51G free). It is a shared k3s node and CI runner; clean `target/` after any cargo build.

## Uncommitted changes (operator to commit/push)

Done and verified (tsc / fmt), ready to ship:

| File | Change |
|---|---|
| `terraform/k8s/app/oauth2_proxy.tf` | `--skip-auth-route=GET=^/api/`. Anonymous GETs (search, profiles, `auth/me`) were 401'd by oauth2-proxy after the Istio/Authentik merge. Already hot-patched live and verified: anonymous search returns 200, a forged-bearer POST returns 401. Still to confirm: a logged-in browser keeps its identity (the oauth2-proxy source says the session still loads on skipped routes). |
| `src/services/lift_profiles/lift_profile_ai.py` | `json.dumps(..., default=float)`. The stimulus estimate 502'd on `Decimal` athlete metrics. |
| `ChartLabel.tsx` + the analysis panels, `WeeklyData`, `PeakingTimeline`, `MuscleVolumeMap`, `AnalysisPage` | The "i label" is now an inline ⓘ icon beside each chart title, with a one-line hover tooltip. No link and no text line. |
| `AnalysisPage.tsx` | Flags card moved from the bottom to directly under Coaching Alerts. |
| `terraform/k8s/app/services.tf` | pl-glossary 256→384Mi (it was OOMKilled during the backfill). Already live. |
| `terraform/k8s/app/analytics_ai.tf` | pl-analytics-ai 128→512Mi. Already live. The operator may want a lower number. |

ROI → Main-Lift Drivers rework: **complete, compiles, scoped tests green** (spec `docs/plans/2026-11-13-main-lift-drivers.md`):

- **Rust (pl-analytics):**
  - The proto `CorrelationInputsReply` adds fields 8–14: `exercise_weeks`, `exercises`, `muscle_weeks`, `muscle_landmarks`, `fatigue_weeks`, `lift_sessions`, `driver_stats`.
  - New `src/drivers.rs`; small helpers in `muscle_volume.rs`, `model.rs`, `util.rs` (`spearman`).
- **Go (pl-analytics-ai):**
  - stubs regenerated with protoc (the analytics-export copy too)
  - new `internal/prompts/drivers.go`; `correlation.go` maps the new fields
  - prompts rewritten; the tool schema is the new driver schema (max 8 findings)
  - `operations.json` updated in both places
  - `CorrelationPromptVersion = "main-lift-drivers-v1"` is part of the generation identity, so old cached reports regenerate
- **Export:** `analytics-export/internal/render/block.go` and `export/analysis_reports/export.py` read the new fields, with fallback to the old ones.
- **Frontend:** `DriversTable.tsx`; `AiAnalysis.tsx` and `BlockWeeklySurface.tsx`; the normalizer reads old reports.
- **Not yet verified against real data.** The Rust gRPC test was compiled but not run, and nothing has looked at the UI in a browser. After deploy, and after the AI quota resets, run a correlation with `refresh:true` and check the findings quality.
- Known limit: `driver_stats` covers the whole block even when the trailing-weeks window is shorter.

Later fixes, also uncommitted and verified (cargo check, scoped go test, tsc):

- **Anonymous analysis (403 "Authenticated Person required"):** pl-analytics, pl-rankings, pl-analytics-ai and pl-analytics-export had a Person gate that Python never had. Python only requires a Person for `ownership: person` ops, and every op in these four is athlete-owned. The gate is removed in the `operations.rs` files and `service.go`, and its two Go test rows are dropped. `Resume` keeps its Person check, matching Python.
- **Dashboard long decimals:** `utils/units.ts` `toDisplayUnit` and `displayWeight` now round kg to 0.1. The kg branch printed the raw value, and the Rust analytics returns full precision where the old Node path rounded. **Not confirmed against the operator's screen.** If they still see long decimals, ask which value.

- **Analysis page muscle maps:** the original `MuscleWorkloadMap` is restored in `WeeklyData.tsx`, and the new `MuscleVolumeMap` stays directly below it. Both stay; never replace one with the other.
- **Glossary uniqueness:** `runtime/glossary_store.py` `upsert_exercise_sync` now enforces case- and whitespace-insensitive unique names.
  - An add with an existing name fills that entry's missing fields and returns its id.
  - A rename onto an existing name raises an error.
  - Checked offline; `test_glossary.py` can't import locally because `redis` isn't installed.
  - The live data still has one duplicate pair: `Ab Rollout` (`ed5adf46…`) and `ab rollout` (`2289309c…`). It needs a merge, pending operator OK: keep `ed5adf46`, copy over its missing fatigue_profile fields, remove `2289309c`.

## Unfinished work

### 1. Main-Lift Drivers: verify after deploy

Code is done (see above). Once deployed and the quota resets:
- Generate the current-block report (`refresh:true`) and a past-block one.
- Judge the findings against the operator's bar: dose numbers, sequencing, muscle weak links and overloads, one action each, no trivia.
- Tune `correlation_system.tmpl` if the findings are weak.

### 2. Glossary `lift_transfer` backfill (needs AI quota, after 00:29)

- Rule defaults are already written: 64 of 91 exercises for athlete `operator`.
- The AI estimates still have to run. For each exercise whose `lift_transfer.source != "ai"`, call `glossary_estimate_lift_transfer` with `{pk:"operator", id}`; the result is persisted.
- Script used: a node script run in the backend pod. It POSTs `http://pl-glossary:8000/operations/<op>` with headers `X-Person-Pk: sir_simpalot`, `X-Athlete-Pk: operator`, then polls `$IF_API_URL/v1/jobs/<job_id>/result` until it is no longer 202. Use concurrency 3.
- Afterwards, spot-check the weights in the Glossary page.

### 3. Other open items

- Verify a logged-in session after the oauth2-proxy change: `/api/auth/me` should return the user, not `readOnly: true`.
- Correlation with `refresh:true` returned `cached:true` instantly. Check whether refresh bypasses the exact prompt cache in pl-analytics-ai.
- The frontend sends `window_start`/`window_end`, which the backend ignores.
- The analysis fingerprint shows `s4-v89--` (empty start/end).
- Unverified muscle landmarks: front delts, rear delts, glutes.
- Part I item 7: the final offline golden compare (harness in the old session scratchpad, not in the repo), plus the `bug.md` entries.
- S3 video bucket: old object versions remain unless purged. Ask the operator.
- The AlertsStrip still has an "Open formula reference" anchor link (pre-existing).

## Operator preferences (also in auto-memory)

- Do exactly what's asked.
  - UI: keep existing components unchanged; labels are one short line in an ⓘ tooltip.
  - Resources: touch only the pods named, with modest bumps.
- Rust only for compute-heavy services; Go for the rest. Never split a service by layer.
- No git writes, no comments in code, no new low-value tests, never write fixtures to prod.
- Check live state (kubectl / git) before claiming anything. Clean build artifacts (shared disk).
