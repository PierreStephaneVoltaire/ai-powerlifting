# Backend DynamoDB → Fission replacement status

Goal: the powerlifting backend should be a thin router to the Fission functions in
`utils/powerlifting-app/lambda/` plus auth logic. Direct DynamoDB usage in
`backend/src/db/dynamo.ts` is being phased out.

## What was changed in this pass

- Easy-win backend modules were rewired to call existing Fission functions
  instead of touching DynamoDB directly.
- `npm run build` passes.

## Easy wins completed

| Backend file | Fission tool(s) used |
|---|---|
| `controllers/exerciseController.ts` | `exercise_get_glossary`, `exercise_upsert`, `exercise_remove`, `exercise_archive`, `exercise_unarchive`, `exercise_set_e1rm` |
| `controllers/maxController.ts` | `max_history_get`, `max_history_add`, `max_target_get`, `max_target_update` |
| `controllers/weightController.ts` | `weight_log_get`, `weight_log_add`, `weight_log_remove` |
| `controllers/dietNotesController.ts` | `health_get_diet_notes`, `health_update_diet_note`, `health_delete_diet_note` (emulated full-replacement) |
| `controllers/supplementController.ts` | `health_get_supplements`, `health_update_supplements` |
| `controllers/blockNotesController.ts` | `block_notes_get`, `block_notes_update` |
| `controllers/budgetController.ts` | `budget_get_config`, `budget_put_config`, `budget_list_items`, `budget_create_item`, `budget_update_item`, `budget_delete_item`, `budget_get_summary`, `budget_priority_timeline` |
| `controllers/settingsController.ts` | `settings_get`, `settings_update_nickname`, `settings_update_profile`, `settings_update_avatar`, `settings_update_ranking_location`, `settings_update_age_class` |
| `controllers/profilesController.ts` | `profile_get`, `profile_get_current`, `profile_search` |
| `services/userSettings.ts` | `settings_*` for read/update; only `getOrCreateSettings` still touches DynamoDB (no `settings_create` tool yet) |
| `services/masterCopy.ts` | `master_copy_seed_user` |

## Gaps / mismatches that need a Fission handler or contract change

These files still import `backend/src/db/dynamo.ts`. They are documented here so
they can be tackled next; this pass intentionally did not change them because the
existing Fission tools do not match the backend's current contract or data shape.

### 1. `controllers/programController.ts` — program / version / designer CRUD
- `listPrograms` can use `program_list`.
- `getProgram` can use `health_get_program`.
- `updateMetaField` can use `health_update_meta`.
- `updatePhases` can use `health_update_phases`.
- `forkProgram` can use `health_new_version`.
- `archiveProgram` / `unarchiveProgram` can use `program_archive` / `program_unarchive`.
- **Gap:** `batchCreateWeek`, `updatePlannedExercises`, `updateLiftProfiles` have no
  dedicated Fission tool. They can be emulated with `health_create_session` /
  `health_update_session` but the designer-specific logic should probably move
  into a single Fission function such as `program_designer_batch_week` or
  `program_update_planned_exercises`.

### 2. `controllers/sessionController.ts` + `services/sessionStore.ts`
- `createSession` → `health_create_session`.
- `deleteSession` → `health_delete_session`.
- `getSession` → `health_get_session`.
- `updateSession` / `completeSession` / `updateSessionStatus` → `health_update_session`.
- `rescheduleSession` → `health_reschedule_session`.
- `addExercise` / `removeExercise` → `health_add_exercise` / `health_remove_exercise`.
- **Gap:** `updateExerciseField` and multi-session-same-date index handling have no
  matching tool. `health_get_session` only resolves by `date`, not by `(date, index)`.
  Either the frontend stops sending `index` for same-date sessions or a new
  `health_update_exercise_field` tool is needed.

### 3. `controllers/videoController.ts` — session videos
- Relies heavily on `services/sessionStore.ts` to list/patch sessions by video.
- **Gap:** needs the session CRUD Fission tools plus a way to update video metadata
  without loading the whole session (e.g. `session_video_update_metadata`).

### 4. `controllers/competitionController.ts` — user competition library
- **Mismatch.** The backend reads/writes the separate
  `if-powerlifting-user-competitions` table (seeded from master competitions).
  The Fission `health_*_competition` tools operate on `program.competitions` inside
  `if-health`. Either the backend switches to program-embedded competitions, or
  new tools (`competition_library_list`, `competition_library_patch`,
  `competition_library_complete`) are required.

### 5. `controllers/federationsController.ts` — master/user federation library
- **Mismatch.** `listFederations` scans `if-powerlifting-user-federations` with
  `pk = operator`. `federation_list` / `federation_library_*` read from the shared
  `federations#v1` item in `if-health`. Need clarity on which table is canonical.

### 6. `controllers/goalsController.ts` — athlete goals
- **Mismatch.** Backend stores goals in the dedicated
  `if-powerlifting-goals` table. `health_get_goals` / `health_update_goals` now
  read/write `program.goals` inside `if-health`. Data migration or a dedicated
  `goals_*` toolset is needed.

### 7. `services/analysisCache.ts` + `services/blockAnalytics.ts`
- These read/write `if-powerlifting-analysis-cache` and `if-powerlifting-goals`
  directly and orchestrate cache jobs.
- **Gap:** cache orchestration should move behind `analysis_cache_*` and the
  analysis AI tools (`weekly_analysis`, `analysis_section`, `program_evaluation`,
  etc.) already exist as Fission functions, but the backend currently mixes
  direct cache management with tool invocation.

### 8. `services/userSettings.ts` — user creation on first login
- Read/update operations were moved to Fission tools.
- **Gap:** there is no `settings_create` or `settings_get_or_create` tool. The
  backend still needs to create the initial user row when Discord OAuth fires for
  the first time. A new Fission function should be added, or the auth flow needs
  to call `health_setup_initialize` first and rely on that to create the user.

## Next step

Pick one gap above and add the missing Fission handler(s) in `lambda/`, register
them in the tool registry, then remove the remaining direct DynamoDB imports.
Once every file above is migrated, `backend/src/db/dynamo.ts` can be deleted.
