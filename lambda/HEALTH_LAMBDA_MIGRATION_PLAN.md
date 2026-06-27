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

## Phase 0 — Focused shared layers (NO monolithic layer)

**Architecture: per-lambda self-contained packages + a few small focused layers.** No monolithic `powerlifting_core` layer. Each lambda gets its own folder with ONLY the code it needs (copied verbatim from `tools/health/`, trimmed to that tool's dependency graph). Heavyweight shared deps live in small focused layers so no lambda pays cold-start cost for code/deps it doesn't use.

**Layer assignments:**
| Layer | Contents | Used by | Size profile |
|-------|----------|---------|--------------|
| `pl-boto3` | boto3 + botocore + s3transfer | all 63 DynamoDB lambdas (Streams D,E,F,G,H,I + deterministic analytics that read DynamoDB) | ~60MB |
| `pl-pandas` | pandas + numpy | ONLY the 3 OpenPowerlifting stats lambdas (Stream B) | ~110MB |
| (no layer) | stdlib only | the 10 pure-math lambdas (Stream A) — no third-party deps at all | ~KB |

**Must NOT appear in any layer or lambda package:** `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `prompts/loader.py`, `chromadb`, any `*_ai.py` module.

### Phase 0a — `pl-boto3` layer
- [x] `utils/powerlifting-app/lambda/layers/pl-boto3/requirements.txt` (boto3, botocore, s3transfer — pinned)
- [x] `utils/powerlifting-app/lambda/layers/pl-boto3/build.sh` (pip install into `python/` for the lambda zip layout)
- [x] `utils/powerlifting-app/lambda/layers/pl-boto3/README.md`
- [ ] Terraform `aws_lambda_layer_version.pl_boto3` (compatible_runtimes = ["python3.12"])

### Phase 0b — `pl-pandas` layer
- [x] `utils/powerlifting-app/lambda/layers/pl-pandas/requirements.txt` (pandas, numpy — pinned)
- [x] `utils/powerlifting-app/lambda/layers/pl-pandas/build.sh`
- [x] `utils/powerlifting-app/lambda/layers/pl-pandas/README.md`
- [ ] Terraform `aws_lambda_layer_version.pl_pandas` (compatible_runtimes = ["python3.12"])

### Phase 0c — Shared Terraform IAM role (one execution role, scoped policies)
- [ ] `terraform/` — `aws_iam_role.lambda_exec` + inline policy for DynamoDB (`if-health`, `if-health-templates`, `if-sessions`, `if-powerlifting-analysis-cache`, `if-proposals`), S3 (`POWERLIFTING_S3_BUCKET` read for stats lambdas), CloudWatch Logs
- [ ] Terraform `for_each`-template helper for the 73 functions (Timeout: 900 each)

### Phase 0d — `tools/health/` re-export note
- [ ] Document that `tools/health/` stays AS-IS for the agent path (no re-export refactor needed — lambdas copy only what they need; the agent keeps using the original in-process modules). If a lambda's copied module would diverge, the lambda's copy wins for that lambda only.

---

## Phase 1 — Lambda handlers (one per tool, timeout = 900s each, self-contained)

Every handler lives at `utils/powerlifting-app/lambda/<tool>/` and is **self-contained**:
```
utils/powerlifting-app/lambda/<tool>/
├── handler.py          # thin wrapper: parse event → call local logic → return JSON
├── <logic>.py          # ONLY the functions this tool needs, copied verbatim from tools/health/
├── <store>.py          # ONLY the store module(s) this tool touches (if any)
├── config.py           # env-only reads for THIS tool (table names, AWS_REGION, SANDBOX_PATH)
└── requirements.txt    # ONLY this tool's direct deps (usually empty — boto3 comes from layer)
```

**The move is a LOGIC MOVE, not a rewrite.** Copy the exact function(s) from `tools/health/` that the `ROUTES` entry calls, fix intra-package imports to point at the local copies, and wrap in `handler.py`. Do not refactor, "improve", or generalize anything.

`handler.py` shape (each tool substitutes its own name + local logic call):
```python
import json
import os
from <local_logic> import <the_exact_function_the_ROUTE_calls>

def handler(event, context):
    args = event.get("args", event)
    # call the EXISTING function with the EXACT arg mapping from tools/health/tool.py ROUTES
    result = <the_exact_function_the_ROUTE_calls>(<args mapping>)
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
```

Terraform: one `aws_lambda_function` per tool, `Timeout: 900`, layer(s) attached per the Phase 0 table, the self-contained folder zipped as `source_dir`. IAM role from Phase 0c.

### Stream A — Pure math (no DynamoDB, no pandas)
- [x] `lambda/kg_to_lb/handler.py` + Terraform `aws_lambda_function.pl_kg_to_lb` (Timeout: 900)
- [x] `lambda/lb_to_kg/handler.py` + Terraform `aws_lambda_function.pl_lb_to_kg` (Timeout: 900)
- [x] `lambda/ipf_weight_classes/handler.py` + Terraform `aws_lambda_function.pl_ipf_weight_classes` (Timeout: 900)
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
