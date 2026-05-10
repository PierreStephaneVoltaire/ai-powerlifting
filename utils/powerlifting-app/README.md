# Powerlifting App

Implementation-accurate documentation for `utils/powerlifting-app/`.

This README is intentionally code-exact. It describes what the powerlifting
portal does today, including current limitations, caching behavior, and a few
places where older UI prose no longer matches the implementation.

If you want the current truth, treat these files as the real sources of truth:

- `frontend/src/pages/AnalysisPage.tsx`
- `frontend/src/components/analysis/WeeklyData.tsx`
- `frontend/src/components/analysis/AiAnalysis.tsx`
- `frontend/src/constants/formulaDescriptions.ts`
- `backend/src/routes/analytics.ts`
- `tools/health/analytics.py`
- `tools/health/*_ai.py`
- `packages/types/index.ts`

## What This App Is

The powerlifting app is a single-athlete training portal that combines:

- deterministic analytics for progress, workload, fatigue, readiness, scoring,
  competition projection, PRR calibration, volume landmarks, and specificity
  bands
- narrow AI tools for fatigue-profile estimation, lift-profile cleanup and
  stimulus estimation, accessory ROI analysis, program evaluation, template
  evaluation, and spreadsheet import
- DynamoDB-backed storage for the full training record
- optional S3-backed video attachments

The frontend is React 19 + Vite + TypeScript + Mantine. The backend is
Express/TypeScript. Most serious analytics and AI work does not happen inside
the Node backend itself. The backend is primarily a thin transport layer that
calls IF health tools through the IF agent API.

High-level request flow:

```text
React page
  -> Express route
    -> invokeToolDirect(...)
      -> IF API /v1/chat/completions with X-Direct-Tool-Invoke: true
        -> tools/health/tool.py
          -> deterministic analytics module or AI module
            -> JSON back to frontend
```

For the Analysis page specifically there are three separate computation paths:

1. Backend deterministic analysis via `weekly_analysis`
2. Frontend-local derivations from program data, glossary data, and weight log
3. Separate AI reports for correlation analysis and full-block program evaluation

## Storage And Data Model

### Core storage model

The app stores its main state in DynamoDB table `if-health`. Important records:

- `program#current`
  Active-program pointer. Resolves to the latest concrete program version.
- `program#vNNN`
  Full program snapshot. New versions are written instead of updating in place.
- `weight_log#vNNN`
  Bodyweight history for the same program version.
- `max_history#vNNN`
  Historical max entries.
- `glossary#v1`
  Canonical exercise glossary plus fatigue metadata and accessory e1RM metadata.
- Template and import records
  Stored through the health tool layer and exposed in the portal through the
  template and import pages.

Storage conventions:

- Dates are `YYYY-MM-DD`
- Timestamps are ISO8601
- Weights are stored in kilograms
- Frontend unit switching is display-only

### Program meta

`Program.meta` captures:

- Identity and versioning:
  `program_name`, `version_label`, `updated_at`, `archived`, `archived_at`
- Timeline:
  `program_start`, `comp_date`, `weight_class_confirm_by`
- Training-week boundaries:
  `program_week_start_day`, `block_week_start_days`
- Federation / class context:
  `federation`, `practicing_for`, `weight_class_kg`
- Bodyweight context:
  `current_body_weight_kg`, `current_body_weight_lb`
- Targets:
  `target_squat_kg`, `target_bench_kg`, `target_dl_kg`, `target_total_kg`
- Attempt defaults:
  `attempt_pct.opener`, `attempt_pct.second`, `attempt_pct.third`
- Anthropometrics:
  `height_cm`, `arm_wingspan_cm`, `leg_length_cm`
- Manual and lift-specific max helpers:
  `manual_maxes`, `lift_attempt_settings`
- Program history/context:
  `training_notes[]`, `change_log[]`, `last_comp`
- Template lineage:
  `template_lineage.applied_template_sk`, `applied_at`, `week_start_day`,
  `start_date`

Important nuance:

- Powerlifting weeks are program/block-defined, not standard calendar weeks.
  Analysis and planning must use the stored `block_week_start_days[block]`
  value plus the caller's `asOfDate`. Missing historical block values fall
  back to Monday; do not infer Saturday from the block name. To set the current
  block explicitly in DynamoDB, run
  `npm run set:week-start --workspace=backend -- Saturday`.
- The typed schema does not currently declare `meta.sex`.
- Backend projection and backend `estimated_dots` still look for `meta.sex`.
- Frontend DOTS and IPF GL calculations instead use `settingsStore.sex`.

### Phases

`Phase` captures:

- `name`
- `intent`
- `start_week`
- `end_week`
- `target_rpe_min`
- `target_rpe_max`
- `days_per_week`
- `notes`
- `block`

Phases matter to:

- RPE drift
- readiness score
- AI program evaluation
- template evaluation

### Sessions and exercises

`Session` captures:

- Date placement:
  `date`, `day`, `week`, `week_number`
- Phase resolution:
  `phase`
- Block grouping:
  `block`
- Status:
  `status`, `completed`
- Planned work:
  `planned_exercises[]`
- Logged work:
  `exercises[]`
- Subjective/context fields:
  `session_notes`, `session_rpe`, `body_weight_kg`, `wellness`, `pain_log`
- Media:
  `videos[]`

`Exercise` captures:

- `name`
- `sets`
- `reps`
- `kg`
- `notes`
- `failed`
- `failed_sets[]`
- `set_statuses[]`
- `failed_set_reasons[][]`
- `load_source`
- `rpe_target`

`set_statuses[]` is the current per-set execution state:

- `pending`
- `completed`
- `failed`
- `skipped`

For backward compatibility, `failed_sets[]` is still written and is derived from
`set_statuses[]`. Analytics treat `completed` and `failed` as executed sets.
`skipped` and `pending` do not count toward executed volume, fatigue workload,
INOL, specificity, or muscle-set totals.

`failed_set_reasons[][]` is aligned to `set_statuses[]`. Each failed set can
store multiple reason tags. Non-failed sets store an empty reason list. Valid
reason tags are:

- `strength_failure`
- `technical_failure`
- `command_failure`
- `grip`
- `depth`
- `pause`
- `lockout`
- `balance`
- `pain`
- `fatigue`
- `misload_bad_attempt_selection`

These are the raw inputs to almost everything:

- e1RM estimation
- progression rate
- volume and intensity trends
- fatigue index
- fatigue-dimension workload
- INOL
- ACWR
- readiness
- specificity
- correlation AI

### Competitions

`Competition` captures:

- `name`, `date`, `federation`, `location`
- `hotel_required`
- `status`
- `weight_class_kg`
- `body_weight_kg`
- `targets`
- `results`
- `post_meet_report`
- `notes`
- `decision_date`
- `between_comp_plan`
- `comp_day_protocol`

`post_meet_report` is an optional completed-meet detail object. It stores:

- fixed 9-attempt log: squat/bench/deadlift attempts 1-3
- per-attempt `result`: `made`, `missed`, or `not_taken`
- miss category and miss reasons for missed attempts
- official bodyweight remains on `body_weight_kg`
- sleep, travel, warm-up timing, food, caffeine, equipment issues, commands
  missed, attempt-selection grade, and meet notes

When a post-meet report is saved, `results` remains the compatibility summary:
best made squat, bench, deadlift, and total. DOTS, PRR, readiness, exports, and
analysis continue to read `results`.

Competition data drives:

- current max fallback from actual meet results
- weeks-to-comp context
- meet projection selection and projection snapshots
- projection-to-result ratio calibration
- attempt selection
- DOTS/IPF GL interpretations
- AI program evaluation competition-alignment output

### Diet notes

`DietNote` captures averaged recovery/nutrition context, not meal-by-meal logging:

- `date`
- `notes`
- `avg_daily_calories`
- `avg_protein_g`
- `avg_carb_g`
- `avg_fat_g`
- `avg_sleep_hours`
- `water_intake`
- `water_unit`
- `consistent`

These are currently used mostly in frontend trend cards and AI interpretation,
not the hard deterministic training formulas.

### Supplements and supplement phases

Supplement data is stored:

- `supplements[]` with `name`, `dose`
- `supplement_phases[]` with phase notes, item list, peak-week protocol, block,
  start/end week

Important implementation note:

- Older app prose says supplements are not fed into AI yet.
- Current `program_evaluation_ai.py` does include a supplement summary in the
  prompt payload.
- The prompt still instructs the model to treat supplements cautiously and only
  mention them if materially relevant.

### Lift profiles

`LiftProfile` is one of the most important custom-data structures in the app.

Per lift (`squat`, `bench`, `deadlift`) it stores:

- `style_notes`
- `sticking_points`
- `primary_muscle`
- `volume_tolerance`
- `stimulus_coefficient`
- `stimulus_coefficient_reasoning`
- `stimulus_coefficient_confidence`
- `stimulus_coefficient_updated_at`

These profiles are used in two different ways:

1. As direct deterministic inputs through `stimulus_coefficient`, which modifies
   INOL
2. As soft AI context for lift-profile review, lift-profile rewrite, stimulus
   estimation, fatigue-profile estimation, correlation analysis, program
   evaluation, accessory e1RM backfill, template evaluation, and spreadsheet
   import

### Weight log and max history

Additional tracked records:

- `WeightEntry`: `date`, `kg`
- `MaxEntry`: `date`, `squat_kg`, `bench_kg`, `deadlift_kg`, `total_kg`,
  `bodyweight_kg`, `context`

The Analysis page bodyweight trend uses `weight_log`. It does not derive
bodyweight trends only from `program.meta.current_body_weight_kg`.

### Glossary

`GlossaryExercise` captures:

- Identity and classification:
  `id`, `name`, `category`, `fatigue_category`, `equipment`
- Muscle mapping:
  `primary_muscles[]`, `secondary_muscles[]`
- Coaching metadata:
  `cues[]`, `notes`, `video_url`
- Fatigue metadata:
  `fatigue_profile`, `fatigue_profile_source`, `fatigue_profile_reasoning`
- Accessory e1RM metadata:
  `e1rm_estimate`
- Archive status:
  `archived`

The glossary is essential for:

- fatigue-dimension math
- specificity ratio broad counting
- muscle-group aggregation on the Analysis page
- import resolution
- AI fatigue estimation
- accessory e1RM backfill

### Templates and imports

Templates capture:

- `meta`: name, description, estimated weeks, days/week, timestamps,
  archival state, derivation lineage, AI evaluation
- `phases[]`
- `sessions[]`
- `glossary_resolution`
- `required_maxes[]`

Pending imports capture:

- file identity and classification
- AI parse result
- merge strategy and conflict resolution
- apply / reject state
- expiry / TTL

Import flows are AI-assisted and are covered later in this README.

### Local settings and external inputs

Some values are not stored inside `Program` but still change outputs:

- `settingsStore.unit`
  Display unit only
- `settingsStore.barWeightKg`
  Plate calculator and related tools
- `settingsStore.sex`
  Frontend DOTS and IPF GL calculations
- OpenPowerlifting dataset
  Used only on the Rankings page

### Intentionally missing or still-lightweight data

The current app does not do the following:

- no HRV
- no bar-velocity capture
- no vision-based technical analysis
- no per-meal diet logging
- no per-night sleep staging
- no true multi-athlete normalization

It also uses some soft context in AI without pushing that same context into the
rigid formulas. Body metrics are the best example: they are available to AI
prompts, but the deterministic fatigue math does not directly adjust for them.

## Analysis Page: Data Sources And Render Path

`frontend/src/pages/AnalysisPage.tsx` pulls data from three places:

1. `fetchWeeklyAnalysis(effectiveWeeks, 'current')`
   - route: `GET /api/analytics/analysis/weekly`
   - backend tool: `weekly_analysis`
   - primary source for fatigue, compliance, readiness, INOL, ACWR, specificity,
     projections, per-lift stats, flags, and backend current maxes
2. `fetchWeightLog(version)`
   - used for the bodyweight trend and as fallback bodyweight for local DOTS/IPF GL
3. `fetchGlossary()`
   - used for muscle-group aggregation and per-lift accessory/category grouping

AI cards are loaded separately by `AiAnalysis.tsx`:

- `GET /api/analytics/correlation?weeks=...&block=current`
- `GET /api/analytics/program-evaluation?refresh=...`

Windowing behavior:

- `Current Week` is the block week containing the frontend `asOfDate`
- `1`, `2`, `4`, `8` modes count positional training weeks before current,
  including empty gaps
- `Full Block` spans Week 1 through the current positional block week

Important distinction:

- backend analysis uses deterministic health-tool math
- several cards on the page are frontend-derived and can disagree with backend
  values
- AI sections are cached separately and regenerated on demand

## Analysis Page: Every Section And What It Means

### 1. Estimated 1 Rep Maxes

This top card is not a pure pass-through of backend `current_maxes`.

Render priority:

1. If local `dotsTrend` rows exist, the card uses `highestMaxes`, which scans the
   locally-computed weekly Epley trend rows and takes the highest squat, bench,
   and deadlift value seen in the selected window.
2. If there is no local trend data, the card falls back to backend
   `data.current_maxes`.

Local trend rules:

- built from completed sessions only
- main-lift matching is name-based
- Epley formula is `kg * (1 + reps / 30)`
- local DOTS is then computed from local total plus latest bodyweight from
  weight log or session bodyweight

Backend `current_maxes` rules are different and more conservative; they are
documented in the formula section below.

Result: the top max card can legitimately differ from the backend maxes used by
projections and INOL.

### 2. Compliance

Source: backend `weekly_analysis -> session_compliance`

Displayed fields:

- percent complete
- completed / planned sessions
- current phase name
- average sessions per week across the selected window

Implementation notes:

- compliance uses all session rows in the window
- completed means `completed == true` or `status in ('logged', 'completed')`
- planned count does not exclude deload or break weeks

### 3. Current Fatigue State

Source: backend `fatigue_index`

Displayed:

- current fatigue state as a percentage
- selected-window mean and peak fatigue
- label: low / moderate / high / very high
- component breakdown (7 dimensions):
  `failure_stress`, `acute_spike_stress`, `rpe_stress`,
  `chronic_load_stress`, `overload_streak`,
  `intensity_density_stress`, `monotony_stress`
- reservoir dimension stress and fatigue context confidence

Threshold colors:

- `< 0.25` low
- `0.25 - 0.44` moderate
- `0.45 - 0.64` high
- `>= 0.65` very high / overreaching risk

### 4. Readiness

Source: backend `compute_readiness_score`

Displayed:

- overall readiness score on a 0-100 scale
- training readiness and external readiness
- normalized components:
  fatigue, RPE drift, subjective wellness, short-term performance trend, bodyweight deviation

Threshold colors are implicit through the backend zone:

- `> 75` green
- `50 - 75` yellow
- `< 50` red

### 5. Stimulus-Adjusted INOL

Source: backend `compute_inol`

Displayed:

- average adjusted INOL per lift across the selected window
- raw INOL per lift across the selected window
- lift-specific stimulus coefficient
- phase-adjusted target range, uncertainty display range, and trend pressure
- lift-level flags:
  low stimulus, high INOL monitor, or overreaching risk

Important nuance:

- INOL is selected-window and phase-adjusted
- ramp-up weeks can suppress low-stimulus flags
- trend pressure strengthens high-INOL warnings when volume or RI is rising

### 6. ACWR

Source: backend `compute_acwr`

Displayed:

- composite ACWR
- composite zone / label
- per-dimension EWMA ACWR for axial, neural, peripheral, systemic

Zones:

- `< 0.80` detraining trend
- `0.80 - 1.30` steady load
- `1.30 - 1.50` rapid increase
- `> 1.50` load spike

If there are fewer than 25 calendar days of completed training, the UI shows an insufficient-data
message instead of ratios.

### 7. Relative Intensity Distribution

Source: backend `compute_ri_distribution`

Displayed:

- overall heavy / moderate / light distribution
- per-lift bucket distribution

Buckets:

- heavy: `RI > 0.85`
- moderate: `0.70 <= RI <= 0.85`
- light: `RI < 0.70`

### 8. Specificity Ratio

Source: backend `compute_specificity_ratio`

Displayed:

- narrow specificity = direct SBD sets / total sets
- broad specificity = (SBD + same-category secondary work) / total sets
- supporting counts: SBD sets and total sets
- expected narrow/broad bands when a competition is on the calendar
- flags when the current ratio is below or above the expected band

### 9. Fatigue Dimensions (Weekly)

Source: backend `_weekly_fatigue_by_dimension`

Displayed:

- weekly axial, neural, peripheral, systemic totals
- last 8 weeks only in the table/card UI

This section only exists because the health tool always loads the glossary and
passes it to `weekly_analysis`.

### 10. Projections

Source: backend `meet_projection`

Displayed:

- projected total
- confidence
- weeks to competition
- method
- first and last upcoming competitions when multiple upcoming meets exist
- calibration badge when recent completed meets provide a PRR history
- 20% ceiling cap on projected gains, even for far-out meets

If no eligible competition exists, the page shows a reason string instead.

Important hidden detail:

- backend also computes `attempt_selection`
- the Analysis page currently does not render it

### 10a. Projection Calibration / PRR

Source: backend `compute_prr` and projection calibration inside `meet_projection`

Displayed:

- projection-to-result ratio per lift when a meet has both the actual result and the T-1w snapshot
- total PRR when all three lifts are valid
- calibration badge when at least two completed meets provide usable total PRR
- athlete-specific lambda multiplier derived from the median of recent total PRR values

### 10b. Volume Landmarks

Source: backend `compute_volume_landmarks`

Displayed:

- per-lift MV, MEV, MAV, and MRV estimates
- confidence band from whole-program history length
- only lifts with sufficient history are rendered in the UI

Landmark rules:

- weeks are bucketed into 2-set bins
- deload and break weeks are excluded
- MV is the first bin with non-negative week-over-week e1RM change
- MEV is the first bin with a positive e1RM change
- MAV is the bin with the largest e1RM change
- MRV is the first bin where `count >= 3` and any of: median fatigue index
  `>= 0.55`, probability of negative e1RM change `>= 0.60`, or median readiness
  `< 60`

### 11. e1RM Progression, DOTS, and IPF GL Trend

Source: frontend-local `dotsTrend` / `ipfGlTrend`

Displayed:

- weekly local Epley-estimated squat, bench, deadlift, and total
- local DOTS trend
- local IPF GL trend
- weekly change badges

Implementation details:

- weekly bodyweight is the max session bodyweight seen in that week, or the
  latest weight-log entry if the week has none
- IPF GL mode is:
  - `classic_powerlifting` for full SBD weeks
  - `classic_bench` for bench-only weeks

This section is not sourced from backend `weekly_analysis`.

### 12. Body Weight Trend

Source: frontend-local `weightLog`

Displayed:

- latest weight
- change over the selected analysis window
- last 8 entries

It compares the latest weight to the oldest entry inside the current window,
falling back to the oldest overall entry if the window is empty.

### 13. Sleep Trend

Source: frontend-local aggregation of `diet_notes`

Displayed:

- average sleep hours
- week-over-week delta
- weekly sleep cards
- simple 7-hour threshold messaging

### 14. Nutrition Trend

Source: frontend-local aggregation of `diet_notes`

Displayed:

- average calories
- average protein
- average carbs
- average fat
- average water
- consistency percent

Aggregation rules:

- notes are bucketed into Monday-start weeks
- per-week averages are computed from whatever fields exist in that week
- deltas compare the first and last available weekly values, normalized by the
  number of points

### 15. Athlete Measurements

Source: `program.meta`

Displayed when present:

- height
- arm wingspan
- leg length

This is display-only on the Analysis page. These measurements matter more to AI
context than to rigid formulas.

### 16. Lift Style Profiles

Source: `program.lift_profiles`

Displayed:

- style/setup notes
- sticking points
- primary driver
- volume tolerance

This section is descriptive, but the same data also affects INOL and multiple AI
paths.

### 17. Competitions

Source: `program.competitions`

Displayed:

- meet name
- date
- status
- meet results if present

This table is informational. Projection logic uses competition data separately.

### 18. WeeklyData Subsections

Rendered by `frontend/src/components/analysis/WeeklyData.tsx`.

Subsections:

- Per-Lift Breakdown
  - progression rate
  - R-squared
  - volume and intensity week-over-week percent change
  - failed-set count
  - RPE trend
  - frequency and raw-set totals
  - expandable accessory list by same glossary category
- Exercise Volume
  - total sets
  - total volume
  - max weight
  - raw table or charts
- Sets by Muscle Group
  - glossary primary muscles get full set credit
  - glossary secondary muscles get 0.5 credit
- Avg Weekly by Muscle Group
  - same 1.0 / 0.5 weighting
  - average sets/week and average volume/week

### 19. AI Analysis

Rendered by `AiAnalysis.tsx`.

Subsections:

- Exercise ROI Correlation
  - requires at least 4 weeks selected
  - cached unless regenerated
- Program Evaluation
  - only shown in Full Block mode
  - frontend gate is at least 4 completed sessions
  - backend gate is stricter: at least 4 completed weeks

### 20. Formula Accordion And Flags

The accordion is a prose layer from `frontend/src/constants/formulaDescriptions.ts`.
It is useful, but it is not the final authority where code and prose differ.

The `Flags` card is a merged list from multiple backend analytics sources:

- RPE drift flags
- fatigue flags
- INOL flags

## Deterministic Formulas And Why They Are Customized

### Estimated 1RM and current max selection

Where used:

- backend current maxes
- backend meet projection
- backend INOL / ACWR / RI distribution
- frontend trend table uses a separate local Epley path

Backend session estimate:

```text
If session RPE exists and reps are 1..6 and RPE is 6..10:
  e1RM = weight / RPE_TABLE[(reps, RPE)]

Else if no RPE exists and reps are 1..5:
  e1RM = weight / CONSERVATIVE_REP_PCT[reps]
```

Selection rules:

- ignore failed sets
- use only recent session estimates within the last 42 days
- take the 90th percentile per lift
- require at least 3 qualifying estimates per lift
- require at least 2 lifts total for a session-derived current-max object
- prefer the latest completed competition results over session-derived estimates

Why this is customized:

- the main analysis intentionally avoids generic Epley/Brzycki as the primary
  truth path
- the implementation is explicitly conservative
- the percentile selection dampens one-off inflated sets
- real competition results override estimates when available

### Deload detection and effective weeks

Where used:

- progression rate
- effective training week count
- projection logic
- deload info block on the Analysis page

Rules:

```text
A week is a break if volume load == 0.

A week is a deload if:
  1. weekly volume load is below a rolling median threshold
  2. and intensity confirms it is intentionally easy
```

Exact thresholds:

- volume threshold with squat/deadlift present: `< 0.65 * median(previous rolling non-deload weeks)`
- volume threshold with no squat/deadlift present: `< 0.75 * median(...)`
- intensity confirmation:
  - all primary-lift RPEs `<= 6`, or
  - best primary-lift e1RM dropped by at least 10 percent vs the previous two
    non-deload weeks
- stagnation alone does not count as a deload

Why this is customized:

- progression math should not punish intentionally easy weeks
- the code deliberately requires both low volume and low intensity evidence
- a week is not labeled deload just because it stopped improving

### Progression rate

Where used:

- per-lift breakdown
- meet projection

Formula:

```text
For each effective training week:
  best_weekly_e1RM = max(qualifying e1RMs in that week)

slope = Theil-Sen(best_weekly_e1RM ~ effective_week_index)
kendall_tau = KendallTau(effective_week_index, best_weekly_e1RM)
fit_quality = 1 - MAD(residuals) / MAD(series)
```

Important details:

- cutoff is the last 90 days
- only completed/logged sessions count
- deload and break weeks are excluded
- weekly point uses the best qualifying set, not the average

Why this is customized:

- Theil-Sen is robust to noisy training logs and outliers
- "effective week" indexing prevents deliberate deloads from flattening slope

### Volume/intensity correlation

Where used:

- per-lift volume and intensity percent-change display
- accessory ROI prior for correlation AI

Formula:

```text
weekly_volume = sum(sets * reps * kg) for the exercise in that week
weekly_avg_intensity = mean(kg) for that exercise in that week
pearson_r = corr(weekly_volume, weekly_avg_intensity)
```

Requirements:

- at least 3 weeks of data

### RPE drift

Where used:

- per-lift breakdown
- readiness score
- flags

Current implementation:

```text
If phase target RPE ranges exist:
  residual = actual_session_rpe - phase_target_midpoint
  slope = Theil-Sen(residual ~ week)
Else:
  slope = Theil-Sen(actual_rpe ~ week)
```

Fit quality:

```text
kendall_tau = KendallTau(week, residual_or_raw_rpe)
fit_quality = 1 - MAD(residuals) / MAD(series)
```

Flags:

- slope `>= 0.1` -> fatigue
- slope `<= -0.1` -> adaptation
- otherwise stable

Why this is customized:

- it compares performance against the intended phase difficulty, not just raw RPE
- it treats rising RPE at the same planned difficulty as a fatigue signal

### Fatigue model and fatigue dimensions

Where used:

- fatigue dimensions table
- fatigue index spike path
- ACWR

Per-set model:

```text
I = weight / e1RM
phi(I) = 0                                if I <= 0.60
phi(I) = ((I - 0.60) / 0.40)^3           otherwise

axial      = profile.axial      * weight^1.30 * reps
neural     = profile.neural     * reps * phi(I) * sqrt(weight / 100)
peripheral = profile.peripheral * weight^1.15 * reps
systemic   = profile.systemic   * weight * reps * (1 + 0.30 * I)
```

Implementation details:

- only squat, bench, and deadlift get direct current-max lookup for `I`
- non-SBD exercises fall back to `I = 0.70` for neural scaling
- weekly totals multiply the per-set values by `sets`
- missing glossary fatigue profiles fall back to:
  `axial=0.3, neural=0.3, peripheral=0.5, systemic=0.3`

Why this is customized:

- the app intentionally tracks four recovery dimensions instead of one tonnage
  number
- neural fatigue is intensity-sensitive and intentionally zeroed below 60 percent

### Fatigue index

Where used:

- Fatigue Signal card
- readiness score
- flags

Formula:

```text
R_d,t = R_d,t-1 * exp(-ln(2) / half_life_d) + Load_d,t
S_d,t = clamp((R_d,t / baseline_d - 1.0) / 0.75, 0, 1)
ReservoirStress = 0.60 * max(S_d) + 0.40 * weighted_mean(S_d)

FI = 0.10*fail + 0.12*spike + 0.15*rpe + 0.34*reservoir
   + 0.10*streak + 0.10*density + 0.09*monotony
```

Component details:

- `failure_stress`: Clamped failed compounds
- `acute_spike_stress`: Volume spike
- `rpe_stress`: RMS of phase-relative RPE excess and 9+ frequency
- `chronic_load_stress`: Decaying reservoir stress compatibility key
- `overload_streak`: Consecutive weeks of high loading
- `intensity_density_stress`: Ratio of heavy sets
- `monotony_stress`: Monotony and 4-week strain ratio
- `reservoir_dimension_stress`: Axial, neural, peripheral, and systemic stress
- `current_state_fi`: Current fatigue as of the selected end date
- `window_mean_fi` / `window_peak_fi`: Selected-window summaries

Flags:

- `failed_sets_spike` if failure ratio > 0.15
- `volume_spike` if composite spike > 0.20
- `high_rpe_stress` if RPE stress > 0.50
- `sustained_overload` if overload streak >= 0.75
- `high_chronic_load` if chronic load stress >= 0.65
- `localized_fatigue_high` if any reservoir dimension stress >= 0.75
- `high_intensity_density` if intensity density stress >= 0.65
- `high_monotony_strain` if monotony stress >= 0.65
- `fatigue_high` if FI >= 0.45
- `overreaching_risk` if FI >= 0.65
- `neural_overload` and `axial_overload` if dimension ACWR > 1.3

Why this is customized:

- skip rate was intentionally removed
- code comment rationale: resting reduces fatigue, not increases it
- the model treats high-RPE grinding as fatigue even without misses
- when glossary data exists, fatigue is computed through axial/neural/peripheral/
  systemic workload rather than plain tonnage
- selected week filters affect window summaries, not the current fatigue state

### INOL

Where used:

- Stimulus-Adjusted INOL card
- flags

Formula:

```text
I = kg / current_max_for_lift
raw_set_INOL = reps / (100 * sqrt((1 - min(I, 0.995))^2 + 0.02^2))
raw_weekly_INOL = sum(raw_set_INOL * sets)
adjusted_weekly_INOL = raw_weekly_INOL * stimulus_coefficient
TargetRange_l,w = BaseRange_l * PhaseMultiplier_w
DisplayRange = TargetRange widened for small selected windows
TrendPressure = 0.60*volume_spike + 0.40*RI_spike
```

Only canonical lifts count:

- squat
- bench / bench press
- deadlift

Stimulus coefficient behavior:

- default `1.0`
- read from `lift_profiles[].stimulus_coefficient`
- clamped to `[1.0, 2.0]`
- optional lift-profile overrides:
  - `lift_profiles[].inol_low_threshold`
  - `lift_profiles[].inol_high_threshold`

Default productive ranges:

- squat: `1.6 - 3.5`
- bench: `2.0 - 5.0`
- deadlift: `1.0 - 2.5`

Phase and trend behavior:

- deload/taper/peak/overreach/hypertrophy/strength phases adjust target ranges
- one- and two-week windows widen the display range to reflect uncertainty
- early effective training weeks get ramp-up grace for low-INOL flags
- high INOL becomes an overreaching warning when volume or relative intensity is also rising

Why this is customized:

- raw INOL assumes the same load/intensity stress means the same practical
  stimulus for every lifter
- the stimulus-coefficient prompt explicitly adjusts for:
  - effective ROM
  - mechanical advantage or disadvantage
  - total muscle mass under meaningful tension
  - time under tension near the weak point
  - eccentric loading
  - volume recovery tolerance
- baseline `1.0` means competition-standard stimulus

### ACWR

Where used:

- ACWR card
- fatigue-overload flagging

Formula:

```text
EWMA_acute_d,t = 0.25 * load_d,t + 0.75 * EWMA_acute_d,t-1
EWMA_chronic_d,t = (2/29) * load_d,t + (27/29) * EWMA_chronic_d,t-1
ACWR_d = EWMA_acute_d,t / EWMA_chronic_d,t
Composite = 0.30*axial + 0.30*neural + 0.25*peripheral + 0.15*systemic
```

Requirements:

- at least 25 calendar days of completed training

Zones:

- `< 0.80` detraining trend
- `0.80 - 1.30` steady load
- `1.30 - 1.50` rapid increase
- `> 1.50` load spike

Why this is customized:

- workload is measured through fatigue-dimension totals, not simple tonnage
- code comment rationale: deload weeks are included for a more accurate chronic
  baseline

### Banister Fitness-Fatigue Model

Where used:

- Form / Peaking Readiness card

Formula:

```text
load_t = 100 * (0.30*F_axial/B_axial + 0.30*F_neural/B_neural + 0.25*F_peripheral/B_peripheral + 0.15*F_systemic/B_systemic)
CTL_t = (2/43) * load_t + (1 - 2/43) * CTL_t-1
ATL_t = (2/8) * load_t + (1 - 2/8) * ATL_t-1
TSB_t = CTL_t - ATL_t
CTL_0 = ATL_0 = mean(load first 14 days)
```

Interpretation:

- TSB `< -30` -> deep overload
- TSB `-30 to -10` -> productive overreach
- TSB `-10 to +5` -> building
- TSB `+5 to +15` -> peaking window
- TSB `> +15` -> detraining risk

Why this is customized:

- the daily load input comes from the same four-dimensional fatigue model used
  everywhere else in the app
- historical and future projected TSB use the same normalized load units
- rest days are explicit zeros, so the model respects recovery gaps instead of
  collapsing them into missing data

### Foster Monotony & Strain

Where used:

- Monotony / Strain weekly card

Formula:

```text
Monotony = mean(daily_load) / max(SD(daily_load), 0.10*mean(daily_load), load_floor)
Monotony_display = min(Monotony, 7.0)
Strain = weekly_load * Monotony_display
StrainIndex = Strain / rolling_4wk_median(Strain)
```

Flags:

- `high_monotony` when monotony `> 2.0` and at least 3 nonzero training days exist
- `strain_spike` when strain index exceeds `1.5`

Why this is customized:

- it uses the same composite daily load as Banister and ACWR
- denominator floors and display caps prevent tiny-load weeks from exploding
- it catches "same moderate load every day" patterns that a ratio-based
  workload metric can miss

### Strength-Fatigue Decoupling

Where used:

- Decoupling card

Formula:

```text
Decoupling = slope(e1RM_total, 3wk) - slope(FI, 3wk)
```

Notes:

- `e1RM_total` is the weekly sum of best squat, bench, and deadlift e1RM
  estimates
- `FI` is the weekly fatigue-index score
- both slopes are normalized to per-week units
- negative decoupling for 3 consecutive windows triggers
  `decoupling_fatigue_dominant`

### Taper Quality Score

Where used:

- Taper Quality Score card

Formula:

```text
TQS = 0.30 * V_reduction + 0.25 * I_maintained + 0.25 * F_trend + 0.20 * T_SB
V_reduction = clamp((pre_taper_peak_volume - taper_weekly_volume) / (pre_taper_peak_volume * 0.5), 0, 1)
I_maintained = 1 if taper top-set intensity >= 0.95 * pre-taper else linear falloff
F_trend = 1 if fatigue index is trending down, 0 if flat, negative if rising
T_SB = clamp((TSB_today + 5) / 20, 0, 1)
```

Interpretation:

- `score < 40` -> poor
- `40 - 59` -> acceptable
- `60 - 79` -> good
- `>= 80` -> excellent

Windowing:

- only shown inside the final 3 weeks before the next confirmed/optional
  competition
- taper start is the earlier of a named taper phase or 21 days pre-comp
- pre-taper volume baseline is the max weekly volume in the 4 weeks before taper
  start

### Relative intensity distribution

Where used:

- RI Distribution card

Formula:

```text
RI = kg / current_max_for_lift

heavy    if RI > 0.85
moderate if 0.70 <= RI <= 0.85
light    if RI < 0.70
```

Counts are set-based, not exercise-entry-based.

### Specificity ratio

Where used:

- Specificity Ratio card

Formula:

```text
narrow = direct_SBD_sets / total_sets
broad  = (direct_SBD_sets + same_category_secondary_sets) / total_sets
```

Secondary category matching uses glossary categories `squat`, `bench`, and
`deadlift`.

Target competition selection prefers primary-goal meets, then competition notes,
then the nearest confirmed/optional meet.

### Readiness score

Where used:

- Readiness card

Formula:

```text
TrainingReadiness = 100 * (1 - weighted_penalty(fatigue, rpe_drift, performance_trend))
ExternalReadiness = 100 * (1 - weighted_penalty(wellness, bodyweight))
OverallReadiness = 0.70*TrainingReadiness + 0.30*ExternalReadiness
```

When a component is missing, it is excluded and the remaining weights are
renormalized. Readiness confidence is reported overall and separately for
training and external readiness.

Component construction:

- `fatigue_norm`
  fatigue index over the last 14 days; `None` if unavailable (excluded)
- `rpe_drift`
  `clamp((avg_rpe_last_14d - current_phase_target_midpoint) / 2, 0, 1)`;
  `None` if no RPE data (excluded)
- `subjective_wellness`
  `1 - mean(wellness values in the last 14 days) / 5`; fallback `0.5` if none
- `performance_trend`
  `clamp((-slope(e1RM_last_14d)) / denominator, 0, 1)` where denominator is
  `max(2.5, mean(current_maxes) * 0.01)`; fallback `0.5` if < 2 points
- `bodyweight_deviation`
  cut-aware trajectory deviation when a weight cut is in progress,
  otherwise coefficient of variation of the last 7 session bodyweight entries
  normalized by `0.03`; fallback `0.5` if < 2 entries

Why this is customized:

- it is a training-readiness model tied to actual logged training behavior
- it blends stress, subjective wellness, short-term performance trend, and
  bodyweight deviation instead of relying on a generic one-number readiness score

### DOTS and IPF GL

Where used:

- local trend card
- rankings/tools pages

DOTS:

```text
DOTS = 500 * total / (a + b*bw + c*bw^2 + d*bw^3 + e*bw^4)
```

IPF GL:

```text
GL = result * 100 / (A - B * exp(-C * bw))
```

Important implementation nuance:

- backend `weekly_analysis.estimated_dots` looks for `meta.bodyweight_kg` and
  `meta.sex`
- frontend local trend cards use `settingsStore.sex` and weight log / session BW
- this is one reason backend `estimated_dots` can be null while local trend DOTS
  still renders

### Meet projection

Where used:

- Projections card
- backend attempt selection input

Formula skeleton:

```text
weeks_to_comp = (comp_date - today) / 7

Choose lambda and peak_factor from current DOTS:
  DOTS < 300  -> lambda=0.96, peak=1.01
  300-399.99  -> lambda=0.90, peak=1.03
  >= 400      -> lambda=0.85, peak=1.05

weeks_taper =
  3 if weeks_to_comp >= 12
  2 if weeks_to_comp >= 8
  1 otherwise

planned_deload_weeks =
  detected future deloads, else floor(weeks_to_comp / 4) if no future deloads
  are found and the meet is more than 4 weeks away

n_t = max(0, weeks_to_comp - weeks_taper - planned_deload_weeks)

projected_gain = delta_w * lambda * (1 - lambda^n_t) / (1 - lambda)
comp_max = (current_max + projected_gain) * peak_factor
```

Ceiling clamp:

```text
ceiling_pct = min(20%, 10% + 0.5% * max(0, weeks_to_comp - 8))
comp_max is clamped to [current_max, current_max * (1 + ceiling_pct)]
```

Why this is customized:

- projection is time-aware and DOTS-aware
- the ceiling is intentionally tighter for near-term meets and looser for far-out
  meets
- taper and planned deloads are explicitly subtracted

### Attempt selection

Where used:

- computed in backend `weekly_analysis`
- currently not rendered on the Analysis page

Formula:

```text
opener = round_to_2.5(projected_comp_max * opener_pct)
second = round_to_2.5(projected_comp_max * second_pct)
third  = round_to_2.5(projected_comp_max * third_pct)
```

Default percents:

- opener `0.90`
- second `0.955`
- third `1.00`

### Compliance

Where used:

- Compliance card
- Readiness score

Formula:

```text
compliance = completed_sessions / planned_sessions * 100
```

Important implementation detail:

- all weeks in the selected compliance window are counted
- deloads and breaks are not excluded

## Where And How AI Is Used

### AI execution model

The app has multiple AI entry points, but each is narrow.

The powerlifting portal does not call OpenRouter directly from the browser or
backend feature routes. AI requests go through the IF Agent API. Specialist
flows use IF slash-specialist commands such as `/powerlifting_coach`, so model
selection, specialist prompts, tool access, and context injection stay inside
the IF agent layer.

Current model/config variables:

- `ANALYSIS_MODEL`
  correlation analysis, program evaluation, template evaluation, import parsing
- `ANALYSIS_MODEL_THINKING_BUDGET`
  thinking budget for those heavier calls
- `ESTIMATE_MODEL`
  fatigue estimation, muscle-group estimation, lift-profile estimate flows, accessory e1RM backfill
- `ESTIMATE_MODEL_REASONING_EFFORT`
  reasoning effort for those estimate calls, default `xhigh`
- `ESTIMATE_MODEL_VERBOSITY`
  output effort/detail for those estimate calls, default `max`
- `HEALTH_HELPER_MODEL`
  session note drafting, session auto-regulation, and lift-profile rewrite cleanup, default `openai/gpt-5.4-mini`
- `MODEL_ROUTER_MODEL`
  lightweight routing
- `IMPORT_FAST_MODEL`
  import classification and glossary resolution

### Session note assistance

User-visible surface:

- Session editor -> `Help write notes`

Route:

- `POST /api/sessions/:version/:date/:index/notes/draft`

Specialist path:

- IF Agent API `/powerlifting_coach`

Boundary:

- The feature drafts text for `session_notes` only.
- It receives the exact session, planned work, executed work, wellness, RPE,
  set statuses, and the structured answers from the form.
- It must not answer training questions, mention future workouts, create or
  delete sessions, change exercises, or suggest program changes.
- The backend rejects obvious out-of-scope requests before specialist invocation
  and requires the submitted session date to match the route date.
- The backend only reads a returned `notes` string. No mutation happens until
  the user inserts the draft and saves the session.

### Session auto-regulation

User-visible surface:

- Session editor -> per-exercise auto-regulation button

Route:

- `POST /api/sessions/:version/:date/:index/autoregulation`

Specialist path:

- IF Agent API `/powerlifting_coach`

Boundary:

- The feature is limited to the exact session date/index and selected exercise
  index.
- The specialist can approve, deny, or ask follow-up questions.
- The specialist is instructed not to answer unrelated questions, not to emit
  `HANDOFF_REQUIRED`, and not to create, delete, reschedule, complete, or drop
  sessions.
- The backend rejects obvious out-of-scope requests before specialist invocation
  and requires the submitted session date to match the route date.
- The backend sanitizes the specialist JSON before the frontend can apply it:
  only the selected exercise can differ, all other exercise rows are restored
  from the submitted session, and completed or failed set statuses are preserved.
- `planned_exercises[]` is never mutated. Applying the result updates only the
  executed `exercises[]` list and appends concise reasoning to exercise notes.

### 1. Exercise fatigue-profile estimation

User-visible surfaces:

- auto-trigger when a new glossary exercise is added without a manual fatigue profile
- explicit estimate button in the glossary flows
- route: `POST /api/analytics/fatigue-profile/estimate`
- route: `POST /api/exercises/:id/estimate-fatigue`

Tool/module path:

- `fatigue_profile_estimate`
- `tools/health/fatigue_ai.py`

Inputs:

- exercise name, category, equipment
- muscle groups (primary, secondary, tertiary)
- optional athlete body metrics (bodyweight, height, arm wingspan, leg length)
- optional lift profiles (style notes, sticking points, volume tolerance)

Outputs:

- `axial`: spinal compression loading 0.0-1.0
- `neural`: CNS demand baseline 0.0-1.0
- `peripheral`: local muscle damage potential 0.0-1.0
- `systemic`: cardiovascular/metabolic demand 0.0-1.0
- `reasoning`: brief explanation

Prompt summary:

- estimates 4-dimensional fatigue profiles for exercises
- uses calibration anchors (competition squat/bench/deadlift, bicep curl, face
  pulls) as reference points
- athlete body metrics and lift profiles are soft modifiers, not hard overrides
- diet, supplements, and training history are explicitly out of scope
- values are rounded to nearest 0.05
- confidence is intentionally only `medium` or `low`

### 2. Exercise ROI correlation analysis

User-visible surface:

- Analysis page -> `Exercise ROI Correlation` (requires >= 4 weeks selected)

Route:

- `GET /api/analytics/correlation?weeks=...&block=current`

Tool/module path:

- `correlation_analysis`
- `tools/health/correlation_ai.py`

Inputs:

- weekly e1RM estimates per SBD lift (Epley formula)
- weekly volume per accessory exercise
- lift profiles for anatomical context
- exercise ROI prior (Pearson r per accessory)
- glossary for muscle mapping and anatomical plausibility

Outputs:

- `findings[]`: per accessory, correlation direction (positive/negative/unclear),
  strength (strong/moderate/weak), biomechanical reasoning, caveat
- `summary`: 1-2 sentence overall summary
- `insufficient_data`: boolean
- `insufficient_data_reason`: string if applicable

Prompt summary:

- biomechanics-focused analyst identifying anatomically plausible correlations
  between accessory volume and SBD e1RM trends
- anatomical plausibility filter: only reports correlations where the accessory
  works muscles that are primary or significant secondary movers in the lift
- lift profiles contextualize relevance (e.g., tricep-dominant bencher benefits
  more from tricep accessories)
- exercise ROI prior tunes strength ratings: |r| >= 0.60 with >= 4 weeks
  upgrades strength by one level; anatomical filter is the gate, ROI only tunes
- does not critique programming, call it random, or flag insufficient data
  unless fewer than 2 weeks of activity

Cache behavior:

- cached by Monday-aligned window key:
  `corr_report#{window_start}_{weeks}w`
- `Regenerate` bypasses cache
- exported XLSX uses the cached report if one exists

Minimum data:

- current code requires at least 4 distinct weeks of data

### 3. Full-block program evaluation

User-visible surface:

- Analysis page -> `Program Evaluation` (Full Block mode, >= 4 completed sessions)

Route:

- `GET /api/analytics/program-evaluation?refresh=...`

Tool/module path:

- `program_evaluation`
- `tools/health/program_evaluation_ai.py`

Prompt:

```text
You are an objective sports scientist producing a data-driven evaluation of a
powerlifting competition block. Your audience is the athlete — someone who
already wrote the program deliberately and wants to know if the data supports
staying the course or making small corrections.

═══════════════════════════════════════════════════════════════════
ROLE BOUNDARIES
═══════════════════════════════════════════════════════════════════
You are an ANALYST, not a coach. Your job:
  ✓ Identify what the data says is working
  ✓ Identify what the data says is not working
  ✓ Suggest the smallest useful corrections grounded in the data
  ✗ Do NOT redesign the program, restructure training splits, or suggest
    wholesale changes unless a serious, data-backed issue threatens the
    athlete's ability to compete safely.
  ✗ Do NOT critique exercise selection, training frequency, volume strategy,
    or session structure. These are deliberate programming choices. Programs
    legitimately vary — some alternate exercises weekly, some avoid spamming
    competition lifts to manage fatigue, some use high volume, some use low
    volume. All are valid.
  ✗ Do NOT call the program "sporadic", "inconsistent", "random", or
    "unstructured". If the schedule looks unusual to you, assume it is
    intentional and analyze the results it is producing.

Default stance: "continue as-is" or "monitor". Only escalate to "adjust" or
"critical" when multiple data points converge on a clear problem.

═══════════════════════════════════════════════════════════════════
UNDERSTANDING THE DATA YOU RECEIVE
═══════════════════════════════════════════════════════════════════
You will receive a JSON payload with the following sections. Use ALL of them.

PROGRAM META & PHASES
  - Block name, start date, planned phases, and phase progression.
  - Phases tell you the INTENT of the current training period (hypertrophy,
    strength, peaking, deload, etc.). Evaluate results relative to phase
    goals — a hypertrophy phase should not be judged by peak 1RM output.

GOALS & QUALIFICATION STANDARDS
  - The program now has explicit block goals. These define which competitions
    matter most, which standards must be hit, whether a meet should be
    treated as train-through, and what weight-class constraints exist.
  - Goals override any naive assumption that the last meet is automatically
    the main priority.
  - Qualification standards are goal-owned in this system. Competitions are
    opportunities to satisfy goals; goals define the actual standard,
    federation, strategy mode, and weight-class target.
  - A goal may now link to multiple competitions and multiple standards.
    Treat those as alternative paths to the same block outcome, not as noise.
  - Never silently downgrade a primary goal to an easier secondary standard.
    If a primary OPA path requires 570 kg and a secondary CPU path requires
    535 kg, a 535 total does NOT satisfy the 570 goal even if the meet
    counts toward both federations.

COMPETITIONS
  - Every competition in the block, with dates and weeks-to-comp.
  - Competition role is derived from explicit goals when available.
  - A competition has one host federation plus a list of extra federations it
    counts toward. Use this to judge whether a meet is actually eligible for a
    goal's target federation or standard.
  - Competition notes are ground-truth context. If the notes say a meet is a
    qualifier, backup shot, practice day, or low-priority tune-up, use that.
  - Each competition may include a governing_goal and required_total_kg when
    the analysis context can infer them. Anchor recommendations to that bar,
    not to the lowest available qualifying standard in the payload.
  - Weeks-to-comp is critical context: an athlete 12 weeks out should look
    different than one 3 weeks out. Taper expectations, volume shifts, and
    intensity curves should be evaluated relative to proximity.
  - Some meets may be appropriate to deprioritize, sandbag, train through, or
    even drop if they materially interfere with a higher-priority goal.

LIFT PROFILES (if provided)
  - Style notes, sticking points, primary muscles, volume tolerance per lift.
  - Use these to contextualize every finding. A metric that looks suboptimal
    in a textbook sense may be fine for THIS athlete's leverages and style.

ATHLETE MEASUREMENTS (if provided)
  - Height, arm wingspan, leg length, weight class, current bodyweight.
  - These affect what "good" looks like. Long-armed pullers have different
    deadlift mechanics. Short-torso squatters have different positions. Do
    not apply generic standards without accounting for the athlete's build.

DIET & BODYWEIGHT (if provided)
  - Caloric status (surplus, deficit, maintenance, unclear).
  - Bodyweight trend with direction and magnitude.
  - An athlete in a deficit should NOT be expected to hit PRs. Strength
    maintenance in a cut is a win. Evaluate accordingly.

SLEEP & RECOVERY (if provided)
  - Average sleep hours and trends.
  - Poor or declining sleep is a confounder for every other metric. Flag it
    as a root cause before blaming programming.

SUPPLEMENTS (if provided)
  - Current supplement stack.
  - Note only if something is conspicuously missing for the context (e.g.,
    creatine for a strength athlete) or if a supplement could explain a trend.
    Do not lecture about supplements unprompted.

SESSION COMMENTS (if provided)
  - Athlete-written notes on individual sessions.
  - These are first-person context — fatigue notes, pain reports, RPE feel,
    life stress mentions. Treat them as ground truth for subjective state.
    They often explain why a number looks off better than any metric can.

COMPLETED & PLANNED SESSIONS
  - What has been done and what is scheduled.
  - Gaps between sessions are NORMAL. Rest days, deload weeks, life
    interruptions, and rotating schedules are all standard. A week with no
    deadlift data means the athlete did not deadlift that week — it does not
    mean the data is incomplete or the program is flawed.
  - Partial weeks at the start or end of the analysis window are valid data.

PLANNED SESSION INTERPRETATION:
- Sets with load_type "rpe": intensity-regulated. Do NOT treat as zero load.
  Estimate relative intensity for qualitative assessment only:
  RPE 10 ≈ 100%, RPE 9 ≈ 96%, RPE 8 ≈ 92%, RPE 7 ≈ 88% of current e1RM.
  Use language like "RPE 8 prescribed" — never cite a projected kg figure.
- Sets with load_type "absolute": use kg value as-is.
- Sets with load_type "unspecified": exclude from volume assessment entirely.
  Note their presence as a data gap if it affects a meaningful number of sets.
- When summarising future block load for an exercise that mixes absolute and
  RPE sets, describe them separately — do not aggregate into a single volume
  figure unless you can resolve both to the same intensity basis.

WEEKLY ANALYSIS (deterministic analytics report)
  - Pre-computed metrics: e1RM trends, volume loads, tonnage, fatigue
    indicators, etc.
  - This is your primary quantitative evidence. The formula_reference section
    explains how each metric was calculated — use it so your reasoning is
    grounded in the actual computation, not assumptions.

EXERCISE ROI (if provided)
  - Per-accessory pearson r between weekly volume and average intensity over
    the block. Treat |r| >= 0.60 with >= 4 weeks observed as a strong prior
    that the accessory is pulling its weight; low |r| on a high-fatigue
    accessory is a flag worth noting in monitoring_focus or small_changes.
  - Anatomy still gates: a high |r| on an accessory unrelated to the
    competition lifts is not evidence of ROI toward the primary goal.

═══════════════════════════════════════════════════════════════════
EVALUATION FRAMEWORK
═══════════════════════════════════════════════════════════════════
For each competition in the block:
  1. Role: primary or practice, based on the explicit goals and competition strategy.
  2. Weeks to comp: how far out is the athlete right now?
  3. Alignment: given the current phase, metrics, and trajectory, is the
     athlete on track for a good showing? Rate: good / mixed / poor.
  4. Reason: cite specific data points (e1RM trends, volume progression,
     bodyweight, fatigue indicators) that support your rating.

For goal_status:
  - Rate each explicit goal: achieved / on_track / at_risk / off_track / unclear.
  - Reason from linked standards, projections, bodyweight trend, meet timing,
    meet federation eligibility, and weight-class compatibility.

For competition_strategy:
  - For each relevant meet, decide whether it should be prioritized,
    treated as supporting practice, deprioritized, or dropped.
  - Choose an approach: all_out / qualify_only / minimum_total / podium_push /
    train_through / conservative_pr / drop.
  - If a competition has governing_goal.required_total_kg, use that as the
    success bar for the recommendation. Mention lower secondary standards only
    as fallback context; do not substitute them for the real target.
  - If a primary goal has only 1-2 remaining eligible opportunities, do not
    casually label those meets as practice unless the goal is already achieved
    or clearly unrealistic.
  - If recommending a drop, tie it directly to a higher-priority goal or an
    interference problem.
  - alternative_strategies: when multiple viable paths exist, include
    alternative approaches with target_total_kg, target_weight_class_kg, and
    reason.

For weight_class_strategy:
  - State the recommended class for the block, list viable options, and explain
    tradeoffs around bodyweight trend, cut feasibility, and qualifying goals.

For what_is_working / what_is_not_working:
  - Cite the actual numbers. "Squat e1RM trending up from X to Y over Z
    weeks" is useful. "Squat looks good" is not.
  - If diet, sleep, or bodyweight context explains a trend, say so.

For small_changes:
  - Each change must be the MINIMUM intervention needed.
  - Include risk: what could go wrong if this change is made.
  - Priority: low (nice to have), moderate (worth doing soon), high (address
    this week).
  - If nothing needs changing, return an empty array. "No changes needed" is
    a valid and good outcome.

For monitoring_focus:
  - What should the athlete keep an eye on over the next 1-2 weeks?
  - Tie each item to a specific metric or trend.

═══════════════════════════════════════════════════════════════════
INSUFFICIENT DATA
═══════════════════════════════════════════════════════════════════
Set insufficient_data to true ONLY if there are fewer than 2 completed
sessions in the entire block. If there is any meaningful data to analyze,
analyze it. Partial data is normal. Work with what exists.

Return valid JSON only using the tool schema.

```

Inputs:

- `task`: evaluation goal string
- `instructions`: tuning instructions (tone, stance preference, do-not list, focus)
- `program_meta`: block metadata (name, start, comp date, federation, sex, weight
  class, body weight, targets, anthropometrics, attempt percents, last comp)
- `phases`: phase definitions with target RPE ranges
- `goals`: explicit block goals with linked competitions, standards, target totals,
  weight classes, and remaining eligible opportunities
- `full_block_summary`: completed sessions and weeks count
- `competitions`: full competition context with eligible federations, linked goals,
  governing goals, and required totals
- `meet_interference`: pairwise meet conflict analysis
- `lift_profiles`: style notes, sticking points, volume tolerance, stimulus coefficient
- `athlete_measurements`: height, wingspan, leg length, bodyweight
- `supplements`: current stack and supplement phases
- `diet_context`: caloric status, macros, sleep, consistency
- `bodyweight_trend`: points, latest, oldest, change, direction
- `completed_sessions`: full session detail with exercises, wellness, notes
- `planned_sessions`: future sessions with load-type-aware serialization
- `weekly_analysis`: deterministic backend analytics report
- `exercise_roi`: top 15 accessories by |Pearson r|
- `formula_reference`: definitions of internal analytics formulas

Output (all required unless noted):

- `stance`: `continue` / `monitor` / `adjust` / `critical`
- `summary`: 2-4 sentence overall summary
- `what_is_working[]`: positive findings
- `what_is_not_working[]`: negative findings
- `competition_alignment[]`: per-meet with `competition`, `role` (primary/practice),
  `weeks_to_comp`, `alignment` (good/mixed/poor), `reason`
- `goal_status[]`: per-goal with `goal`, `priority` (primary/secondary/optional),
  `status` (achieved/on_track/at_risk/off_track/unclear), `reason`
- `competition_strategy[]`: per-meet with `competition`,
  `priority` (prioritize/supporting/practice/deprioritize/drop),
  `approach` (all_out/qualify_only/minimum_total/podium_push/train_through/
  conservative_pr/drop), `reason`,
  optional `alternative_strategies[]` with `approach`, `target_total_kg`,
  `target_weight_class_kg`, `reason`
- `weight_class_strategy`: `recommendation`, `recommended_weight_class_kg`,
  `viable_options[]` with `weight_class_kg`, `suitability` (best/viable/risky),
  `reason`
- `small_changes[]`: per-change with `change`, `why`, `risk`,
  `priority` (low/moderate/high)
- `monitoring_focus[]`: metrics to watch
- `conclusion`: short final recommendation
- `insufficient_data`: boolean (optional)
- `insufficient_data_reason`: string (optional)

Cache behavior:

- cached on a weekly cadence under `program_eval#{window_start}`
- `Regenerate` bypasses cache
- cache invalidated if `program_updated_at` or `federation_library_updated_at` change

Minimum data:

- backend requires at least 4 completed weeks

Important frontend/backend mismatch:

- frontend gate only checks for at least 4 completed sessions before trying to
  show the card
- backend is stricter and may still return insufficient data

### 4. Accessory e1RM backfill

User-visible surface:

- glossary estimate e1RM flows

Route:

- `POST /api/exercises/:id/estimate-e1rm`

Tool/module path:

- `glossary_estimate_e1rm`
- `tools/health/e1rm_backfill_ai.py`

Prompt summary:

- estimate accessory training maxes as conservative ratios of primary SBD lifts
- use lift profiles and past logged instances when available
- prefer underestimation to overestimation
- confidence is intentionally only `medium` or `low`

Persisted output:

- writes `glossary[].e1rm_estimate`

### 5. Template evaluation

User-visible surface:

- Template detail -> `AI Evaluation`

Route:

- `POST /api/templates/:sk/evaluate`

Tool/module path:

- `template_evaluate`
- `tools/health/template_evaluate_ai.py`

Prompt summary:

- judge whether a template fits current athlete context and meet timeline
- produce stance, strengths, weaknesses, suggestions, projected readiness at comp
- treat RPE and percentage-based planned sessions specially

Important current rough edge:

- `core.template_evaluate()` currently passes mocked athlete context:
  - `current_maxes`
  - `dots_score = 350`
  - `weeks_to_comp = 12`
- so template evaluation is real AI output, but not yet fed by the full current
  athlete context you might expect

### 6. Spreadsheet import AI

User-visible surface:

- Import wizard

AI modules:

- `import_classify_ai.py`
  - classify file as `template`, `session_import`, or `ambiguous`
- `import_parse_ai.py`
  - parse structured phases, sessions, warnings, parse notes
- `glossary_resolve_ai.py`
  - resolve exercise names to glossary IDs or suggest new entries

Prompt summaries:

- classification looks for real dates vs relative weeks and absolute kg vs RPE/%
- parsing extracts structured training data and warnings without inventing rows
- glossary resolution handles abbreviations and nicknames, but only suggests
  new entry `name`, `category`, and `equipment`

## Other Important User-Facing Surfaces

### Dashboard

The Dashboard is the main control surface for:

- program meta edits
- weight log interaction
- lift-profile review / rewrite / stimulus estimation
- anthropometrics

### Glossary page

The Glossary page is where exercise intelligence lives:

- canonical exercise definitions
- category and muscle mapping
- fatigue profile
- fatigue-profile reasoning
- accessory e1RM estimates
- archive state

### Template library and designer

These pages manage:

- blank template creation
- block-to-template conversion
- template archive/unarchive
- application to a program
- AI evaluation

### Tools page

Deterministic utility tools include:

- DOTS calculator
- attempt selector
- unit converter
- percent table
- plate calculator
- weight tracker

### Rankings page

The Rankings page is separate from the core training analytics. It compares user
totals and DOTS to the OpenPowerlifting dataset with filterable federation,
country, region, equipment, sex, age class, year, and event type.

### Videos

Videos are stored and displayed, but no computer-vision analysis is currently
performed.

## Current Rough Edges And Read The Code Notes

These are the places where the UI, backend, or data model still have deliberate
or temporary mismatches:

1. Backend `weekly_analysis.estimated_dots` still depends on
   `meta.bodyweight_kg` and `meta.sex`, not `meta.current_body_weight_kg`, while
   frontend trend cards use `settingsStore.sex` and local weight-log / session
   bodyweight sources. That is why backend DOTS can be null while the local
   trend DOTS still renders.
2. The top max card is not the same thing as backend `current_maxes`. It prefers
   local Epley-based trend maxima when those exist, then falls back to backend
   current maxes.
3. `attempt_selection` is computed but not rendered on the Analysis page.
4. Program-evaluation gating differs between frontend and backend.
5. Template evaluation still passes mocked, minimal athlete context.
6. The glossary fatigue-estimation path is rougher than the auto-add path.

Consistency rule:

- every formula-touching change must update `README.md`, `AboutPage.tsx`, and
  `formulaDescriptions.ts` in the same PR

## Bottom Line

The powerlifting app is not just a logbook. It is a layered system:

- raw training data and meet data in DynamoDB
- glossary metadata for anatomy and fatigue semantics
- deterministic analysis in `tools/health/analytics.py`
- narrow AI interpretation layers in `tools/health/*_ai.py`
- a React Analysis page that mixes backend analytics with additional local trends

The most important customizations are the ones that make the portal athlete-
specific instead of textbook-generic:

- conservative current-max estimation instead of naive Epley everywhere
- deload-aware progression math
- four-dimensional fatigue instead of one load number
- fatigue index without skip-rate inflation
- stimulus-adjusted INOL from lift profiles
- phase-aware RPE drift and readiness
- DOTS-sensitive, taper-aware meet projection

If you are changing the analytics or the AI prompts, update this README at the
same time. The portal's behavior is now too custom for a short marketing README
to stay truthful.
