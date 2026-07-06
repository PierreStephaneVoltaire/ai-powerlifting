# Lambda Domain Grouping & Pod Migration

172 Fission nano-functions evaluated as a domain aggregation exercise.
Groupings are derived from shared layer dependencies (`resources.yaml`
`layers:`) and conceptual boundaries — not arbitrary prefixes. Goal is
~14 multi-operation pods behind a small router, with schemas combined at
the parent Terraform level to generate the MCP discovery doc.

## Domain Table (14 domains → 14 pods)

| # | Domain / Pod | Functions | Core Layers | R/W Character |
|---|--------------|-----------|-------------|---------------|
| 1 | Training Program | `program_get`, `program_list`, `program_list_full`, `program_archive`, `program_unarchive`, `program_update_meta_field`, `program_update_phases`, `program_update_lift_profiles`, `block_notes_get/update`, `diet_notes_get/update`, `supplement_phases_get/update`, `export_program_history`, `export_program_markdown`, `health_new_version`, `health_setup_initialize`, `health_setup_status`, `health_invalidate_program_cache` | `pl_program` | Read-heavy, writes are structured updates |
| 2 | Sessions | `session_create/delete/get/list/list_full/patch/patch_by_date/replace/replace_all`, `health_create/get/delete/reschedule/update_session`, `health_add/remove_exercise`, `health_get_sessions_range` | `pl_sessions` (+ `pl_program` for health_*) | Mixed R/W — writes always follow a read |
| 3 | Competition | `health_create/get/update/delete_competition`, `health_complete_competition`, `health_snapshot_competition_projection`, `calculate_attempts` | `pl_program` + `pl_sessions` | Write follows read (snapshot → complete) |
| 4 | Maxes & Targets | `health_get/update_current_maxes`, `max_history_add/get`, `max_target_get/update` | `pl_boto3` | Read then write |
| 5 | Glossary / Exercise Library | `glossary_add/update/list_terms/set_e1rm`, `exercise_upsert/archive/unarchive/remove/search/get_glossary/set_e1rm` | `pl_glossary` | Read-heavy catalog |
| 6 | Templates | `template_create_blank/from_block/from_payload`, `template_get/list/update/copy/archive/unarchive/publish/unpublish`, `template_apply/apply_confirm`, `template_evaluate` | `pl_templates` (+ `pl_program` for apply/evaluate) | Read-heavy, occasional writes |
| 7 | Analysis | `weekly_analysis`, `analysis_section`, `analyze_progression`, `analyze_rpe_drift`, `analyze_powerlifting_stats`, `correlation_analysis`, `block_correlation_analysis`, `multi_block_comparison_analysis`, `program_evaluation`, `regenerate_analysis`, `powerlifting_ranking_percentile`, `powerlifting_filter_categories` | `pl_program` + `pl_sessions` + `pl_pandas` + `pl_ai` | Almost entirely read/compute-heavy |
| 8 | Budget | `budget_create/delete/update/list_item`, `budget_get/put_config`, `budget_get_summary`, `budget_advisor`, `budget_priority_timeline` | `pl_budget` (+ `pl_ai` for advisor) | Mixed R/W |
| 9 | Federation | `federation_list`, `federation_master_list/update`, `federation_user_library_get/set`, `federation_library_get/set`, `health_get/update_federation_library` | `pl_federation` | Read-heavy reference data |
| 10 | User / Settings / Profile | `settings_create/get`, `settings_update_*` (age_class, avatar, nickname, profile, ranking_location), `profile_get/get_current/search` | `pl_boto3` / `pl_user-settings` | Read then write |
| 11 | Goals | `goals_list`, `goals_replace`, `health_get/update_goals` | `pl_goals` | Read then write |
| 12 | Weight Log | `weight_add/remove_entry`, `weight_log_add/remove/get` | `pl_boto3` | Read then write, low volume |
| 13 | Import Pipeline | `import_list/list_pending/get_pending/parse_file/apply/reject` | `pl_imports` (+ `pl_program` for apply, `pl_ai` for parse) | Write follows read (parse → review → apply) |
| 14 | Lift Profile AI | `lift_profile_estimate_stimulus/review/rewrite/rewrite_and_estimate`, `fatigue_profile_estimate`, `muscle_group_estimate`, `glossary_estimate_e1rm/fatigue/muscles`, `glossary_generate_text` | `pl_ai` + `pl_program` | Pure inference, read-only |

### Left alone (not part of the pod migration)

- **Authorizer & Registry**: `pl_authorizer`, `tool_registry`, `master-sync`, `master_copy_seed_user`
- **Pure Calculators**: `calculate_dots`, `estimate_1rm`, `kg_to_lb`, `lb_to_kg`, `pct_of_max`, `days_until`, `ipf_weight_classes` — stateless, no layers

### Removed

- **Analysis Cache** (`analysis_cache_*`, `get_analysis_markdown`): no longer used. Delete handlers and `pl_analysis_cache` layer during migration.

## Note: Writes Always Follow Reads

The key architectural property: **within every domain, writes always
follow some kind of read.** Session create follows a program read.
Competition complete follows a snapshot read. Budget update follows a
summary read. Glossary upsert follows a search or get. Template apply
follows a template get + program get. Import apply follows a parse +
review read.

Co-locating read and write handlers in the same pod means the pod is
already warm from the read when the write arrives — the cold-start
penalty is paid once per conversation flow, not once per operation. This
is the primary argument for fewer multi-operation pods over many
single-operation pods.
## Migration TODO

One domain at a time. For each domain: write the TODO → plan the move →
implement (move existing `handler.py` to a domain-specific module, add a
`router.py` that dispatches by operation name with logging + input
pass-through) → cross off the TODO → compact/handoff → next domain.

The expected code change per function is minimal: the existing
`handler.py` logic moves to a named function inside a domain module
(e.g. `handlers/program_get.py`), and a new `router.py` at the pod root
maps `operation` → handler function. No rewrite of business logic.

After all 14 pods are migrated, go to the parent folder to update the
MCP schema generation so `tool_registry` reads the combined per-pod
schemas instead of one schema per nano-function.

### Domain 1 — Training Program ✅

- [x] Move `program_*`, `block_notes_*`, `diet_notes_*`,
      `supplement_phases_*`, `export_program_*`, `health_new_version`,
      `health_setup_*`, `health_invalidate_program_cache` handlers into
      `pod_training_program/` (handlers/ keeps each tool folder intact)
- [x] Add `handler.py` router dispatching by `event["function"]` param
- [x] Combined `resources.yaml` with 20 operations, layers: pl_boto3, pl_program, pl_sessions, pl_templates
- [x] Verify build passes (`npm run build`)

### Domain 2 — Sessions ✅

- [x] 17 handlers into `pod_sessions/` (session_*, health_*_session, health_add/remove_exercise, health_get_sessions_range)
- [x] `handler.py` router, layers: pl_boto3, pl_program, pl_sessions
- [x] Build passes

### Domain 3 — Competition ✅

- [x] 7 handlers into `pod_competition/` (health_*_competition, calculate_attempts, health_snapshot_competition_projection)
- [x] `handler.py` router, layers: pl_boto3, pl_program, pl_sessions
- [x] Build passes

### Domain 4 — Maxes & Targets ✅

- [x] 6 handlers into `pod_maxes/` (health_*_current_maxes, max_history_*, max_target_*)
- [x] `handler.py` router, layers: pl_boto3, pl_program, pl_sessions
- [x] Build passes

### Domain 5 — Glossary / Exercise Library ✅

- [x] 11 handlers into `pod_glossary/` (glossary_*, exercise_*)
- [x] `handler.py` router, layers: pl_boto3, pl_glossary
- [x] Build passes

### Domain 6 — Templates ✅

- [x] 14 handlers into `pod_templates/` (all template_*)
- [x] `handler.py` router, layers: pl_ai, pl_boto3, pl_glossary, pl_program, pl_templates
- [x] Build passes

### Domain 7 — Analysis ✅

- [x] 13 handlers into `pod_analysis/` (weekly_analysis, analysis_section, analyze_*, correlation_*, block_correlation_*, multi_block_*, program_evaluation, regenerate_analysis, powerlifting_*)
- [x] `handler.py` router, layers: pl_ai, pl_analysis_cache, pl_boto3, pl_glossary, pl_pandas, pl_program, pl_sessions
- [x] Build passes

### Domain 8 — Budget ✅

- [x] 9 handlers into `pod_budget/` (all budget_*)
- [x] `handler.py` router, layers: pl_ai, pl_boto3, pl_budget, pl_program
- [x] Build passes

### Domain 9 — Federation ✅

- [x] 9 handlers into `pod_federation/` (federation_*, health_*_federation_library)
- [x] `handler.py` router, layers: pl_boto3, pl_federation, pl_federation_library, pl_program, pl_sessions
- [x] Build passes

### Domain 10 — User / Settings / Profile ✅

- [x] 10 handlers into `pod_user/` (settings_*, profile_*)
- [x] `handler.py` router, layers: pl_boto3
- [x] Build passes

### Domain 11 — Goals ✅

- [x] 4 handlers into `pod_goals/` (goals_*, health_*_goals)
- [x] `handler.py` router, layers: pl_boto3, pl_goals, pl_program, pl_sessions
- [x] Build passes

### Domain 12 — Weight Log ✅

- [x] 6 handlers into `pod_weight/` (weight_*, weight_log_*)
- [x] `handler.py` router, layers: pl_boto3
- [x] Build passes

### Domain 13 — Import Pipeline ✅

- [x] 6 handlers into `pod_import/` (all import_*)
- [x] `handler.py` router, layers: pl_ai, pl_boto3, pl_imports, pl_program, pl_templates
- [x] Build passes

### Domain 14 — Lift Profile AI ✅

- [x] 10 handlers into `pod_lift_profile_ai/` (lift_profile_*, fatigue_profile_estimate, muscle_group_estimate, glossary_estimate_*, glossary_generate_text)
- [x] `handler.py` router, layers: pl_ai, pl_boto3, pl_program
- [x] Build passes

### Cleanup — Remove Analysis Cache

- [ ] Delete `analysis_cache_*` and `get_analysis_markdown` handlers
- [ ] Delete `pl_analysis_cache` layer
- [ ] Remove references from any `resources.yaml` that still list it
- [ ] Verify build passes

### Final — Parent MCP Schema Update

- [ ] Update `tool_registry` (or parent Terraform) to read combined
      per-pod schemas instead of one schema per nano-function
- [ ] Verify MCP discovery doc lists 14 pods with multi-operation
      endpoints
- [ ] Verify build passes