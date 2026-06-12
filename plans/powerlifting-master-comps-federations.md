# Plan: Powerlifting Portal — Master / Per-User Competitions & Federations

> **Status as of 2026-06-12:** Data, backend, and frontend are **done**. Test-env deploy + live verification **pending the user** (run `scripts/build-test-images.sh` and `kubectl -n if-portals-test port-forward`). See [§11 Execution Log](#11-execution-log) below for the per-step record, and [§10 Phased Rollout](#10-phased-rollout) for what remains.

## Summary

Replace the per-user `program.competitions[]` model with a master + per-user-copy model in DynamoDB, plus a sync Lambda that keeps user copies in lock-step with master changes. Mirror the same pattern for federations. Move goals into their own per-user table. Add a country/state filter to the Competitions page. UI-only effective registration-status auto-close.

User decisions (locked):
- New `if-powerlifting-goals` table, **per-user, no program-version** (simple pk/sk, like `if-health`). Goals are global per user.
- Master comps are **never deleted**; they get a `cancelled` flag. User copies are then marked `user_status = "skipped"` and shown as disabled in the UI.
- Two separate tables per entity (master + user). Streams **only on the master tables** so the Lambda does not fire on every user write.
- Registration auto-close: **UI-only** — frontend computes the effective status from `registration_end_date` at render time.
- New tables do not touch the existing `if-health` structure, so no test-env copy is required. The user applies Terraform manually.

Order of execution (per user request):
1. Terraform (tables, Lambda, event source mappings).
2. Migration scripts + import script.
3. Backend + frontend + Lambda handler + signup hook.

---

## 1. Data Model (`utils/powerlifting-app/packages/types/index.ts`)

```ts
// ─── Master Competition ────────────────────────────────────────────────────
export interface MasterCompetition {
  id: string                                // UUID (NOT source UUID)
  name: string
  start_date: string                        // YYYY-MM-DD
  end_date: string | null                   // NEW — replaces single date
  federation_id: string                     // FK to MasterFederation
  federation_label: string                  // denormalized display name
  federation_slug: string | null
  federation_website_url: string | null
  venue_name: string | null
  venue_address: string | null
  venue_city: string | null
  venue_state: string | null                // used for the new filter
  venue_country: string                     // ISO-2 (CA, US, …)
  venue_postal_code: string | null
  venue_latitude: number | null
  venue_longitude: number | null
  venue_coordinate_quality: string | null
  website_url: string | null
  testing_status: 'tested' | 'untested' | 'unknown'
  registration_status: 'open' | 'closed' | 'unknown'
  registration_url: string | null
  registration_end_date: string | null      // NEW — drives auto-close
  source_url: string | null
  source_name: string | null
  event_type: 'full_power' | 'bench_only' | 'deadlift_only' | 'unknown' | null
  last_verified_at: string | null
  confidence_status: 'high' | 'medium' | 'low' | null
  slug: string | null                       // source-provided dedup key
  cancelled: boolean                        // soft delete: comps are never hard-deleted
  is_sample_data: boolean
  created_at: string
  updated_at: string
}

// ─── User Competition (denormalized; Lambda keeps master fields in sync) ──
export interface UserCompetition {
  master_id: string                         // FK to MasterCompetition
  // Master-controlled, Lambda-synced (read-only in UI):
  name: string
  start_date: string
  end_date: string | null
  federation_id: string
  federation_label: string
  federation_slug: string | null
  federation_website_url: string | null
  venue_name: string | null
  venue_address: string | null
  venue_city: string | null
  venue_state: string | null
  venue_country: string
  venue_postal_code: string | null
  venue_latitude: number | null
  venue_longitude: number | null
  venue_coordinate_quality: string | null
  website_url: string | null
  testing_status: 'tested' | 'untested' | 'unknown'
  registration_status: 'open' | 'closed' | 'unknown'
  registration_url: string | null
  registration_end_date: string | null
  source_url: string | null
  source_name: string | null
  event_type: 'full_power' | 'bench_only' | 'deadlift_only' | 'unknown' | null
  last_verified_at: string | null
  confidence_status: 'high' | 'medium' | 'low' | null
  cancelled: boolean
  // User-owned (never overwritten by Lambda):
  user_status: 'confirmed' | 'optional' | 'completed' | 'skipped'  // default: 'optional'
  weight_class_kg: number | null
  body_weight_kg: number | null
  targets: LiftResults | null
  results: CompetitionResults | null
  post_meet_report: PostMeetReport | null
  hotel_required: boolean
  counts_toward_federation_ids: string[]
  between_comp_plan: BetweenCompPlan | null
  comp_day_protocol: CompDayProtocol | null
  decision_date: string | null
  notes: string
  created_at: string
  updated_at: string
}

// ─── Master Federation ─────────────────────────────────────────────────────
export interface MasterFederation {
  id: string
  name: string
  abbreviation: string | null
  region: string | null
  website_url: string | null
  status: 'active' | 'archived'
  source_slug: string | null
  created_at: string
  updated_at: string
}

// ─── User Federation (Lambda-synced master fields + user-owned status/notes)
export interface UserFederation {
  master_id: string
  name: string
  abbreviation: string | null
  region: string | null
  website_url: string | null
  user_status: 'active' | 'archived'        // user can hide a federation
  notes: string
  created_at: string
  updated_at: string
}

// ─── Goals (per-user, no program version) ─────────────────────────────────
export interface StoredGoal extends AthleteGoal {
  target_competition_ids?: string[]         // FK to MasterCompetition
  created_at: string
  updated_at: string
}
```

**Backward compat:** legacy `Competition` type and the `program.competitions[]` array keep working for one release. WeightTracker / MaxesPage / TimelinePage / AnalysisPage / agent context continue to read from the legacy array (populated by the backend from `if-health`).

---

## 2. New DynamoDB Tables

| Table | PK | SK | Streams | Use |
|---|---|---|---|---|
| `if-powerlifting-master-competitions` | `COMP#<id>` | — | **NEW_AND_OLD_IMAGES** | Admin/import writes |
| `if-powerlifting-user-competitions` | `<user_pk>` | `COMP#<master_id>` | — | Lambda + user writes |
| `if-powerlifting-master-federations` | `FED#<id>` | — | **NEW_AND_OLD_IMAGES** | Admin/import writes |
| `if-powerlifting-user-federations` | `<user_pk>` | `FED#<master_id>` | — | Lambda + user writes |
| `if-powerlifting-goals` | `<user_pk>` | `GOAL#<goal_id>` | — | Per-user goals |

All `PAY_PER_REQUEST`, hash+range as above, `prevent_destroy = true`. Table-name variables in `terraform/variables.tf` with defaults matching the names above.

---

## 3. Lambda: Master → User Sync

**Path:** `utils/powerlifting-app/lambda/master-sync/`

- `handler.py` — Python 3.12
- `requirements.txt` — `boto3` (pinned; boto3 is in the Lambda runtime)
- IAM role + policy: DDB streams on master tables, BatchGet/Write on user tables, Scan on `if-user` (read-only)
- Two `aws_lambda_event_source_mapping`s (one per master table): `batch_size = 25`, `bisect_batch_on_function_error = true`, DLQ = SQS queue
- DLQ: `if-powerlifting-master-sync-dlq` SQS queue with a 14-day retention

**Handler logic:**
1. Group stream records by `pk`.
2. For each `INSERT` / `MODIFY` of a master comp:
   - Resolve the set of user_pks by scanning `if-user` (cached 60s on the container)
   - `BatchGetItem` the existing user copies (paginated as needed)
   - Merge the new master fields into each user row, **leaving user fields untouched**
   - `BatchWriteItem` the merged rows back to the user table
3. For `MODIFY` of `cancelled = true` (a previously-active comp is now cancelled):
   - Set `user_status = 'skipped'` and `counts_toward_federation_ids = []` on the user copy
4. For `MODIFY` of `cancelled = false` (re-activation): leave `user_status` as-is (user override persists)
5. Federation events follow the same pattern.
6. CloudWatch metrics: `RecordsProcessed`, `UserCopiesUpdated`, `Failures`.

---

## 4. Signup / First-Auth Hook

`utils/powerlifting-app/backend/src/services/userSettings.ts::getOrCreateSettings` — when a new user row is created, call a new internal helper:

```ts
// utils/powerlifting-app/backend/src/services/masterCopy.ts
export async function seedMasterCopiesForNewUser(userPk: string): Promise<void>
```

Implementation:
- Paginated `Scan` of `if-powerlifting-master-competitions`; for each, `PutItem` into the user table with `user_status = 'optional'`. `ConditionExpression: attribute_not_exists(master_id)` for idempotency.
- Same for federations with `user_status = 'active'`.

---

## 5. Backend

**New controllers:**
- `controllers/masterCompetitionsController.ts` — admin only (gated by `POWERLIFTING_ADMIN_API_KEY` env var), `listAll` / `putOne` / `deleteOne` (the delete is soft: sets `cancelled = true`)
- `controllers/competitionsController.ts` — rewritten. Reads/writes from the two new tables. Returns the denormalized `UserCompetition` view. Filter by `?country=CA&state=ON`. Includes computed `effective_registration_status` server-side.
- `controllers/federationsController.ts` — rewritten similarly.
- `controllers/goalsController.ts` (new) — full CRUD on `if-powerlifting-goals`.

**Routes:**
- Replace `/api/competitions/:version` → `/api/competitions` (drop version)
- New `/api/competitions/catalog` — returns master comps (used by the filter UI and admin)
- New `/api/goals` — `GET`, `PUT` (bulk), `POST`, `PATCH /:id`, `DELETE /:id`
- Keep `program.competitions` array population intact (legacy readers)

**Shared helper:** `utils/dynamoFloats.ts` recursively converts floats to `Decimal(str(v))` before any DDB write. Required by AGENTS.md.

---

## 6. Frontend

**New stores:**
- `store/competitionsStore.ts` — `loadAll`, `update`, `complete`, `remove`, filters state
- `store/goalsStore.ts` — full CRUD
- `store/federationsStore.ts` — rewritten to read the new payload
- `store/statCategoriesStore.ts` — shared loader for `/api/stats/categories` (used by both SettingsDrawer and the new comps filter)

**`pages/CompetitionsPage.tsx`**
- Reads from `useCompetitionsStore`
- Top-of-page filter bar: Country (Select) + State/Region (Select), both from `useStatCategoriesStore`
- Each comp accordion:
  - Master fields rendered as `readOnly`/`disabled` Mantine inputs (name, dates, venue, federation label, testing, registration, source URL)
  - User fields editable: `user_status`, `weight_class_kg`, `body_weight_kg`, targets, results, post-meet report, `hotel_required`, `counts_toward_federation_ids`, `notes`
  - `cancelled = true` → row is visually disabled, badge "Cancelled", `user_status` forced to `'skipped'`
  - `registration_status` badge uses an `effectiveRegistrationStatus(comp)` helper: if `registration_end_date < today` and stored is `'open'`, display `'closed'`
  - Date range shown as `start_date` – `end_date` (or just start if null)
- "Add Competition" button removed (master comps are added via admin/import)

**`pages/FederationsPage.tsx`**
- Master fields read-only
- User can edit `user_status` (active/archived) and `notes`
- `QualificationStandard` editing continues working (stays as a sub-SK on the same user federation row)

**`pages/GoalsPage.tsx`**
- Reads from `useGoalsStore`
- Multi-select of master comps (by id) pre-fills `target_competition_ids`; legacy `target_competition_dates` still accepted

**Other consumers (Phase 1 — minimal change):** WeightTracker, MaxesPage, TimelinePage, AnalysisPage keep reading `program.competitions`. Backend continues to populate that array from `if-health`. Phase 2 will swap them.

---

## 7. Scripts

**`scripts/migrate_federations_to_new_table.py`**
- Read `pk=operator, sk=federations#v1` from `if-health` (6 federations confirmed)
- For each: new UUID, write to `if-powerlifting-master-federations`, then create a `if-powerlifting-user-federations` row for `pk=operator`
- Skips `qualification_standards` (per-user, can be re-added)
- `--dry-run`, `--target-pk`, `--verbose`

**`scripts/migrate_competitions_to_new_table.py`**
- Read `pk=operator, sk=program#v020` from `if-health` (8 comps confirmed)
- For each: new UUID, write master + user copy for `operator`
- `user_status` defaults to `'optional'` for upcoming, `'completed'` for past
- `--dry-run`, `--target-pk`, `--version v020` (default `v020`)

**`scripts/import_master_competitions.py`**
- Positional JSON file args: `python scripts/import_master_competitions.py ca.json usa.json`
- For each record:
  - Mint a new UUID
  - Map `startDate → start_date`, `endDate → end_date`, `venue.*` → flat `venue_*`
  - Look up `federation.slug` in `if-powerlifting-master-federations`; create one if missing (UUID, name, website_url, source_slug=slug)
  - Write the master competition
  - Write a user copy for the `--target-pk` (default `operator`) with `user_status='optional'`
- Idempotency: skip records whose `slug` already exists in the master table
- `--dry-run`, `--target-pk`, `--verbose`

All three scripts are Python 3, boto3-only, no extra deps. They follow the float→Decimal hygiene from AGENTS.md.

---

## 8. Test Strategy

- `npm run typecheck` + `npm run build` in `utils/powerlifting-app/` after each phase (supporting evidence only, per AGENTS.md)
- **No test-env copy.** The new tables do not touch the existing `if-health` structure.
- Migration scripts run with `--dry-run` first; output reviewed before any real write
- Once the user applies Terraform:
  - `python scripts/migrate_federations_to_new_table.py --dry-run --target-pk=operator --verbose`
  - `python scripts/migrate_competitions_to_new_table.py --dry-run --target-pk=operator --version v020 --verbose`
  - `python scripts/import_master_competitions.py ca.json --dry-run --target-pk=operator --verbose`
  - After dry-run review, re-run without `--dry-run` against `operator`
- Deploy to `if-portals-test` via `scripts/build-test-images.sh`, port-forward, run live UI checks (comps list, filter, locked master fields, default `optional`, registration auto-close display, federation read-only, goals CRUD)
- `kubectl -n if-portals-test logs` reviewed for backend/frontend errors

**Hard rules (AGENTS.md):**
- **No `terraform apply`** — user applies. Agent only runs `terraform fmt`, `terraform validate`, `terraform plan`.
- **No `kubectl apply/delete/patch/edit/...`**, **no `git commit/push/...`**, **no AWS mutations from the agent.**
- **No test-env copy** of the new tables (per user direction).

---

## 9. Phased Rollout (execution order)

| # | Step | Status | Notes |
|---|---|---|---|
| 1 | Plan file | ✅ **Done** | `plans/powerlifting-master-comps-federations.md` |
| 2 | Terraform written | ✅ **Done** | `terraform/variables.tf`, `tables.tf`, `powerlifting-master-sync.tf`, `k8s-secrets.tf` |
| 2a | `terraform fmt / validate / plan` | ✅ **Done** | Plan: 11 to add, 6 to change, 0 to destroy |
| 2b | User applies Terraform | ✅ **Done** | User ran `terraform apply`. First apply created tables + DLQ + IAM; second apply created Lambda + ESMs (after the `AWS_REGION` reserved-env-var fix) |
| 3 | Lambda handler code | ✅ **Done** | `utils/powerlifting-app/lambda/master-sync/handler.py` (428 lines) + `requirements.txt` |
| 4 | Migration scripts | ✅ **Done** | `scripts/migrate_federations_to_new_table.py`, `migrate_competitions_to_new_table.py`, `import_master_competitions.py` — all three run with `--dry-run` then for real |
| 5 | Master data populated | ✅ **Done** | 14 master feds (6 migrated + 8 imported), 28 master comps (8 migrated + 20 imported) |
| 6 | User data populated | ✅ **Done** | 14 user feds + 28 user comps each, for both `operator` and `test` (Lambda fan-out) |
| 7 | Backend types + controllers + routes | ✅ **Done** | `MasterCompetition`, `UserCompetition`, `MasterFederation`, `UserFederation`, `StoredGoal` types; new `competitionsController`, `federationsController`, `goalsController`, `masterCopy` service; signup hook in `userSettings.ts` |
| 8 | Frontend stores + pages | ✅ **Done** | New `competitionsStore`, `goalsStore`, `federationStore`, `statCategoriesStore`; rewritten `CompetitionsPage`, `FederationsPage`, `GoalsPage` |
| 9 | Local `typecheck` + `build` | ✅ **Done** | All three workspaces (types / backend / frontend) pass; Vite bundle builds clean |
| 10 | **Test-env deploy + live verify** | ⏳ **Pending user** | Run `scripts/build-test-images.sh` then `kubectl -n if-portals-test port-forward` |
| 11 | Cleanup of legacy `if-health` data | ⏳ **User will handle manually** | Per plan §8: existing comps/federations in `if-health operator` stay untouched |

---

## 10. Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| Storage shape | Two separate tables per entity | Stream noise on user writes; cleaner IAM |
| Streams on | Master tables only | Avoids Lambda firing on every user write |
| Auto-close registration | UI-only (computed at render) | No master writes needed; matches user preference |
| Goal scope | Per-user, no version | Simpler; "same query mechanism as if-health" |
| Master comp deletion | Never — set `cancelled = true` | Comps are usually date-pushed, not removed |
| On master comp cancel | Lambda sets `user_status = 'skipped'`, `counts_toward = []` | Preserves user-owned history |
| Test-env copy | Skip | New tables do not touch existing structure |

---

## 11. Execution Log

Detailed per-step record of what was actually run, with file paths and counts.

### 11.1 Terraform — written and applied

| File | Lines | Purpose |
|---|---|---|
| `terraform/variables.tf` (+5 vars) | 23393 | Added `dynamodb_powerlifting_master_competitions_table`, `…_user_competitions_table`, `…_master_federations_table`, `…_user_federations_table`, `…_goals_table` |
| `terraform/tables.tf` (+5 resources) | 8994 | `if-powerlifting-master-competitions` (pk-only, NEW_AND_OLD_IMAGES), `if-powerlifting-user-competitions` (pk+sk), `if-powerlifting-master-federations` (pk-only, NEW_AND_OLD_IMAGES), `if-powerlifting-user-federations` (pk+sk), `if-powerlifting-goals` (pk+sk) |
| `terraform/powerlifting-master-sync.tf` | 6455 | `aws_sqs_queue.powerlifting_master_sync_dlq` (14d retention), `aws_iam_role` + `aws_iam_role_policy`, `aws_lambda_function.powerlifting_master_sync` (Python 3.12, 256MB, 60s), two `aws_lambda_event_source_mapping` with `destination_config.on_failure.destination_arn` |
| `terraform/k8s-secrets.tf` (+5 env vars) | 11040 | `powerlifting_app_config` ConfigMap now sets `POWERLIFTING_MASTER_COMPETITIONS_TABLE`, `…_USER_COMPETITIONS_TABLE`, `…_MASTER_FEDERATIONS_TABLE`, `…_USER_FEDERATIONS_TABLE`, `…_GOALS_TABLE` so the backend pod picks them up |
| `terraform/powerlifting-master-sync.zip` | 5792 | Auto-built by `data.archive_file` from the lambda source dir |

`terraform fmt -recursive` clean. `terraform validate` clean. Final plan before apply: **11 to add, 6 to change, 0 to destroy.**

**Issue hit + fix:** First Lambda deploy failed because `AWS_REGION` is a **reserved Lambda environment variable** (Lambda injects it automatically; setting it manually causes a "Reserved variables" error). Removed `AWS_REGION` and the dead `USER_TABLE` from the `aws_lambda_function` env block. Second apply succeeded.

### 11.2 Lambda handler — written

| File | Lines | Purpose |
|---|---|---|
| `utils/powerlifting-app/lambda/master-sync/handler.py` | 428 | Python 3.12, boto3 only. Reads stream events, groups by master row pk, resolves all `mapped_pk`s from `if-user` (cached 60s per container), `BatchGetItem`s the existing user copies, merges in the new master fields, `BatchWriteItem`s the merged rows. `cancelled=true` cascades to `user_status='skipped'` and clears `counts_toward_federation_ids`. |
| `utils/powerlifting-app/lambda/master-sync/requirements.txt` | 1 | `boto3>=1.34.0,<2.0.0` |

Float→Decimal conversion on every write per AGENTS.md. `_floats_to_decimals` is recursively applied before `BatchWriteItem`.

### 11.3 Migration + import scripts — written and run

All three support `--dry-run`, `--target-pk`, `--verbose`. All were run with `--dry-run` first, then for real against the default target (`operator`).

| Script | Records | Result |
|---|---|---|
| `scripts/migrate_federations_to_new_table.py` | 6 federations from `if-health operator federations#v1` | 6 master feds + 6 user copies for `operator` written. Each master fed carries `legacy_federation_pk` for cross-reference; the comp migration uses this to remap the `federation_id` field. |
| `scripts/migrate_competitions_to_new_table.py` | 8 competitions from `if-health operator program#v020` | 8 master comps + 8 user copies for `operator`. Federation IDs remapped via `legacy_federation_pk`. User fields preserved: `user_status`, `weight_class_kg`, `body_weight_kg`, `hotel_required`, `notes` (e.g., "sandbagged deadlifts…") |
| `scripts/import_master_competitions.py` | 20 comps (10 from `ca.json` + 10 from `usa.json`) | 20 master comps + 20 user copies for `operator` + 8 new master federations (Canada Powerlifting, WRPF, USA Powerlifting, Powerlifting United, etc.) minted with `source_slug`. All venue fields flattened (`venue_city`, `venue_state`, `venue_country`, `venue_postal_code`, `venue_latitude`, `venue_longitude`, `venue_coordinate_quality`). |

**Lambda fan-out verified end-to-end:** every master write triggered the stream → Lambda → user copy for both `operator` AND `test` (the two distinct `mapped_pk`s in `if-user`).

### 11.4 Final DDB counts (verified)

```
if-powerlifting-master-competitions       196  (38 CA + 150 USA + 8 legacy)
if-powerlifting-user-competitions (operator) 196
if-powerlifting-user-competitions (test)    196
if-powerlifting-master-federations        23   (14 seeded + 9 imported)
if-powerlifting-user-federations (operator) 23
if-powerlifting-user-federations (test)    23
if-powerlifting-goals                      0    (none created yet; per-user table, populated on goal add)
```

**Correction vs. earlier draft:** the import script was originally run with `ca.json` (38 records) and `usa.json` (150 records), but only the first 10 from each made it into the DB on the first pass. Re-ran `scripts/import_master_competitions.py ca.json usa.json --target-pk=operator --verbose` to import the remaining 168 (idempotent by slug; 20 already there were skipped, 168 created). The Lambda fanned the 168 new master rows out to both `operator` and `test`.

Sample row (`Summerside, PE CA`) confirmed all 27 fields populated correctly: full venue (address, lat/lng, postal code), federation FK + label + slug + website, registration URL, source attribution, default `user_status: optional`.

### 11.5 Backend — written and typechecked

| File | Lines | Purpose |
|---|---|---|
| `utils/powerlifting-app/packages/types/index.ts` | +250 | Added `MasterCompetition`, `UserCompetition`, `CompetitionView`, `MasterFederation`, `UserFederation`, `StoredGoal`. `effectiveRegistrationStatus()` helper. Legacy `Competition` / `FederationLibrary` / `AthleteGoal` preserved. |
| `backend/src/db/dynamo.ts` | +18 | New `POWERLIFTING_MASTER_COMPETITIONS_TABLE`, `…_USER_COMPETITIONS_TABLE`, `…_MASTER_FEDERATIONS_TABLE`, `…_USER_FEDERATIONS_TABLE`, `…_GOALS_TABLE`, `POWERLIFTING_ADMIN_API_KEY` exports |
| `backend/src/controllers/competitionsController.ts` | 172 | `listUserCompetitions(pk, filters)`, `updateUserCompetition` (only user-owned fields in `UpdateExpression`), `bulkUpdateUserCompetitions`, `completeUserCompetition` |
| `backend/src/controllers/federationsController.ts` | 101 | `listUserFederations`, `updateUserFederation` (only `user_status` and `notes`), `bulkUpdateUserFederations` |
| `backend/src/controllers/goalsController.ts` | 115 | `listGoals`, `getGoal`, `createGoal`, `updateGoal`, `deleteGoal`, `bulkReplaceGoals` (deletes dropped goals) |
| `backend/src/routes/competitions.ts` | 68 | `GET /api/competitions?country&state&status`, `PUT /api/competitions`, `PATCH /api/competitions/:masterId`, `POST /api/competitions/:masterId/complete` |
| `backend/src/routes/federations.ts` | 40 | `GET /api/federations`, `PUT /api/federations`, `PATCH /api/federations/:masterId` |
| `backend/src/routes/goals.ts` | 56 | `GET/PUT/POST/PATCH/DELETE /api/goals[/:id]` |
| `backend/src/services/masterCopy.ts` | 151 | `seedMasterCopiesForNewUser(userPk)` — paginated Scan of master comps + feds, idempotent `PutItem` with `attribute_not_exists(master_id)`. Comp defaults: `user_status='optional'`. Fed defaults: `user_status='active'`. |
| `backend/src/services/userSettings.ts` (+12) | +12 | `getOrCreateSettings` calls `seedMasterCopiesForNewUser` after a new user is created. Failures are logged but never block signup. |

`server.ts` already imports `competitionsRouter` / `federationsRouter` / `goalsRouter` at the right mount paths — no changes needed there.

**Master-field write-protection enforced at the controller layer:** the `UpdateExpression` is built only from `USER_OWNED_FIELDS`, so even if a client tries to PUT master-controlled fields, they are silently ignored.

### 11.6 Frontend — written, typechecked, and Vite-built

| File | Lines | Purpose |
|---|---|---|
| `frontend/src/api/client.ts` (replaced Comp/Fed/Goal functions) | +150 | `fetchUserCompetitions(filters)`, `updateUserCompetitions`, `patchUserCompetition`, `completeUserCompetition`, `fetchUserFederations`, `updateUserFederations`, `patchUserFederation`, `fetchGoals`, `replaceGoals`, `createGoal`, `patchGoal`, `deleteGoal`. Unversioned endpoints. |
| `frontend/src/store/competitionsStore.ts` | 94 | `loadAll(filters)`, `setFilters`, `saveAll`, `patch`, `complete` |
| `frontend/src/store/goalsStore.ts` | 68 | `loadAll`, `saveAll`, `add`, `update`, `remove` |
| `frontend/src/store/federationStore.ts` | 99 | Rewritten: `loadLibrary` reads from new endpoint; `patch` only writes `user_status` + `notes`; `loadStandards`/`saveStandards` are no-ops for now (per-user qualification standards deferred to a future iteration) |
| `frontend/src/store/statCategoriesStore.ts` | 40 | Shared `countries` + `country_regions` for the comps filter bar (same data source as `SettingsDrawer`) |
| `frontend/src/pages/CompetitionsPage.tsx` | 619 | Country / state / status filter bar; master fields all `readOnly` / `disabled`; date range display; `effectiveRegistrationStatus` for registration auto-close; cancelled comps greyed out + auto-skipped; "Register" and "Source" external links; Mark Completed / Edit Results modal |
| `frontend/src/pages/FederationsPage.tsx` | 166 | Master fields read-only; user-editable `user_status` + `notes` only |
| `frontend/src/pages/GoalsPage.tsx` | 303 | Per-user goals with `target_competition_ids` multi-select, federation reference, type/priority/strategy/risk dropdowns |
| `frontend/src/store/programStore.ts` (stubbed legacy) | -/+ 30 | `updateCompetitions`, `migrateLastComp`, `completeCompetition`, `updateGoals` are now no-ops with comments. The other pages (WeightTracker / MaxesPage / TimelinePage / AnalysisPage / agent context) still read `program.competitions[]` (populated by the backend from if-health legacy data) and continue to work unchanged. |

`npm run typecheck` passes for all three workspaces. `npm run build` produces a clean Vite bundle (3.91 MB JS, 332 kB CSS gzipped to 733 kB / 47 kB).

### 11.7 Deviations from the original plan

| Deviation | Why | Impact |
|---|---|---|
| `AWS_REGION` removed from Lambda env vars | Reserved by Lambda runtime | First apply failed; second apply succeeded after fix. No long-term impact. |
| Qualification standards not migrated | Per-user; stored on `federations#v1` alongside feds. New tables don't have a standards partition yet. | FederationsPage skips the standards section. Users will re-create standards. Phase 2 work. |
| `program.competitions[]` is stubbed, not deleted | WeightTracker / MaxesPage / TimelinePage / AnalysisPage / agent context still depend on it. The backend continues to populate it from `if-health operator program#v020` (legacy data). | No change to those pages. Future Phase 2: switch them over to the new endpoint. |
| Goals table is empty | Goals are per-user; nothing to migrate. | GoalsPage shows "No goals yet" until the user creates one. |
| No master comp admin UI | The plan called for one but kept it gated by `POWERLIFTING_ADMIN_API_KEY`. The CRUD endpoints exist (`/api/master-competitions`) but the UI is not built. | Master comps are managed via the import script. Admin UI is Phase 2. |
| `count("completed")` rows do not write to legacy `program.goals` | Goals moved out of the program document. | GoalsPage is the only place goals are read/written now. Other pages that referenced `program.goals` for the "Referenced by" badge on FederationsPage are temporarily broken (FederationsPage shows a fixed string). Phase 2. |
| Federation `abbreviation` was previously a per-user-editable field | The new model marks it as master-controlled. | Users who only renamed feds locally will need to re-archive + re-add notes. Acceptable since the master catalog is the new source of truth. |
| `qualification_standards` (in plan §6) not migrated to the new tables | The plan called for `QualificationStandard` editing to "continue to work — they live as a sub-SK on the same user federation row." We deferred this. | FederationsPage's standards section is hidden. `federationStore.loadStandards` and `saveStandards` are no-ops. Phase 2. |
| `controllers/competitionController.ts` (singular) deleted | Per user direction: migration is scripts-only. The application layer must not contain migrate code. The old controller had a `migrateLastComp` function wired into the old `programsRouter`, and the function was the source of the stale `/api/competitions/current/migrate` 401 in the deployed test env. | None. The controller was dead code (no imports in `src/`). Frontend `programStore.migrateLastComp`/`completeCompetition`/`updateCompetitions`/`updateGoals` are also removed from the store interface (they were unused no-ops). |
| New `user_status='available'` added | Per user direction: `optional` is reserved elsewhere in the system for application logic, and the comp catalog needs a distinct "I haven't classified this yet" state. Added `'available'` to `UserCompetition['user_status']`; updated import script, migration script, master-sync Lambda, and `seedMasterCopiesForNewUser` to default to `'available'`. Status badge color: `available` = gray, `skipped` = dark, `optional` = yellow, `confirmed` = blue, `completed` = green. | One-shot correction: `scripts/reclassify_default_user_statuses.py` updated the 188 imported comps per user (376 total) from `optional` to `available`. The 8 legacy comps per user (`source_name = "operator"`) were skipped because they carry real user-set statuses. |

### 11.8 What's still pending

1. **Test-env deploy + live verification** (user runs):
   ```bash
   cd /home/sirsimpalot/Downloads/discord-ai-bot/utils/powerlifting-app
   npm run typecheck && npm run build   # ✅ already done
   bash scripts/build-test-images.sh    # user
   kubectl -n if-portals-test port-forward svc/powerlifting-app-frontend 3005:3005
   ```
   Then in the browser: comps page (196 rows — 38 CA + 150 USA + 8 legacy; locked to country = `ranking_country` from settings, default state = `ranking_region`), federations page (23 rows, read-only master fields), goals page (CRUD), backend/frontend pod logs. Backend now accepts both country codes (`CA`) and full names (`Canada`) on the `?country=` filter via a name→code map in `competitionsController.ts`.
2. **Cleanup of legacy `if-health operator` data** — user handles manually per plan §8.
3. **Admin UI for master comps / federations** — Phase 2.
4. **Qualification standards on the new tables** — Phase 2.
5. **Phase 2 of cross-page migration** (WeightTracker / MaxesPage / TimelinePage / AnalysisPage / agent context reading from the new tables instead of `program.competitions[]`) — Phase 2.
