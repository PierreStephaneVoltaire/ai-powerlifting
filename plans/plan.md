
## Goal

Add a simple per-lift multiplier:

```text
adjusted_e1RM = raw_e1RM * multiplier
```

Where default multiplier is:

```text
1.00
```

Example:

```text
Raw squat e1RM: 500 lb
Multiplier: 0.96
Adjusted squat e1RM: 480 lb
```

Use this to correct formulas that are consistently too optimistic or pessimistic for the athlete.

---

# Phase 1 — Add minimal multiplier fields

**Can be implemented independently:** Yes.

**Purpose:** Store one multiplier per lift.


## Data model

Add these fields to each `LiftProfile`:

```ts
type LiftProfile = {
  // existing fields...

  e1rm_multiplier?: number
  e1rm_multiplier_updated_at?: string
  e1rm_multiplier_note?: string
}
```

Rules:

```text
missing multiplier = 1.00
minimum = 0.85
maximum = 1.10
```

That’s it.

## Prompt

```text
Implement minimal per-lift e1RM multiplier storage.

Context:
The powerlifting app needs a simple athlete/lift-specific multiplier to correct
raw e1RM estimates when they are consistently too optimistic or pessimistic.

Do not add source enums, sample models, mock meet concepts, or calibration
history in this task.

Tasks:
1. Update `packages/types/index.ts` so each `LiftProfile` can optionally store:
   - `e1rm_multiplier?: number`
   - `e1rm_multiplier_updated_at?: string`
   - `e1rm_multiplier_note?: string`
2. Add helper logic wherever lift profiles are normalized:
   - missing `e1rm_multiplier` means `1.00`
   - clamp saved values to `0.85` through `1.10`
3. Ensure existing programs load without migration errors.
4. Ensure saving lift profiles preserves these fields.
5. Do not change analytics formulas yet.

Acceptance criteria:
- Existing programs behave exactly the same.
- Missing multiplier acts as `1.00`.
- Multipliers persist correctly in DynamoDB.
- No analytics output changes in this phase.
```

---

# Phase 2 — Add manual UI control

**Can be implemented independently:** Depends only on Phase 1.

**Purpose:** Let the athlete/coach set the multiplier manually.

This is the main useful feature.

## UI behavior

In the lift profile area, show for each lift:

```text
Squat e1RM multiplier: 0.96
Raw e1RM: 500 lb
Adjusted e1RM: 480 lb
```

User copy:

```text
Use this if the app consistently overestimates or underestimates your real max
for this lift. 1.00 means no adjustment. 0.96 lowers estimates by 4%.
```

## Prompt

```text
Add manual e1RM multiplier controls to the lift profile UI.

Context:
Each lift profile may now contain:
- `e1rm_multiplier`
- `e1rm_multiplier_updated_at`
- `e1rm_multiplier_note`

The multiplier is simple:
adjusted e1RM = raw e1RM * multiplier.

Tasks:
1. In the Dashboard or lift profile editor, add one control per lift:
   - squat
   - bench
   - deadlift
2. The control should allow values from `0.85` to `1.10`.
3. Default display should be `1.00` when missing.
4. Add explanatory copy:
   "Use this if the app consistently overestimates or underestimates your real
   max for this lift. 1.00 means no adjustment. 0.96 lowers estimates by 4%."
5. On save:
   - persist `e1rm_multiplier`
   - set `e1rm_multiplier_updated_at` to the current timestamp
   - optionally save `e1rm_multiplier_note`
6. Add a reset button that sets multiplier back to `1.00`.
7. If raw backend current maxes are available on the page, show a preview:
   - raw e1RM
   - adjusted e1RM

Do not implement auto-inference in this task.
Do not change analytics usage yet unless Phase 3 is also being implemented.

Acceptance criteria:
- Athlete/coach can manually set squat, bench, and deadlift multipliers.
- Values persist.
- Reset works.
- UI is understandable without explaining a complex calibration system.
```

---

# Phase 3 — Apply multiplier to backend e1RM/current maxes

**Can be implemented independently:** Depends on Phase 1. Phase 2 is useful but not required.

**Purpose:** Make the multiplier actually affect analysis.

## Formula

$adjusted\_e1RM = raw\_e1RM \times multiplier$

## Recommended behavior

Keep both raw and adjusted values.

Return:

```ts
current_maxes_raw
current_maxes_adjusted
current_maxes
```

For compatibility:

```text
current_maxes = current_maxes_adjusted
```

## Use adjusted current maxes for

- displayed backend current maxes
- meet projection starting max
- RI distribution
- INOL
- fatigue neural intensity scaling for SBD lifts
- readiness performance trend denominator

## Important

If a current max comes from an actual completed competition result, do **not** multiply it down. That is already a real result.

So:

```text
session-estimated e1RM -> apply multiplier
manual max / comp result -> probably do not apply multiplier
```

Manual maxes and comp results are already athlete-specific reality.

## Prompt

```text
Apply per-lift e1RM multipliers to backend session-derived current maxes.

Context:
Lift profiles now support:
- `e1rm_multiplier?: number`

The multiplier should adjust raw session-derived e1RM estimates:
adjusted_e1RM = raw_e1RM * multiplier.

Rules:
1. Missing multiplier means `1.00`.
2. Clamp multiplier to `0.85` through `1.10`.
3. Preserve raw values.
4. Do not mutate logged training data.
5. Do not apply the multiplier to actual completed competition results.
6. Do not apply the multiplier to manual maxes unless the existing code treats
   manual maxes as estimates. Prefer treating manual maxes as already adjusted
   athlete-provided truth.

Backend tasks:
1. In `tools/health/analytics.py`, update current max calculation so each lift has:
   - raw session-derived estimate
   - adjusted session-derived estimate
   - multiplier used
2. Return:
   - `current_maxes_raw`
   - `current_maxes_adjusted`
   - existing `current_maxes`, set to adjusted values for backward compatibility
3. Use adjusted current maxes in downstream analytics:
   - INOL
   - relative intensity distribution
   - SBD neural fatigue intensity scaling
   - readiness performance trend denominator
   - meet projection starting max
4. Keep actual competition results as actual values.
5. Update TypeScript types.
6. Update the Analysis page to label raw vs adjusted values where both are present.

Acceptance criteria:
- With multipliers at `1.00`, analytics output is unchanged.
- Setting squat multiplier to `0.96` lowers session-derived squat current max by 4%.
- Raw e1RM remains visible somewhere in the output.
- Projections use adjusted current maxes.
- Actual meet results are not incorrectly reduced by the multiplier.
```

---

# Phase 4 — Add simple auto-suggest from existing comps and max history

**Can be implemented independently:** Depends on Phase 3 if you want meaningful raw-vs-actual comparison. Can be implemented after Phase 1 if only generating suggestions.

**Purpose:** Suggest a multiplier using data the app already has.

Use only existing concepts:

- completed `Competition.results`
- `post_meet_report` best made attempts through compatibility `results`
- `max_history`
- maybe `manual_maxes`

No mock meet. No gym test abstraction. No new source taxonomy.

## How inference works

For each lift, compare known actual result against raw estimate near that date.

```text
ratio = actual_kg / raw_estimated_kg
```

Math:

$ratio = \frac{actual\_kg}{raw\_estimated\_kg}$

Example:

```text
Raw pre-meet squat estimate: 227.5 kg
Actual squat result: 217.5 kg
Suggested multiplier: 217.5 / 227.5 = 0.956
```

If multiple usable data points exist, use recent weighted average or median.

Simple version:

```text
suggested_multiplier = median(last 3 usable ratios)
```

Clamp:

```text
0.85 to 1.10
```

Do **not** auto-apply. Show suggestion.

## UI copy

```text
Suggested from recent results: 0.956

The app estimated this lift higher than the result/max you recorded.
Apply this as the new multiplier?
```

Buttons:

```text
Ignore
Apply suggestion
```

That’s enough.

## Prompt

```text
Implement simple e1RM multiplier suggestions from existing competition results
and max history.

Context:
The app already has:
- `program.competitions[].results`
- optional `post_meet_report`, while compatibility results remain in `results`
- `max_history`
- `manual_maxes`

Do not add mock meet, gym test, source enums, or a calibration sample system.

Goal:
For each lift, suggest a multiplier by comparing known actual results/maxes
against raw session-derived e1RM estimates near the same date.

Formula:
ratio = actual_kg / raw_estimated_kg

Tasks:
1. Add backend helper to compute suggested multiplier per lift.
2. Data sources:
   - completed competition results
   - max_history entries
   - manual maxes if they have enough date/context to compare safely
3. For each usable actual:
   - find or recompute raw session-derived e1RM estimate as of that date
   - do not use already-adjusted e1RM for this comparison
   - compute ratio = actual_kg / raw_estimated_kg
4. Ignore unusable comparisons:
   - missing actual
   - missing raw estimate
   - raw estimate <= 0
   - ratio outside a sanity range, e.g. below `0.80` or above `1.15`
5. For each lift, suggest:
   - `suggested_multiplier`
   - `current_multiplier`
   - `difference`
   - `basis`, a short human-readable explanation
6. Use a simple recent median:
   - use up to the latest 3 usable ratios per lift
   - suggested multiplier = median of those ratios
   - clamp final suggestion to `0.85` through `1.10`
7. Add frontend UI near the manual multiplier controls:
   - show suggested multiplier if available
   - show basis/explanation
   - button: `Apply suggestion`
   - button: `Ignore`
8. Applying the suggestion simply writes it to `e1rm_multiplier`,
   updates `e1rm_multiplier_updated_at`, and optionally writes a short note.
9. Do not auto-apply without user action.

Acceptance criteria:
- The app can suggest a simple multiplier from completed comps and max history.
- User can apply or ignore the suggestion.
- Suggestion uses raw estimates, not already-adjusted estimates.
- No new abstract event types are introduced.
```

---

# Phase 5 — Projection optimism fix, separate from e1RM multiplier

**Can be implemented independently:** Yes, but it should happen after Phase 3 if projections now use adjusted maxes.

**Purpose:** If the estimate is still too optimistic after the multiplier, the issue is likely projected gain, not current e1RM.

Keep this separate.

Do **not** add another user-facing complex calibration model.

## Simple fix

Add a projection gain dampener based on confidence.

Current projection roughly does:

```text
projected_gain = slope-based gain over remaining training weeks
```

Change to:

```text
projected_gain = raw_projected_gain * projection_confidence_factor
```

Where:

```text
projection_confidence_factor = 0.50 to 1.00
```

Based on simple things you already have:

- number of effective weeks behind the slope
- fit quality
- Kendall tau
- upcoming taper weeks
- planned deload/break weeks
- current fatigue/readiness

This is not the same as e1RM multiplier.

- e1RM multiplier corrects current estimate.
- projection confidence corrects future optimism.

## Prompt

```text
Add a simple projection confidence factor to reduce optimistic meet projections.

Context:
The app already computes progression rate and meet projection.
The issue is that projected gains can be too optimistic, especially when the
slope is based on limited data, weak fit, breaks, deloads, or taper context.

Do not change week semantics in this task unless required by existing helpers.
Use the app's existing training-week/block-week logic.

Goal:
Keep current projection formula, but multiply projected future gain by a
confidence factor.

Formula:
adjusted_projected_gain = raw_projected_gain * projection_confidence_factor

Tasks:
1. In `tools/health/analytics.py`, compute `projection_confidence_factor` per lift.
2. Use existing data:
   - qualifying effective week count
   - Kendall tau
   - fit quality
   - planned deload weeks
   - taper weeks
   - known break weeks if already detected
   - fatigue index if available
   - readiness if available
3. Start with simple rules:
   - fewer than 3 qualifying effective weeks: factor <= 0.50
   - 3-4 qualifying effective weeks: factor <= 0.65
   - 5-7 qualifying effective weeks: factor <= 0.80
   - 8+ qualifying effective weeks: factor can be up to 1.00
   - weak Kendall tau or weak fit lowers factor
   - high fatigue or low readiness lowers factor slightly
4. Clamp final factor to `0.50` through `1.00`.
5. Apply only to future projected gain, not current max:
   - projected_comp_max = adjusted_current_max + adjusted_projected_gain
6. Keep existing ceiling clamp after this adjustment.
7. Return debug fields:
   - raw_projected_gain_kg
   - projection_confidence_factor
   - adjusted_projected_gain_kg
   - reasons
8. Frontend should show an expandable explanation:
   "Projected gain was reduced because the trend has limited supporting data /
   weak fit / taper or break context."

Acceptance criteria:
- Current max is not changed by projection confidence.
- Future gain is reduced when trend confidence is low.
- Projection card explains the reduction.
- With strong trend data and good fit, projection remains close to old behavior.
```

---

# Recommended order

If you want the fastest useful path:

```text
1. Phase 1 — minimal multiplier fields
2. Phase 2 — manual UI
3. Phase 3 — apply multiplier to backend current maxes
4. Phase 4 — auto-suggest from comps/max history
5. Phase 5 — projection confidence factor
```
---
