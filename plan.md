# IF Sessions Migration Plan

## Goal

Move health training sessions into a dedicated DynamoDB table named `if-sessions` so the bloated `if-health` program objects no longer need to be loaded or rewritten for normal session reads and writes.

This is copy-first. Do not delete `sessions` from `if-health`. The embedded sessions remain the fallback and source of truth until the health tools and portal have been tested against `if-sessions` and the app is stable.

## Current Additive Migration

- Terraform creates `if-sessions` with `pk` and `sk`, on-demand billing, and `prevent_destroy`.
- `scripts/migrate_sessions_to_if_sessions.py` copies embedded sessions from `if-health` into one item per session.
- The migration resolves `if-health` `program#current` by default and copies only that referenced version.
- `--version program#vNNN` can be used for an explicit version. `--version all` exists only for deliberate audit/backfill runs, not normal migration.
- Target keys support multiple sessions on the same day:
  `session#<program_sk>#<YYYY-MM-DD>#<same_day_ordinal>#<session_id>`.
- Copied items preserve the existing session object and add metadata for lookup and migration safety:
  `entity_type`, `session_id`, `source_table`, `program_sk`, `program_version`, `source_index`, `same_day_ordinal`, `block`, `week_number`, `status`, `phase`, `phase_name`, `phase_ref`, `migrated_at`, and `updated_at`.
- The script is idempotent by default and skips existing target items. Use `--replace` only when intentionally refreshing copied session records.
- `planned_exercises` is copied from the source session only. Ad hoc sessions that do not have planned work remain empty.

## Health Tools Cutover

- Add a Python session store helper alongside the existing health program store.
- Resolve `program#current` from `if-health`, then query `if-sessions` by `pk` and `begins_with(sk, session#<program_sk>#...)`.
- Keep program metadata, phases, goals, competitions, diet notes, supplements, maxes, templates, glossary, and federation data in `if-health`.
- Change session read tools first:
  `health_get_session`, `health_get_sessions_range`, session countdown/planning reads, and analytics inputs should hydrate sessions from `if-sessions`.
- Keep response shapes unchanged by returning normal session objects with resolved `phase` and `phase_name`.
- Support date/index compatibility by sorting sessions by `(date, same_day_ordinal, source_index)` and selecting the requested date/index pair.
- For writes, dual-write during the stability window:
  update the copied item in `if-sessions` and continue updating `if-health.sessions[]`.
- Do not remove embedded sessions from `if-health` in tool code.

## Portal Cutover

- Add a TypeScript session store module in the powerlifting backend using `IF_SESSIONS_TABLE_NAME`.
- In `getProgram`, load the program shell from `if-health`, then replace `program.sessions` with sessions queried from `if-sessions` for the resolved program SK.
- Keep the frontend `Program` and `Session` types unchanged so the portal does not need a major object restructure.
- Update session routes to use the session store for reads and writes, while dual-writing back to the embedded `if-health.sessions[]` array during testing.
- Keep existing route contracts such as `/api/sessions/:version/:date/:index` by mapping date/index to the sorted copied sessions.
- Update designer planned-session operations and video metadata updates to dual-write so planned sessions, logged sessions, and attached videos stay consistent.

## Verification

- Run the migration with `--dry-run` and confirm selected source session count.
- Run against the real target table without `--replace`; verify copied plus skipped counts.
- Compare source embedded sessions from the `program#current` referenced version to copied session items, ignoring added migration metadata.
- Confirm multiple sessions on the same date receive unique SKs and stable `same_day_ordinal` values.
- Test portal pages that load sessions, designer planned sessions, completed session logging, video upload/delete, and analytics.
- Test health tools that read a single session, a date range, planned sessions, countdown, and analytics.

## Rollback

- Disable `IF_SESSIONS_TABLE_NAME` usage or feature-flag the session store back to embedded `if-health.sessions[]`.
- Leave `if-sessions` data in place for inspection. No rollback step should delete sessions from either table.
