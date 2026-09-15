# Context — Powerlifting Meet-Prep Portal (NoLift)

The ubiquitous-language glossary for the powerlifting meet-prep domain. This is a
glossary only: it defines what the domain terms *mean*, not how they are stored,
typed, or computed. Implementation details live in `docs/ARCHITECTURE.md` and the
code.

The portal is a competition-geared meet-prep notebook: an athlete is always
preparing for a meet, and the meet provides the standards and timeline that
anchor everything else.

## People & Roles

**Person** — The human behind a verified login. A Person may select one or more
Athlete, Coach and Handler roles. A Coach-only or Handler-only Person can finish
profile onboarding without creating personal training data. Active role is the
purpose of the current view; selected Athlete is the owner of the records being
viewed. Neither selection grants permission.

**Athlete** — The role that owns a Program, Sessions, Attempts and other personal
training records. Personal training requires Athlete basics. Only the Athlete
administers grants on their records.

**Coach** — A Person offering ongoing training collaboration. A Coach works on
an Athlete's records under a Coach grant and uses a roster to select Athletes.

**Handler** — A Person supporting an Athlete around competition day. A Handler
works under a Handler grant and uses a competition-day roster.

**Grant** — Permission issued by an Athlete to a distinct Person. Coach grants
default to broad training reads and writes. Handler grants default to
competition-day writes and read-only training context. The Athlete may explicitly
choose additional domains. Both require tied Competition Entries and expire
seven days after the latest stored tied competition date. An Athlete has at most
one active Coach and one active Handler. A separate peer grant confers only
specified reads; a favorite is private and confers no access.

**Authored note** — Words owned by the Person who wrote them. A private original
is separate from an attributed revision attached to an Athlete's record. The
Athlete may remove the attachment but cannot rewrite another Person's words.
An authorized author may explicitly publish a new shared revision. Programs,
Sessions and Attempts remain Athlete-owned even when a delegate edits them.

## Competition

**Competition Event** — A powerlifting meet sanctioned by a Federation, at which
an Athlete attempts the squat, bench, and deadlift for a total. An Event exists
in the competition directory independently of any Athlete's participation.
Informal synonym: **meet**, used especially for the day-of event.

**Competition Entry** — An Athlete's participation in a Competition Event: their
targets and projections when upcoming, their results and post-meet report when
completed. An Athlete has many Competition Entries across their history, but a
Program is anchored to one target Entry at a time. A Competition Entry has its
own store and lifecycle independent of the Program.

> Capability test: a domain concept gets its own function (and thus its own
> uniform portal + agent path) when it has its own store, its own identity, and
> its own lifecycle independent of the Program aggregate. Competition Entries,
> Sessions, Goals, Budget, and the Weight Log pass this test; sub-collections
> that live inside the Program document do not.

**Federation** — An organization that sanctions Competition Events and publishes
the Qualification Standards (required totals per sex, equipment, weight class,
and season) that an Athlete must hit to compete at a higher-level meet.

**Qualification Standard** — A Federation-published required total (per sex,
equipment, weight class, and season) that an Athlete must achieve to qualify to
enter a given Competition Event.

**Lift Results** — The squat, bench, deadlift, and total (in kilograms) achieved
at a Competition Entry, or set as a target for one. The canonical four-number
outcome of the three lifts.

**Attempt** — A single competition lift try: the 1st (opener), 2nd, or 3rd
attempt at one discipline (squat, bench, or deadlift) in a Competition Entry.

**Attempt Selection** — The choice of the three attempt weights for a discipline
at an upcoming Competition Entry, derived from projected maxes and configurable
opener / second / third percentages. Also the name of a retrospective miss
category (when a missed attempt is attributed to a poor weight choice).

**Post-Meet Report** — The retrospective debrief after a Competition Entry: each
attempt's outcome and miss reasons, sleep, travel, warm-up timing, fueling,
caffeine, equipment issues, and an attempt-selection grade (1–5).

## Training

**Program** — The Athlete's training plan, anchored to the target Competition
Event being prepared for. A Program is structured into Blocks, Phases, and
Sessions, and carries the Athlete's competition history, diet notes, supplements,
and lift profiles.

**Block** — A coarse training period within a Program. The active period is the
"current" block; completed periods become named past blocks. Training weeks are
counted within a block, not on the calendar.

**Phase** — A named sub-division of a Block, spanning a block-local week range
with a single training intent (e.g. hypertrophy, strength, peaking). A Block
contains one or more Phases.

**Session** — A single training day within a Program. A Session belongs to a
Block and a Phase, and carries the planned exercises (the intent) and the logged
exercises (what actually happened), plus wellness, RPE, notes, and video
attachments.

**Planned Exercise** — An exercise as intended before a Session: its sets, reps,
load, and RPE target.

**Exercise** — An exercise as logged after a Session: per-set execution state
(completed, failed, skipped, pending), failure reasons, and executed RPE.

**Template** — A reusable Program blueprint. Applying a Template creates a
Program (and records the Template's lineage on it); a Template can also be
generated from a Block.

**Lift Profile** — The per-discipline (squat / bench / deadlift) technique
description and tuning parameters: style, sticking points, primary muscle,
volume tolerance, the e1RM multiplier, the AI-tuned stimulus coefficient, and
INOL thresholds. Used both deterministically (stimulus modifies INOL) and as
context for AI analysis.

## Performance

**Max** — The heaviest load achieved for a lift, scoped to a date range (a
window, a block, or all-time). Because a Max is range-scoped, two Maxes for the
same lift are not comparable unless their ranges match. A Max is resolved from
competition results, logged session tops, or a manual value the Athlete sets.

**Estimated 1RM** — An estimate of a one-rep max derived from a set's load,
reps, and RPE. Distinct from a Max: an Estimated 1RM is a *projection* from
sub-maximal performance, not an achieved load. Backed by a single shared
function, so every interface computes it identically.

**Max History** — The dated record of Maxes over time, with bodyweight and
context, used to track progression.

> Invariant: for the same method and the same date range, every interface must
> produce the same Max or Estimated 1RM. Any divergence between interfaces is a
> bug, fixed by routing both through one shared function.

## Budget

**Budget** — The Athlete's meet-prep financial plan: a set of expense items,
each with a priority (mandatory, important, or optional), in a chosen currency.
Competition-linked mandatory items are never candidates for cutting.

**Budget Item** — A single expense in a Budget, with a cost, date, priority, and
optional media. An item can be flagged as cut (by the Athlete or the AI advisor)
without being deleted.

## Analysis

**Analysis** — The analytics surface over training data. Analysis has
deterministic sections computed from sessions and program data, and AI-generated
reports produced on demand.

**Analysis Section** — A deterministic, computed slice of Analysis. The five
sections are: overview, fatigue readiness, peaking, workload, and alerts.

**Correlation** — An AI report that tests whether accessory-exercise volume
trends correlate with improvements in the competition lifts.

**Program Evaluation** — An AI report that assesses the current training block
against the Athlete's context and the deterministic analytics, producing a
conservative program assessment.
