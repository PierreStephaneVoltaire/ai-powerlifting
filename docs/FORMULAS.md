# Formulas

Math-heavy breakdown of every deterministic formula in the portal. For each one:
the equation, the variables, the thresholds, **what's different from the textbook/
original version**, and the **pros and cons** of the chosen approach.

The canonical formula prose in the app lives in
`frontend/src/constants/formulaDescriptions.ts`. Where that prose and this doc
disagree, the code (and [`REFERENCE.md`](./REFERENCE.md)) wins.

A guiding principle across all of these: **training logs are noisy**, and the
portal is **athlete-specific** rather than textbook-generic. Most customizations
exist to be robust to bad data or to avoid a one-size-fits-all assumption.

---

## Table of contents

1. [Estimated 1RM and current max selection](#1-estimated-1rm--current-max-selection)
2. [Deload detection and effective weeks](#2-deload-detection--effective-weeks)
3. [Progression rate](#3-progression-rate)
4. [Volume / intensity correlation](#4-volume--intensity-correlation)
5. [RPE drift](#5-rpe-drift)
6. [Fatigue model (4 dimensions)](#6-fatigue-model-4-dimensions)
7. [Fatigue index](#7-fatigue-index)
8. [Stimulus-adjusted INOL](#8-stimulus-adjusted-inol)
9. [ACWR](#9-acwr)
10. [Volume landmarks (MV / MEV / MAV / MRV)](#10-volume-landmarks)
11. [Specificity ratio](#11-specificity-ratio)
12. [Banister CTL / ATL / TSB, monotony, strain, taper quality](#12-banister-ctl--atl--tsb-monotony-strain-taper-quality)
13. [Relative intensity distribution](#13-relative-intensity-distribution)
14. [Readiness score](#14-readiness-score)
15. [Competition projection](#15-competition-projection)
16. [Projection calibration (PRR)](#16-projection-calibration-prr)
17. [Attempt selection](#17-attempt-selection)
18. [DOTS score](#18-dots-score)
19. [IPF GL score](#19-ipf-gl-score)
20. [Compliance](#20-compliance)

---

## 1. Estimated 1RM and current max selection

Used by: backend current maxes, meet projection, INOL / ACWR / RI distribution.
The frontend trend table uses a *separate* local RPE-table / conservative-percent
path, so the two can legitimately differ.

### Equation

```text
If session RPE exists and reps are 1..6 and RPE is 6..10:
  e1RM = weight / RPE_TABLE[(reps, RPE)]

Else if no RPE exists and reps are 1..5:
  e1RM = weight / CONSERVATIVE_REP_PCT[reps]
```

### Selection rules

- ignore failed sets for the per-set estimate path
- use only recent session estimates within the last **42 days**
- take the **90th percentile** per lift
- require at least **3 qualifying estimates** per lift
- require at least **2 lifts total** for a session-derived current-max object
- **real competition results override estimates** when available

### Variables

| Name | Description |
|------|-------------|
| `weight` | Load lifted in kg |
| `reps` | Repetitions performed |
| `rpe` | Rate of Perceived Exertion (6-10) |
| `pct` | RPE-based or conservative % of 1RM |

### What's different

Textbook e1RM (Epley, Brzycki, Lombardi) is a single closed-form equation fitted
to broad populations. Here it is **not used as the primary truth path**. Instead:

- an **RPE table** is preferred when reps are at most 6 and RPE is present (RPE
  encodes proximity-to-failure directly, which is what these equations are
  *estimating*)
- a **conservative percent table** is the fallback for reps at most 5 with no RPE
- the **90th percentile** dampens one-off inflated sets instead of taking the max
- real meet results override estimates

### Pros

- More accurate for lifters who already log RPE (no need to back-fit an
  equation).
- Percentile selection is robust to a single ego set.
- Meet results are the ground truth and win when present.

### Cons

- Requires RPE discipline in the log; without it, you fall back to the
  conservative table.
- The 3-estimate / 2-lift gates mean early in a program the card can be empty.
- Conservative by design: it will understate a true 1RM more often than it
  overstates it. That's intentional for projection math, but worth knowing.

---

## 2. Deload detection and effective weeks

Used by: progression rate, effective training week count, projection logic, the
deload info block on the Analysis page.

### Rules

```text
A week is a BREAK if volume load == 0.

A week is a DELOAD if:
  1. weekly volume load is below a rolling median threshold, AND
  2. intensity confirms it was intentionally easy
```

### Thresholds

- Volume threshold **with** squat/deadlift present: less than `0.65 * median(previous
  rolling non-deload weeks)`
- Volume threshold **without** squat/deadlift: less than `0.75 * median(...)`
- Intensity confirmation (either):
  - all primary-lift RPEs at most 6, **or**
  - best primary-lift e1RM dropped at least 10% vs the previous two non-deload weeks
- **Stagnation alone does not count as a deload.**

### What's different

Most apps either (a) never detect deloads and let them flatten progression, or
(b) flag any low-volume week as a deload. This does neither:

- it requires **both** low volume **and** low intensity evidence
- it uses a **rolling median of prior non-deload weeks** (relative to *your*
  load, not a fixed cutoff)
- a week where you simply didn't progress is **not** labeled a deload

### Pros

- Deliberate easy weeks don't artificially flatten your progression slope.
- The intensity gate prevents a heavy low-volume week (e.g. a peaked single)
  from being misread as a deload.

### Cons

- Needs a few weeks of history before the rolling median is meaningful.
- The 10% e1RM drop is a heuristic; an off week could look like a deload.

---

## 3. Progression rate

Used by: per-lift breakdown, meet projection.

### Equation

```text
For each effective training week:
  best_weekly_e1RM = max(qualifying e1RMs in that week)

slope = Theil-Sen(best_weekly_e1RM ~ effective_week_index)
kendall_tau = KendallTau(effective_week_index, best_weekly_e1RM)
fit_quality = 1 - MAD(residuals) / MAD(series)
```

- Cutoff: last **90 days**.
- Only completed/logged sessions count.
- Deload and break weeks are excluded (effective-week indexing).
- The weekly point uses the **best** qualifying set, not the average.

### Variables

| Name | Description |
|------|-------------|
| `e1RM` | Estimated 1RM per session |
| `effective_week` | Week index excluding deloads/breaks |
| `slope` | kg per week rate of change |
| `kendall_tau` | Rank correlation between effective week and e1RM (-1 to 1) |
| `fit_quality` | Normalized MAD fit quality (0-1) |

### What's different

Textbook progression is often a plain OLS (least-squares) slope on raw weeks.
This uses **Theil-Sen** (median of pairwise slopes) and **effective weeks**.

### Pros

- **Robust to outliers**: Theil-Sen ignores a single huge or terrible session.
- **Effective-week indexing** prevents deliberate deloads from flattening the
  slope.
- `kendall_tau` + `fit_quality` tell you whether the slope is trustworthy at all
  (a slope on noise is useless).

### Cons

- Theil-Sen is O(n^2): fine for 90 days of weeks, not for huge series.
- The "best set per week" point can still be noisy if a week has one fluke set;
  the percentile e1RM upstream mitigates this.

---

## 4. Volume / intensity correlation

Used by: per-lift volume and intensity percent-change display, accessory ROI
prior for the correlation AI.

### Equation

```text
weekly_volume = sum(sets * reps * kg) for the exercise in that week
weekly_avg_intensity = mean(kg) for that exercise in that week
pearson_r = corr(weekly_volume, weekly_avg_intensity)
```

- Requires at least **3 weeks** of data.

### What's different

Nothing structurally: this is a standard Pearson correlation. The customization
is that it's computed **per exercise per week** and feeds the AI's accessory ROI
analysis as a prior, rather than being a standalone verdict.

### Pros / cons

- Pro: cheap, interpretable, gives the AI a grounded signal.
- Con: Pearson is sensitive to outliers and assumes linearity; with only 3 weeks
  it's directional at best.

---

## 5. RPE drift

Used by: per-lift breakdown, readiness score, flags.

### Equation

```text
If phase target RPE ranges exist:
  residual = actual_session_rpe - phase_target_midpoint
  slope = Theil-Sen(residual ~ week)
Else:
  slope = Theil-Sen(actual_rpe ~ week)

kendall_tau = KendallTau(week, residual_or_raw_rpe)
fit_quality = 1 - MAD(residuals) / MAD(series)
```

### Thresholds

| Label | Condition | Meaning |
|-------|-----------|--------|
| Fatigue | `slope >= 0.1` | RPE rising at the same loads |
| Adaptation | `slope <= -0.1` | Getting stronger at the same loads |
| Stable | `abs(slope) < 0.1` | No significant trend |

### What's different

Textbook RPE tracking plots raw RPE over time. This compares RPE to the
**phase target midpoint** (`(target_rpe_min + target_rpe_max) / 2`), so it
measures drift against the *intended* difficulty, not absolute RPE.

### Pros

- Rising RPE at the same planned difficulty is a real fatigue signal: raw RPE
  trend can't distinguish that from a deliberately harder phase.
- Falls back to raw-RPE slope when no phase target exists.

### Cons

- Requires accurate phase target RPE ranges to be useful.
- The 0.1 RPE/week threshold is a heuristic.

---

## 6. Fatigue model (4 dimensions)

Used by: fatigue dimensions table, fatigue index spike path, ACWR.

### Equation

```text
I = weight / e1RM                       (intensity ratio)
phi(I) = 0                              if I <= 0.60
phi(I) = ((I - 0.60) / 0.40)^3         otherwise

F_axial      = profile.axial      * weight^1.30 * reps
F_neural     = profile.neural     * reps * phi(I) * sqrt(weight / 100)
F_peripheral = profile.peripheral * weight^1.15 * reps
F_systemic   = profile.systemic   * weight * reps * (1 + 0.30 * I)
```

### Implementation notes

- Only squat, bench, deadlift get a direct current-max lookup for `I`.
- Non-SBD exercises fall back to `I = 0.70` for neural scaling.
- Weekly totals multiply per-set values by `sets`.
- Missing glossary fatigue profiles fall back to category defaults.

### What's different

Textbook fatigue is a single number (usually tonnage or training stress score).
This splits fatigue into **four dimensions** with **nonlinear** per-set scaling:

- `axial` and `peripheral` scale super-linearly with load (`^1.30`, `^1.15`)
- `neural` is **intensity-gated** by the cubic `phi(I)`: it's zero below 60%
  and ramps hard near-maximal
- `systemic` scales with load x reps x intensity

### Pros

- A heavy single and a high-rep accessory set produce *different kinds* of
  fatigue, not just different magnitudes.
- The neural gate means a light high-rep day doesn't read as "neurally fatiguing."

### Cons

- The per-dimension profile coefficients come from the glossary/AI estimation:
  quality depends on those inputs.
- The `^1.30` / `^1.15` exponents are tuned heuristics, not derived from
  physiology directly.

---

## 7. Fatigue index

Used by: the current fatigue state card.

### Equation

```text
R_d,t = R_d,t-1 * exp(-ln(2) / half_life_d) + Load_d,t
S_d,t = clamp((R_d,t / baseline_d - 1.0) / 0.75, 0, 1)
ReservoirStress = 0.60 * max(S_d) + 0.40 * weighted_mean(S_d)

FI = 0.10*fail + 0.12*spike + 0.15*rpe + 0.34*reservoir
   + 0.10*overload_streak + 0.09*intensity_density + 0.10*monotony
```

### Thresholds

| State | Range |
|-------|-------|
| Low | less than 0.25 |
| Moderate | 0.25 - 0.44 |
| High | 0.45 - 0.64 |
| Very high / overreaching risk | at least 0.65 |

### What's different

Most fatigue indices are dominated by chronic load. This combines **seven
components** (failures, acute spikes, RPE, decaying reservoirs, overload streaks,
intensity-density, and monotony) and crucially the **reservoir** component uses
`max(S_d)` weighted at 0.60 so a **localized** dimension overload isn't diluted
away by quiet lifts in other dimensions.

### Pros

- A single blowout session or one overloaded fatigue dimension surfaces even if
  the rest of the week was easy.
- Half-life decay means recent work matters more than old work.

### Cons

- Many weights to tune; they're hand-set, not learned.
- Requires the 4-dimension per-set model above as input.

---

## 8. Stimulus-adjusted INOL

Used by: INOL card, AI paths.

### Equation

```text
INOL = sets * reps / (1 - intensity_ratio)
stimulus_adjusted_INOL = INOL * stimulus_coefficient
```

- `stimulus_coefficient` comes from the per-lift `LiftProfile`.

### Thresholds

| Label | Low | High |
|-------|-----|------|
| Underwork | below `inol_low_threshold` | - |
| Sweet spot | at least low | at most high |
| Overreach | - | above `inol_high_threshold` |

### What's different

Standard INOL is a single formula for all lifts. This multiplies by a
**per-lift stimulus coefficient** (with confidence + reasoning, AI-tuned) so the
same set/rep/intensity scheme can be appropriately dosed differently for squat vs
bench vs deadlift based on *your* lift profile.

### Pros

- Acknowledges that lifters respond differently to volume on different lifts.
- The thresholds are per-lift, not global.

### Cons

- Depends on a good stimulus coefficient estimate (AI).
- Adds a tuned parameter where INOL had none.

---

## 9. ACWR

Used by: fatigue/readiness.

### Equation

```text
ACWR = acute_load / chronic_load
```

### Thresholds

| Zone | ACWR |
|------|------|
| Under-training | below 0.80 |
| Sweet spot | 0.80 - 1.30 |
| Overreaching | above 1.30 |

### What's different

Nothing structurally: standard acute:chronic workload ratio. The customization
is that the *load* feeding it is the **4-dimension fatigue model** output, not
raw tonnage, so the ratio reflects stress dimensions rather than just volume.

### Pros / cons

- Pro: more physiologically meaningful than tonnage-based ACWR.
- Con: inherits the fatigue model's tuning and glossary-profile dependency.

---

## 10. Volume landmarks

Used by: volume landmarks card.

### Equation

```text
weekly_sets_bin = floor(weekly_sets / 2) * 2
MV  = first bin with delta_e1rm >= 0
MEV = first bin with delta_e1rm > 0
MAV = bin with max delta_e1rm
MRV = first bin where next_week_fi > 0.60 or delta_e1rm < 0
```

### Confidence by history length

| Confidence | Weeks |
|------------|-------|
| Low | 12 - 17 |
| Medium | 18 - 25 |
| High | 26+ |

### What's different

Textbook landmarks (Reinaro/Helms) are fixed heuristics. These are **derived
from your own history**: weekly sets are binned, and the landmarks are read off
the e1RM-delta and next-week-fatigue response. MRV uses a fatigue-index gate
(`next_week_fi > 0.60`) rather than a fixed volume cap.

### Pros

- Personalized to your response curve.
- The fatigue-index MRV gate ties recovery capacity to your actual fatigue
  state, not a generic number.

### Cons

- Needs a lot of clean history (12+ weeks minimum).
- Binning into 2-set buckets is coarse for low-volume weeks.

---

## 11. Specificity ratio

Used by: peaking section, comp alignment.

### Equation

```text
SR_narrow = SBD sets / total sets
SR_broad  = (SBD + secondary category) / total sets
```

Only **executed** sets count.

### Expected bands by weeks-to-comp

| Weeks to comp | Narrow | Broad |
|---------------|--------|-------|
| 16+ | 0.30-0.50 | 0.60-0.75 |
| 12-16 | 0.40-0.55 | 0.65-0.80 |
| 8-12 | 0.50-0.65 | 0.75-0.85 |
| 4-8 | 0.60-0.75 | 0.80-0.90 |
| 0-4 | 0.70-0.85 | 0.85-0.95 |

### What's different

Textbook specificity is usually just "% of work that is competition lifts." This
adds a **broad** ratio (competition lifts + same-category accessories) and
**timeline-relative expected bands** so the ratio is judged against where you are
in the prep, not a flat target.

### Pros / cons

- Pro: the broad ratio credits close-grip bench / pause squats etc. without
  pretending they're competition lifts.
- Con: "secondary category" depends on glossary classification quality.

---

## 12. Banister CTL / ATL / TSB, monotony, strain, taper quality

Used by: peaking section.

### Equation

```text
CTL  = EWMA(7-day load, large time constant)
ATL  = EWMA(7-day load, small time constant)
TSB  = CTL - ATL
Monotony = mean(daily load) / std(daily load)
Strain   = Monotony * sum(load)
TaperQuality = score from load reduction, monotony drop, TSB rise
```

### Taper quality thresholds

| Label | Score |
|-------|-------|
| Poor | below 40 |
| Serviceable | 40 - 59 |
| Good | 60 - 79 |
| Excellent | at least 80 |

### What's different

Standard Banister model. The customization is the **taper quality** composite
score, which combines load reduction, monotony drop, and TSB rise into a single
0-100 grade rather than reporting them separately.

### Pros / cons

- Pro: one number for "is my taper going well."
- Con: the EWMA time constants and taper-quality weights are tuned heuristics.

---

## 13. Relative intensity distribution

Used by: RI distribution card.

### Equation

```text
RI = weight / E_now
Heavy:    RI > 0.85
Moderate: 0.70 <= RI <= 0.85
Light:    RI < 0.70
```

### What's different

Standard relative-intensity bucketing. The customization is that `E_now` is the
**conservative** e1RM from section 1 (not a generic max), so the buckets reflect
your *real* current strength.

### Pros / cons

- Pro: distribution is against your current capacity, not a stale or generic
  number.
- Con: if the e1RM estimate lags a real PR, you'll briefly over-bucket as heavy.

---

## 14. Readiness score

Used by: readiness card.

### Equation

```text
TrainingReadiness  = 100 * (1 - weighted_penalty(fatigue, rpe_drift, performance_trend))
ExternalReadiness  = 100 * (1 - weighted_penalty(wellness, bodyweight))
OverallReadiness   = 0.70*TrainingReadiness + 0.30*ExternalReadiness
```

- Missing data **re-weights** available components without penalizing.
- Performance trend only uses executed sets.

### Thresholds

| Label | Score |
|-------|-------|
| Green | above 75 (ready to train) |
| Yellow | 50 - 75 (proceed with caution) |
| Red | below 50 (recovery priority) |

### What's different

Most readiness scores either ignore missing data or penalize it. This
**re-weights** the available components so a day with no wellness log isn't a
zero: it just shifts weight to fatigue/RPE/trend. It also splits training vs
external readiness (70/30) so subjective context can't fully mask training
stress.

### Pros

- Doesn't punish you for not logging wellness one day.
- `readiness_confidence` (available/total weight) tells you how much to trust it.

### Cons

- The 70/30 split is a fixed choice.
- More moving parts to tune than a single composite.

---

## 15. Competition projection

Used by: projection card, attempt selection.

### Equation

```text
C_max = [E_now + delta_w * lambda_effective * (1 - lambda_effective^n) / (1 - lambda_effective)] * P
lambda_effective = min(lambda_tier * lambda_multiplier, 0.995)
ceiling_pct      = min(20%, 10% + 0.5% * max(0, weeks_to_comp - 8))
clamped to [E_now, E_now * (1 + ceiling_pct)]

n = weeks_remaining - taper_weeks - planned_deloads
```

### Tiered decay and peak factors (by DOTS)

| DOTS | lambda (decay) | P (peak) |
|------|----------------|----------|
| below 300 | 0.96 | 1.01 |
| 300 - 400 | 0.90 | 1.03 |
| at least 400 | 0.85 | 1.05 |

### What's different

Textbook projection is often a linear extrapolation of progression rate. This is
a **diminishing-returns geometric series** with three extra guards:

1. **DOTS-tiered lambda and P**: stronger lifters decay faster and peak higher.
2. **PRR-calibrated lambda** (section 16): `lambda_multiplier` re-tunes decay
   from actual meet results.
3. **Time-scaled ceiling**: gain is clamped to `E_now * (1 + ceiling_pct)`,
   topping out at 20%, so the model can't promise an absurd number.

### Pros

- Taper and planned deloads are subtracted from `n`, so peaking is realistic.
- The ceiling prevents runaway optimism on long horizons.
- Calibration makes it self-correcting across meets.

### Cons

- Needs a few completed meets before calibration kicks in.
- The DOTS-tier breakpoints are hand-set.

---

## 16. Projection calibration (PRR)

Used by: competition projection (feeds `lambda_multiplier`).

### Equation

```text
PRR_lift  = actual_lift / projected_at_t_minus_1w_lift
PRR_total = actual_total / projected_total   (only when all 3 lifts are valid)
lambda_multiplier = clamp(median(PRR_total over last 3 completed meets), 0.92, 1.05)
```

Calibrated if at least **2 completed meets** have valid total PRR.

### What's different

Most projection models are static. This measures how well past projections did
against actual results (the **Projection-to-Result Ratio**) and uses the median
over the last 3 meets to nudge the decay factor, clamped to `[0.92, 1.05]` so a
single meet can't wildly swing it.

### Worked example (real data)

At the Ottawa Open (CPU, 2025-10-04), the T-1w projection was **546.4 kg** total
and the actual was **520 kg** (185/115/220 at 78.2 kg). That's a total PRR of
**0.952**: the model over-projected by about 5%. Per-lift: squat 1.012 (under-
projected), bench 0.969, deadlift 0.898 (most over-projected, consistent with the
athlete's own note: *"sandbagged deadlifts: had at least 10 kg in me"*). Feeding
this back tightens future deadlift decay.

### Pros

- The model learns from its own errors across meets.
- The clamp prevents overreaction to one outlier meet.

### Cons

- Requires the `projected_at_t_minus_1w` snapshot to have been stored at the
  time; without it, PRR can't be computed for that meet.
- Needs at least 2 qualifying meets before it engages.

---

## 17. Attempt selection

Used by: attempt selection (computed; not currently rendered on the Analysis
page).

### Equation

```text
attempt_k = round_to_2.5(C_max * pct_k)
total = sum of all third attempts
round_to_2.5(v) = round(v / 2.5) * 2.5
```

### Defaults

| Attempt | % | Intent |
|---------|---|--------|
| Opener | 90% | Should feel easy under worst conditions |
| Second | 95.5% | A confident single, builds momentum |
| Third | 100% | Your projected max |

### What's different

Standard attempt-percentage model. The customization is that `C_max` is the
**calibrated competition projection** (sections 15/16), not a raw max, and the
percentages are user-configurable in program meta.

### Pros / cons

- Pro: attempts track the projection (and thus calibration) automatically.
- Con: rounding to 2.5 kg can mask small projection changes.

---

## 18. DOTS score

Used by: projection tiering, rankings.

### Equation

```text
DOTS = 500 * total / (a + b*bw + c*bw^2 + d*bw^3 + e*bw^4)
```

`total` and best e1RM per session only consider **executed sets**.

### What's different

Standard DOTS polynomial with sex-specific coefficients. The customization is
operational: only executed sets count, and it's computed consistently from the
same e1RM source as everything else.

### Pros / cons

- Pro: widely understood scoring coefficient; good for federation-agnostic
  comparison.
- Con: polynomial can over-reward extreme bodyweight edges; that's inherent to
  DOTS, not this implementation.

---

## 19. IPF GL score

Used by: scoring card, rankings.

### Equation

```text
GL = result * 100 / (A - B * e^(-C * bw))
```

`result` is the SBD total for classic powerlifting, or the bench result for
bench-only. Best results only consider executed sets.

### What's different

Standard IPF GL formula with sex- and discipline-specific coefficients. Like
DOTS, the customization is consistency: executed-sets-only and shared e1RM
source.

### Pros / cons

- Pro: IPF-recognized; better for IPF-affiliated meet planning than DOTS.
- Con: the exponential denominator is more sensitive at extreme bodyweights.

---

## 20. Compliance

Used by: compliance card.

### Equation

```text
session_compliance = (completed_sessions / planned_sessions) * 100
set_compliance      = (executed_sets / planned_sets) * 100
volume_compliance   = (executed_volume / planned_volume) * 100
```

### What's different

Textbook compliance often excludes deloads/breaks to flatter the number. Here,
**all weeks are counted**: deloads and programmed breaks are **not** excluded.
`completed` means `completed == true` or `status in ('logged', 'completed')`.
Executed sets = `completed` or `failed`.

### Pros

- An honest picture of adherence, not a curve-friendly one.
- Three angles (sessions / sets / volume) catch different kinds of non-
  compliance (skipped session vs skipped sets vs lighter loads).

### Cons

- A programmed deload that you followed will look like 100% session compliance
  but low set/volume compliance (by design, but can confuse a casual reader).
- No partial credit for a shortened session.

---

## Summary of design intent

Across all formulas, three themes repeat:

1. **Robust to noisy logs**: percentile selection, Theil-Sen, MAD fit quality,
  re-weighted readiness. A single bad entry shouldn't move the needle.
2. **Athlete-specific, not generic**: per-lift stimulus coefficients, derived
  volume landmarks, PRR-calibrated projection, phase-aware RPE drift.
3. **Honest over flattering**: compliance doesn't exclude deloads, fatigue
  doesn't let skips dilute real stress, errors are loud.

If you change any of these, update `formulaDescriptions.ts` and this doc at the
same time.
