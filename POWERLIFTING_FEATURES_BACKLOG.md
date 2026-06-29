# Powerlifting App Features Backlog — implement after the substrate migration

Status: DRAFT user-story backlog. **Implement after the health-tool runtime
substrate migration is settled** (see `HEALTH_LAMBDA_MIGRATION_PLAN.md` and
`FISSION_MIGRATION_PLAN.md`). The substrate swap and these features are
independent — features reference tool names resolved by the substrate; pick
Fission or Lambda, then start here.

Format: user stories grouped by epic. Each starts with `As a [persona], I want
[behavior] so that [value]`. Acceptance criteria are inferable bullets; if a
detail is ambiguous, the implementing agent must `ask_question` — never guess.

> **Backlog-wide baseline (added after the Fission substrate work):** every
> backend / data-backed capability in this backlog is delivered as a **Fission
> function** — that is the new substrate baseline. PM note (non-technical): any
> story that reads or writes data implies one or more function endpoints; the
> portal backend and the IF agent only ever call functions, they never run data
> logic in-pod. The implementing agent should enumerate the functions a story
> needs during planning. This does not change the *user* requirements below; it
> just sets the delivery shape. Where a story already names a tool/table, treat
> those as the data it touches, not as the only function it needs.

> **What changed in this revision:** the stories below were expanded from a PM
> lens to close requirement blind spots. Each story now carries, where useful,
> an **"Acceptance criteria (expanded)"** block and an **"Open questions /
> blind spots"** block. The expansions are product-level (behavior, edge cases,
> empty/error/loading states, permission interactions, notifications) — not
> implementation. Original operator text is preserved; new bullets are additive.

## Cross-cutting concerns (apply to every story unless explicitly excluded)

These were implicit or missing across the backlog. Treat them as default
acceptance criteria for any story they touch; if a story should deviate, say so
in that story.

- **States for every view:** every data-backed screen defines a **loading**,
  **empty** (no data yet), **error** (fetch/write failed, with a retry), and
  **success** state. "No program / no sessions / no athletes / no results"
  empty states must read as intentional, not broken.
- **Offline / PWA conflict:** the target release is an offline-capable PWA
  (see README). Any create/edit flow must define what happens when the user is
  offline and when two writers (e.g. athlete + coach) edit the same record.
  Default: last-write-wins is NOT acceptable for session logs — define a merge
  or conflict prompt. Flag per-story if offline is out of scope.
- **Units:** the app supports kg/lb toggles. Every weight shown to a user
  (guidance copy, maxes, attempts, plates) respects the user's unit preference;
  stored canonical unit is kg. State the displayed unit in any copy.
- **Notifications:** several stories (requests, grants, expiry, video-ready)
  imply the recipient is told something changed. There is **no notification
  system specified anywhere in this backlog** — see OPEN DECISION "Notification
  channel" below. Each story that needs to notify says what event fires and to
  whom; the channel is resolved once, centrally.
- **Audit / attribution:** when a coach or handler acts "as" an athlete, the
  change must be attributable to the actor, not silently recorded as the
  athlete. Define what (if anything) the athlete sees about who changed what.
- **Account lifecycle:** sign-out everywhere, account deletion, and data export
  are not covered by any story. See OPEN DECISION "Account lifecycle".
- **Accessibility:** interactive targets meet the 44pt / focus-order / screen-
  reader bar already called out in BUG-1.1; apply it everywhere, not just there.
- **Concurrency on relationships:** grants, revokes, role swaps, and expiries
  can race. Each relationship story states the expected outcome when two of
  these happen close together.

## Personas

- **Unauth / Guest** — not authenticated. Sees the legacy operator-style UI kept
  for demo (per operator instruction: the existing look and feel for demo
  purposes is NOT to change). Nav: Search, About, Switch role. Search lists
  public profiles only.
- **Athlete** — fully onboarded user with athlete attributes, profile, and
  optional federations. Today's athlete nav + Search + Switch role (in settings
  sidebar). Can have 1 coach + 1 handler. Owns their data + access grants.
- **Coach** — functionally the same UI as an athlete but sees everything of
  each athlete they coach (full read + write unless revoked). Can coach multiple
  athletes. Athletes grant coach access granularly.
- **Handler** — guest-style UI + a dashboard of profiles they handle. Uses
  attempt-specific tools (attempt calculator, plate calculator, unit converter,
  dots calculator) + the comp-day view (1-week padding for past comps). Sessions
  read-only, budget read-only, analysis tabs hidden. Can handle multiple
  athletes. Write access expires 1 week after each comp they handle for.

## Hard constraints (apply across all stories — restated from `AGENT_HANDOFF.md`)

- Use battle-tested identity **and** RBAC libraries only. Do NOT handroll role
  comparisons, claims parsing, or session management. Discord login is fine but
  must flow through Passport.js (or equivalent) — see `Identity & RBAC
  mechanism` decision below.
- New DynamoDB tables follow the same single-domain-per-table rule as the
  existing health/finance/diary tables. No domain mixing.
- Every float bound for a DynamoDB write is converted to `Decimal(str(value))`
  via the existing helper pattern in the relevant store module.
- Comments are forbidden in newly written code (modulo shebangs).
- No `AWS_REGION`-style reserved env-var leakage.
- Portal verification is via `if-portals-test` pod port-forward, not local
  Vite. Update `scripts/copy_operator_health_to_test.py` if any new domain is
  introduced (it must mirror operator data for `pk=test`).

## Identity & RBAC mechanism — decision required BEFORE Phase A starts

The operator is explicit: identity + RBAC must use battle-tested tools. Do NOT
handroll ~~permission flags in the backend~~ or ~~role checks in route
handlers~~. Pick one and confirm with the operator via `ask_question`:

- **(A) Keycloak** — self-hosted in the cluster (`if-portals` namespace).
  Battle-tested, supports Discord as a social identity provider (so users log
  in with Discord through Keycloak's broker), ships full RBAC: realm roles,
  group roles, scopes, fine-grained authorization services (``evaluate
  permissions'' API), and user attributes for the display-name / federations /
  public-private toggle. The Node backend validates JWTs with
  `passport-keycloak-oauth2` / `keycloak-connect`. The frontend still gets a
  JWT + refresh-token pattern. Heavy container (~600MB JVM) — fits the cluster
  but adds memory pressure on the single node.
- **(B) Ory Kratos + Ory Keto + Ory Oathkeeper** — identity (Kratos),
  permissions (Keto — zanzibar-style tuple relation graph for permissions:
  `(user, relation, object)`), access gateway (Oathkeeper). Discord login via
  Kratos' social-identity provider flow. Lighter than Keycloak on RAM (~150MB
  each) and the Keto tuple graph maps cleanly to the coach/handler/athlete
  relationship needed here (favorite" too).
- **(C) AWS Cognito + Amazon Verified Permissions** — managed, off-cluster,
  zero cluster RAM. Discord login via Cognito hosted UI (Cognito social IdP).
  Verified Permissions uses Cedar policy language + the same tuple-style
  relation model. Adds AWS per-active-user billing — small for an operator's
  handful of users but grows with user count.

Operator's quoted constraints: "battle-tested tools and libs," "add it into
the cluster" (favors A or B over C), "passportjs similar" (Passport.js is fine
as the Node-side strategy, paired with one of A/B/C as the identity store).

Default to **(A) Keycloak** if the operator gives no preference; the JVM
footprint on a single node is real but tolerable, and the Discord-broker +
full-RBAC story is the most battle-tested.

---

## Epic 1 — Session-detail UX bugs

### BUG-1.1 — Session-detail action menu is too small
As an athlete, when I open a session detail page and try to tap the plate
calculator I want the action targets to be comfortably sized so I don't
accidentally trigger **Delete** (the irreversible action next to the
calculator).

- Menu row height + tap-hit-box ≥ 44pt (mobile-friendly). Delete is visually
  separated and behind a confirm step; calculator and other safe actions are
  grouped together.
- Verify on a real mobile-width browser via the port-forwarded pod; do not
  handwave this as "looks fine in desktop."

**Acceptance criteria (expanded):**
- The destructive **Delete** action is not just visually separated but also
  ordered away from the most-tapped action; an accidental tap on Delete always
  surfaces a confirm with the session name/date so the user knows what they're
  deleting.
- The menu is keyboard- and screen-reader-navigable (focus order, labels), not
  only touch-sized.
- Define the action set explicitly for this menu (plate calculator, …, delete)
  so "grouped safe actions" is unambiguous — list which actions exist.
- The menu behaves the same whether opened by a coach acting on an athlete's
  session or by the athlete; a coach deleting an athlete's session must hit the
  same confirm and the action is attributed to the coach.

**Open questions / blind spots:**
- Is Delete reversible (soft-delete / undo toast) or hard-delete? The story
  calls it "irreversible" — confirm there is no undo, or add one.
- Does the same too-small-menu problem exist on the set-row actions inside the
  editor, or only the session-level menu? Scope it.

### BUG-1.2 — Add/remove a set wipes RPE and completed sets
As an athlete, when I change my mind and decide to add or remove a set on an
exercise mid-session, my prior inputs — RPE per set, completed-set flags,
notes per set — must be preserved and carried over to the new set list.

- Adding a set inserts a blank new row; existing rows keep their state.
- Removing a set drops only that row's state (with a confirm); the other rows
  are untouched.
- Existing state survives an upstream 'regenerate-session' call only when the
  caller is the user (UI) — server-side regeneration may wipe rows but the UI
  is responsible for merging prior state by `set_id` or by stable
  `(exercise, set_index)` if no `set_id` exists.
- Implement a stable-identity merge in the frontend before POSTing the
  update so the backend doesn't see the wipe as a feature.

**Acceptance criteria (expanded):**
- Define which set fields are "state to preserve": at minimum RPE, completed
  flag, per-set notes, actual weight, actual reps, and failure reason. List the
  full set of preserved fields so nothing is missed.
- Reordering sets (not just add/remove) preserves per-row state too, if
  reordering is possible in the editor.
- If a set is removed and then the user adds a set back, the removed set's old
  state does NOT silently resurrect — removal is final once confirmed.
- Unsaved changes warning: if the user adds/removes sets and navigates away
  without saving, they're warned (ties into the offline/PWA conflict concern).
- Behavior is identical when a coach edits the athlete's in-progress session.

**Open questions / blind spots:**
- What is the source of truth for set identity — does the backend emit a
  stable `set_id` today, or only `(exercise, set_index)`? This determines
  whether the merge is reliable; confirm before building.
- "Planned vs logged" sets: when the user adds a set, is it a planned set or a
  logged set, and does that distinction affect compliance/analytics downstream?
- Does adding/removing a set mid-session change the program's planned volume,
  and should that propagate to analytics, or is it a session-local edit only?

### BUG-1.3 — Dashboard "next workout" card doesn't navigate
As an athlete on the dashboard, when I click the "next workout" card I expect
to be redirected to that session's detail page.

- Card has a primary action (router-link / click handler) → routes to
  `/sessions/:id` for the next-up session.
- Loading state on the card while the session is being fetched.

**Acceptance criteria (expanded):**
- Define "next workout": the soonest future planned session, or today's if one
  exists? State the tie-break (e.g. today before tomorrow; earliest start time).
- Empty state: if there is no upcoming session (program finished, no program,
  rest day), the card shows a clear message and a sensible CTA instead of a
  dead/empty card.
- If the fetch fails, the card shows an error with retry, not an infinite
  spinner.

**Open questions / blind spots:**
- What does the card show on a rest day or between blocks — nothing, the last
  session, or "start a new block"?
- For a coach viewing an athlete, does "next workout" reflect the athlete's
  program (expected) and route into the athlete's session?

### BUG-1.4 — Session list scroll position carries into session detail
As an athlete, when I scroll down my sessions list and click one, I expect to
land on the session detail page scrolled to the top — not preserving the
list's scroll offset from the previous page.

- On route change from `/sessions` → `/sessions/:id` (and back), the new page
  resets `window.scrollTo(0,0)` or uses the framework's
  `scrollBehavior: () => ({ top: 0 })` equivalent.
- Affects every nav where scroll is preserved unexpectedly (audit the router
  config).

**Acceptance criteria (expanded):**
- Forward navigation (list → detail) lands at top; **back** navigation (detail
  → list) restores the list's previous scroll position so the user doesn't lose
  their place. State this asymmetry explicitly — it's the common expectation.
- Deep-linking / refresh on a detail page lands at top, not mid-page.

**Open questions / blind spots:**
- Should back-from-detail preserve scroll (better UX) or also reset? Confirm the
  expected back behavior; the story only specifies the forward case.

---

## Epic 2 — Lift profile enhancements

### FEAT-2.1 — Upload three form-demonstration videos per lift
As an athlete, on the lift-profile page I want to be able to upload three
videos per lift demonstrating my form — front, side, and diagonal — so a coach
or handler can see mechanics from multiple angles.

- Three slots per lift: front, side, diagonal. Each slot accepts one video.
- The guidance copy under each slot instructs the user to load the bar with
  **one red plate per side fewer than their training max** (closest red plate
  pair at-or-below max, rounded down), or the empty bar if their training max
  is fewer than two red-plates-per-side.
- Concrete specs the agent must implement:
  - `bar_weight = 20` (kg, men's IPF bar — make configurable since women's is
    15kg and the app already has unit toggles).
  - `plate_weight = 25` (kg, red IPF plate).
  - `plates_per_side = floor((training_max_kg - bar_weight) / (2 * plate_weight))`.
  - If `plates_per_side < 2`: prompt shows "Use the empty bar for this
    video." (no calibration weight needed).
  - Else: prompt shows "Load `plates_per_side - 1` red plates per side (≈
    `(plates_per_side - 1) * 50 + bar_weight` kg) for this video."
  - Worked examples embedded in the guidance copy:
    - 130 kg bench → `plates_per_side = 2` → load 1 red per side ≈ 70 kg.
    - 230 kg squat → `plates_per_side = 4` → load 3 reds per side ≈ 170 kg.
    - 50 kg lift → `plates_per_side = 0` → just the bar.
- Videos are stored alongside the existing lift-profile DynamoDB record (new
  attribute / new entries in the profile's media items); use the existing
  S3 bucket (`aws_s3_bucket.powerlifting_data`); convert floats to
  `Decimal(str())` before storing any embedded weights.
- Video processing reuses the existing `utils/video-lambda/` pipeline (which
  already handles thumbnails + transcode). Hook its completion webhook to mark
  the slot 'ready'.
- The slot guidance is computed **client-side** from the training_max that's
  already in the profile; do not push the weight formula into a new lambda.

**Acceptance criteria (expanded):**
- Per-slot lifecycle states are explicit: empty → uploading (with progress) →
  processing (video-lambda working) → ready → playable; plus a **failed**
  state with a retry/replace action.
- Replacing a video in an occupied slot: confirm before overwrite; the old
  video (and its derived thumbnail/transcode) is cleaned up so storage doesn't
  leak orphaned media.
- Define accepted formats, max file size, and max duration up front, with a
  clear message when a file is rejected. (Blind spot: none specified.)
- Define orientation/quality guidance (portrait vs landscape) since the point
  is for a coach to judge mechanics from a fixed angle.
- Read-only viewers (coach/handler with access) can play the videos but cannot
  upload/replace/delete; viewers without access cannot see them at all.
- If the athlete's training max changes after recording, the guidance copy
  recomputes, but already-uploaded videos are NOT invalidated — they stay until
  the athlete chooses to replace them (state this so videos don't silently
  disappear).
- Unit-aware: guidance copy renders weights in the viewer's unit preference
  (kg/lb), while the canonical stored values remain kg.

**Open questions / blind spots:**
- Are these three videos required to "complete" a lift profile, or always
  optional? Does an empty slot block anything downstream?
- Retention/privacy: are form videos covered by the public/private profile
  toggle, or always private even on a public profile? (Likely always private —
  confirm.)
- Plate-math realism: the formula assumes only red (25kg) plates. Should the
  guidance acknowledge that the athlete may not own enough reds, or is the
  "fewer than max" calibration intentionally coarse? Confirm the copy is
  guidance, not a strict requirement.
- Who can delete a video — only the athlete, or also their coach?

### FEAT-2.2 — Failure-mode nodes per lift
As an athlete, I want to be able to specify **failure nodes** for each lift ——
common scenarios that usually cause me to fail the lift (e.g. "falls forward
in the hole," "hits J-hooks on the way up," "loses upper back tightness off
the floor").

- Failure nodes are free-text tags on a lift-profile, multiple per lift.
- Stored alongside the existing lift-profile record. Don't create a new table
  for these — they're metadata on the existing lift profile value object.
- Displayed on the lift-profile card and surfaced to coach/handler readonly
  views.
- Used downstream by the IF agent's `powerlifting_coach` specialist when
  summarizing the athlete's profile (no new tool needed — extend the existing
  lift-profile read tool to include the field).

**Acceptance criteria (expanded):**
- Add, edit, and remove a failure node; duplicates on the same lift are
  prevented or merged.
- Define a sane cap on length and count per lift so the card doesn't become an
  unbounded text dump.
- Empty state: a lift with no failure nodes shows a prompt to add one, not a
  blank gap.
- Optional but worth confirming: can a failure node be linked to a specific
  set's "failure reason" already captured in the session editor, or are these
  two independent concepts? (See blind spot.)

**Open questions / blind spots:**
- The session editor already has a per-set **failure reason** (README). Are
  lift-profile "failure nodes" the curated/reusable list that the per-set
  failure reason picks from, or fully separate free-text? Clarify the
  relationship — this is the biggest ambiguity in this story.
- Should free-text be fully free, or chosen from a suggested starter list to
  keep them comparable across athletes for a coach?

---

## Epic 3 — Onboarding flow (replaces the current "go straight to create a
block" landing)

### FEAT-3.1 — Mandatory athlete basics
As a new user, before I can create my first training block I expect to be
prompted for the mandatory athlete basics: body weight, current training max
per lift (squat, bench, deadlift), sex, country, and state/province. Most of
the app is useless without these.

- All listed fields are required; cannot be skipped.
- Validate: weight > 0, max per lift > 0, country ∈ ISO list, state/province
  matches the selected country's subdivision list.
- Stored in the existing user-settings / athlete-profile store with floats
  decayed to `Decimal(str())` before any DynamoDB write.
- This step only fires for athletes & coaches — handlers and guests skip it.

**Acceptance criteria (expanded):**
- The flow is resumable: if a user abandons onboarding partway, returning lands
  them back at the first incomplete step rather than restarting or, worse,
  dropping them into a half-configured app.
- Each field captures its unit where relevant (bodyweight + maxes in the user's
  unit preference, stored canonical in kg).
- Editable later: every "mandatory basic" can be changed after onboarding from
  settings/profile — onboarding is the first capture, not the only one. State
  where they live post-onboarding.
- Define whether "training max" here means a true 1RM, a working/training max,
  or a recent gym top single — this materially affects every downstream
  calculation (attempts, plate guidance, projections). This MUST be unambiguous.

**Open questions / blind spots:**
- "sex" — what options, and is it used only for DOTS/weight-class math or also
  shown on the profile? Confirm the allowed values and their purpose so the copy
  is respectful and correct.
- Are bodyweight and maxes a point-in-time snapshot that seeds history, or the
  start of an ongoing tracked series? (Maxes history is a real feature per
  README — clarify how onboarding seeds it.)
- What if the user genuinely doesn't know a current max for a lift (e.g.
  returning from injury, never tested bench)? Is an estimate / "unknown"
  allowed, or is a number always forced?

### FEAT-3.2 — Profile creation
As a new user after the basics, I expect to create a profile.

- Display name — required.
- Federations — optional; pulled from the master federation list
  (`federation_store.get_federation_library` already exists in the health
  tools). Multi-select of abbreviations.
- Public / private — required (single toggle). Default = private. Surfaces a
  one-liner: "Public profiles are searchable by other users. Private profiles
  are only visible to you and anyone you explicitly grant access to."
- Stored in the same `if-health` user-settings record schema used today.

**Acceptance criteria (expanded):**
- Display name rules are defined: length bounds, allowed characters, and
  whether it must be unique across users (matters because Search shows display
  names — duplicate "John" profiles are confusing).
- Public/private can be changed any time later; flipping a profile public ↔
  private states what happens to existing access grants and pending requests
  (e.g. going private does NOT auto-revoke already-granted access — confirm).
- Federation multi-select handles the "my federation isn't listed" case
  gracefully (the master list is finite).

**Open questions / blind spots:**
- Is display name the public identifier, or is there a separate handle/username?
  Search and relationship requests need a stable way to find someone.
- Profile photo / avatar — implied by "profiles" but never specified. In scope?
- What exactly is visible on a PUBLIC profile to a stranger (display name +
  federations + tags only, or also maxes / recent comps)? This is a privacy
  decision the search + profile-view stories depend on — pin it down here.

### FEAT-3.3 — Role selection during onboarding
As a new user, I select my role during onboarding: athlete, coach, or handler.

- Guest path: an unauthenticated user can skip all of this (current demo UI
  behavior is preserved per the operator's stance).
- Athlete: full onboarding (FEAT-3.1 + FEAT-3.2).
- Coach: FEAT-3.2 only (no mandatory max/sex/region chips).
- Handler: FEAT-3.2 with display-name only (federations optional but
  irrelevant for handler role).

**Acceptance criteria (expanded):**
- The role chosen here determines the post-onboarding landing nav (Epic 5);
  state the redirect target per role.
- The "Switch role" nav item (Personas section) implies a user can hold or move
  between roles after onboarding. Define whether role is a one-time choice, a
  switchable mode for a single account, or whether one account can be BOTH an
  athlete and a coach simultaneously. This is referenced all over Epic 5/6/7 but
  never actually defined — it's the single biggest structural blind spot in the
  backlog.
- Re-running onboarding when switching into a role you haven't set up yet (e.g.
  an athlete who later also wants to coach) collects only the missing pieces.

**Open questions / blind spots:**
- Can one human be an athlete AND a coach AND a handler under one login, or is
  each account exactly one role? Everything downstream (data ownership, `mapped_
  pk`, the single-coach rule, the handler dashboard) hinges on this answer.
- Is a coach also implicitly an athlete (do they have their own training data),
  or coach-only? The personas say a coach's UI equals an athlete's — confirm
  whether a coach has their own program too.

---

## Epic 4 — Identity & RBAC infrastructure

### FEAT-4.1 — Identity provider in the cluster
As the operator, I want a battle-tested identity provider deployed in the
cluster that handles Discord social login, user attributes, sessions, and
credential rotation so the team isn't handrolling auth.

- Deployment belongs in a NEW `terraform/k8s-identity.tf` (or appends to
  `k8s-secrets.tf` if cleaner).
- Discord client_id/secret stored in `aws_ssm_parameter` plain String (NO
  KMS) — mirrors the existing pattern in
  `utils/powerlifting-app/terraform/ssm.tf`.
- Backend (Node) uses Passport.js with the chosen identity strategy
  (`passport-keycloak-oauth2` / `@ory/client` / `passport-cognito` etc.) —
  the existing Discord OAuth flow is replaced, not duplicated.

**Acceptance criteria (expanded):**
- Existing operator/Discord users are migrated, not orphaned: define what
  happens to the current operator identity and any existing data keyed by the
  current `pk`/`mapped_pk` when the new IdP becomes the source of truth.
- Session lifecycle is defined: token/refresh expiry, sign-out (single device
  vs everywhere), and what the user sees when their session expires mid-action
  (graceful re-auth, not data loss).
- Failure modes: IdP is down / login fails / Discord denies consent — each has
  a user-visible message, not a blank screen.

**Open questions / blind spots:**
- Login methods: Discord-only, or also email/password? If Discord-only, what's
  the recovery path if a user loses their Discord account?
- This is operator-facing infra, but it gates EVERY other authed story. Confirm
  the mechanism decision (Open Decisions list) is closed before any of Epics
  3/5/6/7 start.

### FEAT-4.2 — Granular RBAC for athlete / coach / handler
As an athlete, I want to be the grant-admin of read/write permissions on my
own data so I can scope what a coach or handler can see.

- Policy language: the chosen RBAC store exposes "full read",
  "full read+write", plus granular per-domain reads/writes. Athletes pick from
  these presets when granting; they can also custom-grant per-domain.
- Default perm sets:
  - **coach-default**: full_read + full_write on every domain for the granted
    athlete.
  - **handler-default**: read on sessions + budget (read-only),
    read+write on competitions + attempts + their tools (attempt calculator,
    plate calculator, unit converter, dots calculator). No access to
    analytics / lift-profile-AI tabs.
- Athlete can override the default at grant time per relationship.
- RBAC is enforced at the backend route layer using the RBAC library (not
  inline role flags in handlers).
- The backend route map is the source of truth for which RBAC scope each
  route expects. List it in a single `backend/src/auth/scopes.ts` so
  reviewers can audit it.

**Acceptance criteria (expanded):**
- The full list of grantable domains is enumerated explicitly (e.g. profile,
  sessions, program/designer, competitions, attempts, budget, analytics,
  lift-profile + videos, maxes history, templates, glossary). A granular grant
  UI is meaningless without the canonical domain list — define it here.
- The athlete has a single screen to view and manage all current grants: who
  has what, on which domain, granted when, and a one-click revoke per grantee.
- Revoke is immediate for new requests; in-flight writes follow the Open
  Decision "revoking a coach mid-cycle" default (finish in-flight, block new).
- The grantee sees a clear "access revoked / read-only now" state rather than
  silent failures when they next act.
- Self-access is implicit and total: an athlete always has full read+write to
  their own data regardless of grant state.
- A coach/handler attempting an action beyond their scope gets a clear,
  consistent "not permitted" response (same shape everywhere), never a 500.

**Open questions / blind spots:**
- Can an athlete grant another *athlete* read access (peer sharing), or only a
  coach/handler? FEAT-6.2 implies athletes can request read access to each
  other — reconcile this with the grant model.
- Do grants have an optional expiry the athlete can set, or only the
  handler-auto-expiry (FEAT-7.3)?
- When a coach is replaced (single-coach rule, FEAT-7.4), are the old coach's
  grants fully revoked, downgraded to read, or left until manually removed?
- Does write-by-coach create data "owned" by the athlete, and can the athlete
  later edit/delete what the coach wrote? Confirm ownership semantics.

---

## Epic 5 — Per-role navigation

### FEAT-5.1 — Guest / unauth nav
As an unauth (or logged-in guest), I see only Search, About, and Switch role
in the nav.

- The current operator look-and-feel for unauth is preserved as the demo state.
- The yellow "Sign up with Discord" banner is replaced with a "Go back"
  banner when a search-result navigation has replaced the demo state. The click
  restores the demo landing.

### FEAT-5.2 — Athlete nav
As an athlete, I see the current nav (today's tabs) plus Search + Switch role.
Switch role lives in the settings sidebar, not as its own nav item.

### FEAT-5.3 — Coach nav
As a coach, I see the same nav as an athlete. Visiting an athlete I coach gives
me full read+write (per FEAT-4.2 coach-default) using that athlete's data — UI
is the same, but my actions go through their `mapped_pk` for that session.

### FEAT-5.4 — Handler nav
As a handler, I see guest-style nav (Search, About, Switch role) plus a
"Dashboard" of profiles I handle.

- Each athlete rendered as a card listing: display name, current block phase,
  next competition date, attempt selections last edit time.
- Clicking the card opens the handler's "athlete details" page (FEAT-6.4).

**Acceptance criteria (expanded — applies across FEAT-5.1 to 5.4):**
- "Switch role" behavior is defined consistently with the FEAT-3.3 role-model
  decision: is it switching which data I'm operating on, or switching my own
  account's active role? The nav cannot be specified until that's settled.
- Each role's nav has a defined landing/default tab after login.
- Tabs/items a role must NOT see are actually hidden AND blocked at the route
  level (a handler can't reach the analytics tab by typing the URL), not just
  visually omitted.
- Handler dashboard empty state: a handler with zero current athletes sees an
  intentional empty dashboard, not a blank screen.
- Handler card fields degrade gracefully when data is missing (no block, no
  upcoming comp, no attempts yet).

**Open questions / blind spots:**
- When a coach is "operating as" an athlete, is there a persistent, obvious
  visual indicator (banner/badge) showing whose data they're editing, to
  prevent a coach accidentally logging to the wrong athlete? Strongly implied,
  never stated.
- Can a coach switch between their athletes without going back to Search each
  time (an athlete switcher), or is Search the only entry point?
- Does a coach have their own training tabs at the same time as viewing an
  athlete, and how does the UI separate "my data" from "their data"?

---

## Epic 6 — Search & profile navigation state

### FEAT-6.1 — Public search
As anyone (incl. unauth), when I use Search I see all public profiles (athletes
and coaches only — handlers and guests are never in the search list because
they're not athletes).

- Results show display name + federation pills (FEAT-10.1).
- Result-item click carries the athlete's `mapped_pk` (if defined, falling back
  to `pk`) into the app state and routes to the readonly profile view.
- The nav reverts to the current (athlete-style) nav so the visitor can browse
  the profile. A "Go back" banner replaces the yellow Discord banner — click
  it to return to the demo/guest landing.
- Athletes searching filter themselves out of the result list.

**Acceptance criteria (expanded):**
- Define what the search box matches on: display name only, or also tags
  (FEAT-8.1) and federations? State the match rule (prefix, fuzzy, exact).
- Results have a defined order (relevance, alphabetical, recently active?),
  pagination or infinite scroll for large result sets, and a no-results empty
  state.
- A profile that flips from public to private disappears from results for users
  who don't have explicit access (consistency with the privacy model).
- Rate-limit / abuse consideration noted for unauth search (it's a public,
  unauthenticated endpoint).

**Open questions / blind spots:**
- Can guests see the same profile detail as authed users, or a reduced view?
  (Ties to the "what's on a public profile" decision in FEAT-3.2.)
- What is searchable text exactly — is searching by tag a first-class filter
  here, or only in the Tags epic? FEAT-8.1 says search by tag; reconcile.

### FEAT-6.2 — Authenticated-athlete search
As an athlete, I use Search and can see all public profiles PLUS any private
profiles I have read access to (granted to me explicitly).

- Same navigation, state, and go-back banner logic as FEAT-6.1.
- Result item actions include a "favorite" toggle and, on the user's page, a
  "Request read access" button (requests are reviewed by the profile owner).

### FEAT-6.3 — Athlete browsing another athlete
As an athlete/coach, when I am viewing another user's (mapped_pk or pk)
profile, the active app "operating as" state has been switched (via
`req.mapped_pk` thread-through — same pattern the backend already uses for the
Discord-operator identity) so every downstream fetch resolves their data, not
  mine.

- The existing backend `req.mapped_pk` plumbing already supports this.
- The frontend's currently-'operator'-implicit profile context becomes
  explicit: switch the active `mapped_pk`/`pk` when entering a readonly or
  coach/handler view, restore on "Go back".
- The `mapped_pk or pk` fallback rule: prefer `mapped_pk`; if absent, use `pk`.
  This matches the existing Discord-operator convention.

### FEAT-6.4 — Handler's athlete-details page
As a handler, when I open an athlete card from my dashboard I see everything I
need for the comp-day flow:

- Top section: athlete profile (display name, federations, failure nodes,
  onboarded basics).
- Block phase card (the same component used on the athlete's own dashboard).
- Estimated-max card (per lift).
- Upcoming-competitions card — with **1-week historic padding** on the
  widget's filter so that during the comp day a handler can still see the
  comp they're standing at, plus reasonably-recent past comps.
- Per-competition attempt selections + notes (editable by the handler).
- Bottom: a "Go to profile" link → routes into FEAT-6.1 pattern with the
  handler's permission scopes layered.

- Handler's dashboard / details are scoped to competitions where they're the
  handler of record; if they no-longer-handle an athlete (revoked / expired),
  that athlete disappears from the dashboard.

**Acceptance criteria (expanded):**
- Each card field renders the athlete's data in the unit preference appropriate
  to comp day (the competition's declared unit, typically kg) — be explicit,
  since handlers act on real platform numbers.
- The attempt selections the handler edits write back to the athlete's data and
  are attributed to the handler; the athlete can see that the handler set them.
- During the 1-week post-comp window the handler can still edit (per FEAT-7.3);
  after expiry the page becomes read-only with a clear "write access expired"
  banner rather than failing edits silently.
- If the athlete revokes mid-comp, define the handler's experience: do in-flight
  edits on the comp-day screen complete, or hard-stop? (Tie to FEAT-4.2 default.)

**Open questions / blind spots:**
- "Estimated-max card" — is this the athlete's current training max, an e1RM
  computed from recent sessions, or the comp projection? Name the source.
- Can a handler see the athlete's failure nodes and form videos (useful on
  platform), or are those coach-only? Confirm the handler's read scope on
  lift-profile content.
- What does the handler do if an athlete has no upcoming competition at all —
  can they still be a handler-of-record, or is a competition required to exist
  first?

---

## Epic 7 — Relationship requests

### FEAT-7.1 — Send a relationship request
Everyone (athlete, coach, handler) can request one of:
- To be **someone's** coach or handler (you take the role on their profile).
- To be **coached or handled by** that person's existing coach or handler
  (you want to be their athlete) — when used, this is scoped to a **specific
  competition** (use the `competition_id` for the relation scope).
- Favorite someone (no expectation of access — just a saved profile link).
- Request basic read access to a private profile (granularity is granted by
  the athlete).

- Requests store: `if-powerlifting-requests` (new table, one row per
  request). Item shape: `request_id`, `from_user`, `to_user`, `kind`
  (favorite | read | coach | handler | be_coached_by | be_handled_by),
  `competition_id` (nullable, only for COMP-scoped requests), `state`
  (pending | approved | rejected | revoked | expired), timestamps,
  `requested_scope` (granular read or read+write preset).
- No tables, no cross-domain rows. The IF bot's existing "proposals" store is
  NOT this — different domain.

**Acceptance criteria (expanded):**
- Duplicate-request guard: a user cannot have two identical pending requests to
  the same target (same `kind` + `competition_id`); re-requesting updates the
  existing pending row or is blocked with a clear message.
- The requester can see the state of requests they've sent (pending/approved/
  rejected) and can cancel a pending one.
- Self-targeting is prevented (can't request to coach yourself, favorite
  yourself, etc.).
- Requesting against a non-existent / now-private / deleted target fails
  gracefully with a clear message.
- "be_coached_by / be_handled_by" requires a valid `competition_id`; the UI
  only lets the user pick a competition that exists and is in a valid window.
- Each successful send triggers a notification to the recipient (channel per
  the cross-cutting Notification decision).

**Open questions / blind spots:**
- Who approves a `be_coached_by`/`be_handled_by` request — the target athlete,
  or the coach/handler being asked to take on the work, or both? The approval
  story (7.2) only covers the athlete approving inbound requests; this comp-
  scoped "ask to join someone's coach" path has an ambiguous approver. Resolve.
- Does "favorite" notify the favorited user, or is it silent/private to the
  requester? (Implies privacy expectations.)
- Can a coach proactively request to coach an athlete (inbound to the athlete),
  AND an athlete request a coach (inbound to the coach)? Define both directions
  and who approves each.

### FEAT-7.2 — Athlete-side approve / reject page
As an athlete, I expect a page where I see every pending request sent to me
(favorite, read access, coach, handler, athlete-to-their-coach-for-comp, etc.)
and can approve or reject each one.

- Approval writes the resulting permission tuple into the RBAC store
  (`Keto` / `Keycloak authorization services` / `Cognito AVP`) — not a
  handrolled join table.
- Rejection flips the request state to `rejected` and does NOT create a
  permission tuple.
- UI action buttons go through the backend route that holds the permission
  ledger — UI is naive; backend + RBAC library do the work.

**Acceptance criteria (expanded):**
- Empty state: an athlete with no pending requests sees an intentional "no
  requests" state.
- Each request row shows enough context to decide: who (display name), what
  kind, which competition (if scoped), what scope is being requested, and when
  it was sent.
- Approving a `coach`/`handler` request that would violate the single-coach /
  single-handler rule routes through the FEAT-7.4 replace-confirm flow rather
  than silently failing or double-assigning.
- Approve/reject is idempotent and race-safe: if the requester cancels at the
  same moment, the athlete gets a clear "no longer pending" result.
- Both requester and target are notified of the approve/reject outcome (channel
  per the Notification decision).

**Open questions / blind spots:**
- Can an athlete later revoke an already-approved relationship from this same
  page, or is revoke a separate surface (the grants screen in FEAT-4.2)?
  Reconcile so revoke has exactly one home.
- Is there any history/audit of past approved/rejected requests, or only the
  current pending list?

### FEAT-7.3 — Handler write-access auto-expiry
As a handler, my write access to an athlete I'm handling lapses 1 week after
the competition I'm handling them for. I still retain read access after
that.

- The relation tuple includes the `competition_id`; on expiry, only the
  `write` capability is revoked (read stays).
- Background job (or on-first-fetch-of-the-morning lazy check in the backend)
  compares `now()` vs `competition_end_at + 1week` and removes the write
  tuple from the RBAC store.
- Lazy check is preferred — no new scheduled cron on the cluster.

### FEAT-7.4 — Single-coach and single-handler-per-athlete rule
An athlete can have at most 1 active coach and 1 active handler at any one
time.

- On approve-a-new-coach request for an athlete with an existing active coach,
  the athlete gets a confirm dialog: approving replaces the existing coach.
- Coaches and handlers can serve multiple athletes simultaneously.

**Acceptance criteria (expanded):**
- Replacing a coach/handler defines what happens to the outgoing one: their
  write access is removed, and the story states whether they keep read, lose
  all access, or are notified. (Tie to FEAT-4.2 ownership questions.)
- The athlete can proactively remove their current coach/handler without a
  replacement (go back to having none), not only via the replace-on-approve
  path.
- The single-active rule is enforced server-side, not just by UI confirm, so a
  race between two approvals can't leave two active coaches.
- The replaced coach is notified they were replaced (channel per Notification
  decision).

**Open questions / blind spots:**
- Does "1 active handler" mean 1 at a time globally, or 1 per competition? A
  handler relationship is competition-scoped (FEAT-7.1/7.3), so an athlete
  prepping two meets might reasonably want two handlers. Clarify whether the
  single-handler rule is per-comp or absolute — they conflict as written.
- When a coach is replaced mid-training-block, what happens to program notes /
  sessions the old coach authored — retained as-is, attributed historically,
  or removed?

---

## Epic 8 — Tags

### FEAT-8.1 — Profile tags (cosmetic pills)
As an athlete, I want to add tags to my profile that show as pills under my
display name (e.g. "novice", "does not wash knee sleeves") so I can be
lighthearted and so others can search profiles by similar tag.

- Tags are strings normalized to lowercase; duplicates are ignored.
- Each tag is a `(tag_name, approved: bool)` pair. **By default tag names
  added by their owner = `approved=true`** (the athlete added theirs).
- Tags **proposed by other users** for the athlete await approval
  (`approved=false`) and only show publicly once the athlete approves them.
- Search supports tag-AND / tag-OR filtering.

**Acceptance criteria (expanded):**
- Define limits: max tags per profile, max tag length, and allowed characters
  (so pills stay short and the row doesn't overflow).
- The athlete can remove any tag on their profile (including ones they
  approved earlier).
- Profanity / abuse: tags proposed by OTHER users are public-facing once
  approved, but a malicious proposer could spam offensive proposals. Define
  whether there's a block/report or proposal rate-limit. (Blind spot — pills
  are "lighthearted" but this is user-generated content shown publicly.)
- Tags only appear on profiles visible to the viewer (respect public/private).

**Open questions / blind spots:**
- Can the same tag be proposed by multiple users (a "+3 others suggested this"
  count), or is it one row per tag regardless of proposer?
- Do tags participate in Search ranking, or are they only a filter? (FEAT-6.1
  match-rule question.)
- Is there any global/curated tag vocabulary, or fully free-form? Free-form
  hurts tag-based search (typos fragment the space) — confirm that's acceptable.

### FEAT-8.2 — Tag storage (two equal options — operator may pick)

- **Option A — new DynamoDB table `if-powerlifting-tags`**:
  - PK = `pk` (the user's pk/mapped_pk), SK = `tag` lowercased.
  - Attributes: `approved` (bool), `proposed_by` (the user's pk; equals the
    owner's pk for self-tags).
  - Table is small (~ few KB per user at most). Single-domain (tags only);
    no reads from this table affect sessions, programs, competitions.
- **Option B — metadata on the existing user-settings/rbac record**:
  - The existing `if-core`/`if-health` user-settings record carries a
    `tags` attribute (list of `{tag, approved, proposed_by}`).
  - Smaller terraform footprint; one less table; one less store module.
  - Risk: tags get fetched on every user-settings load even when the
    caller doesn't need them.

- Document the chosen option inline in this file (replace options with the
  decision). Preserve both options' below `Status:` as a paper trail if
  anyone needs to revisit later.

---

## Sequencing suggestion for the implementing agent

Epic order is sketched below — handle each epic as its own PR / branch.

1. Bug fixes (Epic 1) — fast, low risk, unblock good UX before the heavy
   RBAC work lands.
2. Lift profile enhancements (Epic 2 — videos + failure nodes) — the
   videos piece depends on the existing video-lambda pipeline; failure
   nodes are a clean metadata addition.
3. Identity + RBAC mechanism (Epic 4) — block before any role-specific UI.
4. Onboarding (Epic 3) — depends on identity lives to enforce role selection.
5. Per-role nav (Epic 5).
6. Search + state thread (Epic 6).
7. Relationship requests (Epic 7) — depends on RBAC + competitions setup.
8. Tags (Epic 8) — closet-it-last since it's independent and safe to split it
   into its own async work.

Verification gate at the end of every epic: `terraform fmt`/`validate` +
`npm run build` + `py_compile` on any new/changed Python + `kubectl port-forward
ps -n if-portals-test → browser smoke`. None of these epics should ship with a
broken validate or a build that breaks the portal.

---

## Open decisions (ask the operator before Phase A starts)

- [ ] Identity & RBAC mechanism: (A) Keycloak, (B) Ory Kratos + Keto +
  Oathkeeper, or (C) AWS Cognito + Verified Permissions. Default if unspecified:
  Keycloak.
- [ ] Tags storage: new `if-powerlifting-tags` table (Option A) vs metadata
  on user-settings/rbac (Option B). Default if unspecified: Option A
  (cleaner domain separation + smaller user-settings fetches).
- [ ] Should guests register ("Sign up" → onboarding) from the demo landing
  page? Or do they switch role explicitly from the existing nav via
  "Switch role" item? Default: Switch role from the nav, no "Sign up" CTA.
- [ ] Bar weight for the video-guidance formula: respect the user's chosen
  sub-type per lift (men's 20kg / women's 15kg / specialty bar override).
  Default: use the existing per-athlete bar_PREF setting if it exists;
  otherwise 20kg.
- [ ] Video storage: reuse `aws_s3_bucket.powerlifting_data` (yes/no). Default
  yes; reuse the existing bucket + CDN/cache behavior.
- [ ] Granular-read presets for athletes granting read access — should we
  ship 3 presets {profile, sessions, competitions} + a custom pick-list,
  or stick to a single "basic read" preset only? Default: 3 presets + custom.
- [ ] Revoking a coach mid-training-cycle: any in-flight writes (session logs)
  are completed but new writes are blocked — confirm this is the desired
  behavior. Default yes.

### New decisions surfaced by the PM review (resolve before the dependent epic)

- [ ] **Role model (blocks Epics 3, 5, 6, 7).** Can one login hold multiple
  roles (athlete + coach + handler) and switch between them, or is each account
  exactly one role? Is a coach also an athlete with their own training data?
  "Switch role" is referenced everywhere but never defined. No safe default —
  must be answered.
- [ ] **Notification channel (blocks every request/grant/expiry/video-ready
  story).** There is no notification system specified. How is a user told a
  request arrived / was approved / access expired / a video finished
  processing? Options likely include in-app inbox, Discord DM (the IF bot
  already has Discord), email, or none-for-now (poll on next load). Default if
  unspecified: in-app only, no push.
- [ ] **What a public profile exposes to a stranger** (blocks FEAT-3.2 /
  6.1 / 8.1). Display name + federations + tags only, or also maxes / recent
  competition results? This is the core privacy contract for the whole social
  layer. Default: display name + federations + tags + public competition
  results only; training data (sessions, analytics, lift videos) always private
  unless explicitly granted.
- [ ] **"Training max" definition** (blocks Epics 2, 3, and all attempt/
  projection math). Is the onboarding "current training max per lift" a true
  1RM, a working/training max, or a recent top single? Everything downstream
  computes off it. Default: treat it as a true 1RM estimate; label the field
  accordingly.
- [ ] **Handler count rule** (blocks FEAT-7.4 vs 7.1/7.3 conflict). Is the
  single-active-handler rule absolute, or per-competition (since handler
  relationships are competition-scoped)? Default: per-competition (1 handler
  per comp), not 1 globally — confirm.
- [ ] **Account lifecycle** (cross-cutting, currently unowned). Sign-out
  (single device vs everywhere), account deletion, and data export are not
  covered by any story. Default: ship sign-out-everywhere + account deletion
  before any public/multi-user exposure; data export deferred.
- [ ] **Offline conflict policy for shared records** (cross-cutting). When an
  athlete and their coach edit the same session/program concurrently (or the
  athlete edits offline then syncs), what is the resolution? Default: detect
  conflicting writes and prompt the second writer; never silent last-write-wins
  on session logs.
- [ ] **Failure-node ↔ per-set failure-reason relationship** (blocks FEAT-2.2).
  Are lift-profile "failure nodes" the reusable vocabulary that the session
  editor's per-set "failure reason" selects from, or independent free-text?
  Default: independent for now, with a note to unify later.
