# Health Tools → Powerlifting Lambda Migration Plan

**Goal:** Move every non-AI, non-ML, non-RAG health tool from `tools/health/` into its own AWS Lambda function under `utils/powerlifting-app/lambda/`. The portal backend (`utils/powerlifting-app/backend`) will invoke these lambdas directly instead of round-tripping through the IF agent pod. The agent keeps its in-process `tools/health/` copies for OpenCode specialist runs.

**Rules**
- One Lambda per tool. No grouped handlers.
- **NO RAG, ML, or AI features move.** Anything calling an `*_ai.py` module, OpenRouter, `httpx` LLM calls, `load_system_prompt`, or the ChromaDB/health-doc RAG corpus stays in the agent.
- **Every Lambda timeout = 900 seconds (15 min)** — the AWS maximum. `Timeout: 900` in Terraform, `timeout=900` in any config. Do not use shorter values.
- The agent's in-process `tools/health/` path must remain byte-identical in behavior. Deterministic modules get extracted into a shared `powerlifting_core` Lambda Layer; `tools/health/` re-exports them so the agent path is unchanged.
- Each Lambda's `handler(event, context)` accepts `{"args": {...}}` and returns the exact JSON that the corresponding `ROUTES` entry in `tools/health/tool.py` returns today.
- Per `AGENTS.md`: never run `terraform apply`/`destroy`, never run `kubectl` mutations, never run git writes, never delete AWS resources. Terraform work is `fmt`/`validate`/`plan` only.

---

## Excluded — stay in the agent (RAG / ML / AI)

These are **NOT** migrated. They remain in `tools/health/` and the portal backend keeps calling them via `invokeToolDirect` against the IF agent pod.

- `fatigue_profile_estimate` (calls `fatigue_ai.py`)
- `correlation_analysis` (calls `correlation_ai.py`)
- `block_correlation_analysis` (calls `correlation_ai.py`)
- `muscle_group_estimate` (calls `muscle_group_ai.py`)
- `lift_profile_review` (calls `lift_profile_ai.py`)
- `lift_profile_rewrite` (calls `lift_profile_ai.py`)
- `lift_profile_rewrite_and_estimate` (calls `lift_profile_ai.py`)
- `lift_profile_estimate_stimulus` (calls `lift_profile_ai.py`)
- `program_evaluation` (calls `program_evaluation_ai.py`)
- `block_program_evaluation` (calls `program_evaluation_ai.py`)
- `multi_block_comparison_analysis` (calls `multi_block_comparison_ai.py`)
- `budget_priority_timeline` (calls `budget_timeline_ai.py`)
- `budget_advisor` (calls `budget_advisor_ai.py`)
- `glossary_generate_text` (calls `glossary_text_ai.py`)
- `glossary_estimate_fatigue` (calls `fatigue_ai.py`)
- `glossary_estimate_muscles` (calls `muscle_group_ai.py`)
- `glossary_estimate_e1rm` (calls `e1rm_backfill_ai.py`)
- `template_evaluate` (calls `template_evaluate_ai.py`)
- `import_parse_file` (calls `import_parse_ai.py`)
- `health_rag_search` (ChromaDB RAG — excluded by the no-RAG rule)

---

## Phase 0 — Shared `powerlifting_core` Lambda Layer

Extract the deterministic modules from `tools/health/` into `utils/powerlifting-app/lambda/powerlifting_core/` as a pip-style package. `tools/health/` re-exports the same names so the agent path is unchanged.

**Must NOT import:** `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `prompts/loader.py`, `chromadb`, any `*_ai.py` module.

Modules to extract:
- [ ] `powerlifting_core/__init__.py`
- [ ] `powerlifting_core/analytics.py` (from `tools/health/analytics.py`)
- [ ] `powerlifting_core/comparison.py`
- [ ] `powerlifting_core/powerlifting_stats.py`
- [ ] `powerlifting_core/training_weeks.py`
- [ ] `powerlifting_core/template_apply.py`
- [ ] `powerlifting_core/template_convert.py`
- [ ] `powerlifting_core/cache_invalidation.py`
- [ ] `powerlifting_core/export.py`
- [ ] `powerlifting_core/renderer.py`
- [ ] `powerlifting_core/core.py` (deterministic CRUD surface only — strip any `*_ai` imports/wrappers)
- [ ] `powerlifting_core/program_store.py`
- [ ] `powerlifting_core/session_store.py`
- [ ] `powerlifting_core/template_store.py`
- [ ] `powerlifting_core/glossary_store.py`
- [ ] `powerlifting_core/federation_store.py`
- [ ] `powerlifting_core/import_store.py`
- [ ] `powerlifting_core/analysis_cache.py`
- [ ] `powerlifting_core/health_types.py`
- [ ] `powerlifting_core/dispatch.py` (exposes `execute(name, args)` + `get_schemas()` for the 73 deterministic tools only)
- [ ] `powerlifting_core/config.py` (env-only reads — `AWS_REGION`, table names, `SANDBOX_PATH`; no LLM vars)
- [ ] `tools/health/` re-exports updated to import from `powerlifting_core` (agent path unchanged)
- [ ] Verify `tools/health/test_*.py` still pass against the re-exported agent path
- [ ] `powerlifting_core/requirements.txt` (boto3, pandas, numpy — NO httpx/openai)
- [ ] Terraform `aws_lambda_layer_version` `powerlifting_core` (Timeout N/A — layers have no timeout)
- [ ] Terraform `aws_lambda_layer_version` `powerlifting_pandas` (pandas/numpy for the 3 stats lambdas)

---

## Phase 1 — Lambda handlers (one per tool, timeout = 900s each)

Every handler lives at `utils/powerlifting-app/lambda/<tool>/handler.py`, imports `powerlifting_core.dispatch`, and is a thin wrapper:
```python
import json
from powerlifting_core import dispatch

def handler(event, context):
    args = event.get("args", event)
    result = dispatch.execute("<TOOL_NAME>", args)
    # dispatch.execute returns JSON-serializable; if it returns a string, pass through
    body = result if isinstance(result, (dict, list)) else {"result": result}
    return {"statusCode": 200, "body": json.dumps(body, default=str)}
```
Terraform: one `aws_lambda_function` per tool, `Timeout: 900`, shared `powerlifting_core` layer, IAM role scoped to the health DynamoDB tables. Template the 73 functions with a `for_each` over the tool list.

### Stream A — Pure math (no DynamoDB, no pandas)
- [ ] `lambda/kg_to_lb/handler.py` + Terraform `aws_lambda_function.pl_kg_to_lb` (Timeout: 900)
- [ ] `lambda/lb_to_kg/handler.py` + Terraform `aws_lambda_function.pl_lb_to_kg` (Timeout: 900)
- [ ] `lambda/ipf_weight_classes/handler.py` + Terraform `aws_lambda_function.pl_ipf_weight_classes` (Timeout: 900)
- [ ] `lambda/pct_of_max/handler.py` + Terraform `aws_lambda_function.pl_pct_of_max` (Timeout: 900)
- [ ] `lambda/calculate_attempts/handler.py` + Terraform `aws_lambda_function.pl_calculate_attempts` (Timeout: 900)
- [ ] `lambda/days_until/handler.py` + Terraform `aws_lambda_function.pl_days_until` (Timeout: 900)
- [ ] `lambda/analyze_progression/handler.py` + Terraform `aws_lambda_function.pl_analyze_progression` (Timeout: 900)
- [ ] `lambda/analyze_rpe_drift/handler.py` + Terraform `aws_lambda_function.pl_analyze_rpe_drift` (Timeout: 900)
- [ ] `lambda/estimate_1rm/handler.py` + Terraform `aws_lambda_function.pl_estimate_1rm` (Timeout: 900)
- [ ] `lambda/calculate_dots/handler.py` + Terraform `aws_lambda_function.pl_calculate_dots` (Timeout: 900)

### Stream B — OpenPowerlifting stats (pandas/numpy layer + S3 dataset warm-start)
- [ ] `lambda/powerlifting_filter_categories/handler.py` + Terraform `aws_lambda_function.pl_powerlifting_filter_categories` (Timeout: 900)
- [ ] `lambda/powerlifting_ranking_percentile/handler.py` + Terraform `aws_lambda_function.pl_powerlifting_ranking_percentile` (Timeout: 900)
- [ ] `lambda/analyze_powerlifting_stats/handler.py` + Terraform `aws_lambda_function.pl_analyze_powerlifting_stats` (Timeout: 900)
- [ ] Warm-start strategy for stats lambdas (provisioned concurrency or `pl_warm` invoke; document in handler README)

### Stream C — Deterministic analytics (DynamoDB reads + compute)
- [ ] `lambda/weekly_analysis/handler.py` + Terraform `aws_lambda_function.pl_weekly_analysis` (Timeout: 900)
- [ ] `lambda/analysis_section/handler.py` + Terraform `aws_lambda_function.pl_analysis_section` (Timeout: 900) — **guard: reject AI section keys** (`ai_correlation`, `program_evaluation`); only serve `overview`, `fatigue_readiness`, `peaking`, `workload`, `alerts`
- [ ] `lambda/regenerate_analysis/handler.py` + Terraform `aws_lambda_function.pl_regenerate_analysis` (Timeout: 900)
- [ ] `lambda/get_analysis_markdown/handler.py` + Terraform `aws_lambda_function.pl_get_analysis_markdown` (Timeout: 900)
- [ ] `lambda/export_program_history/handler.py` + Terraform `aws_lambda_function.pl_export_program_history` (Timeout: 900)
- [ ] `lambda/export_program_markdown/handler.py` + Terraform `aws_lambda_function.pl_export_program_markdown` (Timeout: 900)

### Stream D — Glossary CRUD (DynamoDB only)
- [ ] `lambda/glossary_add/handler.py` + Terraform `aws_lambda_function.pl_glossary_add` (Timeout: 900)
- [ ] `lambda/glossary_update/handler.py` + Terraform `aws_lambda_function.pl_glossary_update` (Timeout: 900)
- [ ] `lambda/glossary_set_e1rm/handler.py` + Terraform `aws_lambda_function.pl_glossary_set_e1rm` (Timeout: 900)

### Stream E — Program / Session CRUD (DynamoDB only)
- [ ] `lambda/health_get_program/handler.py` + Terraform `aws_lambda_function.pl_health_get_program` (Timeout: 900)
- [ ] `lambda/health_get_session/handler.py` + Terraform `aws_lambda_function.pl_health_get_session` (Timeout: 900)
- [ ] `lambda/health_get_sessions_range/handler.py` + Terraform `aws_lambda_function.pl_health_get_sessions_range` (Timeout: 900)
- [ ] `lambda/health_update_session/handler.py` + Terraform `aws_lambda_function.pl_health_update_session` (Timeout: 900)
- [ ] `lambda/health_new_version/handler.py` + Terraform `aws_lambda_function.pl_health_new_version` (Timeout: 900)
- [ ] `lambda/health_create_session/handler.py` + Terraform `aws_lambda_function.pl_health_create_session` (Timeout: 900)
- [ ] `lambda/health_delete_session/handler.py` + Terraform `aws_lambda_function.pl_health_delete_session` (Timeout: 900)
- [ ] `lambda/health_reschedule_session/handler.py` + Terraform `aws_lambda_function.pl_health_reschedule_session` (Timeout: 900)
- [ ] `lambda/health_add_exercise/handler.py` + Terraform `aws_lambda_function.pl_health_add_exercise` (Timeout: 900)
- [ ] `lambda/health_remove_exercise/handler.py` + Terraform `aws_lambda_function.pl_health_remove_exercise` (Timeout: 900)
- [ ] `lambda/health_setup_status/handler.py` + Terraform `aws_lambda_function.pl_health_setup_status` (Timeout: 900)
- [ ] `lambda/health_setup_initialize/handler.py` + Terraform `aws_lambda_function.pl_health_setup_initialize` (Timeout: 900)
- [ ] `lambda/health_invalidate_program_cache/handler.py` + Terraform `aws_lambda_function.pl_health_invalidate_program_cache` (Timeout: 900)

### Stream F — Competition / Meta CRUD (DynamoDB only)
- [ ] `lambda/health_get_competition/handler.py` + Terraform `aws_lambda_function.pl_health_get_competition` (Timeout: 900)
- [ ] `lambda/health_update_competition/handler.py` + Terraform `aws_lambda_function.pl_health_update_competition` (Timeout: 900)
- [ ] `lambda/health_create_competition/handler.py` + Terraform `aws_lambda_function.pl_health_create_competition` (Timeout: 900)
- [ ] `lambda/health_delete_competition/handler.py` + Terraform `aws_lambda_function.pl_health_delete_competition` (Timeout: 900)
- [ ] `lambda/health_snapshot_competition_projection/handler.py` + Terraform `aws_lambda_function.pl_health_snapshot_competition_projection` (Timeout: 900)
- [ ] `lambda/health_complete_competition/handler.py` + Terraform `aws_lambda_function.pl_health_complete_competition` (Timeout: 900)
- [ ] `lambda/health_get_meta/handler.py` + Terraform `aws_lambda_function.pl_health_get_meta` (Timeout: 900)
- [ ] `lambda/health_update_meta/handler.py` + Terraform `aws_lambda_function.pl_health_update_meta` (Timeout: 900)
- [ ] `lambda/health_get_phases/handler.py` + Terraform `aws_lambda_function.pl_health_get_phases` (Timeout: 900)
- [ ] `lambda/health_update_phases/handler.py` + Terraform `aws_lambda_function.pl_health_update_phases` (Timeout: 900)
- [ ] `lambda/health_get_current_maxes/handler.py` + Terraform `aws_lambda_function.pl_health_get_current_maxes` (Timeout: 900)
- [ ] `lambda/health_update_current_maxes/handler.py` + Terraform `aws_lambda_function.pl_health_update_current_maxes` (Timeout: 900)
- [ ] `lambda/health_get_goals/handler.py` + Terraform `aws_lambda_function.pl_health_get_goals` (Timeout: 900)
- [ ] `lambda/health_update_goals/handler.py` + Terraform `aws_lambda_function.pl_health_update_goals` (Timeout: 900)
- [ ] `lambda/health_get_federation_library/handler.py` + Terraform `aws_lambda_function.pl_health_get_federation_library` (Timeout: 900)
- [ ] `lambda/health_update_federation_library/handler.py` + Terraform `aws_lambda_function.pl_health_update_federation_library` (Timeout: 900)
- [ ] `lambda/health_get_diet_notes/handler.py` + Terraform `aws_lambda_function.pl_health_get_diet_notes` (Timeout: 900)
- [ ] `lambda/health_update_diet_note/handler.py` + Terraform `aws_lambda_function.pl_health_update_diet_note` (Timeout: 900)
- [ ] `lambda/health_delete_diet_note/handler.py` + Terraform `aws_lambda_function.pl_health_delete_diet_note` (Timeout: 900)
- [ ] `lambda/health_get_supplements/handler.py` + Terraform `aws_lambda_function.pl_health_get_supplements` (Timeout: 900)
- [ ] `lambda/health_update_supplements/handler.py` + Terraform `aws_lambda_function.pl_health_update_supplements` (Timeout: 900)

### Stream G — Import staging/apply (DynamoDB only; parse stays in agent)
- [ ] `lambda/import_apply/handler.py` + Terraform `aws_lambda_function.pl_import_apply` (Timeout: 900)
- [ ] `lambda/import_reject/handler.py` + Terraform `aws_lambda_function.pl_import_reject` (Timeout: 900)
- [ ] `lambda/import_list_pending/handler.py` + Terraform `aws_lambda_function.pl_import_list_pending` (Timeout: 900)
- [ ] `lambda/import_get_pending/handler.py` + Terraform `aws_lambda_function.pl_import_get_pending` (Timeout: 900)

### Stream H — Template CRUD (DynamoDB only; evaluate stays in agent)
- [ ] `lambda/template_list/handler.py` + Terraform `aws_lambda_function.pl_template_list` (Timeout: 900)
- [ ] `lambda/template_get/handler.py` + Terraform `aws_lambda_function.pl_template_get` (Timeout: 900)
- [ ] `lambda/template_apply/handler.py` + Terraform `aws_lambda_function.pl_template_apply` (Timeout: 900)
- [ ] `lambda/template_apply_confirm/handler.py` + Terraform `aws_lambda_function.pl_template_apply_confirm` (Timeout: 900)
- [ ] `lambda/template_copy/handler.py` + Terraform `aws_lambda_function.pl_template_copy` (Timeout: 900)
- [ ] `lambda/template_archive/handler.py` + Terraform `aws_lambda_function.pl_template_archive` (Timeout: 900)
- [ ] `lambda/template_unarchive/handler.py` + Terraform `aws_lambda_function.pl_template_unarchive` (Timeout: 900)
- [ ] `lambda/template_create_blank/handler.py` + Terraform `aws_lambda_function.pl_template_create_blank` (Timeout: 900)
- [ ] `lambda/template_create_from_block/handler.py` + Terraform `aws_lambda_function.pl_template_create_from_block` (Timeout: 900)
- [ ] `lambda/template_create_from_payload/handler.py` + Terraform `aws_lambda_function.pl_template_create_from_payload` (Timeout: 900)
- [ ] `lambda/template_update/handler.py` + Terraform `aws_lambda_function.pl_template_update` (Timeout: 900)
- [ ] `lambda/template_publish/handler.py` + Terraform `aws_lambda_function.pl_template_publish` (Timeout: 900)
- [ ] `lambda/template_unpublish/handler.py` + Terraform `aws_lambda_function.pl_template_unpublish` (Timeout: 900)

### Stream I — Program archive (DynamoDB only)
- [ ] `lambda/program_archive/handler.py` + Terraform `aws_lambda_function.pl_program_archive` (Timeout: 900)
- [ ] `lambda/program_unarchive/handler.py` + Terraform `aws_lambda_function.pl_program_unarchive` (Timeout: 900)

---

## Phase 2 — Portal backend rewiring

- [ ] `utils/powerlifting-app/backend/src/utils/lambda.ts` — `invokeLambda(functionName, args)` helper (AWS SDK `LambdaClient`/`InvokeCommand`, returns parsed JSON, matches `invokeToolDirect` return shape)
- [ ] Add env config: `POWERLIFTING_LAMBDA_REGION`, per-tool `POWERLIFTING_LAMBDA_FN_<TOOL>` (or a single prefix `POWERLIFTING_LAMBDA_PREFIX=pl-`)
- [ ] Replace deterministic `invokeToolDirect(...)` calls in backend routes/services with `invokeLambda(...)`:
  - [ ] `routes/sessions.ts`
  - [ ] `routes/competitions.ts`
  - [ ] `routes/programs.ts`
  - [ ] `routes/maxes.ts`
  - [ ] `routes/goals.ts`
  - [ ] `routes/federations.ts`
  - [ ] `routes/dietNotes.ts`
  - [ ] `routes/supplements.ts`
  - [ ] `routes/template.ts`
  - [ ] `routes/import.ts`
  - [ ] `routes/analytics.ts` (deterministic sections only; AI sections keep `invokeToolDirect`)
  - [ ] `routes/stats.ts`
  - [ ] `routes/setup.ts`
  - [ ] `routes/export.ts`
  - [ ] `routes/weight.ts`
  - [ ] `routes/budget.ts`
  - [ ] `services/analysisCache.ts`
  - [ ] `services/blockAnalytics.ts`
  - [ ] `services/sessionStore.ts`
- [ ] `routes/analytics.ts` — `analysis_section` branch: deterministic keys → lambda; `ai_correlation`/`program_evaluation` → agent (`invokeToolDirect`)
- [ ] Keep AI tools on `invokeToolDirect`: `program_evaluation`, `correlation_analysis`, `fatigue_profile_estimate`, `muscle_group_estimate`, `lift_profile_*`, `budget_*`, `glossary_generate_text`, `glossary_estimate_muscles/fatigue/e1rm`, `template_evaluate`, `import_parse_file`
- [ ] `npm run build` in `backend/` passes

---

## Phase 3 — Terraform + IAM

- [ ] `terraform/` — `aws_lambda_function` resources templated with `for_each` over the 73 tool names (Timeout: 900 each)
- [ ] IAM execution role per stream (or one shared role) scoped to: `if-health`, `if-health-templates`, `if-sessions`, `if-powerlifting-analysis-cache`, `if-proposals` (imports), S3 `POWERLIFTING_S3_BUCKET` (stats lambdas)
- [ ] `aws_lambda_layer_version` `powerlifting_core` + `powerlifting_pandas`
- [ ] API Gateway (optional, per-tool `/{tool}` mapping) OR direct `Lambda.Invoke` from backend — decide and document
- [ ] `terraform fmt` + `terraform validate` + `terraform plan` only (no `apply`)

---

## Phase 4 — Verification

- [ ] `tools/health/test_*.py` pass (agent path unchanged after re-exports)
- [ ] Per-lambda handler test: `dispatch.execute("<tool>", args)` output == lambda `handler` output (JSON-identical)
- [ ] `npm run build` in `backend/` green
- [ ] `terraform validate` green
- [ ] Document deployed function names + env vars in `utils/powerlifting-app/lambda/README.md`

---

## Parallelization guide

Streams A–I are independent after Phase 0 completes. Assign one agent per stream. Within a stream, each tool is independent and can be built/tested in parallel by the stream agent. Phase 2 (backend rewiring) and Phase 3 (Terraform) can start once the corresponding tools' handlers exist; coordinate on `lambda.ts` to avoid merge conflicts.

**Total: 73 individual lambdas** (74 deterministic tools minus `health_rag_search` which is RAG-excluded).
