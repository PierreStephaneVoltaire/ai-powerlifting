# Exercise ROI Correlation → Main-Lift Drivers

Goal: one report that tells a coach what in the program helps or hurts Squat, Bench and Deadlift, with enough numbers to act on. Only effects on the three main lifts matter. No trivia, no stats dump.

## Problem today

- The AI gets weekly e1RM plus one `volume_kg` number per accessory. Nothing else.
- It never sees sets, reps, intensity, RPE, frequency, muscles, fatigue profile, lift transfer, or session order.
- The "ROI table" block in `correlation_user.tmpl` is never filled.
- Result: findings read exercises in a vacuum ("glute and quad loading") with no dose, no intensity, no sequencing, weak reasoning and generic caveats.

## Decision: one report, one table (no new section)

The existing "Exercise ROI Correlation" card stays where it is. Its finding model changes from "accessory ↔ lift" to "driver ↔ lift". There are three driver types, all in the same table:

| driver_type | Example | Catches |
|---|---|---|
| `exercise` | Romanian Deadlift → deadlift | direct carryover, dose that is too low or too high |
| `muscle` | Core (6 sets/wk, below MEV) → squat | weak links nobody trains (core, upper back), muscles over MRV that add systemic/neural fatigue |
| `sequence` | Heavy hinge day before squat day → squat | residual fatigue: axial/erector load in the 48 h before a main-lift session |

## Data added to `CorrelationInputsReply` (pl-analytics, Rust)

All values are deterministic and computed from existing calcs (`calc/fatigue.rs`, `calc/muscle_volume.rs`, `calc/lift_breakdown.rs`, `calc/e1rm.rs`, glossary). Main lifts are included as well, because their own dose is the main confound.

1. `exercise_weeks`: one row per week × exercise, with:
   - `sets`, `reps`, `volume_kg`, `sessions` (frequency that week)
   - `avg_intensity_pct`: % of that exercise's e1RM (glossary e1RM for non-SBD); absent if unknown
   - `avg_rpe`: absent if none logged
2. `exercises`: one row per exercise trained in the window, with:
   - `primary_muscles`, `secondary_muscles`
   - `fatigue` {axial, neural, peripheral, systemic}: glossary `fatigue_profile`, else the calc default
   - `lift_transfer` {squat, bench, deadlift} and `transfer_source` (ai / rule / none)
3. `muscle_weeks` (week × muscle, weighted sets: primary 1.0, secondary 0.5) and `muscle_landmarks` (muscle → MEV, MAV, MRV, from `data/muscle_landmarks.json`).
4. `fatigue_weeks`: week × {axial, neural, peripheral, systemic}, as a ratio to the athlete's chronic weekly baseline (1.0 = typical week).
5. `lift_sessions`: one row per main-lift session, with:
   - `date`, `lift`, `top_e1rm_kg`
   - `e1rm_residual_pct`: vs the trailing 3-session best of that lift
   - `avg_rpe`
   - `prior48h_fatigue` {axial, neural, peripheral, systemic}: ratio to the typical daily load
   - `prior48h_muscle_sets`: muscle → weighted sets, only muscles with sets > 0
6. `driver_stats`: precomputed evidence, so the model does not do statistics.
   - `exercise` and `muscle` drivers: Spearman ρ of weekly sets vs the next week's e1RM change of the lift, with `n` weeks. Only for exercises with transfer ≥ 0.2 to that lift, or muscles that are primary movers of it.
   - `sequence` drivers, per lift and fatigue dimension: mean `e1rm_residual_pct` and mean RPE for sessions with `prior48h` ≥ 1.25 vs < 1.25, with `n_high` and `n_low`.

Payload limits: at most 20 exercises (transfer-weighted sets, descending) plus the three main lifts. Muscles only if sets > 0 or they are a primary mover of a main lift.

## Prompt (pl-analytics-ai, Go `text/template`)

Rewrite `correlation_system.tmpl` and `correlation_user.tmpl`. Keep the good rules: weeks with gaps are normal, never editorialize about program style, nothing generic, no causation disclaimer, never repeat a caveat.

New rules:
- Judge each driver by dose: frequency × sets × intensity/RPE, not presence.
- Use the fatigue profile and session order. A high-axial or erector-heavy session in the 48 h before a squat or deadlift session is a candidate `hurts` driver; use `lift_sessions` and the `sequence` `driver_stats` as evidence.
- Use the muscle landmarks:
  - A main-lift mover or stabilizer (core, upper back, erectors) below MEV, tied to a sticking point or lift profile, is a candidate weak link.
  - A muscle above MRV is a candidate source of systemic/neural fatigue.
- Use `lift_transfer` and muscles for plausibility. This replaces the hard-coded example list.
- Every finding cites numbers from the payload in `evidence`. A finding with no numbers is not allowed.
- Every finding gives one concrete `action` (what to change, by how much, and where in the week), or `"Keep as is"` when the evidence says it works.
- At most 8 findings, ordered by expected effect on the total. Fewer is better than padding.

## Output schema (`report_correlation_findings` tool, operation result schema)

```json
{
  "findings": [{
    "driver_type": "exercise | muscle | sequence",
    "driver": "string",
    "lift": "squat | bench | deadlift",
    "effect": "helps | hurts | unclear",
    "confidence": "strong | moderate | weak",
    "evidence": "one sentence, numbers from the payload",
    "mechanism": "max 2 sentences: muscles / fatigue dimension / transfer, tied to the lift profile",
    "action": "one concrete program change, or 'Keep as is'",
    "caveat": "the confound specific to this finding, or ''"
  }],
  "summary": "1-2 sentences",
  "insufficient_data": false,
  "insufficient_data_reason": ""
}
```

- Bump the generation identity/prompt version, so cached old-shape reports are not served as new ones.
- The frontend normalizer still reads old reports: `exercise` → `driver` (type exercise), `correlation_direction` positive/negative → helps/hurts, `strength` → `confidence`, `reasoning` → `mechanism`.

## UI (`AiAnalysis.tsx` "Exercise ROI Correlation" card, and the past-block variant)

- Same card and title, plus an ⓘ tooltip: "What helps or hurts each main lift, with dose and an action."
- Lift filter chips: All / Squat / Bench / Deadlift.
- Table columns: Lift · Driver (with a small type badge: Exercise / Muscle / Sequence) · Effect badge (green helps, red hurts, gray unclear) · Evidence · Action. On mobile, only Lift · Driver · Effect.
- Clicking a row expands it to show Mechanism and Caveat as two short lines. No paragraphs.
- Confidence is shown as badge opacity or a small dot, not a column.

## Out of scope

- No new section and no new operation.
- No new tests unless needed to keep existing ones green; no changes to the program-evaluation report.
