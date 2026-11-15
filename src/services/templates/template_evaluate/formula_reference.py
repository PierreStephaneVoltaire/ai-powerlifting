FORMULA_REFERENCE = """\
HOW THE ANALYSIS PAGE METRICS ARE CALCULATED

- Estimated 1RM: conservative RPE-table estimate for qualifying sets, or 90th percentile of
  qualifying session e1RMs when no comp result is available. Current maxes are therefore
  estimated 1 rep maxes, not true tested maxes.
- Progression rate: Theil-Sen slope of e1RM over effective training weeks, with deload and break
  weeks excluded. Fit quality is normalized MAD; Kendall tau is reported alongside the slope.
- RPE drift: Theil-Sen slope on raw or phase-residual RPE. Uses the same fit-quality reporting.
- Fatigue model: axial and peripheral scale nonlinearly with load, neural uses an intensity gate
  plus sqrt(load), systemic adds a modest absolute-load and intensity term.
- Fatigue index: Window-aware composite score derived from failure_stress, acute_spike_stress, rpe_stress, chronic_load_stress, overload_streak, intensity_density_stress, and monotony_stress.
  Values >= 0.65 indicate Very High risk. >= 0.45 indicate High risk.
- INOL: reps / (100 × sqrt((1 - min(intensity ratio, 0.995))^2 + 0.02^2)) aggregated per lift per week,
  then multiplied by the lift profile stimulus coefficient. Defaults are per-lift, with optional overrides.
- ACWR: daily EWMA acute workload divided by daily EWMA chronic workload, with a weighted composite
  and phase-aware planned-overreach labeling.
- Relative intensity distribution: sets bucketed by load ratio vs estimated 1RM.
- Specificity ratio: SBD sets divided by total sets, plus a broader version that includes same-category work.
- Readiness score: weighted composite of fatigue, RPE drift, subjective wellness, short-term performance trend, and bodyweight deviation.
- DOTS: 500 × total / polynomial(bodyweight) using the sex-specific coefficients.
- Attempt selection: projected comp max × attempt percentages, rounded to the nearest 2.5 kg.
"""
