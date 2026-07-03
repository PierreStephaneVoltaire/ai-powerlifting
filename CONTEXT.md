# Context — Powerlifting Meet-Prep Portal (NoLift)

The ubiquitous-language glossary for the powerlifting meet-prep domain. This is a
glossary only: it defines what the domain terms *mean*, not how they are stored,
typed, or computed. Implementation details live in `docs/ARCHITECTURE.md` and the
code.

The portal is a competition-geared meet-prep notebook: an athlete is always
preparing for a meet, and the meet provides the standards and timeline that
anchor everything else.

## People & Roles

**Person** — The human behind a login. A Person holds the Athlete role on their
own data and may additionally hold Coach or Handler grants on other Athletes'
data — one human can be all three at once (e.g. an operator who competes,
coaches a teammate, and handles another at their meet). Switching role changes
which context the Person is acting in, not who they are.

**Athlete** — The owning role. The Athlete is the one who trains and prepares
for Competition Events, and the Athlete's data (Program, Sessions, Analysis,
Budget, Competitions, etc.) belongs to the Athlete. The Athlete has full read
and write to their own data and the full app. Today the portal serves the
Athlete only. *The Athlete is the only role with its own screens and data.*

> Ownership invariant: all training data belongs to the Athlete. A Coach or
> Handler never owns data; they act on an Athlete's data under a grant the
> Athlete issues, and writes they make become the Athlete's data.

**Coach** and **Handler** are not peer roles to Athlete; they are **grant-types**
— named bundles of granular read/write permissions that an Athlete issues to
another Person. Both are tied to one or more specific Competition Events the
Athlete chooses at grant time (a block can target multiple competitions). A
grant ends when the Athlete revokes it, or when all tied competitions have
passed — expiry is `max(tied competition dates) + 7 days`. An Athlete has at
most one active Coach grant and one active Handler grant at a time. Grants are
between distinct Persons (an Athlete already has total access to their own data,
so self-granting a Coach or Handler bundle grants nothing).

**Coach grant** — The broader bundle: scoped read and write on the Athlete's
training data, used for cycle-long collaboration. A Person holding a Coach grant
operates inside the Athlete's screens on the Athlete's data, plus a roster page
listing the Athletes they currently coach. *Planned (roadmap).*

**Handler grant** — The narrower, comp-day bundle: read on Sessions and Budget,
read and write on Competitions and Attempt Selection, plus comp-day tools
(timers, notes, equipment and rule checklists) and the block data needed as
context for modifying attempts. A Person holding a Handler grant operates inside
a trimmed, comp-day-focused view, plus a roster page listing the Athletes they
currently handle. *Planned (roadmap).*

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
