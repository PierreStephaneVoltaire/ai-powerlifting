## Core goal

Fix optimistic e1RM/projection behavior without making the whole system opaque.

Separate these problems:

1. **Display mismatch**
   - Top card uses frontend Epley trend maxima.
   - Backend projections use backend conservative current maxes.
2. **Estimator bias**
   - Raw training e1RM is consistently too high/low for this athlete.
3. **Projection optimism**
   - Progression slope and future block assumptions are too optimistic, especially around breaks, deloads, tapers, or sparse training weeks.
4. **Platform realization**
   - Gym/training e1RM may be fine, but meet result may realize lower than projected.

Do **not** solve all four with one coefficient.

---

# Implementation Phases

## Phase 0 — e1RM provenance / audit panel

**Purpose:** Before changing formulas, expose exactly where the optimistic number comes from.

**Can be implemented independently:** Yes.

**Depends on:** Nothing.

**Why first:** If the app is $58$ lb optimistic, you need to know whether the error is from:

- frontend Epley display
- backend current max
- projection gain
- peak factor
- PRR / meet realization
- stale competition fallback
- wrong training-week window
- inflated best weekly point

### Backend output to add

Extend `weekly_analysis` with an optional debug/audit object:

```ts
type E1rmAuditSet = {
  date: string
  block?: string
  week_number?: number
  exercise: string
  lift: 'squat' | 'bench' | 'deadlift'
  kg: number
  reps: number
  rpe?: number | null
  source_formula: 'rpe_table' | 'conservative_rep_pct' | 'frontend_epley' | 'competition_result' | 'manual_max'
  raw_e1rm_kg: number
  calibrated_e1rm_kg?: number
  included: boolean
  exclusion_reason?: string
}

type E1rmAuditLift = {
  lift: 'squat' | 'bench' | 'deadlift'
  selected_raw_kg?: number
  selected_calibrated_kg?: number
  selection_method: string
  calibration_multiplier?: number
  qualifying_estimate_count: number
  contributing_sets: E1rmAuditSet[]
}

type E1rmAudit = {
  as_of_date: string
  block?: string
  week_start_day?: string
  window_description: string
  lifts: E1rmAuditLift[]
}
```

### UI

Add an expandable section under Estimated 1RMs:

```text
Why these maxes?
```

Show:

- raw backend e1RM
- calibrated e1RM once calibration exists
- source sets
- frontend Epley max if different
- projection current max if different
- selected method

### Acceptance criteria

- You can identify which exact set caused each current max.
- You can see whether the displayed top-card e1RM differs from backend `current_maxes`.
- You can tell whether a meet projection is optimistic because of current max or future gain.

---

## Phase 1 — training-week semantics hardening

**Purpose:** Make every week-based analytics path respect app-defined training weeks.

**Can be implemented independently:** Mostly yes.

**Depends on:** Nothing, but do before projection changes.

**Important:** Do not use “calendar week” language for block/window logic. Use:

- `training week`
- `block week`
- `positional block week`
- `analysis window`
- `asOfDate`

Exception: ACWR can still require **25 completed-training days / elapsed days**, because that is day-based, not week-boundary-based.

### What to audit

Search for week bucketing in:

- `AnalysisPage.tsx`
- `WeeklyData.tsx`
- `analytics.py`
- `correlation_ai.py`
- `program_evaluation_ai.py`
- export code if applicable
- cache key generation

Replace Monday assumptions where the metric is block/window-based.

### Required helper

Create one shared helper conceptually like:

```ts
type TrainingWeekContext = {
  block: string
  asOfDate: string
  weekStartDay: 'Sunday' | 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday'
  currentWeekNumber: number
}
```

Python equivalent in `analytics.py`:

```python
def resolve_training_week_context(program, as_of_date, block=None):
    """
    Resolve block-specific training week boundaries.

    Rules:
    - Use program.meta.block_week_start_days[block] when available.
    - Fall back to program.meta.program_week_start_day when available.
    - Fall back to Monday only when historical metadata is missing.
    - Never infer week start from block name.
    """
```

### Window behavior to preserve

From your README:

```text
Current Week = block week containing frontend asOfDate
1/2/4/8 modes = positional training weeks before current, including empty gaps
Full Block = Week 1 through current positional block week
```

### Acceptance criteria

- Current Week respects custom block week start.
- Full Block spans positional Week 1 to current positional block week.
- Empty training weeks remain represented as gaps where needed.
- Correlation/program eval cache keys no longer silently assume Monday when block metadata exists.
- No code infers Saturday from block names.

---

## Phase 2 — calibration data model

**Purpose:** Add a place to store athlete/lift-specific e1RM calibration without changing behavior yet.

**Can be implemented independently:** Yes.

**Depends on:** Nothing.

**Recommended location:** `lift_profiles`.

You already store lift-specific behavior there, and e1RM calibration is lift-specific.

### Add fields

```ts
type LiftE1rmCalibrationSource = 'none' | 'manual' | 'auto' | 'hybrid'

type LiftE1rmCalibrationConfidence = 'none' | 'low' | 'medium' | 'high'

type LiftE1rmCalibrationSample = {
  id: string
  date: string
  lift: 'squat' | 'bench' | 'deadlift'
  source: 'competition' | 'mock_meet' | 'gym_test' | 'manual_observation'
  raw_estimated_kg: number
  actual_kg: number
  ratio: number
  weight: number
  notes?: string
}

type LiftProfile = {
  // existing fields
  e1rm_calibration_multiplier?: number
  e1rm_calibration_source?: LiftE1rmCalibrationSource
  e1rm_calibration_confidence?: LiftE1rmCalibrationConfidence
  e1rm_calibration_updated_at?: string
  e1rm_calibration_samples?: LiftE1rmCalibrationSample[]
}
```

### Clamp

Use a conservative clamp:

```text
0.85 <= e1rm_calibration_multiplier <= 1.10
```

Default:

```text
1.00
```

### Acceptance criteria

- Existing programs load without migration failure.
- Missing calibration behaves as multiplier `1.00`.
- Type definitions are updated.
- No analytics behavior changes yet.

---

## Phase 3 — manual e1RM calibration UI

**Purpose:** Let athlete adjust formula bias directly.

**Can be implemented independently:** Depends only on Phase 2.

**Depends on:** Phase 2.

### UI location

Dashboard or Lift Profile editor.

Suggested copy:

```text
e1RM Calibration

Use this if the app consistently overestimates or underestimates your real max
for this lift. This does not change your logged training data. It adjusts the
training max derived from estimated 1RM calculations before downstream analytics
use it.

Multiplier:
1.00 = no adjustment
0.96 = reduce estimates by 4%
1.03 = increase estimates by 3%
```

### UI controls

For each lift:

```text
Squat calibration multiplier: [0.96]
Raw e1RM: 227.5 kg
Adjusted e1RM: 218.5 kg
Source: Manual
Confidence: Low
[Reset to 1.00]
```

Slider/input range:

```text
0.85 to 1.10
step 0.005 or 0.01
```

### Acceptance criteria

- User can set per-lift multiplier.
- Multiplier persists in DynamoDB.
- UI shows raw vs adjusted estimate.
- Reset works.
- No downstream analytics need to use it yet unless Phase 4 is implemented.

---

## Phase 4 — apply calibration to backend current maxes

**Purpose:** Actually use the coefficient.

**Can be implemented independently:** Depends on Phase 2. UI from Phase 3 is optional if values can be edited manually or seeded.

**Depends on:** Phase 2.

### Rule

Preserve raw and calibrated values.

Do **not** overwrite raw e1RM.

```text
calibrated_e1RM = raw_e1RM * e1rm_calibration_multiplier
```

In math:

$calibrated\_e1RM = raw\_e1RM \times C_{lift}$

Where $C_{lift}$ is the per-lift calibration multiplier.

### Backend shape

Instead of only returning:

```ts
current_maxes: {
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
}
```

Add:

```ts
current_maxes_raw?: {
  squat_kg?: number
  bench_kg?: number
  deadlift_kg?: number
  total_kg?: number
}

current_maxes_calibrated?: {
  squat_kg?: number
  bench_kg?: number
  deadlift_kg?: number
  total_kg?: number
}

current_maxes?: {
  squat_kg?: number
  bench_kg?: number
  deadlift_kg?: number
  total_kg?: number
}
```

For backward compatibility:

```text
current_maxes = calibrated current maxes
```

But expose raw clearly.

### Apply calibrated maxes to

Use calibrated current maxes for:

- backend current max display fallback
- RI distribution
- INOL
- fatigue neural intensity scaling for SBD
- readiness performance trend denominator
- meet projection starting max

### Do not apply to

Do not use this as a replacement for:

- PRR
- meet realization
- competition result history
- actual meet results
- logged kg values

### Acceptance criteria

- If multiplier is `1.00`, outputs are unchanged.
- If squat multiplier is `0.96`, raw squat e1RM remains visible and calibrated squat max drops by $4\%$.
- INOL/RI shift appropriately because current max changed.
- Meet projections start from calibrated current max.
- Audit panel shows both values.

---

## Phase 5 — projection conservatism and future training-week adjustment

**Purpose:** Fix optimism caused by progression assumptions, especially around breaks/tapers/deloads/sparse weeks.

**Can be implemented independently:** Yes, but should follow Phase 1.

**Depends on:** Ideally Phase 1. Does not require calibration.

### Current issue

Current skeleton:

```text
n_t = max(0, weeks_to_comp - weeks_taper - planned_deload_weeks)
projected_gain = delta_w * lambda * (1 - lambda^n_t) / (1 - lambda)
```

This can still be optimistic if future productive training exposure is lower than nominal block weeks.

### Replace language

Do not say `calendar weeks`.

Use:

```text
block_weeks_to_comp
future_productive_training_weeks
positional_block_weeks
training_density
planned_taper_weeks
planned_deload_weeks
known_break_weeks
```

### New projection concept

```text
future_productive_training_weeks =
  max(0,
    block_weeks_to_comp * recent_training_density
    - planned_taper_weeks
    - planned_deload_weeks
    - known_break_weeks
  )
```

Then:

```text
projected_gain =
  delta_w
  * slope_confidence_factor
  * lambda
  * (1 - lambda^future_productive_training_weeks)
  / (1 - lambda)
```

In math:

$projected\_gain = \Delta_w \times F_{confidence} \times \lambda \times \frac{1 - \lambda^{n}}{1 - \lambda}$

Where:

- $n$ = future productive training weeks
- $F_{confidence}$ = slope confidence factor

### Recent training density

Use positional block weeks, not calendar weeks.

Example:

```text
recent_training_density =
  effective_training_weeks_observed / positional_training_weeks_observed
```

Clamp:

```text
0.50 <= recent_training_density <= 1.00
```

If insufficient history:

```text
recent_training_density = 0.85
```

### Slope confidence factor

Start simple.

```text
slope_confidence_factor =
  base from qualifying week count
  * fit quality adjustment
  * fatigue/readiness adjustment
```

Example:

```python
def compute_slope_confidence_factor(
    qualifying_weeks,
    kendall_tau,
    fit_quality,
    fatigue_index=None,
    readiness=None,
):
    factor = 1.0

    if qualifying_weeks < 3:
        factor *= 0.40
    elif qualifying_weeks < 5:
        factor *= 0.60
    elif qualifying_weeks < 8:
        factor *= 0.80

    if kendall_tau is not None:
        if kendall_tau < 0.20:
            factor *= 0.70
        elif kendall_tau < 0.40:
            factor *= 0.85

    if fit_quality is not None:
        if fit_quality < 0.30:
            factor *= 0.70
        elif fit_quality < 0.55:
            factor *= 0.85

    if fatigue_index is not None and fatigue_index >= 0.65:
        factor *= 0.85

    if readiness is not None and readiness < 50:
        factor *= 0.85

    return clamp(factor, 0.35, 1.00)
```

### Projection output should expose drivers

```ts
projection_debug: {
  block_weeks_to_comp: number
  future_productive_training_weeks: number
  recent_training_density: number
  planned_taper_weeks: number
  planned_deload_weeks: number
  known_break_weeks: number
  raw_weekly_slope_kg: Record<Lift, number>
  slope_confidence_factor: Record<Lift, number>
  adjusted_weekly_slope_kg: Record<Lift, number>
  raw_projected_gain_kg: Record<Lift, number>
  confidence_adjusted_gain_kg: Record<Lift, number>
}
```

### Acceptance criteria

- Projection says why it reduced projected gain.
- Breaks, deloads, and tapers reduce future productive training weeks.
- Sparse recent training reduces future productive training assumption.
- A high raw slope with low data quality no longer produces huge projected gains.
- No code uses Monday week buckets for this.

---

## Phase 6 — separate meet-realization / PRR from e1RM calibration

**Purpose:** Avoid using meet-day underperformance to corrupt training e1RM unless the athlete chooses that.

**Can be implemented independently:** Mostly yes. It can use existing PRR logic.

**Depends on:** Nothing strictly, but better after Phase 0 audit.

### Distinction

`e1rm_calibration_multiplier` answers:

```text
Are training e1RM estimates biased for this lift?
```

`meet_realization_multiplier` answers:

```text
How much of projected/training strength does the athlete usually realize on the platform?
```

### Suggested fields

Could live under `Program.meta` or a new projection calibration object:

```ts
type MeetRealizationCalibration = {
  squat_multiplier?: number
  bench_multiplier?: number
  deadlift_multiplier?: number
  total_multiplier?: number
  confidence: 'none' | 'low' | 'medium' | 'high'
  sample_count: number
  updated_at?: string
}
```

### Application

Use meet realization for:

- platform projection
- attempt selection
- projection confidence

Do not use it for:

- INOL
- RI distribution
- fatigue model
- training readiness
- current max

### Acceptance criteria

- A bad meet can reduce future platform projection without making training loads look artificially heavier.
- PRR history remains interpretable.
- Athlete can distinguish “my e1RM estimate is too high” from “I do not realize gym strength on the platform.”

---

## Phase 7 — auto-calibration from meets/tests

**Purpose:** Let app infer e1RM calibration after enough evidence.

**Can be implemented independently:** Depends on Phase 2. Better after Phase 6.

**Depends on:** Phase 2. Phase 6 recommended.

### Sample creation

After a competition, mock meet, or gym test:

```text
raw_estimated_kg = backend raw current max near test date
actual_kg = best made lift or tested max
ratio = actual_kg / raw_estimated_kg
```

Math:

$r_i = \frac{actual_i}{estimated_i}$

### Inference formula

Use a prior toward $1.00$ so one sample does not overcorrect.

$C_{lift} = \frac{k \times 1.00 + \sum w_i r_i}{k + \sum w_i}$

Suggested:

```text
k = 2.0
competition sample weight = 1.0
mock meet sample weight = 0.75
gym test sample weight = 0.50
manual observation weight = 0.30
```

Clamp final multiplier:

```text
0.85 to 1.10
```

### User confirmation

Do not silently apply.

Prompt in UI:

```text
The app estimated your squat at 227.5 kg before this meet.
Your best made squat was 217.5 kg.

Observed ratio: 0.956

How should this be used?

[Ignore]
[Use for meet realization only]
[Use for e1RM calibration]
[Use for both]
```

### Acceptance criteria

- App can infer suggested calibration.
- User can accept/reject.
- One bad meet does not drastically rewrite the multiplier.
- Samples are stored and explainable.

---

## Phase 8 — frontend consistency pass

**Purpose:** Reduce confusion from frontend local Epley trends disagreeing with backend current maxes.

**Can be implemented independently:** Yes, but best after Phase 0 or Phase 4.

**Depends on:** Nothing strictly.

### Problem

README says:

```text
Top card prefers local Epley trend maxima.
Backend current maxes use conservative current-max selection.
```

This is likely a major source of “off by $58$ lb” confusion.

### Options

#### Option A — keep both but label clearly

```text
Displayed Training Trend Max
Source: frontend Epley trend

Backend Current Max
Source: conservative RPE/rep estimate, 90th percentile, calibrated
```

#### Option B — make backend current max primary

Recommended if projections are the important thing.

Top card priority becomes:

1. backend calibrated current max
2. backend raw current max
3. frontend local trend fallback only if backend unavailable

Then the trend chart can still show local Epley.

### Acceptance criteria

- User can tell which e1RM drives projections.
- Top card does not silently imply the projection uses the same number if it does not.
- Raw/calibrated/backend/frontend values are distinguishable.

---

## Phase 9 — AI prompt/payload updates

**Purpose:** Make program evaluation aware of calibration and projection uncertainty.

**Can be implemented independently:** After backend exposes calibration/projection debug.

**Depends on:** Phase 4 and/or Phase 5 for useful payload.

### Add to AI payload

```ts
e1rm_calibration: {
  squat: {
    raw_current_kg: number
    calibrated_current_kg: number
    multiplier: number
    source: string
    confidence: string
  }
  bench: ...
  deadlift: ...
}

projection_assumptions: {
  block_weeks_to_comp: number
  future_productive_training_weeks: number
  recent_training_density: number
  taper_weeks: number
  deload_weeks: number
  known_break_weeks: number
  slope_confidence_factors: Record<Lift, number>
  meet_realization?: ...
}
```

### Add prompt instruction

```text
E1RM CALIBRATION & PROJECTION ASSUMPTIONS
- The deterministic analytics may provide both raw and calibrated e1RM values.
- Treat calibrated e1RM as the operational training max when discussing current
  readiness, relative intensity, INOL, and projection starting point.
- Use raw e1RM only when explaining estimator bias or data provenance.
- Projection may include future_productive_training_weeks, recent_training_density,
  taper weeks, deload weeks, known break weeks, and slope confidence factors.
  Use these assumptions when explaining whether the projection is conservative,
  balanced, or optimistic.
- Do not treat a lower calibrated e1RM as regression by itself. It may simply
  be an athlete-specific correction to an over-optimistic formula.
- Keep meet-realization separate from e1RM calibration. Meet realization affects
  platform prediction and attempt strategy; e1RM calibration affects training
  max estimates and downstream load metrics.
```

### Acceptance criteria

- Program Evaluation no longer calls calibrated e1RM drop a performance decline.
- AI can explain projection uncertainty.
- AI does not conflate meet performance with training e1RM formula bias.

---

# Recommended build order

If you want the least messy progressive path:

```text
1. Phase 0 — e1RM audit/provenance
2. Phase 1 — training-week semantics hardening
3. Phase 2 — calibration data model
4. Phase 3 — manual calibration UI
5. Phase 4 — apply calibration to backend current maxes
6. Phase 8 — frontend consistency pass
7. Phase 5 — projection conservatism
8. Phase 6 — meet realization separation
9. Phase 7 — auto-calibration
10. Phase 9 — AI prompt/payload updates
```

If you want fastest practical fix:

```text
1. Phase 2
2. Phase 3
3. Phase 4
4. Phase 0
5. Phase 5
```

But I would still do Phase 0 early because it will tell you whether calibration is actually the right fix.

---

# Copy-paste implementation prompts

Below are direct prompts you can give to a coding agent.

<details>
<summary><strong>Prompt 1 — e1RM audit / provenance</strong></summary>

```text
Implement an e1RM audit/provenance feature for the powerlifting app.

Context:
- The app has frontend-local Epley trend estimates and backend conservative current_maxes.
- The top Estimated 1RMs card can differ from backend current_maxes used by projections and INOL.
- I need to see exactly which sets contributed to backend e1RM selection and why the selected max was chosen.
- Do not change formula behavior in this task.

Requirements:
1. In `tools/health/analytics.py`, extend `weekly_analysis` output with an optional `e1rm_audit` object.
2. The audit must be per lift: squat, bench, deadlift.
3. For each lift include:
   - selected raw e1RM kg
   - selected calibrated e1RM kg if available, otherwise same as raw
   - selection method
   - qualifying estimate count
   - calibration multiplier if available
   - contributing sets
4. Each contributing set must include:
   - date
   - block if available
   - week_number if available
   - exercise name
   - canonical lift
   - kg
   - reps
   - RPE if available
   - formula source: `rpe_table`, `conservative_rep_pct`, `competition_result`, `manual_max`, or other explicit value
   - raw_e1rm_kg
   - calibrated_e1rm_kg if available
   - included boolean
   - exclusion_reason if not included
5. Preserve existing `current_maxes` behavior.
6. Update shared TypeScript types in `packages/types/index.ts`.
7. Add an expandable frontend section under the Estimated 1RMs card in `AnalysisPage.tsx` showing:
   - backend raw max
   - backend calibrated max if available
   - selected method
   - contributing sets table
   - note if frontend Epley trend max differs from backend current max
8. Use app terminology:
   - say `training week`, `block week`, or `positional block week`
   - do not call block windows `calendar weeks`
9. Add safe null handling so older outputs do not break the frontend.

Acceptance criteria:
- Existing analytics values are unchanged.
- The UI can explain exactly where each backend current max came from.
- A user can tell whether the top displayed estimate differs from the backend value used by projections.
```

</details>

<details>
<summary><strong>Prompt 2 — training-week semantics hardening</strong></summary>

```text
Audit and harden training-week semantics across the powerlifting app.

Context:
- This app does not use standard calendar weeks for block analysis.
- The user can define the start day of a training week.
- Sessions have `week` and `week_number`.
- Program meta has `program_week_start_day` and `block_week_start_days`.
- Analysis windows must respect block-specific training weeks.

Rules:
1. Current Week means the block week containing the frontend `asOfDate`.
2. 1/2/4/8 week modes count positional training weeks before current, including empty gaps.
3. Full Block spans Week 1 through the current positional block week.
4. Resolve week start using:
   - `program.meta.block_week_start_days[block]` if present
   - else `program.meta.program_week_start_day` if present
   - else Monday as historical fallback
5. Never infer Saturday or any week start from a block name.
6. Avoid the phrase `calendar week` for analysis windows. Use `training week`, `block week`, or `positional block week`.
7. Day-based metrics like ACWR may still use elapsed days / completed training days.

Tasks:
1. Add or centralize helper(s) for resolving training-week context from program, block, and asOfDate.
2. Update backend `weekly_analysis` window selection to use positional block weeks, not hardcoded Monday buckets.
3. Update frontend Analysis page window logic to match backend semantics.
4. Update AI cache keys for correlation/program evaluation where Monday-aligned keys are currently used, unless compatibility requires preserving old keys. If preserving, add a migration-compatible key that includes block week start.
5. Update labels and comments to remove incorrect `calendar week` language.
6. Add tests or test cases for:
   - Monday-start block
   - Saturday-start block
   - missing block-specific value falling back to program week start
   - missing all values falling back to Monday
   - Current Week with `asOfDate`
   - Full Block with empty positional weeks

Acceptance criteria:
- Current Week, rolling windows, and Full Block agree between frontend and backend.
- Empty training weeks are represented when positional windows include them.
- No block analysis path silently assumes Monday when block metadata exists.
```

</details>

<details>
<summary><strong>Prompt 3 — e1RM calibration schema</strong></summary>

```text
Add data-model support for per-lift e1RM calibration without changing analytics behavior yet.

Context:
- The app needs athlete/lift-specific calibration because raw e1RM estimates can be consistently optimistic or pessimistic.
- Calibration belongs per lift: squat, bench, deadlift.
- Existing programs must keep working with default multiplier 1.00.

Tasks:
1. Update `packages/types/index.ts` LiftProfile type with:
   - `e1rm_calibration_multiplier?: number`
   - `e1rm_calibration_source?: 'none' | 'manual' | 'auto' | 'hybrid'`
   - `e1rm_calibration_confidence?: 'none' | 'low' | 'medium' | 'high'`
   - `e1rm_calibration_updated_at?: string`
   - `e1rm_calibration_samples?: LiftE1rmCalibrationSample[]`
2. Add `LiftE1rmCalibrationSample` type:
   - `id: string`
   - `date: string`
   - `lift: 'squat' | 'bench' | 'deadlift'`
   - `source: 'competition' | 'mock_meet' | 'gym_test' | 'manual_observation'`
   - `raw_estimated_kg: number`
   - `actual_kg: number`
   - `ratio: number`
   - `weight: number`
   - `notes?: string`
3. Add backend sanitization/normalization:
   - missing multiplier = 1.00
   - clamp multiplier to 0.85-1.10
   - missing source = `none`
   - missing confidence = `none`
4. Ensure DynamoDB persistence accepts these fields.
5. Do not apply the multiplier to current maxes yet in this task.
6. Add type-safe helpers where useful:
   - `getLiftE1rmCalibrationMultiplier(program, lift)`
   - `normalizeLiftE1rmCalibration(profile)`

Acceptance criteria:
- Existing programs load with no migration errors.
- Missing calibration behaves as 1.00.
- Saving lift profiles preserves calibration fields.
- No analytics numbers change yet.
```

</details>

<details>
<summary><strong>Prompt 4 — manual e1RM calibration UI</strong></summary>

```text
Implement manual per-lift e1RM calibration controls.

Context:
- Calibration fields already exist on lift profiles.
- The athlete needs to manually reduce or increase raw e1RM estimates when the formula is consistently biased.
- This task should persist calibration values but does not need to implement auto-calibration.

UI requirements:
1. Add controls in the Dashboard lift-profile area or equivalent lift profile editor.
2. For squat, bench, and deadlift show:
   - current multiplier
   - source
   - confidence
   - updated_at if present
   - raw current e1RM if available
   - adjusted current e1RM preview if available
3. Allow manual multiplier input:
   - min 0.85
   - max 1.10
   - step 0.005 or 0.01
   - default 1.00
4. On save:
   - set `e1rm_calibration_multiplier`
   - set `e1rm_calibration_source = 'manual'`
   - set `e1rm_calibration_confidence = 'low'` unless user-selected confidence is supported
   - set `e1rm_calibration_updated_at`
5. Add reset button:
   - multiplier 1.00
   - source `none`
   - confidence `none`
6. User-facing copy:
   "Use this if the app consistently overestimates or underestimates your real max for this lift. This does not change your logged training data. It adjusts derived e1RM values before downstream analytics use them."

Acceptance criteria:
- User can manually set and save per-lift calibration.
- Reset works.
- Existing lift profile save paths do not drop calibration fields.
- UI clearly explains 1.00, below 1.00, and above 1.00.
```

</details>

<details>
<summary><strong>Prompt 5 — apply calibration to backend current maxes</strong></summary>

```text
Apply per-lift e1RM calibration to backend current maxes while preserving raw estimates.

Context:
- Lift profiles may now contain `e1rm_calibration_multiplier`.
- Raw e1RM estimates must remain visible.
- Calibrated e1RM should become the operational current max used by downstream training analytics.

Rules:
1. Raw e1RM is computed exactly as before.
2. Calibrated e1RM = raw e1RM * per-lift calibration multiplier.
3. Missing multiplier means 1.00.
4. Clamp multiplier to 0.85-1.10.
5. Do not mutate logged sets or raw estimate history.
6. Do not apply meet-realization / PRR here.

Backend tasks:
1. Update current max selection in `tools/health/analytics.py` to return both:
   - `current_maxes_raw`
   - `current_maxes_calibrated`
2. Keep existing `current_maxes` key for backward compatibility and set it to calibrated values.
3. Include calibration multiplier and source in e1RM audit if audit exists.
4. Use calibrated current maxes in:
   - INOL
   - RI distribution
   - fatigue neural intensity scaling for canonical SBD lifts
   - readiness performance trend denominator
   - meet projection starting max
5. Preserve real competition result behavior:
   - actual meet results are actuals, not formula estimates
   - if competition result is used as current max, multiplier should not reduce the actual result unless there is a clear reason in existing logic
   - document the chosen behavior in code comments
6. Update types and frontend null handling.

Acceptance criteria:
- With all multipliers at 1.00, outputs are unchanged.
- Setting squat multiplier to 0.96 reduces backend calibrated squat current max by 4%.
- Raw and calibrated values are both returned.
- Downstream RI/INOL/projection use calibrated max.
- Audit/provenance makes the adjustment visible.
```

</details>

<details>
<summary><strong>Prompt 6 — projection conservatism using training weeks</strong></summary>

```text
Make meet projection less optimistic by using future productive training weeks and slope confidence.

Context:
- The app uses program/block-defined training weeks, not standard calendar weeks.
- Projection currently subtracts taper and deload weeks but can still be too optimistic.
- Progression slope should be dampened when data quality, training density, fit quality, or fatigue context is weak.

Terminology:
- Use `training week`, `block week`, `positional block week`, and `future productive training weeks`.
- Do not call block windows `calendar weeks`.

Tasks:
1. In `tools/health/analytics.py`, update meet projection to compute:
   - `block_weeks_to_comp`
   - `recent_training_density`
   - `planned_taper_weeks`
   - `planned_deload_weeks`
   - `known_break_weeks`
   - `future_productive_training_weeks`
2. Compute recent training density as:
   effective training weeks observed / positional training weeks observed
   using app-defined block week semantics.
3. Clamp recent training density to 0.50-1.00 when enough data exists.
4. Use fallback density 0.85 when data is insufficient.
5. Add slope confidence factor per lift using:
   - qualifying week count
   - Kendall tau
   - fit quality
   - fatigue index if available
   - readiness if available
6. Clamp slope confidence factor to 0.35-1.00.
7. Modify projected gain:
   projected_gain = raw_slope * slope_confidence_factor * lambda decay over future_productive_training_weeks
8. Add `projection_debug` output:
   - block_weeks_to_comp
   - future_productive_training_weeks
   - recent_training_density
   - planned_taper_weeks
   - planned_deload_weeks
   - known_break_weeks
   - raw weekly slope per lift
   - slope confidence factor per lift
   - adjusted weekly slope per lift
   - raw projected gain per lift
   - confidence-adjusted gain per lift
9. Keep ceiling clamp after adjusted projected gain.
10. Update frontend Projection card to optionally show "Projection assumptions" in an expandable section.

Acceptance criteria:
- Projection output explains why projected gain was dampened.
- Sparse recent training reduces future productive training weeks.
- Low-quality slope reduces projected gain.
- Taper/deload/break weeks reduce productive weeks.
- No Monday-specific week bucketing is introduced.
```

</details>

<details>
<summary><strong>Prompt 7 — meet realization separation</strong></summary>

```text
Separate meet-realization calibration from e1RM calibration.

Context:
- e1RM calibration corrects training estimate bias.
- Meet realization corrects platform projection bias.
- A poor meet should not automatically make all training loads look heavier.

Tasks:
1. Add a meet-realization calibration structure, either in program meta or analytics output:
   - squat_multiplier
   - bench_multiplier
   - deadlift_multiplier
   - total_multiplier
   - confidence
   - sample_count
   - updated_at
2. Use existing PRR data where possible to infer meet realization.
3. Apply meet realization only to:
   - platform projection
   - attempt selection
   - projection confidence
4. Do not apply meet realization to:
   - current max
   - INOL
   - RI distribution
   - fatigue model
   - readiness
5. Update projection output to show:
   - training projected max
   - platform projected max
   - meet realization multiplier
6. Update frontend labels:
   - "Projected training max"
   - "Projected platform max"
   - "Meet realization adjustment"
7. Add code comments explaining the distinction.

Acceptance criteria:
- e1RM calibration and meet realization are separate values.
- PRR/meet history can lower platform projection without changing training current max.
- Attempt selection uses platform projection.
- INOL/RI still use calibrated training current max, not meet realization.
```

</details>

<details>
<summary><strong>Prompt 8 — auto-calibration from meet/test results</strong></summary>

```text
Implement suggested e1RM auto-calibration from meet, mock meet, or gym test results.

Context:
- Lift profiles have e1RM calibration fields and sample history.
- Raw estimates should be compared to actual known outcomes.
- The app should suggest calibration but not silently apply it.

Tasks:
1. Create a helper to generate calibration samples:
   ratio = actual_kg / raw_estimated_kg
2. Supported sources:
   - competition
   - mock_meet
   - gym_test
   - manual_observation
3. Suggested sample weights:
   - competition: 1.00
   - mock_meet: 0.75
   - gym_test: 0.50
   - manual_observation: 0.30
4. Implement inferred multiplier:
   C = (k * 1.00 + sum(weight_i * ratio_i)) / (k + sum(weight_i))
   with k = 2.0
5. Clamp inferred multiplier to 0.85-1.10.
6. Add UI after saving post-meet report or test result:
   "The app estimated your squat at X kg. Your actual result was Y kg. Observed ratio: Z. How should this be used?"
   Buttons:
   - Ignore
   - Use for meet realization only
   - Use for e1RM calibration
   - Use for both
7. If user accepts e1RM calibration:
   - append sample to lift profile
   - recompute multiplier
   - set source `auto` or `hybrid`
   - update confidence based on sample count and total weight
8. If user accepts meet realization:
   - update meet-realization calibration, not e1RM calibration
9. Do not apply automatically without user confirmation.

Acceptance criteria:
- App can suggest calibration from real outcomes.
- User chooses how to apply the observed ratio.
- One bad meet has limited effect because of the prior.
- e1RM calibration and meet realization remain separate.
```

</details>

<details>
<summary><strong>Prompt 9 — frontend max display consistency</strong></summary>

```text
Make e1RM display consistent and transparent on the Analysis page.

Context:
- The top Estimated 1RMs card currently prefers frontend-local Epley trend maxima.
- Backend projections and INOL use backend current_maxes.
- This causes confusion when the displayed e1RM is not the same number driving analytics.

Tasks:
1. Update Estimated 1RMs card to clearly separate:
   - backend calibrated current max
   - backend raw current max
   - frontend local Epley trend max, if present
2. Decide whether the primary displayed value should be backend calibrated current max.
   Preferred behavior:
   - primary value = backend calibrated current max
   - secondary/trend value = frontend local Epley trend max
3. Add source labels:
   - "Used by projections"
   - "Raw backend estimate"
   - "Local Epley trend"
4. If values differ by more than a threshold, show a note:
   "These values differ because the trend chart uses local Epley estimates while projections use backend calibrated current maxes."
5. Add expandable audit/provenance table if available.
6. Keep existing trend chart behavior unless intentionally changed.
7. Update `formulaDescriptions.ts` and `AboutPage.tsx` if user-facing formula descriptions change.

Acceptance criteria:
- User can immediately tell which e1RM drives projections.
- Display no longer implies frontend Epley value is the backend current max.
- Raw and calibrated values are visible.
- Existing local trend chart remains usable.
```

</details>

<details>
<summary><strong>Prompt 10 — AI prompt/payload update for calibration</strong></summary>

```text
Update program evaluation AI payload and prompt to understand e1RM calibration and projection assumptions.

Context:
- Deterministic analytics may now expose raw and calibrated e1RM.
- Meet projection may expose future productive training weeks, training density, slope confidence factors, and meet-realization multipliers.
- AI must not confuse calibration with regression.

Tasks:
1. Add to program evaluation payload:
   `e1rm_calibration` per lift:
   - raw_current_kg
   - calibrated_current_kg
   - multiplier
   - source
   - confidence
2. Add to payload:
   `projection_assumptions`:
   - block_weeks_to_comp
   - future_productive_training_weeks
   - recent_training_density
   - taper_weeks
   - deload_weeks
   - known_break_weeks
   - slope_confidence_factors
   - meet_realization if available
3. Update `program_evaluation_ai.py` prompt with this instruction:

E1RM CALIBRATION & PROJECTION ASSUMPTIONS
- The deterministic analytics may provide both raw and calibrated e1RM values.
- Treat calibrated e1RM as the operational training max when discussing current readiness, relative intensity, INOL, and projection starting point.
- Use raw e1RM only when explaining estimator bias or data provenance.
- Projection may include future_productive_training_weeks, recent_training_density, taper weeks, deload weeks, known break weeks, and slope confidence factors. Use these assumptions when explaining whether the projection is conservative, balanced, or optimistic.
- Do not treat a lower calibrated e1RM as regression by itself. It may simply be an athlete-specific correction to an over-optimistic formula.
- Keep meet-realization separate from e1RM calibration. Meet realization affects platform prediction and attempt strategy; e1RM calibration affects training max estimates and downstream load metrics.
- Use app-defined training weeks / block weeks. Do not describe these as standard calendar weeks.

4. Update schema/output only if needed.
5. Ensure cached program evaluations invalidate when calibration fields change.

Acceptance criteria:
- AI explanations mention calibration correctly when relevant.
- AI does not call calibration-driven reductions performance losses.
- AI distinguishes training max, platform projection, and meet realization.
```

</details>

---

# What I would implement independently vs together

## Safe independent tasks

These can be done without disturbing core formulas much:

- Phase 0: e1RM audit/provenance
- Phase 1: training-week semantics hardening
- Phase 2: calibration schema
- Phase 3: manual calibration UI
- Phase 8: frontend display consistency
- Phase 9: AI prompt update, once payload exists

## Should be bundled carefully

These touch downstream analytics and should be tested together:

- Phase 4: applying calibration to current maxes
- Phase 5: projection conservatism
- Phase 6: meet realization separation

## Should come later

- Phase 7: auto-calibration

Reason: auto-calibration is easy to make misleading before the raw/calibrated/projection distinction is clear.

---

# My recommendation for your immediate problem

Given “projection/e1RM is about $58$ lb too optimistic,” I would not start with auto-calibration.

Do this first:

```text
Phase 0: Audit
Phase 2: Calibration schema
Phase 3: Manual multiplier
Phase 4: Apply calibrated current max
Phase 5: Projection dampening
```

That gives you both knobs you likely need:

1. **Formula bias correction**
   - `e1rm_calibration_multiplier`
2. **Projection optimism correction**
   - `future_productive_training_weeks`
   - `slope_confidence_factor`

Those are separate fixes, and they should stay separate.