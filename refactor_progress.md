# Powerlifting backend → Fission refactor: progress log

## DONE — Domain 1: Goals (`goalsController.ts`)

**What was wrong:** `goalsController.ts` imported `db/dynamo` directly and did all
the DynamoDB work itself — `QueryCommand`/`PutCommand`/`DeleteCommand` against the
`if-powerlifting-goals` table, plus the goal normalization (`normalizeGoal`,
`buildStoredGoal`, `stripStoredFields`) and the full-replace reconciliation
(query existing → upsert incoming by id → delete missing). The backend should
only handle auth + pk/mapped_pk routing; all functionality belongs in Fission.

**What I did:**
- Created layer `pl_goals` → `lambda/layers/pl-goals/python/goals_store.py`
  (`GoalsStore` class) that owns the DynamoDB query/put/delete, the goal
  normalization, and the full-replace reconciliation — a faithful port of the
  controller logic.
- Created two Fission functions:
  - `goals_list` (`{ pk }` → array of athlete goals) — `lambda/goals_list/`
  - `goals_replace` (`{ pk, goals: [...] }` → full replace, returns `{success:true}`)
    — `lambda/goals_replace/`
  - Both ship `pl_boto3` + `pl_goals` layers; `resources.yaml` defines per-function
    cpu+memory requests/limits (consumed by the terraform fission loop).
- Registered `pl_goals` in `fission_layers.py` (LAYER_MODULE_DIRS + LAYER_PIP_REQS).
- Rewrote `goalsController.ts` to two thin `invokeLambda` calls — no dynamo import,
  no normalization, no reconciliation logic. The route (`routes/goals.ts`) is
  unchanged (still calls `getGoals` / `updateGoals` with `req.mapped_pk`).
- Verified: zips build, `goals_store.py` is bundled, controller imports only
  `invokeLambda` + the `AthleteGoal` type.

**Note:** `health_get_goals` (already a Fission tool) is a *different* feature —
it reads goals attached to the **current program block** from the `if-health`
program store. The new `goals_list`/`goals_replace` manage the separate per-user
athlete-goals table. Both now coexist correctly.

---

## DONE — Domain 2: Sessions (`sessionController.ts`)

**What was wrong:** `sessionController.ts` imported `db/dynamo` directly and did
all DynamoDB work itself — `resolveVersionSk` (the `program#current` pointer
GetCommand), `loadPhases` (GetCommand on the program item), then delegated to
`services/sessionStore.ts` which did the real CRUD (Query/Put/Delete/BatchWrite
against `if-sessions`, SK construction, same-day ordinals, buildItem/publicSession,
phase resolution). The backend should only handle auth + pk/mapped_pk routing.

**Key correction from review:** sessions live in their OWN table (`if-sessions`),
NOT embedded in `if-health` — the `health_*session` tools that read embedded
program sessions are LEGACY. Program version is no longer exposed by the
frontend, so the session controller should not handle versioning at all (always
current).

**What I did:**
- Extended the existing `pl_sessions` layer (`session_store.py`) — it was already
  a faithful port of `sessionStore.ts` but MISSING the program-pointer +
  phases-resolution logic that lived in the controller. Added
  `resolve_program_sk_sync()` (reads `program#current` → `ref_sk`, default
  `program#v001`) and `load_phases_sync(program_sk)` (GetItem on the program
  with `ProjectionExpression='phases'`).
- Added `session_tool_helpers.py` to the layer — a `get_store(args)` singleton
  (retargeted to caller's pk) + `resolve_context(store, program_sk)` that
  returns `(program_sk, phases)`, resolving current when no program_sk is passed.
  This keeps every tool core.py tiny.
- Created 8 Fission functions (all `pl_boto3` + `pl_sessions` layers, per-function
  resources.yaml cpu+memory):
  - `session_get`     — `{ pk, date, index? }` → session (finds by date[+index])
  - `session_create`  — `{ pk, session }` → creates for current program
  - `session_replace` — `{ pk, date, index, session }` → full overwrite
  - `session_delete`  — `{ pk, date, index }` → delete
  - `session_patch`   — `{ pk, date, index, patch }` → partial patch
  - `session_list_full` — `{ pk, program_sk? }` → full session objects w/ phases
  - `session_patch_by_date` — `{ pk, date, patch }` → patch by date (no index)
  - `session_replace_all` — `{ pk, sessions, program_sk? }` → bulk replace (fork)
  - (the pre-existing `session_list` summary tool stays as-is)
- Rewrote `sessionController.ts` to thin `invokeLambda` calls — NO dynamo import,
  NO `resolveVersionSk`, NO `loadPhases`, NO sessionStore import. Version param
  kept in signatures (prefixed `_version`) so the route compiles unchanged but is
  ignored — Fission resolves current internally. Compound ops (complete /
  add-exercise / remove-exercise / update-exercise-field) compose with a single
  `session_get` + `session_patch` (trivial field selection, not DynamoDB logic).
- Reduced `services/sessionStore.ts` to a thin Fission-calling SHIM (no dynamo)
  keeping the EXACT export signatures (`listSessions`, `createSession`,
  `patchSessionAt`, `patchSessionByDate`, `replaceProgramSessions`,
  `transformVideo`) so `videoController` + `programController` (not yet
  refactored) keep compiling unchanged. The `phases` args are now ignored
  (Fission loads phases itself).

**Verified:** 164 zips build, `session_store.py` + `session_tool_helpers.py`
bundled into the tool archives, sessionController has 0 dynamo refs, sessionStore
shim has 0 dynamo commands, 12 route calls preserved (same signatures).

## DONE — Domain 3: Program (`programController.ts`)

**What was wrong:** `programController.ts` was the biggest direct-DynamoDB
controller — `resolveVersionSk`, `getProgram` (GetCommand + `listSessions` +
`transformProgram`), `listPrograms` (QueryCommand + pointer logic),
`updateMetaField`/`updateBodyWeight`/`updatePhases`/`updateLiftProfiles`
(UpdateCommand in-place), `forkProgram` (PutCommand + `replaceProgramSessions`),
`archiveProgram`/`unarchiveProgram` (UpdateCommand + pointer repoint),
`batchCreateWeek`/`updatePlannedExercises` (compose session store). Imported
`db/dynamo` + `db/transforms` + `services/sessionStore`.

**Key correction from review:** fork is NOT used anymore, and version is not
exposed by the frontend — so `forkProgram` is removed entirely, and all
operations target the CURRENT program (Fission resolves `program#current`
internally; the `version` param is kept in signatures but ignored).

**What I did:**
- Extended `pl_program` layer (`program_store.py`) — it already had
  `get_program` (joins sessions from `if-sessions` via the session store),
  `archive`, `unarchive`, `list_programs`. Added 3 IN-PLACE update methods that
  DON'T create new versions (matching the controller's pre-refactor behavior, not
  the legacy `_write_new_version` path): `update_meta_field(field, value)` with
  the same ALLOWED_META_FIELDS allowlist, `update_phases(phases, block)` with the
  block-merge logic, `update_lift_profiles(profiles)`. All invalidate the cache.
- Added `program_tool_helpers.py` to the layer — `get_store(args)` singleton.
- Created 7 Fission functions (all `pl_boto3` + `pl_program`, per-function
  resources.yaml):
  - `program_get` — current program with sessions joined
  - `program_list_full` — all program versions (summaries)
  - `program_update_meta_field` — in-place single meta field
  - `program_update_phases` — in-place phases (optionally block-scoped)
  - `program_update_lift_profiles` — in-place lift profiles
  - `program_archive` — archive + repoint current pointer
  - `program_unarchive` — unarchive
- Rewrote `programController.ts` to thin `invokeLambda` calls — NO dynamo import,
  NO `db/transforms` import, NO `services/sessionStore` import, NO `forkProgram`,
  NO `resolveVersionSk`. `batchCreateWeek` composes `session_list_full` (conflict
  check) + `session_create` (per day). `updatePlannedExercises` composes
  `session_get` + `session_patch` (sync-exercises logic stays — it's trivial field
  selection, not DynamoDB). `updateBodyWeight` delegates to two
  `program_update_meta_field` calls (matching the route's two-call pattern).
- Removed the `forkProgram` export — the route's `POST /:version/fork` still
  references `programController.forkProgram` so it will need a route cleanup, BUT
  I kept the route file unchanged per the "don't break the route" rule. Flagging
  this: the fork route will fail at runtime (calling a removed export) — it should
  be deleted from `routes/programs.ts` since fork is dead. Left for your decision.

**Verified:** 169 zips build, `program_store.py` + `program_tool_helpers.py`
bundled, programController has 0 dynamo/transforms/sessionStore refs, 12 route
calls preserved (same signatures — except fork which is flagged above).

---

## DONE — Domain 4: Federations (`federationsController.ts`)

**What was wrong:** `federationsController.ts` did all DynamoDB itself across TWO
tables — `listFederations` (paginated Query of `POWERLIFTING_USER_FEDERATIONS_TABLE`
+ heavy `normalizeFederation`/`normalizeStandard`/`normalizeEntries`/bracket/legacy
parsing), `updateFederation` (UpdateCommand on `FED#<masterId>`), `getFederationLibrary`
(GetItem `federations#v1` from if-health), `updateFederationLibrary` (PutItem).
Imported `db/dynamo` + `@aws-sdk/lib-dynamodb`.

**Key conflation I had to untangle:** pre-existing Fission federation tools served a
DIFFERENT feature — `federation_list` reads the global `federations#v1` and
*reshapes* it for the AI agent; `federation_library_get/set` use a different SK
`federation_library#v1` with shape `{entries:[{federation_slug,...}]}` (the AI-side
per-user library, `FederationLibraryStore`/`pl-federation-library`). Those did NOT
cover the controller's 4 ops and must NOT be repurposed (would break AI tools).

**What I did:**
- Rewrote/extended `pl-federation` layer `federation_store.py` (56→356 lines): kept
  `get_library` (per-user `federations#v1`, raw shape) for `federation_list` compat,
  ported the full TS normalization to Python (`_normalize_federation`,
  `_normalize_standard`, `_normalize_entries`, `_entries_from_brackets`,
  `_entries_from_legacy_maps`, `_coerce_entry`, `_pick_age_category`/`_pick_sex`/
  `_pick_level`, age-category masters→master mapping), added `master_table` (lazy
  `POWERLIFTING_USER_FEDERATIONS_TABLE`), `list_master_federations` (paginated Query
  + normalize), `update_master_federation` (dynamic UpdateExpression), and
  `set_user_library` (PutItem `federations#v1`).
- Created 4 Fission functions (`pl_boto3` + `pl_federation`, per-function
  resources.yaml): `federation_master_list`, `federation_master_update`,
  `federation_user_library_get`, `federation_user_library_set`.
- Rewrote `federationsController.ts` to 4 thin `invokeLambda` calls (317→59 lines),
  zero dynamo. Kept `FederationUpdate` type + all 4 function signatures (routes
  unchanged; `routes/analytics.ts` also imports `getFederationLibrary` +
  `listFederations` — both preserved).

**Verified:** 173 zips (+4), `federation_store.py` bundled, controller 0 dynamo
imports, 5 exports intact, analytics.ts references preserved, Python syntax OK.

---

## DONE — Domains 5–8: Competitions, Glossary, Templates, Block-phases, Profile

**No work needed — already pure routers.** An authoritative grep across all
controllers showed that after Federations, the ONLY controller still importing
`db/dynamo` is `videoController.ts`. The following priority-list domains are
already thin `invokeLambda` routers with zero direct DynamoDB:

- **Competitions** (`competitionController.ts`) — routes to `health_get_program` /
  `health_update_competition` / `health_complete_competition` /
  `health_snapshot_competition_projection`. No dynamo import.
- **Glossary** (`exerciseController.ts`) — routes to `exercise_get_glossary` /
  `exercise_upsert` / `exercise_remove` / `exercise_archive` / `exercise_unarchive`
  / `exercise_set_e1rm` / `glossary_estimate_*`. Only retains request-validation
  (YouTube URL check). No dynamo import.
- **Templates** (`templateController.ts`) — in the routed list. No dynamo import.
- **Block phases** — handled by the Program domain (`update_phases` with block
  scoping) + `blockNotesController.ts` (routed). No dynamo import.
- **Profile** (`profilesController.ts`) — in the routed list. No dynamo import.

---

## DONE — Domain 9: Settings (`services/userSettings.ts`)

**What was wrong:** `userSettings.ts` was almost entirely routed to Fission
(`settings_get`, `settings_update_nickname/profile/ranking_location/age_class/
avatar`) BUT kept ONE direct DynamoDB touch: `getOrCreateSettings` did a
`PutCommand` to `USER_TABLE` (if-user) with `ConditionExpression:
'attribute_not_exists(pk)'` to create the initial user row on first Discord
login (followed by a race re-get + `seedMasterCopiesForNewUser`). There was even
a TODO in the file asking for a `settings_create` Fission handler. Imported
`PutCommand` + `docClient` + `USER_TABLE` from `db/dynamo`.

**What I did:**
- Created Fission function `settings_create` (inline `pl_boto3`, matching the
  existing `settings_get` inline style — the `pl-user-settings` layer exists but
  no settings tool uses it). It takes `{discord_id, discord_username,
  avatar_url}`, builds the default settings row, does a conditional `put_item`
  with `attribute_not_exists(pk)`, catches `ConditionalCheckFailedException` for
  the race, re-gets by pk on race, and returns `{settings, created}`. Ports
  `_sanitize_username` / `_normalize_settings` from `settings_get`.
- Rewrote `getOrCreateSettings` in `userSettings.ts` to call `settings_get` first
  (already did), then `invokeLambda('settings_create', ...)` when absent; seeds
  master copies only when `created` is true. Removed `PutCommand` /
  `docClient` / `USER_TABLE` imports.

**Verified:** `userSettings.ts` has 0 dynamo/aws-sdk refs, 174 zips (+1),
`settings_create.zip` bundles `core.py`, Python syntax OK, all 3 consumers
(`settingsController.ts`, `authController.ts`, `middleware/auth.ts`) still import
from `userSettings` unchanged (signatures preserved).

---

## NEXT — Domain 10: Analytics (`services/analysisCache.ts` + `services/blockAnalytics.ts`)

**Status:** These two services still import `db/dynamo` + `@aws-sdk/lib-dynamodb`
(`BatchWriteCommand`, `DeleteCommand`, `GetCommand`, `PutCommand`, `QueryCommand`,
`UpdateCommand`) against `POWERLIFTING_GOALS_TABLE`. They back the analysis/
block-analytics features (`routes/analytics.ts` is huge).

**User note:** For the analytics/video domains the user said video is the LAST
priority and "I'm getting rid of the cache" — so `analysisCache.ts` may be
largely DELETED rather than ported. Needs a read to confirm whether the cache is
still consumed anywhere or can simply be removed, vs `blockAnalytics.ts` which
is real compute that must move to Fission.

**What needs to be done:**
1. Read `analysisCache.ts` + `blockAnalytics.ts` + who consumes them
   (`routes/analytics.ts`, the AI `analysis_section`/`get_analysis_markdown`/
   `regenerate_analysis` tools). Determine if the cache is removable wholesale.
2. Port the real DynamoDB logic (block analytics compute) into a Fission layer
   (`pl_analytics` or extend an existing one) + functions; delete the cache if
   it's being dropped.
3. Rewrite consumers so no `db/dynamo` import remains.

---

## PENDING — Domain 11: Video (`videoController.ts`) [user's LAST priority]

**Status:** `videoController.ts` imports `db/dynamo` AND `services/sessionStore`.
Manages video metadata stored as an array on session items in `if-sessions` +
S3 uploads.

**User direction:** keep the actual S3 upload in the backend (binary I/O, not
DynamoDB logic), move the session-video-array PATCH to Fission, and "get rid of
the cache."

**What needs to be done:**
1. Read `videoController.ts` + `routes/videos.ts` end-to-end.
2. Move session-video-array read/patch to Fission (extend `pl_sessions` or new
   `video_*` functions); keep S3 `PutObject` in the backend.
3. Rewrite `videoController.ts` — remove `db/dynamo` import; keep S3 client only.
