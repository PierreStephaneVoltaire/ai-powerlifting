# src/services layout: one folder per service

Python domains are served by one image (`PL_DOMAIN` selects the domain) so every domain package and `runtime/` ship together. Handler strings in `operations/*.json` become `services.<domain>.<op>.handler`. Hyphenated domains map to underscore packages (`lift-profiles` -> `lift_profiles`, `weight-log` -> `weight_log`).

## Layout

```
src/services/
  analytics/ rankings/ analytics-ai/ analytics-export/   native services, untouched
  coach/ coach_discord/                                    imports and tests only
  operations/                                              contracts, unchanged
  runtime/   shared Python runtime + shared helpers + data files + tests
  <domain>/  budget calculations competition export federation glossary goals imports
             lift_profiles performance profile program sessions templates videos weight_log
             each: handlers (op folders), domain-only helpers, tests/
```

## Handler groups to domains (grouped by the operation's `domain`, not the old folder)

| Old `handlers/` folder | New home |
| --- | --- |
| budget, calculations, competition, federation, goals, imports, sessions, templates, videos, weight_log | same-named domain |
| glossary | glossary |
| lift_profiles: glossary_estimate_* , glossary_generate_text | glossary |
| lift_profiles: fatigue_profile_estimate, lift_profile_estimate_stimulus, lift_profile_suggest, muscle_group_estimate | lift_profiles |
| program: program_update_lift_profiles | lift_profiles |
| program: export_program_history | export |
| analysis_reports | export/analysis_reports |
| program (rest), health (get_diet_notes, get_supplements) | program |
| maxes | performance |
| user, authored_notes | profile |
| user/_shared/settings_normalize.py (used by runtime access) | runtime |
| user/_shared/requests_table.py | profile |
| `_*_store.py`, `common.py` group helpers | their domain |

## Top-level modules

| Module | New home |
| --- | --- |
| app, dispatch, contract, mesh, authorization, access, access_store, execution, ai, handler_context, analytics_client, analysis_version, publication, competition_access, media_access, program_access, source_access, profile_views, tag_catalog | runtime |
| authored_notes, relationships, profile_media | profile |
| permissions.json, calculation_constants.json, lift_profile_options.json, requirements.txt | runtime |

`permissions.json` stays out of `operations/` because the coach globs `operations/*.json`. Rust `include_str!` and Go `go:generate` paths point at `runtime/`.

## lib/

| Helper | New home | Reason |
| --- | --- | --- |
| countries | competition | only competition |
| lift_profile_ai | lift_profiles | only lift_profiles |
| media_notifications | videos | only videos |
| session_tool_helpers | sessions | only sessions |
| everything else (aws, block_scope, competition_entries, exercise_names, glossary_store, lift_calculations, lift_profiles, llm_log, performed_sets, program_store, program_tool_helpers, prompt_cache, prompts/, session_store, storage_scope, template_patch, template_store, valkey) | runtime | used by 2+ domains, the runtime, or coach |

## tests/

| Tests | New home |
| --- | --- |
| access, authorization_transport, aws, block_scope, competition_entries, generations, handler_context, handler_imports, media_access, native_continuation, owner_aliases, publication, scope, transport, profile_views | runtime/tests |
| analytics, export_naming, export_per_set_values, exports | export/tests |
| authored_notes, grant_core, identity_migration, identity_resolve, onboarding, onboarding_basics, profile, profile_media, relationships, tag_catalog | profile/tests |
| block_transition, handler_serialization, program, program_integrity | program/tests |
| max_history_integrity, performance | performance/tests |
| template_integrity, template_metrics, templates | templates/tests |
| federation, master_sync | federation/tests |
| video_thumbnail, videos | videos/tests |
| coach, template_chat | coach/tests |
| coach_discord | coach_discord/tests |
| calculations, budget, competition, glossary, goals, imports, lift_profiles, sessions, weight | same-named domain/tests |

Shared pytest fixtures (`block_live_aws`, `memory_valkey`) move from `tests/conftest.py` to `src/conftest.py`.
