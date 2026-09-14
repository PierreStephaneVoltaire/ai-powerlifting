# Powerlifting features backlog

Current specification: operator implementation plan of 2026-09-14. This replaces
obsolete Fission, second-environment, identity-choice, self-approved-tag and
write-only-expiry requirements. Historical deployment records remain historical.
See [implementation contracts](docs/BACKLOG_IMPLEMENTATION.md).

## Delivery and evidence

Use the existing sixteen typed HTTP/MCP services in `if-portals`, existing
DynamoDB/S3 stores, Authentik, Valkey and native Codex continuations. No duplicate
environment, second Codex host, Git writes, AWS deletion, Postgres migration or
laptop deployment. Protected IF API changes require a reviewed targeted scope.

The evidence columns are independent: code alone is not verification or
production deployment. Existing screens/handlers do not establish acceptance of
the requirements below. Local/mocked checks and deployed checks are separate.

| Feature | Implementation | Verified | Deployed |
| --- | --- | --- | --- |
| FEAT-2.1 Form videos | In progress: media foundation | Pending | Pending |
| FEAT-2.2 Failure nodes | Pending | Pending | Pending |
| FEAT-3.1 Athlete basics | Existing partial flow; corrections pending | Pending | Pending |
| FEAT-3.2 Profile creation | Existing partial flow; corrections pending | Pending | Pending |
| FEAT-3.3 Multiple roles | Existing partial flow; corrections pending | Pending | Pending |
| FEAT-4.1 Identity | In progress | Pending | Pending |
| FEAT-4.2 Application permissions | In progress | Pending | Pending |
| FEAT-5.1 Guest navigation | Pending acceptance | Pending | Pending |
| FEAT-5.2 Athlete navigation | Pending acceptance | Pending | Pending |
| FEAT-5.3 Coach navigation | Pending | Pending | Pending |
| FEAT-5.4 Handler navigation | Pending | Pending | Pending |
| FEAT-6.1 Public search | Existing partial search; corrections pending | Pending | Pending |
| FEAT-6.2 Granted private search | Pending | Pending | Pending |
| FEAT-6.3 Athlete context | Pending | Pending | Pending |
| FEAT-6.4 Handler details | Pending | Pending | Pending |
| FEAT-7.1 Relationship requests | Pending | Pending | Pending |
| FEAT-7.2 Decisions/history | Pending | Pending | Pending |
| FEAT-7.3 Grant expiry | Existing partial grants; corrections pending | Pending | Pending |
| FEAT-7.4 Single Coach/Handler | Pending | Pending | Pending |
| FEAT-8.1 Profile tags | Existing partial tags; corrections pending | Pending | Pending |
| FEAT-8.2 Global catalog | Pending | Pending | Pending |
| Block lifecycle | In progress | Pending | Pending |
| Session/set integrity | In progress | Pending | Pending |
| Offline editing and authored notes | Pending | Pending | Pending |
| Backend upload and media access | In progress | Pending | Pending |

## Cross-cutting acceptance

Every view has loading, empty, error/retry and success states. Interactive targets
are accessible, keyboard reachable and labelled; primary actions meet 44px target
size. Canonical weights are kg and displays respect kg/lb preference.

Persons may hold Athlete, Coach and Handler roles. Active role and selected
Athlete are separate; selecting a role grants no access. Only an Athlete manages
grants on their records. Programs, Sessions and Attempts remain Athlete-owned
and editable by the Athlete, with attribution for delegated changes.

Private Coach/Handler note originals and attributed shared revisions are separate.
Athletes can remove attachments, not edit somebody else's words. Authors can
explicitly update attachments while authorized; editing an original cannot
silently rewrite attached history. Revocation does not erase historical notes.

Every operation rechecks current permissions; gateway and HTTP/MCP service
boundaries use the Profile service's PyCasbin evaluator. Authenticate the Person
separately from the selected Athlete. Reject forged identities, arbitrary username
selectors and untrusted internal headers. Use a complete operation-permission map;
cached report reads need read, generation needs write. Permission failures are
consistent errors, not unexplained 500 responses.

Profiles default private. Public baseline fields are display name, avatar,
federations and approved tags. An Athlete explicitly publishes additional domains.
Apply publication on the server to profiles/search, training/reports, exports and
media. Never publish identity records, grants, notifications or author originals.
Revocation/expiry removes that grant's permissions; independent peer/public reads
can remain. Cached URLs and responses cannot bypass current access.

Durable deduplicated in-app notifications cover relationship events and video
readiness. No Discord notifications. Account export, sign-out-everywhere and
account closure are excluded. Existing logout and training/report exports remain.

## Epic 2 — Lift profiles

### FEAT-2.1 — Three optional form videos per competition lift

Front, side and diagonal slots each accept one recording using the existing
thumbnail/transcode pipeline. Missing recordings never block training. Show
empty/upload progress/processing/ready/failed with retry and clear angle guidance.
Require confirmation for replacement. Preserve the old ready video until the new
one succeeds. Match processing completion to the exact pending media ID and target
revision; stale results cannot replace newer recordings. Do not delete AWS objects
as part of this implementation; provide any required cleanup command to operator.

Preserve accepted Session-video formats and the 500 MiB allowance. Form videos
additionally have a three-minute maximum. All files go to an existing backend
endpoint in one ordinary request, streamed or spooled with bounded memory. The
backend transfers bytes to storage and confirms. Existing upload endpoints,
identifiers, storage operations and processing stay. Browser receives no storage
upload URL and performs no S3 upload. No chunk protocol, resumable upload API or
browser-direct fallback. Interrupted requests retry the file; retries cannot
attach duplicates or confirm incomplete storage objects. Already backend-mediated
avatar, budget-photo and spreadsheet uploads remain.

Serve media through authorized `/api` GET, HEAD and Range. Close unauthenticated
CloudFront access by configuration and invalidation without deleting infrastructure.
Full 500 MiB public-route acceptance waits for the Cloudflare allowance upgrade.

Red-plate guidance is client-side and advisory, using configurable bar weight
(default 20 kg), 25 kg red plates and the best-known current max:
`plates_per_side = floor((max_kg - bar_kg) / 50)`. Below two plates per side use
the empty bar; otherwise use one red plate per side fewer. For a 20 kg bar,
130 kg -> 70 kg, 230 kg -> 170 kg, 50 kg -> empty bar. Display kg/lb correctly.
Changed maxes update guidance without invalidating recordings.

### FEAT-2.2 — Failure nodes

Up to ten free-text nodes per lift, trimmed/deduplicated and <=160 characters
each. Add/edit/remove with a useful empty state. Store on existing Lift Profiles;
keep distinct from per-set failure reasons. Permitted Coach/Handler views and
native Specialist context include them. Nodes are optional and never block training.

## Epic 3 — Onboarding

### FEAT-3.1 — Athlete basics

Fix the HTTP-method mismatch and Discord-only identity check. Resume the first
incomplete step. Athlete basics require positive bodyweight and best-known current
1RMs (identified estimates allowed), sex for competition calculations, valid country
and subdivision. Store kg, seed dated max history and allow later editing. Personal
training requires the Athlete role and completed basics; Coach-only/Handler-only
Persons do profile onboarding without inventing Athlete maxes.

### FEAT-3.2 — Profile creation

Require a display name, allow optional multiple federations and default private.
Keep a stable handle distinct from display name and retain avatars. Allow later
editing of basics/federations/publication. Public/private changes do not silently
revoke explicit grants. Expose only permitted fields, including to guests.

### FEAT-3.3 — Multiple roles

One Person may hold all three roles. Role selection only changes active context;
it does not create grants. Collect only missing onboarding fields when adding a
role. Land Athletes on their dashboard, Coaches on their roster and Handlers on
their competition-day roster. Preserve the guest/demo route.

## Epic 4 — Identity and permissions

### FEAT-4.1 — Authentik identity

Retain the deployed Authentik provider. Replace manual OAuth with Passport and
openid-client, using existing Valkey for server-side sessions. Preserve existing
Person/Athlete mappings including operator. Link verified issuer/provider subjects,
never names/email alone. Graceful login failure/session expiry preserves drafts.
Retain logout. Distinguish Authentik internal RBAC from application permissions in
ADR-0002; do not provision another identity provider.

### FEAT-4.2 — Granular application access

One Profile-service PyCasbin evaluator handles gateway and all HTTP/MCP operations.
Coach defaults broadly cover training. Handler defaults cover competition-day
writes and read-only training context. Athletes may explicitly add domains.
Navigation and direct routes follow effective permission, including report read
versus generate. Only Athletes administer their grants; peer read grants are
separate from Coach/Handler relations. Current grants are checked on every action.

## Epic 5 — Navigation

### FEAT-5.1 — Guest navigation

Preserve demo presentation with Search, About and role/sign-in entry points.
Browsing a public profile shows a Go back banner that restores the prior context.

### FEAT-5.2 — Athlete navigation

Existing training navigation plus Search and role switching in settings. Dashboard
is the Athlete landing page. Keep training unavailable until Athlete basics exist.

### FEAT-5.3 — Coach navigation

Coach roster is the landing page. Provide an Athlete switcher and obvious persistent
context banner. Athlete tools follow effective permissions. Own training requires
switching to an onboarded Athlete context. Preserve prior context on return.

### FEAT-5.4 — Handler navigation

Competition-day roster and details show permitted training context, current Block
phase, next tied competition and Attempt update information. Empty/missing data is
intentional. Hide unavailable navigation and guard direct routes. Seven-day
post-competition window follows current stored competition dates.

## Epic 6 — Search and context

### FEAT-6.1 — Public search

Search public Athlete/Coach profiles; match display name and handle. Federation
filters and currently approved tag AND/OR filters combine with text. Order
alphabetically and return twenty-result cursor pages. Empty/loading/error states
and public-field filtering apply server-side. Hidden/private profiles disappear
unless an independent current grant allows viewing.

### FEAT-6.2 — Granted private search

Authenticated search additionally includes profiles the Person has grants to read.
Favorites are private and grant no access. Peer read requests go to the Athlete.
Search actions and cards respect current publication and grants.

### FEAT-6.3 — Athlete context

Separate acting Person, active role and selected Athlete. All requests/caches/drafts
stay with their original Person/Athlete. Switcher/banner identify the selected
Athlete and restore previous context reliably. Guard routes alongside navigation.

### FEAT-6.4 — Handler details

Include permitted profile/basics, failure nodes/form videos, current Block phase,
canonical estimated maxes, tied competitions, Attempts and attributed notes.
Attempt weights use competition units. Scope competitions to the relationship and
retain seven-day post-competition access; remove unauthorized writes immediately
when current grants expire/revoke. Preserve drafts and explain access changes.

## Epic 7 — Relationships and inbox

### FEAT-7.1 — Requests and favorites

Support coach/handler requests in both directions and independent peer read grants.
Requests to work with somebody's Coach/Handler go directly to that Person; the
requesting Athlete selects competitions and permissions. Prevent self-targets and
duplicate pending requests. Show sent/received lists and cancellation. Favorites
are immediate, private, silent and confer no access.

### FEAT-7.2 — Decisions and history

Approval/rejection/cancellation are idempotent and race-safe. Display who, requested
scope, tied competitions and timestamps. Preserve history. Durable deduplicated
in-app notifications tell participants about decisions, replacement and revocation.
Only the Athlete authorizes grants; a Coach's acceptance uses the Athlete's already
chosen request scope. One grants/relationships surface supports revocation.

### FEAT-7.3 — Coach/Handler expiry

Require stored tied Competition Entries. Expiry is the latest tied competition
date plus seven days; no untied sixty-day fallback. Evaluate current dates/grants
on every operation. Expired/revoked grants lose all their permissions; independent
peer grants or public visibility may still provide reads. No extra scheduled job.

### FEAT-7.4 — One active Coach and Handler

Enforce one active Coach and one active Handler per Athlete transactionally across
competitions. Replacement explicitly confirms the currently active relationship;
racing approvals cannot create two. Replaced grants lose their permissions and
participants are notified. Preserve Athlete records and historical attribution.
Reuse the relationship table with queryable inbox/roster indexes.

## Epic 8 — Global tags

### FEAT-8.1 — Profile selections

Athletes select approved vocabulary or request names for manual operator approval.
Normalize/deduplicate names; <=30 characters per tag and <=20 tags per profile.
Show pending state. Ignore browser approval fields and legacy self-approval flags.
Pills/search always check current catalog approval. Preserve associations but hide
unapproved names. Personal selections remain in existing profile settings.

### FEAT-8.2 — Catalog and moderation

Dedicated global tag catalog table with deduplicated pending requests. Only the
operator approves vocabulary; Athletes cannot approve it themselves. A separate
notification table stores inbox items. Migrations are additive and repeatable.

## Training Block lifecycle and integrity

Add stable Block IDs and editable names preserving labels/historical windows.
Provide Complete Block, Start next Block and combined flow, starting from a
Template or Program designer. Warn about unfinished Sessions and archive their
actual statuses; never silently complete/move them. Require expected Program
revision and idempotency key; retries create exactly one archive and next Block.

Stage the entire new Program version before publishing. Retain historical
Sessions, Phases, notes, start maxes and week metadata. Honor Template targets
new Block/append/replace incomplete, preserving logged work and independent
Competition Entries. Reset next-Block week numbering and capture dates, week-start
preference and confirmed start maxes. Update analytics fingerprints/references
without double-counting history. Use stable Session/set identities, retain logged
set data during edits, fix same-day navigation, accessible targets and scroll return.

## Offline editing

IndexedDB caches, drafts and pending mutations are partitioned by Person/Athlete.
Use stable IDs, revisions and idempotency keys. Reauthorize each synchronization;
apply unchanged-base edits automatically and show local/server differences on
conflict. Never overwrite Session logs, Attempts or author notes silently. Failed
sync retains drafts. Clear delegated caches when expiry/revocation is observed.
Uploads, generation, relationship approval and publication remain online-only,
while unsent form state is preserved.

## Verification and rollout record

- 2026-09-14 baseline: `kubectl get deployments,pods,services`, Profile describe,
  Profile/portal logs, namespace events and AWS DynamoDB table listing inspected.
  All sixteen services and portal frontend/backend, Authentik and Valkey ready.
  No current namespace events. This establishes availability only.
- Implementation underway in three exclusive Luna assignments: identity/access,
  minimal backend upload/media, and Block/training integrity. Fresh Terra review
  must resolve specification/security/data/integration findings before deployment.
- Required gates: focused checks, typed HTTP/MCP contracts, workspace typechecks,
  sequential required builds and review. Then existing-environment isolated-record
  acceptance; copied operator source data/media remain unchanged.
- Pending deployed acceptance: authenticated browser onboarding/context, requests
  and racing replacements, tag moderation, note ownership, offline conflicts;
  backend-only upload network evidence, retry/incomplete/duplicate/stale processing;
  HTTP/MCP forged/cross-Athlete/revoked access; public filtering and cached-media
  denial; reports/cache/deduplication, historical exports, import review/apply and
  bounded native Codex canaries.
- Full-size upload acceptance is pending the Cloudflare request allowance upgrade.
  Record image digests and compatible rollback before each deployment. Prune only
  disposable local build images after publication. No feature deployment is claimed
  by this baseline record.
