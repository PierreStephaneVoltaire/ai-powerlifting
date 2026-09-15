# Backlog implementation contract

The operator's 2026-09-14 implementation plan supersedes conflicting historical
requirements. Work stays in the existing sixteen HTTP/MCP services in
`if-portals`, with the existing native Codex runtime and retained AWS stores.
No second environment, Git writes, AWS deletion, chunk upload protocol,
browser-to-storage uploads, account lifecycle features, or Postgres migration.

## Shared boundaries

- Guest entry has a dedicated landing page with both Discord and Authentik
  login options. About is separate. Authenticated entry retains onboarding and
  role-specific dashboard/roster routing. Read-only notices describe relevant
  Athlete editing access and do not appear on Landing, Login, Search or About.
  Verify navigation and content at 320 and 375 pixel widths; passing desktop
  checks does not establish small-screen usability.
- Identity is an authenticated Person, resolved from verified provider issuer
  and subject. The selected Athlete is a separate storage partition. Usernames,
  email and display names cannot establish identity or account linkage.
- The Profile service evaluates application permissions with PyCasbin and
  current stored grants/publication settings. Every HTTP/MCP operation has an
  explicit permission; unmapped operations fail closed. The gateway uses the
  same evaluator. Read-cached reports need read; generation needs write.
- Keep operation manifests in `services/operations/*.json`, and register new
  operations in an existing domain. Coordinator owns shared TypeScript types.
- Mutation envelopes use `expected_revision` (nonnegative integer) and
  `idempotency_key` (nonempty string). Conflict responses are HTTP 409 with
  `code: conflict`, current revision and current record where permitted.
- Block transitions use `block_transition` with `action` equal to `complete`,
  `start_next`, or `complete_and_start`; stable `block_id`, editable name,
  confirmed start maxes in kg, dates and week-start preference. Never change
  unfinished Session statuses or overwrite logged work.
- Retain Session upload route `POST /api/videos/:version/:date`. One multipart
  request carries the file; bounded backend spooling/streaming calls existing
  storage and confirmation operations. Preserve 500 MiB limit and media IDs.
- Media references remain backend `/api` URLs. Authorize GET, HEAD and Range.
  Lift slots identify lift + angle + target revision + pending media ID. Ready
  replacements publish only on a matching completion; old ready media survives
  pending/failed replacement. Demonstrations additionally require <=180 seconds.
- Author originals and shared attributed note revisions are separate records.
  Athlete attachment removal never edits author text.
- New tag/notification tables are dedicated domains; relationships retain their
  table. Additive migrations are repeatable and preserve existing ownership.

## Wave ownership

1. Identity worker: backend auth/middleware/auth/routes/auth, identity settings
   linkage, services app/dispatch/contract and new access evaluator/permission
   map, Profile access operations, identity ADR and dependencies for auth.
2. Media worker: backend video route/controller, browser Session video upload,
   video handlers/manifests and thumbnail pipeline; media-focused tests.
3. Training worker: Program/Session stores and handlers, Template apply,
   program/session/template manifests and training-focused tests. Propose shared
   types and gateway/UI wiring to coordinator.
4. Coordinator: contracts, exclusive worker ownership, backlog/architecture,
   deployment evidence and integration reviews. Luna workers perform product
   implementation, deployment and acceptance; Terra independently reviews.

Workers implement and run focused checks; fresh Terra reviews gate dependent
work and deployment. Existing uncommitted changes are preserved. Baseline live
inspection found sixteen ready service Deployments and a ready portal backend
and frontend, Authentik and Valkey; no current namespace events. This is baseline
availability evidence, not feature acceptance.

## Verification boundaries

Record local/mocked checks separately from deployed browser, Authentik, native
Codex and processing acceptance. Use isolated Person/Athlete records in existing
stores. Source operator records/media stay unchanged. Full 500 MiB public-route
acceptance waits for the Cloudflare allowance upgrade; no upload fallback.
Protected IF API/targeted Terraform changes require a concrete reviewed operator
approval. Portal service updates are already authorized by the supplied plan.

## Applied entry and mobile correction — 2026-09-15

Both login choices, the dedicated guest landing, informational-page banner
suppression and small-screen navigation/context are deployed. Gateway `87403487…`
and frontend `5bb25bdb…` are Ready; actual login dispatch, fresh Authentik login,
mobile menus and final Dashboard sizing pass. The
[scoped evidence](../../../deploy/rewrite/powerlifting-backlog/entry-mobile-correction.md)
records exact test boundaries and supersedes earlier entry-screen acceptance.

## Prior integration state — 2026-09-15 10:45 UTC

The approved release is applied in the existing environment. All sixteen domain
services, gateway and frontend are Ready with observed generations and zero
restarts. Final immutable pins, rollout/rollback manifests and independently
labelled evidence are in the
[deployment evidence](../../../deploy/rewrite/powerlifting-backlog/deployment-evidence.md).
Luna performed implementation, deployment and acceptance; Terra reviewed the
changes. Source operator records and copied media remain unchanged.

- Block complete/start-next/combined and Template append/replace/new-Block checks
  pass, including unchanged unfinished statuses and logged work, exact HTTP/MCP
  replay, revision conflicts and stable Session identities.
- Genuine Authentik onboarding, later basics/profile edits, role-specific landing,
  Athlete context, guest/search navigation and Handler details pass. Search covers
  name/handle, federation, alphabetical twenty-result pagination and privacy.
- Distinct Coach and Handler approvals race to one success and one conflict.
  Confirmed replacement, rejection, cancellation, revocation, stored competition
  expiry, independent peer reads and notification replay deduplication pass.
- Actual browser checks cover authored-note ownership, offline partitioning,
  retained drafts/edits on conflicts and revocation, delegated-cache clearing,
  revoked synchronization, same-day Session navigation, logged edits, 44px action
  targets and scroll restoration.
- Public/OIDC report generation completed through the existing native worker.
  Owner and exactly scoped read-only delegate receive the same cached result;
  generation is denied to the delegate, unknown caches return 404 and cache reads
  create no new report records. Native continuations, historical exports and
  backend spreadsheet upload/native parse/review/apply also pass.
- Ordinary Program GETs now fetch current domain state. A signed native-domain
  current-max update and restoration appear immediately at the identical portal
  URL without a cachebuster. Report caches and offline drafts are preserved.
- Backend-only uploads, authorized GET/HEAD/Range, failure/retry/confirmation,
  exact 180-second acceptance and 181-second rejection pass. Previous ready media
  survives failed replacement and max edits; successful replacement keeps the
  assigned target revision. Ready notifications deduplicate and owned removal
  and replay pass. A real concurrent run observes the older processing completion
  after the replacement is ready; it cannot displace the newer recording.
- Lift Profile node boundaries, per-set reason preservation, actual Handler/Coach
  context and signed native HTTP/MCP context pass. Deployed browser bar/unit
  interactions change numeric guidance and restore the original controls.
- The target-max response contract is repaired and deployed, with actual
  write/read/replay/restoration proof. CloudFront is disabled with completed
  invalidation; infrastructure remains in place.
- Final regression evidence: 253 service tests and 16 subtests passed; selected
  live signed HTTP/MCP checks passed 22/22 across 16 services. Manifest self-test
  and an 18-Deployment dry run pass. These are separate from actual browser,
  Authentik, native generation and processing evidence.
- Disposable task Docker build images were removed after verifying ECR publication
  and absence of Docker container references. Live k3s containerd images, rollback
  archives and AWS resources remain intact.

Full 500 MiB public-route acceptance awaits the Cloudflare request allowance
upgrade. Genuine operator access is unavailable, so positive tag moderation,
approved catalog migration and approved-tag AND/OR acceptance remain unverified.
The final evidence separates the accepted actual stale-processing race from
local CAS checks and earlier non-overlapping attempts. Earlier pending-approval,
pre-fix and old-image records are historical.
