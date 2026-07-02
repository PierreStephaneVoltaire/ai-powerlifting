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

## NEXT — Domain 2: Videos (`videoController.ts`)

**Status:** `videoController.ts` still imports `db/dynamo` and does direct
DynamoDB work itself (it's in the grep list of controllers importing dynamo).

**What needs to be done:**
1. Read `videoController.ts` + `routes/videos.ts` + the existing `video_*` Fission
   tools (if any) to map the current behaviour (list/get/create/update/delete +
   any S3 media handling for videos).
2. Create a `pl_videos` store layer (`video_store.py`) owning the DynamoDB CRUD
   against the videos table + any normalization, mirroring the budget/goals
   pattern. If videos have S3 media (like budget photos), decide whether the S3
   upload stays in the backend (binary upload boundary) or moves to Fission via
   presigned URLs.
3. Create/extend Fission functions for each video operation the backend currently
   does inline (`video_list`, `video_create`, `video_update`, `video_delete`, …)
   with `resources.yaml` per-function sizing.
4. Register the layer in `fission_layers.py`.
5. Rewrite `videoController.ts` to thin `invokeLambda` calls — remove the
   `db/dynamo` import and all direct DynamoDB logic. Keep only pk passing +
   minimal result shaping.
6. Verify the route still compiles against the same exported function signatures.

**Routing to Fission / exporting logic to Fission / making Fission represent
what the app expects:** all three apply — move dynamo CRUD to a Fission store
layer, expose operations as Fission functions, and ensure the Fission tools
return exactly the shapes the frontend expects so no backend logic is needed.
