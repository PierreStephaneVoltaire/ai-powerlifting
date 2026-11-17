# Restore Exercise ROI Correlation

## Why

The "Exercise ROI Correlation" card is an accessory → main-lift correlation
analysis. `docs/plans/2026-11-13-main-lift-drivers.md` (shipped in `acad1a5d`)
replaced it with a "drivers" report that:

- dropped the correlation table (Exercise, Lift, Direction, Strength,
  Reasoning, Caveat) for a `DriversTable`;
- requires an `action` per finding, which contradicts the app's rule that
  analyses never tell the athlete how to train ("Do NOT speculate about whether
  the athlete should be training differently");
- only computes stats for exercises with lift transfer ≥ 0.2 and caps the
  payload at 20 exercises, so most accessories disappear.

The operator wants the original correlation analysis back, with the richer
data kept only as extra context that improves the reasoning.

## Target

### Output (unchanged from before acad1a5d)

Findings are accessory → lift correlations. Each finding:

- `exercise`: accessory exercise name
- `lift`: `squat`, `bench` or `deadlift`
- `correlation_direction`: `positive`, `negative` or `unclear`
- `strength`: `strong`, `moderate` or `weak`
- `reasoning`: 2–3 sentences on why it makes biomechanical sense given the data
- `caveat`: the one concrete confound from this athlete's data, or empty

Plus the report `summary` and `insufficient_data_reason` as before. No
`action`, no `driver_type`, no `muscle` or `sequence` drivers as findings.

Source of truth for the original contract: `git show acad1a5d^:src/services/lib/prompts/correlation_system.j2`,
`correlation_user.j2`, the original tool schema for the correlation tool, and
`git show acad1a5d^:src/frontend/src/components/analysis/AiAnalysis.tsx`
(lines ~120–200, the table and badges `CORR_DIR_BADGE` / `CORR_STRENGTH_BADGE`).

### Prompt

`src/services/analytics-ai/internal/prompts/templates/correlation_system.tmpl` is a
NEW prompt. It is not the pre-`acad1a5d` text. It keeps only:

- the output contract (accessory → lift findings: `exercise`, `lift`,
  `correlation_direction`, `strength`, `reasoning`, `caveat`; no `action`, no advice);
- the data-gap rules;
- the no-editorializing and no-advice rules;
- the anatomical plausibility gate (the only gate; no transfer threshold, no cap);
- the style rules (no generic disclaimers, no causation boilerplate, no repeated caveats).

The core of the new prompt is the analysis method. For each accessory, judge how it
relates to each main lift's e1RM change using everything in the payload together:

- position: where the accessory sits relative to main-lift sessions (the day before,
  within 48 h), from `lift_sessions` prior-48h data and session order;
- volume (sets, reps, volume_kg) and frequency (sessions per week) over the weeks, and
  how changes in that dose line up with the main lift's e1RM changes in the following
  week or weeks;
- intensity (% e1RM) and RPE;
- muscles, fatigue profile and lift transfer for plausibility; muscle volume against
  MEV/MAV/MRV and weekly fatigue ratios as context for whether an accessory adds useful
  stimulus or competing fatigue;
- the precomputed correlation stats (every accessory × lift) as quantitative evidence
  for direction and strength;
- lift profiles (dominance, sticking points) to weight relevance.

`reasoning` cites the concrete numbers (dose, frequency, position, r and n) that support
the direction and strength. `caveat` names the one concrete confound. Findings describe
what the data shows, never what to change.

`correlation_user.tmpl`: keep the weekly e1RM and per-accessory weekly data (every
accessory trained in the window, no transfer threshold, no 20-exercise cap), fill the
"Accessory Exercise ROI" table (Pearson r between weekly volume and the lift's
next-week e1RM change, with weeks observed) for every accessory × lift, and append the
context blocks (exercise dose, exercise profiles, muscle sets vs landmarks, weekly
fatigue, main-lift sessions).

### Data (pl-analytics, Rust)

`CorrelationInputsReply` keeps the enriched fields, but:

- remove the lift transfer ≥ 0.2 gate and the 20-exercise cap: every accessory
  trained in the window is included;
- correlation stats are computed for every accessory × main lift.

### Schema / API / frontend

- Correlation tool/result schema: back to the finding fields above (analytics-ai
  `internal/prompts/tools/report_correlation_findings.json` and the Go types,
  backend passthrough, `src/frontend/src/api/analytics.ts` `CorrelationReport`
  types).
- `AiAnalysis.tsx` and any other place rendering it (`BlockWeeklySurface.tsx`,
  `BlockAnalytics.tsx`, `WeeklyPeakingSections.tsx`): restore the original table
  (Exercise, → Lift, Direction badge, Strength badge, Reasoning, Caveat) and its
  badges; remove `DriversTable` and the "with dose and an action" label. Restore
  the original card label text from before acad1a5d. Do not change anything else
  on those pages.

### Cache identity

Corrected 2026-11-15: saved Analysis reports must survive prompt changes as well
as data updates and elapsed time. Neither a version constant nor a prompt hash
belongs in their identity. Only explicit regeneration replaces a saved report.
The input-sensitive prompt cache is separate; see the cache design rules in
`docs/ARCHITECTURE.md`.

## Tests

No new tests. Update existing assertions/goldens that encode the drivers schema
(analytics-ai `internal/prompts/testdata`, prompts_test.go, Rust correlation
inputs tests) minimally; regenerate prompt testdata from the templates. Run the
affected Go packages, `cargo test -j2 --lib` + `--test parity` for analytics,
frontend `npx tsc --noEmit` in src/frontend.
