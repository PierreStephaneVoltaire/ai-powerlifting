# UX regressions plan

## 1. Block-scoped notes and nutrition

Root cause: `services/lib/block_scope.py:102-116` returns an existing
`block_id` before considering a record date, treats undated supplements as
active without a durable stamp, and falls back to the most recent completed
block for supplement phases. The TypeScript mirrors at
`backend/src/utils/blockScope.ts:76-92` and `frontend/src/utils/blockScope.ts:76-92`
have the same precedence. `scope_entries` also uses stamp-only matching for
sessions. The live `if-health` `program#current` pointer resolves to
`program#v023-c2c5b4cb64804831b1255a574837ae8d`, whose completed block starts
2026-02-15 and whose active block starts 2026-10-06. Its dated diet and block
notes are unstamped, while generic supplements and supplement phases are also
unstamped, so the fallback rules cannot represent the date-based ownership
consistently. `git log -p`/`git log -S` identifies the stamp-first and
supplement fallback behavior in the block-scope/backfill changes around
`615733a`.

Fix: make a usable record date authoritative over an old stamp, derive
supplement phase dates from `program_start` plus `start_week` when needed, and
use the same resolver for all scoped lists and notes in Python, backend, and
frontend. Stamp newly created records with the active block and extend the
backfill to report and optionally correct both missing and incorrect stamps.
The script remains dry-run by default and is not run with `--apply`.

Verification: add Python and TypeScript resolver coverage for dated notes,
nutrition, phases, and stale stamps; inspect the dry-run output shape without
writing live data; run the full service tests and workspace builds.

## 2. Block-scoped budget

Root cause: `services/handlers/budget/_budget_store.py:306-311` scopes budget
items against a synthetic program containing only the active ID, so dates and
real block ranges are unavailable. The backend budget controller and routes
(`backend/src/controllers/budgetController.ts:47-101`,
`backend/src/routes/budget.ts:47-86`) do not carry a selected block, and the
frontend store/API (`frontend/src/store/budgetStore.ts:23-58`,
`frontend/src/api/client.ts:1187-1259`) always reads and writes the active
view. Existing item normalization preserves a stamp but new/updated paths do
not consistently resolve it by item date.

Fix: load the real current Program for service filtering, make date resolution
the fallback for budget items, accept `block_id` through backend routes and
domain calls, and make the frontend budget store/page pass the selected block
when reading, creating, updating, and summarizing. New items are stamped with
the active block.

Verification: add service tests proving dated budget items resolve to the
correct block and new items carry the active stamp; build backend and frontend
workspaces.

## 3. Shared read-only athlete profile

Root cause: `frontend/src/pages/ProfilesPage.tsx:192-380` defines a separate
`PublicProfilePage`, and `frontend/src/App.tsx:19,87` routes search results to
it instead of `ProfilePage`. The duplicate page has a different layout and
does not render the lifting profile. The history around the public-profile
addition was inspected with `git log -p`/`git log -S`.

Fix: move target-athlete loading into the existing profile page, render one
profile layout for self and target athletes, and use a read-only flag to hide
or disable editing. Delete the duplicate page and route search results to the
shared page.

Verification: typecheck/build the frontend and retain the existing profile
tests while checking the route and read-only controls in the rendered code.

## 4. Single login entry point

Root cause: login controls are independently rendered by page content, the
navigation, and settings dialog components. Their handlers duplicate the
authentication entry point.

Fix: remove content and nav login controls and keep the settings-dialog login
component/handler as the only unauthenticated entry point.

Verification: search the frontend for unauthenticated login buttons and build
the frontend.

## 5. Independent analysis sections

Root cause: `frontend/src/pages/AnalysisPage.tsx:426-528` starts section
polling only after the manifest and queue requests resolve. A failed manifest
therefore prevents all sections from starting. The manifest route in
`backend/src/routes/analysis.ts:358` also aggregates every section with
`Promise.all`.

Fix: start each section request/poll independently, keep per-section loading
and error state, make manifest/queue best-effort metadata, and use settled
aggregation in the backend so one section cannot reject the whole response.

Verification: add/update analysis tests for independent section failure and
run frontend/backend tests and builds.

## 6. Per-set session editing

Root cause: `frontend/src/components/sessions/SessionDrawer.tsx:296-395`
renders exercise-level reps, weight, and RPE, while
`updateSetsWithResize:852-884` resizes only status/reason arrays. The
`Exercise` type in `packages/types/index.ts:321-336` has no per-set value
model, and planned exercise synchronization in
`backend/src/controllers/programController.ts:126-140` reconstructs exercises
without one. The session store only preserves set IDs in
`services/lib/session_store.py:391-396`. The regression history was checked
with `git log -p`/`git log -S` around the session-card changes.

Fix: add a backward-compatible per-set data shape for reps, weight, RPE, and
video association; render and edit it inside one exercise card; resize it by
preserving existing indexes; and preserve it through planned-session sync and
service persistence. Keep legacy aggregate fields synchronized for existing
consumers.

Verification: add frontend/service tests for heterogeneous sets and resize
preservation, then run all relevant tests and builds.

## 7. Competition regions and ranking dataset

Root cause: `frontend/src/pages/CompetitionsPage.tsx:159-204` sends the saved
country directly as a key, while the dataset category keys are case-sensitive;
the default `CANADA` therefore misses the dataset's country key and yields no
regions. The analysis dataset loaders in
`services/handlers/analysis/powerlifting_filter_categories/core.py:28-59`
expect `POWERLIFTING_S3_BUCKET` and otherwise search the pod-local directory.
The live `pl-competition` logs show health checks but no application error;
its deployment environment lacks the dataset bucket. Read-only S3 inspection
found the actual bucket `powerlifting-data-2b0f699b` and keys under
`datasets/openpowerlifting-...csv`, configured by root Terraform.

Fix: canonicalize the selected country against loaded dataset categories,
reload regions when the canonical key changes, make ranking/filter loaders use
the S3 dataset path, and inject the configured bucket into powerlifting
workload deployments. Add a loader test using a fake S3 client.

Verification: run the new dataset-loading test, build the relevant workspaces,
and report the live log/S3 evidence without changing the cluster.

## 8. Other profile exercises

Root cause: the profile lift/video selector only exposes all, squat, bench, and
deadlift in `frontend/src/pages/ProfilePage.tsx:48-55`.

Fix: add an Other tab and a dependent exercise dropdown populated from the
athlete's non-big-three exercises, preserving the same selector in the shared
read-only profile.

Verification: frontend build and selector-focused type/test coverage.

## 9. Profile federation and weight classes

Root cause: `frontend/src/pages/ProfilePage.tsx` only edits display/bio and age
class; it does not expose the program federation or weight class fields. Its
summary combines federation and practicing federation without de-duplication,
which produces `CPU + WRPF - 83KG - CPU`.

Fix: add profile controls backed by the existing metadata update API for one
main federation and up to two weight classes, validate the two-value limit,
and construct the summary from unique federation labels.

Verification: add/profile-test the update payload and summary formatting, then
run frontend/backend tests and builds.

## 10. Terraform imports

Root cause: root `terraform/imports-powerlifting.tf` contains 38 import blocks,
which conflicts with the operator's preferred explicit adoption workflow.

Fix: remove that file, write all 38 exact `terraform import '<address>' '<id>'`
commands to `scripts/import_powerlifting_workloads.sh`, and update root ADR
0003 to document command-based adoption.

Verification: count the generated commands, run root `terraform fmt -check`
and `terraform validate`, and do not execute any import or Terraform state
command.
