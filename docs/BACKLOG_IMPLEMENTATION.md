# Backlog implementation contract

The operator's 2026-09-14 implementation plan supersedes conflicting historical
requirements. Work stays in the existing sixteen HTTP/MCP services in
`if-portals`, with the existing native Codex runtime and retained AWS stores.
No second environment, Git writes, AWS deletion, chunk upload protocol,
browser-to-storage uploads, account lifecycle features, or Postgres migration.

## Shared boundaries

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
4. Coordinator: backlog/architecture, shared types, client and UI integration,
   migrations/deployment evidence, remaining waves and integration reviews.

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
