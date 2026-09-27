# Powerlifting features backlog

Current specification: operator implementation plan of 2026-09-14. This replaces
obsolete Fission, second-environment, identity-choice, self-approved-tag and
write-only-expiry requirements. Historical deployment records remain historical.
See [implementation contracts](docs/BACKLOG_IMPLEMENTATION.md).

## Profile setup corrections — 2026-09-15

Profile creation and later editing must offer federation options from the existing
master federation catalog, including for a Person whose personal library is empty.
No library population/import is a prerequisite. Preserve canonical federation
identifiers and existing selections. This reported FEAT-3.2 regression is corrected;
earlier profile-edit acceptance did not establish empty-library dropdown behavior.
Remove the manual "Identify any estimated 1RMs" prompt and
checkboxes from onboarding and later basics editing. Estimated 1RMs derive from
logged training through the existing calculation path; do not invent estimates
for a Person with no data or rewrite historical estimate metadata. This latest
operator direction supersedes the earlier manual estimate-identification UI.
Luna owns implementation and rollout; Terra reviews source and deployed checks
in the existing environment.

The operator also requires removal of the redundant top Athlete-context strip;
use existing navigation and normal Back behavior instead. Back from another
Athlete must restore the previous context. Archived Blocks must not display the
generic active label "Current". Production audit found all 453 unique Sessions
intact under v020: 407 have completed status and 46 remain planned, spanning May
2023 through August 2026. The pointer incorrectly selected empty v021. A reviewed,
conditional pointer-only repair restored v020, retaining allocation version 21
and both Program records. Independent hashes confirm every Session and both
Programs are unchanged. There are 41 retained video references across ten
Sessions and 196 Competition Entries. Normal operator browser verification is
still unavailable. See [recovery evidence](../../deploy/rewrite/powerlifting-backlog/production-visibility-recovery.json).
Navigation and label changes must not rewrite training records.

The latest UI correction requires distinct Athlete, Coach and Handler views
selected after login; membership in multiple roles must not combine their screens.
Profile, privacy, relationship/roster management and inbox belong in a dedicated
Settings page. Page/display preferences stay in the existing page-settings drawer.
Athlete profiles do not contain Coach rosters. Tags use selected pills and a plus
modal for approved choices or pending requests, without duplicate entry controls.
Competition loading must follow the current Person/Athlete context and reject
late responses from earlier contexts. These corrections are implemented, deployed
and accepted by Terra within the explicit evidence limits below.

Deployment checkpoint, 2026-09-16: frontend `b9d2ac18…` generation 14, Federation
service `97de3419…` generation 12 and analytics reports `2f9ea229…` in deployment
generation 22 are Ready. All 18 portal Deployments are Ready; gateway/login and
protected IF runtimes remain unchanged. Normal Authentik checks pass for Settings
at 320/375 pixels, mobile navigation, separate Coach selection/roster, pending tags,
Competition rendering and routed analytics. A Coach with an empty personal library
sees all 23 master Federation options in the live profile form. Archived labels
are corrected in the actual reports sidecar; its compiled hash matches review.
Workspace builds/typechecks and focused Federation (5), Block-index (2), Template
(8) and ProgramStore transition (14) checks pass, including empty-next-Block
preservation of external Sessions. Mocked context/tag checks remain separately
identified. Operator browser/video playback remains unverified; storage integrity
is established by the recovery evidence. See [scoped release](../../deploy/rewrite/powerlifting-backlog/profile-ui-release.json)
and [final review](../../deploy/rewrite/powerlifting-backlog/profile-ui-terra-review.md).

## Discord login correction — 2026-09-15

The operator reported an invalid redirect URI. Live inspection confirmed that
the Discord button changed the callback to
`https://auth.nolift.training/source/oauth/callback/discord/`, whereas the
existing gateway config uses `https://dev.nolift.training/api/auth/discord/callback`.
The earlier authorization-dispatch check did not establish a usable Discord login.

Luna restored direct Discord login through maintained Passport OAuth2 alongside
Authentik; Terra accepted source and deployed checks. Gateway `b688e943…` is Ready
at generation 31. Four real-strategy tests and workspace typecheck/build pass.
An independent browser observes the original Discord client/callback without an
invalid-redirect message before consent; fabricated state is rejected. Fresh
Authentik login completes and `/api/auth/me` returns 200. The deployed compiled
auth module matches reviewed source. Full live Discord identity completion
remains unverified because Discord consent was unavailable.
See [correction evidence](../../deploy/rewrite/powerlifting-backlog/discord-login-correction.md).

## Prior login, landing and small-screen correction — 2026-09-15

The operator reported that the guest entry experience did not meet the intended
design. A dedicated landing page must show both Discord and Authentik login
options; About remains a separate informational page. Read-only notices belong
on relevant Athlete editing views, not Landing, Login, Search or About. Navigation
and content must remain usable at iPhone SE widths, including 320 and 375 pixels.

The earlier correction was implemented and deployed by Luna workers and passed
its scoped Terra review; its Discord acceptance is superseded by the repair above.
Gateway `87403487…` and frontend `5bb25bdb…` are Ready. Actual Discord authorization
dispatch, fresh Authentik login, public landing/navigation, banner scope, compact
context and More navigation pass. Deployed Dashboard width is 320/320 and 375/375
pixels after the grid fix. Workspace builds/typechecks, three Passport tests and
39 local mocked browser assertions pass; mocked and deployed evidence remain
separate. The earlier guest Search/About checks did not establish this correction.
See [scoped evidence](../../deploy/rewrite/powerlifting-backlog/entry-mobile-correction.md)
for exact viewports, image pins and limits.

## Delivery and evidence

Use the existing sixteen typed HTTP/MCP services in `if-portals`, existing
DynamoDB/S3 stores, Authentik, Valkey and native Codex continuations. No duplicate
environment, second Codex host, Git writes, AWS deletion, Postgres migration or
laptop deployment. Protected IF API changes require a reviewed targeted scope.

The evidence columns are independent: code alone is not verification or
production deployment. Existing screens/handlers do not establish acceptance of
the requirements below. Local/mocked checks and deployed checks are separate.

Current rollout, 2026-09-15: the operator explicitly approved apply and test.
The API/foundation, relationship indexes, retention updates and media changes
have been applied. After a reviewed OIDC transport/proxy correction, the gateway,
all sixteen service candidates and the frontend candidate are deployed and
Ready. Authenticated feature checks and their remaining limits are recorded
individually below; readiness alone does not establish feature acceptance. See the current
[deployment evidence](../../deploy/rewrite/powerlifting-backlog/deployment-evidence.md).
Earlier dated statements that approval or deployment is pending are historical.
The Cloudflare allowance upgrade remains pending, so the full 500 MiB test has
not run.

| Feature | Implementation | Verified | Deployed |
| --- | --- | --- | --- |
| FEAT-2.1 Form videos | Backend upload and revisioned lift-slot processing implemented | Actual 180s ready / 181s failure, retry, notification dedup, removal/replay and successful replacement pass; native-domain max changes appear at the same portal URL and preserve recording; actual stale-completion race and deployed bar/unit guidance pass; 500 MiB awaits Cloudflare | Media, gateway credentials and Lambda fixes applied |
| FEAT-2.2 Failure nodes | Implemented in Lift Profiles and permitted context | Live trim/dedup, ten-node acceptance, 11-node rejection and 160/161-character boundaries pass; per-set reasons preserved; exact nodes appear in Handler/Coach and native HTTP/MCP context; revoked Coach denied | Applied |
| FEAT-3.1 Athlete basics | Method/auth fixes, dated estimated 1RMs and settings editor implemented | Genuine onboarding, staged incomplete-basics status, dated kg maxes/estimate flags, later basics edits and Coach-only training denial pass; exhaustive UI matrix not claimed | Applied |
| FEAT-3.2 Profile creation | Resume/edit and explicit publication domains implemented | Actual profile/federation edits and restoration, browser profile save/restore and publication GET/update/replay/restore pass | Applied |
| FEAT-3.3 Multiple roles | Role/context separation and role-specific onboarding implemented | Multiple roles, Coach-only and Handler-only normal onboarding pass; role/context restoration passes | Applied |
| FEAT-4.1 Identity | Passport/openid-client, Valkey sessions and verified subject mapping implemented | Genuine Authentik login passes; forged identity and mismatched OAuth state rejected | Applied; preserved by gateway follow-ups |
| FEAT-4.2 Application permissions | Shared Profile evaluator and operation map implemented | Private/public HTTP/MCP boundaries, grants, expiry and revocation pass; all 221 operations mapped; central Profile update closes delegated cached Block 200/404 with generation 403 | All sixteen services applied |
| FEAT-5.1 Guest navigation | Demo/Search/About and context restoration implemented | Real guest Search/About, public profile and Go Back restoration pass | Frontend `a7aad69…` |
| FEAT-5.2 Athlete navigation | Dashboard, training guards and role switching implemented | Actual dashboard landing, role/context, same-day Session navigation and scroll pass | Frontend `a7aad69…` |
| FEAT-5.3 Coach navigation | Roster landing and effective-permission navigation implemented | Real Coach-only onboarding, browser roster landing, selected-Athlete access and profile editor save/restore pass | Applied |
| FEAT-5.4 Handler navigation | Competition roster and permission-aware navigation implemented | Handler-only normal onboarding, roster landing and Athlete details pass | Applied |
| FEAT-6.1 Public search | Approved tags, federation, role/name and twenty-result cursor implemented | Name/handle, federation, alphabetical 20+1 pagination and privacy pass; approved-tag AND/OR awaits operator access | Applied |
| FEAT-6.2 Granted private search | Current grants and field filtering implemented | Granted reads, favorite isolation and revoked denial pass | Applied |
| FEAT-6.3 Athlete context | Banner/switcher, guards and partitioned drafts implemented | Context restoration, delegated-cache removal, retained drafts/edits, revoked sync blocking and remaining public reads pass | Frontend `a7aad69…` |
| FEAT-6.4 Handler details | Permitted profile, phase, maxes, tied Attempts and notes implemented | Actual Handler details include phase, maxes, tied competition, Attempts, notes and stored seven-day expiry | Applied |
| FEAT-7.1 Relationship requests | Requests, cancellation, favorites and peer grants implemented | Request/replay/cancel/history/favorite checks pass | Applied with query indexes |
| FEAT-7.2 Decisions/history | Approval, rejection, replacement, revocation and history implemented | Approval/replay/replacement/revocation, actual rejection/cancel and rejection-replay notification dedup pass | Applied |
| FEAT-7.3 Grant expiry | Stored competition expiry and current-grant checks implemented | Expired/revoked access denied; stored date plus seven days verified | Applied |
| FEAT-7.4 Single Coach/Handler | Transactional slot and confirmed replacement implemented | Distinct Coach and Handler approvals race 200/409; active-slot counts, confirmed replacement, old-Coach denial and independent peer read pass; created grants cleaned up | Applied |
| FEAT-8.1 Profile tags | Global approval enforced; personal selections retained | Normalization/dedup and self-approval denial pass; positive approved pills/filters await operator access | Applied |
| FEAT-8.2 Global catalog | Pending catalog, operator decisions and additive storage implemented | Genuine operator approval unavailable; full catalog migration acceptance incomplete | Dedicated table and handlers applied |
| Block lifecycle | Stable identities, staged publication and complete/start-next/combined flows implemented | Sixteen transition checks and Template append/replace/new-Block preservation pass; exact HTTP/MCP new-Block replay creates no duplicate; changed payload rejected | Program/Templates `da1aca5…` |
| Session/set integrity | Stable identities, logged-data preservation and duplicate/ambiguous-ID guards implemented | Typed 409/no-write, unique historical lookup, actual same-day navigation, stable exercise IDs, logged edits, 44px actions and scroll pass | Shared-store fixes applied; frontend `a7aad69…` |
| Offline editing and authored notes | Partitioned queue/conflicts and private/shared note revisions implemented | Corrected browser queue checks, actual authorship, revocation/sync blocking and Attempt modal 409 with retained typed edit pass | Frontend `a7aad69…` and services applied |
| Backend upload and media access | Existing multipart route, bounded transfer, idempotent confirmation and authorized media implemented | Real backend-only network/pipeline/retry/HEAD/Range/auth checks and concurrent stale-completion preservation pass; 500 MiB awaits Cloudflare | Gateway/services/Lambda/CloudFront changes applied |

Evidence checkpoint: 2026-09-15 10:45 UTC. Applied records deployment; the
verification column records actual coverage and limits. Final local service suite:
**253 tests and 16 subtests passed**. Final live signed HTTP/MCP harness:
**16/16 services, 22/22 checks**. Actual public native report generation, owner and
exactly scoped delegate cache reuse, generation denial, max read/replay/restore,
180/181-second processing, successful replacement and ordinary Program freshness
pass separately. Fresh Terra accepted the final source/evidence review, including
actual Handler/Coach/native Lift Profile context and deployed guidance controls.
The remaining external tests are the Cloudflare 500 MiB upload and operator tag
approval/catalog/approved-tag AND/OR acceptance. Exact pins and sanitized evidence are in the
[release evidence](../../deploy/rewrite/powerlifting-backlog/deployment-evidence.md).

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
1RMs, sex for competition calculations, valid country
and subdivision. Store kg, seed dated max history and allow later editing. Personal
training requires the Athlete role and completed basics; Coach-only/Handler-only
Persons do profile onboarding without inventing Athlete maxes.
Do not ask the Person to classify entered 1RMs as estimated. The existing canonical
calculation derives Estimated 1RMs automatically from logged training; a Person
with no training data has no generated estimate. Preserve historical metadata.

### FEAT-3.2 — Profile creation

Require a display name, allow optional multiple federations and default private.
Populate federation choices from the existing master federation catalog even
before the Person's own library has any records.
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
Browser Back from a public profile restores the prior context; do not add a
redundant top banner.

### FEAT-5.2 — Athlete navigation

Existing training navigation plus Search and role switching in settings. Dashboard
is the Athlete landing page. Keep training unavailable until Athlete basics exist.

### FEAT-5.3 — Coach navigation

Coach roster is the landing page. Keep Athlete context in existing navigation
without a redundant top strip. Athlete tools follow effective permissions. Own training requires
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
stay with their original Person/Athlete. Existing navigation identifies the
selected Athlete; browser Back restores previous context reliably. Do not add a
duplicated context strip above every page. Guard routes alongside navigation.

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

## Historical verification and rollout record

The dated preparation entries below are historical. The delivery table and
linked deployment evidence above describe the current applied release.

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
- 2026-09-14 local foundation checks: 20 Python checks passed for identity links,
  signed HTTP/MCP authorization, operation-map coverage, media handlers and handler
  imports; a separate avatar ownership check passed. Node checks passed for OIDC
  endpoint confinement, HTTP byte ranges, Budget media ownership and same-day
  Session routing. Workspace typechecks passed. These use mocked stores/network;
  they are not deployed Authentik, browser, S3-processing or native acceptance.
- Both Terraform roots validate. The root configuration reports pre-existing
  undeclared-variable warnings; the nested media configuration validates cleanly.
  New secrets, identity configuration, dedicated tag/notification tables and
  disabling the retained CloudFront distribution are prepared only. No apply,
  cache invalidation or deployment has been performed.

- Additional local evidence: identity transactions now have tests capturing the
  actual boto3 wire body; two transactions had double serialization, now fixed.
  Onboarding saves profile basics and dated estimated max-history entries in one
  transaction, with a wire-encoding check. The HTTP/MCP conflict test preserves
  the current revision/record. Seventeen native continuation/import/generation/
  onboarding checks passed; the broader 24-check identity/access selection passed.
- Fresh reviews found fixed-key media output races and missing same-day edit/delete
  selectors and processing-retry UI. Corrections are active; fifteen media checks
  alone do not establish acceptance. The thumbnail IAM PutItem change is prepared.
- Session writes now advance Program and Session revisions atomically, protecting
  a concurrent Block transition from losing a log. The latest full service suite
  passed 136 tests plus seven subtests under mocks/offline checks. Required client
  mutation envelopes and Template target validation still need closure.
- Losing publication attempts can leave hidden, unpublished staging records.
  They are not visible Programs/Blocks; unique staging keys avoid overwriting a
  published version. No cleanup or AWS deletion has been performed.
- Global tags now use a separate pending/approved/rejected catalog and ignore legacy
  approval flags. Two catalog checks and the workspace typecheck passed. The
  repeatable migration only registers missing vocabulary as pending; it has not run.
- Live read-only onboarding audit found the operator has existing Program maxes/
  bodyweight but no settings-level Athlete basics. Migration must preserve those
  records and must not invent missing sex or other personal facts. The personal
  training gate and migration remain pending together.


### Profile, publication and context integration evidence (local)

- Focused profile/avatar/publication/search/onboarding/access suite: 14 passed.
  Covers private/public avatar mapping, current grants, tag approval removal,
  cursor pages, nested domain filtering and unknown-sex/unachieved-target handling.
- Explicit publication settings use expected revision and idempotency. History
  exports retain all Blocks; current-Block Markdown remains separately available.
- Current roles and selected Athlete are separate browser controls. Direct routes
  and navigation use the same permission mapping. IndexedDB Program drafts belong
  to the original Person/Athlete and retain original revisions when restored.
- Online cache reads contact the API. Visibility/online/30-second refresh and
  401/403 events recheck access and clear changed cache partitions.
- Terraform fmt/validate passed for the prepared relationship inbox/sent/roster
  indexes and dedicated tables (existing variable/deprecation warnings remain).
- Terra's relationship review found approval-expiry/replay/UI defects; these
  remain in progress. Current shared workspace typecheck is waiting for training
  mutation caller integration. No live browser/Authentik/DynamoDB acceptance or
  deployment is claimed by these checks.


### Notes, Block UI and gateway integration evidence (local)

- The full service regression run reached 153 passing tests and one registered
  handler import failure. Relative relationship-handler imports fixed that
  failure; the subsequent handler-import check passed.
- Seven gateway forwarding checks passed, including current operation permission
  denial before dispatch. Gateway and service boundaries call the same Profile
  evaluator. Metadata writes check their additional domain; legacy competition
  write variants require write permission despite their read-shaped operation name.
- Six focused access/Handler/import checks passed. Handler context limits Entries
  to current relationship ties and uses the existing Analysis max estimator.
  Profile and Handler views now render permitted failure nodes and form recordings.
- Authored-note storage has seven passing checks for atomic private saves,
  immutable attachments, actor/payload-bound retries and conflicts. Private notes
  have their own authenticated route after delegated access ends. Fresh Terra
  review found no note defect in this pass; deployed acceptance is still pending.
- Fresh Terra relationship review found a legacy slotless-grant roster mismatch.
  Luna is aligning roster and access behavior and adding distinct-request races.
- Block UI now offers a Template or Program designer and independent Block rename.
  Required Program/Template mutation callers and end-to-end acceptance are active.
- Media worker reports 31 local checks passing for replacement, notification,
  media preservation and CAS. Fresh final review and real S3 processing remain
  pending. Prepared Lambda configuration adds notification PutItem/GetItem access
  and 2 GiB temporary storage; nested Terraform validation passed. DynamoDB
  transaction IAM uses the underlying item permissions, per [AWS documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html).
- Offline queue/synchronization implementation is active. Current evidence does
  not yet establish offline acceptance. No deployment or Terraform apply occurred.

### Continued integration evidence (local, 2026-09-14)

- Fresh Terra review found form-media confirmation/playback were missing the
  lift-profile domain check. Profile now resolves the stored media allocation
  and rechecks both video and lift-profile permissions for confirmation, reads,
  metadata edits and removal. Read-only copied allocations cannot be confirmed;
  Session removal retries succeed after a lost response. Focused access/media
  suites: **25 passed**. These are local tests, not deployed processing evidence.
- Offline queue is mounted. Mutation identity stays attached to the original
  Person/Athlete through IndexedDB waits; cross-partition retries cannot shadow
  each other. The conflict dialog permits explicit review and resubmission at
  the reported server revision. `node scripts/test_offline_queue_browser.mjs`
  passed **12 checks in Chromium with simulated server responses**, including
  lost response replay, conflicts, revocation/cache removal, retained drafts and
  late responses after a context switch. This is not Authentik/live acceptance.
- Frontend typecheck passes after removing the obsolete onboarding publication
  checkbox contract and selecting explicit settings/Session write permissions.
- A full service test run passed **170 tests and 9 subtests**, with one failing
  outbound relationship grantee assertion. Luna corrected that regression and
  the relationship suite passed **12 tests**. Fresh Terra review then identified
  legacy-grant replacement, terminal replay, inbound replacement controls and
  concurrent-approval HTTP conflict gaps; those corrections remain in progress.
- Fresh Terra review identified Template result-schema/revision errors, copy
  retry duplication and index concurrency defects. Luna applied fixes and
  reported **22 tests and 16 subtests**; fresh verification is in progress.
- Performance target and lift-profile operation contracts now require mutation
  envelopes. The legacy current-max update uses the shared Program CAS helper.
  Focused performance/lift-profile tests: **11 passed**.
- Read-only cluster inspection confirms all sixteen existing Powerlifting domain
  Deployments and the current portal backend/frontend have one ready replica.
  They retain the earlier deployed images; this backlog work is not deployed.


### Continued review and acceptance (local, 2026-09-14)

- The full local domain-service suite passed **187 tests and 16 subtests** before
  the latest setup, Template, and source-access revisions. Workspace typechecks
  and the required workspace build passed. These checks do not establish deployed
  browser, Authentik, native Codex, or processing acceptance.
- Current Competition Entries are joined into Program reads, Analysis, max history,
  Handler estimates, and training exports without rewriting Program snapshots or
  duplicating legacy results. Tied grants filter both list envelopes and derived
  competition-history rows. Focused export/access/report/performance checks passed
  **22 tests**. Handler views retain stable Attempt IDs and Entry display units.
- Program source mutations invalidate Analysis caches, use actual DynamoDB error
  codes for revision conflicts, and recover lost-response deletion retries before
  reapplying the edit. Reused keys are bound to their operation and payload.
  Program/Block/Template checks passed **23 tests and 16 subtests**.
- Whole-Program patches and Template application now check the affected domains.
  Restricted tied grants use individual Competition Entry operations for changes.
  The access-context result schema includes the evaluator's complete fields.
  Focused permission/transport/projection checks passed **10 tests**.
- Fresh Terra review accepted the relationship expiry-slot correction and the
  migrated request records consumed by roster/context switching. Read-only review
  checks passed **20 nested migration/relationship tests** and **7 copy-helper
  tests**; the review found missing Template and author-original copy plans plus
  an unchecked manual ownership map. Copy/migration tooling remains unaccepted
  until those findings are resolved; no copy or migration has run.
- Fresh Terra review rejected initial setup staging and identified partial-set,
  whole-metadata, Template index, copy-identity, and retry gaps. Luna has added
  **8 new Program integrity tests** and applied further corrections. Fresh closure
  review and Template corrections remain pending.
- Saved generation references and native job reads now carry source access
  requirements and recheck current domains and Competition ties. Report/source
  and native-continuation tests passed **20 tests**; fresh security review remains
  pending. Legacy saved results without source requirements remain readable by
  their Athlete and need regeneration before delegated reads.
- No backlog image has been deployed, no Terraform apply has run, and no AWS
  resources have been deleted. Full 500 MiB upload acceptance still awaits the
  Cloudflare request allowance upgrade.

### Source privacy and integration follow-up (local, 2026-09-14)

- Fresh Terra setup/source review found filtered empty federation data could
  reload the private library during report generation. All three affected report
  handlers now distinguish an absent source key from an intentionally empty
  value. Source assembly skips unpermitted federation reads and imports the
  existing Federation store. Thirteen focused source/generation checks passed.
- The full service suite passed 210 tests and 16 subtests; workspace production
  build passed. These are local checks, with mocked storage/native HTTP.
- Additional Program version checks preserve skipped set records, allow editable
  metadata while rejecting Block/version ledgers and identity fields, and load
  the current Program before retry replay. The focused Program/setup/Block suite
  passed 29 tests and three subtests after these changes.
- Handler details now bind rendered data/errors to Person, selected Athlete and
  permissions, including the render before an effect runs on context changes.
  Local browser acceptance is still in progress.
- The current architecture document now describes native continuations, scoped
  report references and atomic publication; obsolete OpenRouter/slash-command
  execution and budget-cache claims were removed. Historical deployment records
  remain historical.
- Saved foundation plan: `/tmp/powerlifting-backlog-foundation.tfplan`, eight
  targeted resources, no deletions. It adds two protected tables, relationship
  indexes and principal/session configuration. Secret values remain private.
  Review/approval and all applies remain pending; no deployment is claimed.

### Final release evidence (local, 2026-09-14)

- The latest nested service suite passed **223 tests**. Root access/tool checks
  passed **8 tests**. Accepted Session HTTP/MCP identity and partition evidence,
  Accepted Markdown source/cache checks and **8 rollout tests** are recorded in
  the release package. Terra manually reviewed all **21 features**. The recovered Analytics
  rollback child image is `ACTIVE` in the existing ECR repository.
- Frontend AuthoredNotes source and frontend candidate are Terra accepted. Social
  review is closed: **18 scenario checks plus
  aggregate** include the mounted regression, with all eight state outcomes
  verified and no unhandled, browser, or expected-response errors. Local offline
  checks passed (**25 checks**); live revocation/conflict acceptance remains
  pending. The
  frontend candidate was built and published to the existing ECR repository with
  an immutable digest, Terra accepted it, and it is enabled in the bounded
  rollout manifest. Terra’s final closure covered frontend repository/digest and
  live-container checks, candidate/rollback pins, eight mocked tests, the
  self-test, the default 18-patch dry-run, and the frontend rollback dry-run.
  Deployment approval and deployed acceptance remain pending.
- Workspace typecheck and production build passed. The final package records the
  candidate and live rollback digests, source hashes, temporary recipe changes,
  regenerated targeted API/foundation plan, refreshed zero-change Authentik review
  and media plan, and sanitized approval commands. No apply, rollout, invalidation,
  or AWS deletion occurred. The disposable Analytics scan container was stopped
  gracefully and auto-removed; its local candidate image was then removed by exact
  ID. OCI rollback archives and node containerd images were preserved.
- Cloudflare request allowance upgrade remains pending, so full **500 MiB** media
  acceptance remains pending. Candidates are accepted for the coordinated
  rollout after required Terraform approval; deployed acceptance and the full
  500 MiB test remain pending afterward.
