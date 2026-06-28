# Powerlifting App Features Backlog — implement after the substrate migration

Status: DRAFT user-story backlog. **Implement after the health-tool runtime
substrate migration is settled** (see `HEALTH_LAMBDA_MIGRATION_PLAN.md` and
`FISSION_MIGRATION_PLAN.md`). The substrate swap and these features are
independent — features reference tool names resolved by the substrate; pick
Fission or Lambda, then start here.

Format: user stories grouped by epic. Each starts with `As a [persona], I want
[behavior] so that [value]`. Acceptance criteria are inferable bullets; if a
detail is ambiguous, the implementing agent must `ask_question` — never guess.

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

### BUG-1.3 — Dashboard "next workout" card doesn't navigate
As an athlete on the dashboard, when I click the "next workout" card I expect
to be redirected to that session's detail page.

- Card has a primary action (router-link / click handler) → routes to
  `/sessions/:id` for the next-up session.
- Loading state on the card while the session is being fetched.

### BUG-1.4 — Session list scroll position carries into session detail
As an athlete, when I scroll down my sessions list and click one, I expect to
land on the session detail page scrolled to the top — not preserving the
list's scroll offset from the previous page.

- On route change from `/sessions` → `/sessions/:id` (and back), the new page
  resets `window.scrollTo(0,0)` or uses the framework's
  `scrollBehavior: () => ({ top: 0 })` equivalent.
- Affects every nav where scroll is preserved unexpectedly (audit the router
  config).

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

### FEAT-3.3 — Role selection during onboarding
As a new user, I select my role during onboarding: athlete, coach, or handler.

- Guest path: an unauthenticated user can skip all of this (current demo UI
  behavior is preserved per the operator's stance).
- Athlete: full onboarding (FEAT-3.1 + FEAT-3.2).
- Coach: FEAT-3.2 only (no mandatory max/sex/region chips).
- Handler: FEAT-3.2 with display-name only (federations optional but
  irrelevant for handler role).

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
