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

## NEXT — Domain 4: Videos (`videoController.ts`)

**Status:** `videoController.ts` imports `db/dynamo` AND `services/sessionStore`
(`listSessions`, `patchSessionByDate`, `transformVideo`). It manages video
metadata stored INSIDE session items (videos are an array on each session) +
S3 uploads for the video files themselves.

**What needs to be done:**
1. Read `videoController.ts` + `routes/videos.ts` end-to-end to map the video
   operations (list/get/create/update/delete + S3 upload + thumbnail handling).
2. Videos are stored as an array on session items in `if-sessions`, so video
   ops compose session reads + patches. The session fission tools
   (`session_get`, `session_patch`) already exist — decide whether video ops
   should be their own fission functions (cleaner, the backend stays a pure
   router) OR compose the session tools from the backend (simpler but the
   backend retains video-specific merge logic). Recommend: own fission functions
   so ALL logic moves out of the backend.
3. S3 uploads: videos upload binary to S3. Decide whether the S3 `PutObject`
   stays in the backend (binary upload boundary — multer already handles the
   multipart in the route) or moves to Fission (would need the binary passed
   through, which is awkward over the fission HTTP path). Likely: S3 upload
   stays in backend (it's I/O, not DynamoDB logic), but the session-video-array
   PATCH moves to Fission.
4. Create `pl_videos` layer or extend `pl_sessions` with video-array helpers;
   create `video_*` fission functions for the metadata CRUD.
5. Rewrite `videoController.ts` — remove `db/dynamo` import; for S3 uploads keep
   the S3 client but delegate the session-video-array update to Fission.
6. Verify `routes/videos.ts` still compiles against the same signatures.

**Also pending (services with direct dynamo, not yet addressed):**
- `services/userSettings.ts` — mapped_pk lookup (auth-adjacent, may stay in
  backend as it's part of the auth/middleware path — needs a decision)
- `services/analysisCache.ts` — analysis cache table read/write
- `services/blockAnalytics.ts` — block analytics
- `services/masterCopy.ts` — master competition/federation table scans + batch
  writes
- `controllers/federationsController.ts` — per-user federation library
