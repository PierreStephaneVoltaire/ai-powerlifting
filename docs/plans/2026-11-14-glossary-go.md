# Glossary: own table, shared catalog + per-athlete overlay, Go rewrite

Subagents read this file as their spec. Same rules and Go stack as
`2026-11-11-analytics-rankings-rewrite.md` and
`2026-11-14-sessions-program-competition-go.md` (huma/v2 on chi, jsonschema/v6,
aws-sdk-go-v2, go-redis/v9, slog, distroless non-root, GOMEMLIMIT, mesh auth
copied from `analytics-export/internal/{auth,contract,apperr,serve}`).

## Execution rules

- Sonnet subagents write the code; Opus orchestrates.
- **Fresh rewrite, no bloat.** Read the Python (`src/services/glossary/**`,
  `runtime/glossary_store.py`, the prompts) to learn behaviour and the wire
  contract, then write idiomatic Go. No helper-by-helper port, no dead branches,
  no legacy fallbacks, no migration shims (no reading `glossary#v1` from the new
  service).
- Go builds/tests serialized and memory-capped:
  `flock /tmp/claude-1000/go-build.lock systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 --quiet -- env GOFLAGS=-p=3 <go cmd>`.
  Rust (pl-analytics) builds:
  `flock /tmp/claude-1000/cargo-build.lock env CARGO_BUILD_JOBS=3 systemd-run --user --scope -p MemoryMax=7G -p MemorySwapMax=0 --quiet -- <cmd>`.
- No git writes (the orchestrator commits). No `terraform apply`; `fmt`/`validate`
  only. Only the pipeline applies.
- Tests offline, scoped to the module you changed. Never `*_live*`, never a live
  table, no AWS credentials in tests.
- No code comments. Unrelated bugs → `bug.md`; stuck >4 cycles → `HANDOFF.md`.
- No env values in code or tf defaults: table names, hostnames, ids only come
  from tfvars / env.

## 1. Data model: new DynamoDB table (glossary)

Own table (name from tfvars `glossary_table_name`), keys `pk` (S) / `sk` (S),
PAY_PER_REQUEST, stream `NEW_IMAGE`, PITR on, deletion protection on.

| Item | pk | sk | Content |
|---|---|---|---|
| Catalog exercise (shared by everyone) | `CATALOG` | `EXERCISE#<id>` | Definition only: `id`, `name`, `name_key`, `category`, `equipment`, `primary_muscles`, `secondary_muscles`, `tertiary_muscles`, `description`, `how_to_perform`, `why_do_it`, `video_url?`, `lift_transfer` (+`lift_transfer_source`, `lift_transfer_reasoning`), **generic** `fatigue_profile` (+`fatigue_profile_source` = `ai_generic` or `default`, `fatigue_profile_reasoning`), `generic_status` (`pending`/`ready`/`failed`), `generic_attempts`, `created_by`, `created_at`, `updated_at`. |
| Athlete overlay | `ATHLETE#<athlete_pk>` | `EXERCISE#<id>` | Everything personal: **personal** `fatigue_profile` (+source `ai_personal`/`manual`, reasoning, `estimated_at`), `e1rm_estimate`, `archived`, `hidden`, and any definition fields the athlete overrides. When the athlete created the exercise, the overlay also carries the definition it was created with (`custom: true`). |

- Sparse GSI `generic-pending`: hash `generic_pending` (S, constant `"1"`), range
  `created_at`. The attribute exists only while `generic_status = pending`, so
  the index is empty in steady state.
- `name_key` = casefolded, whitespace-collapsed name (same as Python `_name_key`).
  Catalog is unique by `name_key`.
- Effective exercise for an athlete = catalog item ⊕ overlay (overlay wins
  field-by-field). Response also carries `generic_fatigue_profile` and
  `fatigue_profile_personalized: bool`, so the UI can show both. Athletes see all
  catalog exercises (minus their `hidden` ones) plus their own custom ones.
- Fatigue is never shared: an athlete's personal estimate writes only to their
  overlay. The catalog `fatigue_profile` is the generic default that everyone
  without a personal one falls back to.

## 2. Flows

**Add exercise (`exercise_upsert`, new id or unknown name):** write the athlete
overlay with `custom: true` and the definition. Nothing else in the request
path.

**Lambda `glossary-catalog` (Go, `src/lambda/glossary-catalog/`, provided.al2023
arm64):** DynamoDB stream trigger on the glossary table, filter = INSERT/MODIFY of
`pk` begins_with `ATHLETE#` and `custom = true`. For each record: Query `CATALOG`
for the `name_key` (keep it simple: a `name_key` lookup item
`pk=CATALOG_NAME, sk=<name_key>` → id, written in the same TransactWrite as the
catalog item with `attribute_not_exists` conditions). If absent, create the
catalog item from the overlay's definition fields only (no fatigue, no e1rm, no
personal data), `generic_status = pending`, `generic_pending = "1"`. Idempotent;
conflicts are a no-op. Batch failures report `batchItemFailures`.

**Background generic estimation (in `pl-glossary`):** a ticker (interval from env
`GLOSSARY_GENERIC_INTERVAL`, e.g. 5m) Queries GSI `generic-pending` (limit small).
For each item, call the coach with operation `glossary_generic_estimate` — prompt
carries only the exercise definition, never athlete data — get muscles (if
empty), fatigue profile, lift_transfer, text (if empty); write them to the catalog
item, `generic_status = ready`, REMOVE `generic_pending`. On failure increment
`generic_attempts`; after 3 set `failed` and remove `generic_pending`. One
replica, so no lease needed. The coach maps `glossary_generic_estimate` to the
cheap OpenRouter alias (`pl-background`, see §4), never the ChatGPT subscription.

**First personal analysis (`glossary_estimate_fatigue` for an athlete):** run the
personal estimate (athlete program meta + lift profiles, existing model mapping)
and write it to the athlete overlay. In the same request, if the catalog item is
missing or not `ready`, ensure it is `pending` (create from the effective
definition if missing) so the background job fills the generic one. Result =
both: `{personal, generic_status}`; when the generic already exists, return it
too. Same split for `glossary_estimate_muscles` / `lift_transfer` / `generate_text`:
these are definition-level, so they write to the catalog when the athlete's
exercise is in the catalog, otherwise to the overlay. `glossary_estimate_e1rm`
is personal only (overlay).

## 3. Service `pl-glossary` in Go (`src/services/glossary-go/`)

- Same k8s Service name `pl-glossary`, HTTP :8000, `POST /operations/<op>`,
  `POST /mcp`, `/healthz`, `/docs`. Contract `operations/glossary.json` keeps op
  names; result schemas extended for the new fields; `glossary_backfill_lift_transfer`
  is dropped if no caller uses it (check callers). Embedded via `go:generate`
  copies of `operations/glossary.json` and `runtime/permissions.json`.
- Auth / check order identical to analytics-export / analytics-ai (mesh model).
- AI ops use the coach execution protocol exactly as `analytics-ai/internal/execution`
  does (submit / needs_inference / resume); prompts become `text/template`
  under `internal/prompts/` from the existing `.j2` prompts.
- Valkey: keep invalidating the same glossary cache keys the backend reads
  (`cacheGet(['glossary'])` tag in the backend) — find the key format in
  `src/backend/src/**/cache*` and `runtime/valkey.py`.
- Fuzzy resolve (`rapidfuzz.token_sort_ratio` ≥ 0.92) is needed by callers that
  resolve names (`runtime/exercise_names.py`, imports, templates). Implement
  token-sort ratio in Go if an op exposes it; Python callers move to reading the
  new table via `runtime/glossary_store.py` (rewritten, §5).

## 4. Cheap background model

- LiteLLM alias `pl-background` → OpenRouter model chosen in phase A3 (verified
  through Codex → LiteLLM `/v1/responses` → OpenRouter). Added in the k8s tfvars
  `litellm_models` (operator updates `K8S_TFVARS` secret) — no defaults in tf.
- Coach: `operation_ai.glossary_generic_estimate = { provider = "litellm", model = "pl-background", effort = "low" }`
  in `COACH_TFVARS` / `terraform.tfvars.example`; register the op in the coach catalog.
- If Codex cannot drive a non-GPT model through LiteLLM reliably, the coach gets
  an OpenCode harness path for API-key providers (decided after A3).

## 5. Readers that move to the new table

- Rust `pl-analytics` `source/dynamo.rs` (`glossary#v1` on the health table) →
  Query `CATALOG` + `ATHLETE#<athlete>` on the glossary table and merge (overlay
  wins). New env `GLOSSARY_TABLE_NAME`, IAM/pod access.
- Python `runtime/glossary_store.py` → same table/merge; used by templates,
  imports, program, exercise_names. `export/export_program_history` and
  `program/export_program_markdown` read via it.
- Backend `exerciseController.ts` unchanged except types; frontend shows
  "personal" vs "generic" fatigue.
- No migration code.

## 6. Pipeline

- `build-images.yml` deploys only on `pull_request` (opened/synchronize/reopened →
  environment `stage`; closed+merged into `master` → environment `main`). No
  deploy on push. Environment branch policies (set by the operator in GitHub)
  decide which head branches may use `stage`, so a branch outside the allow list
  gets no terraform apply.
- Build the Go lambda before the AWS terraform plan.
- New image `powerlifting-glossary` (Packer, like `powerlifting-analytics-export.pkr.hcl`),
  ECR repo, matrix + rollout list; the services image excludes `glossary-go`.

## Phases

- [ ] **A1. glossary-go service** (own dir only).
- [ ] **A2. AWS: table + GSI + stream + Go lambda + IAM** (root `terraform/` +
  `src/lambda/glossary-catalog/`).
- [ ] **A3. Verify Codex → LiteLLM → OpenRouter non-GPT** (scratchpad only, report).
- [ ] **A4. Pipeline** (`.github/**`, Packer, ECR list).
- [ ] **B. Cutover:** k8s `glossary.tf` (remove from `services.tf`), coach op +
  alias, Rust/Python readers, delete Python
  `services/glossary/`, frontend fields.
- [ ] **C. Verify after pipeline (operator).**
