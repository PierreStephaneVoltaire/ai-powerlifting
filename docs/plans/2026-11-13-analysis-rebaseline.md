# Analysis rebaseline (R1)

Operator fixture, `fixtures/operator`, as of 2026-11-11. "Old" is the golden; "new" is `pl-analytics` after R1.
Parity comparator: `tests/common/mod.rs` (`REBASELINED`, `REBASELINED_EXACT`) skips exactly the paths below.
Every other path still matches the goldens.

| Metric (path) | Old | New | Why |
|---|---|---|---|
| ACWR composite (`acwr.composite`, current window) | 0.392 | 0.446 | EWMA now seeded from full history across blocks (was the current block only); dimensions without a ratio are excluded and weights renormalised. |
| ACWR dimensions (`acwr.dimensions.*.value`) | axial 0.282, neural 0.579, peripheral 0.344, systemic 0.320 | 0.351, 0.597, 0.413, 0.390 | Same (history seed). New fields `acute`, `chronic` per dimension and `weights_used`. |
| ACWR labels (`composite_label`, `dimensions.*.label`) | "Detraining trend (expected during planned overreach)" | "Detraining trend" | The suffix is added only to elevated zones, only when the active phase of the block is tagged "overreach" (RPE >= 9 rule dropped). |
| Banister (`banister.ctl_today`, `atl_today`, `tsb_today`) | 97.019, 34.528, 62.492 | 66.664, 32.135, 34.529 | Seeded from full history; baselines from the trailing 12 complete weeks of all blocks (`load_baselines.axial` 2651.0 -> 3333.7). Model id `normalized_dimension_banister_v3`. |
| Banister label (`banister.tsb_label`) | "Productive overreach" (TSB -30..-10) | "Productive fatigue", or "Planned overreach" when the block's active phase is tagged overreach | The label describes the balance neutrally; overreach wording needs an explicit phase tag. Covered by the `.banister` skip. |
| Banister series (`banister.series`) | 33 points from 2026-10-10 | one point per day of the window | Series restricted to the window start; the values come from the full-history run. |
| Peaking timeline (`peaking_timeline.series`, `current_tsb`, `peak_date`, `peak_delta_days`, `closest_*`, `status_message`) | current_tsb 62.492, peak 2026-12-25 (127 d early) | current_tsb 34.529, peak 2026-11-13 (169 d early) | Derived from the Banister series. |
| Decoupling (`decoupling.current.decoupling`) | -22.273 | -17.223 | Fatigue index inside it changed (monotony stress below). |
| Monotony and strain (`monotony_strain.*`, current window) | 6 weekly rows, week 1 monotony 0.531, strain 5463.1 (raw units) | 3 rows (window only), week 1 monotony 0.750, strain 526.5 (normalized units); last row `partial: true`, `days_observed: 2` | Normalized load, restricted to the window, partial weeks flagged, `high_monotony` needs 3+ training days. New fields `days_observed`, `partial`. The old `strain_spike` flag disappears from `alerts.flags` (strain unit changed). |
| Fatigue index window stats (`fatigue_components.window_mean_fi`, `window_peak_fi`, `window_weighted_fi`) | 0.441, 0.521, 0.448 | 0.458, 0.546, 0.459 | The fatigue index's monotony stress was computed from one week of sessions against today's week and was always 0. It now uses the real weekly monotony and strain. |
| Fatigue index, block 2a82b27dee04e5 (`fatigue_index`, `current_state_fi`, `latest_week_fi`, `monotony_stress`) | 0.414, monotony_stress 0 | 0.504, monotony_stress 1.0 | Same fix. |
| ACWR summary, block 2a66df1513cb9e (`analyticsSummary.acwrComposite`) | 1.05 | 1.029 | Full-history seed. |
| Specificity (`specificity_ratio.broad`, `secondary_sets`) | broad 0.262, secondary_sets 3 | broad 0.190, secondary_sets 0.0, new `weighted_sets` 8.0 | Narrow = `lift_transfer` >= 0.9 (unchanged at the fixture, 0.190); broad weights the rest by transfer. The fixture glossary has no `lift_transfer` yet, so non-SBD exercises count 0 until the glossary backfill lands. |
| INOL thresholds (`inol.phase_adjusted_thresholds`) | bench low 2.2, high 5.5 (weekly, week 1 case) | bench low 3.5, high 8.75 (coefficient 1.4 x phase 1.25) | Thresholds are scaled by the stimulus coefficient so they are comparable with the adjusted value; the phase is now looked up inside the block (the old `weekly` run matched a phase of another block, multiplier 1.10, instead of the block's own 1.25). |
| INOL trend pressure (`inol.trend_pressure`) | from block weeks only | from the full-history previous 4 weeks | History seed. New `inol.lifts` and `inol.coefficient_sources`. |
| Current block / phase (`weekly` `block`, `compliance.phase`) | "Pivot / Reload" | "Off-season rebuild" | Phase lookup is scoped to the block (a phase of an older block matched before). |
| Readiness (`weekly` `readiness_score`) | score 38.8, zone red | score 59.8, zone yellow | The RPE target now comes from the block's own phase. |
| Fatigue dimensions weekly, spike, density, exercise stats (`fatigue_dimensions.weekly`, `fatigue_dimensions.spike`, `fatigue_components.intensity_density_stress`, `exercise_stats`) | e.g. weekly 2 axial 18557, density 0.922 (block 2a66), Lunges 6 sets | 18124.1, 0.701, Lunges 8 sets | One exercise-name normalizer (lowercase, trim, strip parentheses, singularize): plural and singular spellings now share the glossary profile, e1RM and stats. |
| Alerts (`alerts`, `flags` in weekly and alerts) | readiness alert, `strain_spike` | specificity alert; no `strain_spike` | Follows the changes above. |
| New fields | - | `workload.per_lift`, `workload.muscle_volume`, `fatigue_dimensions.normalized`, `fatigue_dimensions.chronic_baseline`, `fatigue_dimensions.baseline_weeks_used`, `acwr.weights_used`, `acwr.dimensions.*.acute/chronic`, `inol.lifts`, `inol.coefficient_sources`, `monotony_strain.weekly[].partial/days_observed`, `banister.baseline_weeks_used` | Additive. |

Unchanged and still matching goldens: overview (projections, compliance, maxes, DOTS), progression, RPE drift, workload `lifts`, blocks list, manifests, queue, taper quality, readiness for section windows, and every other field not listed above.

The lifetime shape snapshot (`tests/snapshots/lifetime__lifetime_shape.snap`) changed key order in one "worked" signal because the ACWR peak exposure feeding it changed.

`historical.analyticsSummary.muscleMap` stays `{}` for stored blocks: the legacy `muscle_volume` key no longer feeds it, because the key now carries the new per-muscle object. R4 should wire the new object in deliberately.
