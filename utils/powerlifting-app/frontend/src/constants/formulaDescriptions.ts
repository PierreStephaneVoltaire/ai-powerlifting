export interface FormulaDescription {
  id: string
  title: string
  summary: string
  formula: string
  variables: { name: string; description: string }[]
  thresholds?: { label: string; value: string; flag?: string }[]
}

export const FORMULA_DESCRIPTIONS: FormulaDescription[] = [
  {
    id: 'estimated_1rm',
    title: 'Estimated 1RM',
    summary: 'Estimated one-rep max from RPE table (reps <= 6) or conservative table (reps <= 5). 90th percentile of executed sets (completed or failed) over 6 weeks. No Epley/Brzycki.',
    formula: `E1RM = weight / pct(reps, rpe)

-- RPE table (reps <= 6, RPE 6-10)
-- Conservative table (reps <= 5, no RPE)
-- Final = P90(all executed estimates, last 42 days)`,
    variables: [
      { name: 'weight', description: 'Load lifted in kg' },
      { name: 'reps', description: 'Repetitions performed' },
      { name: 'rpe', description: 'Rate of Perceived Exertion (6-10)' },
      { name: 'pct', description: 'RPE-based or conservative % of 1RM' },
    ],
  },
  {
    id: 'progression_rate',
    title: 'Progression Rate',
    summary: 'Theil-Sen regression on e1RM per effective training week. Deloads and break weeks excluded; only executed sets contribute to the session e1RM.',
    formula: `slope = theilsen_median(e1RM ~ effective_week)
kendall_tau = KendallTau(effective_week, e1RM)
fit_quality = 1 - MAD(residuals) / MAD(series)`,
    variables: [
      { name: 'e1RM', description: 'Estimated 1RM per session' },
      { name: 'effective_week', description: 'Week index excluding deloads/breaks' },
      { name: 'slope', description: 'kg per week rate of change' },
      { name: 'kendall_tau', description: 'Rank correlation between effective week and e1RM (-1 to 1)' },
      { name: 'fit_quality', description: 'Normalized MAD fit quality (0-1)' },
    ],
  },
  {
    id: 'competition_projection',
    title: 'Competition Projection',
    summary: 'Diminishing-returns projection from current maxes. Uses PRR-calibrated lambda and clamps gain at a time-scaled ceiling that tops out at 20%.',
    formula: `C_max = [E_now + delta_w * lambda_effective * (1 - lambda_effective^n) / (1 - lambda_effective)] * P
lambda_effective = min(lambda_tier * lambda_multiplier, 0.995)
lambda_multiplier = clamp(median(PRR_total over last 3 completed meets), 0.92, 1.05)
ceiling_pct = min(20%, 10% + 0.5% * max(0, weeks_to_comp - 8))
clamped to [E_now, E_now * (1 + ceiling_pct)]

lambda: DOTS < 300 -> 0.96, 300-400 -> 0.90, >= 400 -> 0.85
P (peak): DOTS < 300 -> 1.01, 300-400 -> 1.03, >= 400 -> 1.05
n = weeks_remaining - taper_weeks - planned_deloads`,
    variables: [
      { name: 'E_now', description: 'Current estimated 1RM' },
      { name: 'delta_w', description: 'Progression rate (kg/week)' },
      { name: 'lambda', description: 'Diminishing returns decay factor' },
      { name: 'P', description: 'Peaking factor based on DOTS level' },
      { name: 'n', description: 'Effective training weeks remaining' },
    ],
  },
  {
    id: 'projection_calibration',
    title: 'Projection Calibration (PRR)',
    summary: 'Post-meet calibration of projection decay using Projection-to-Result Ratio (PRR) from recent completed competitions.',
    formula: `PRR_lift = actual_lift / projected_at_t_minus_1w_lift
PRR_total = actual_total / projected_total (only when all 3 lifts are valid)
lambda_multiplier = clamp(median(PRR_total over last 3 completed meets), 0.92, 1.05)
Calibrated if at least 2 completed meets have valid total PRR`,
    variables: [
      { name: 'actual_lift', description: 'Completed meet result for one lift' },
      { name: 'projected_at_t_minus_1w_lift', description: 'Snapshot projection taken 1 week before the meet' },
      { name: 'PRR_total', description: 'Total PRR from the completed meet' },
      { name: 'lambda_multiplier', description: 'Per-athlete projection multiplier derived from recent PRR' },
    ],
    thresholds: [
      { label: 'Calibrated', value: '>= 2 completed meets', flag: 'Projection decay uses athlete-specific PRR history' },
      { label: 'Clamp', value: '0.92 - 1.05', flag: 'Prevents overreacting to outlier meets' },
    ],
  },
  {
    id: 'volume_landmarks',
    title: 'Volume Landmarks',
    summary: 'Per-lift MV / MEV / MAV / MRV estimates from whole-program history, excluding deload and break weeks. Only executed sets are counted toward weekly volume.',
    formula: `weekly_sets_bin = floor(weekly_sets / 2) * 2
MV = first bin with delta_e1rm >= 0
MEV = first bin with delta_e1rm > 0
MAV = bin with max delta_e1rm
MRV = first bin where next_week_fi > 0.60 or delta_e1rm < 0`,
    variables: [
      { name: 'weekly_sets', description: 'Main-lift sets actually executed (completed or failed) inside a training week' },
      { name: 'delta_e1rm', description: 'Week-over-week main-lift e1RM change' },
      { name: 'next_week_fi', description: 'Fatigue index for the following week' },
      { name: 'history_weeks', description: 'Eligible weeks with lift data after excluding deloads and breaks' },
    ],
    thresholds: [
      { label: 'Low confidence', value: '12 - 17 weeks', flag: 'Bare minimum history for a first-pass landmark estimate' },
      { label: 'Medium confidence', value: '18 - 25 weeks', flag: 'More stable landmark estimate' },
      { label: 'High confidence', value: '26+ weeks', flag: 'Best-supported landmark estimate' },
    ],
  },
  {
    id: 'attempt_selection',
    title: 'Attempt Selection',
    summary: 'Competition attempts calculated from projected maxes with user-configurable percentages.',
    formula: `attempt_k = round_to_2.5(C_max * pct_k)
total = sum of all third attempts

round_to_2.5(v) = round(v / 2.5) * 2.5`,
    variables: [
      { name: 'C_max', description: 'Competition projected max' },
      { name: 'pct_k', description: 'Attempt percentage (opener/second/third)' },
      { name: 'total', description: 'Sum of third attempts' },
    ],
    thresholds: [
      { label: 'Opener', value: '90% (default)', flag: 'Should feel easy under worst conditions' },
      { label: 'Second', value: '95.5% (default)', flag: 'A confident single, builds momentum' },
      { label: 'Third', value: '100% (default)', flag: 'Your projected max' },
    ],
  },
  {
    id: 'fatigue_model',
    title: 'Fatigue Model',
    summary: '4 dimensions (axial, neural, peripheral, systemic) per exercise. Nonlinear load scaling with an intensity-gated neural term.',
    formula: `F_axial = profile.axial * weight^1.30 * reps
F_peripheral = profile.peripheral * weight^1.15 * reps
F_systemic = profile.systemic * weight * reps * (1 + 0.30 * I)
F_neural = profile.neural * reps * phi(I) * sqrt(weight / 100)
phi(I) = ((max(0, I - 0.60) / 0.40)^3)
I = weight / E_now (intensity ratio)`,
    variables: [
      { name: 'profile.d', description: 'Exercise fatigue coefficient per dimension (0-1)' },
      { name: 'weight', description: 'Load in kg' },
      { name: 'reps', description: 'Repetitions in the set' },
      { name: 'I', description: 'Intensity ratio (weight / estimated max)' },
      { name: 'phi(I)', description: 'Cubic neural scaling function, zero below 60% intensity' },
    ],
  },
  {
    id: 'fatigue_index',
    title: 'Fatigue Index',
    summary: 'Current fatigue state from failures, acute spikes, RPE, intensity density, monotony, and decaying fatigue reservoirs. Recent work matters more, and localized dimension overload is not diluted away by quiet lifts.',
    formula: `R_d,t = R_d,t-1 * exp(-ln(2) / half_life_d) + Load_d,t
S_d,t = clamp((R_d,t / baseline_d - 1.0) / 0.75, 0, 1)
ReservoirStress = 0.60 * max(S_d) + 0.40 * weighted_mean(S_d)

FI = 0.10*fail + 0.12*spike + 0.15*rpe + 0.34*reservoir
   + 0.10*streak + 0.10*density + 0.09*monotony`,
    variables: [
      { name: 'R_d,t', description: 'Decaying fatigue reservoir for each fatigue dimension' },
      { name: 'half_life_d', description: 'Dimension-specific fatigue half-life in days' },
      { name: 'ReservoirStress', description: 'Max-sensitive chronic fatigue pressure' },
      { name: 'failure_stress', description: 'Failed compound ratio clamped to 15%' },
      { name: 'acute_spike_stress', description: 'Normalized recent volume spike' },
      { name: 'rpe_stress', description: 'RMS of phase-relative RPE excess and 9+ frequency' },
      { name: 'chronic_load_stress', description: 'Compatibility key for reservoir-based chronic pressure' },
      { name: 'overload_streak', description: 'Consecutive weeks of high chronic load or intensity' },
      { name: 'intensity_density_stress', description: 'Ratio of heavy (85%+) and very heavy (90%+) sets' },
      { name: 'monotony_stress', description: 'Foster monotony and 4-week strain ratio' },
    ],
    thresholds: [
      { label: 'Low', value: '< 0.25', flag: 'Normal' },
      { label: 'Moderate', value: '0.25 - 0.44', flag: 'Caution' },
      { label: 'High', value: '0.45 - 0.64', flag: 'Overreaching risk' },
      { label: 'Very High', value: '>= 0.65', flag: 'High accumulated fatigue' },
    ],
  },
  {
    id: 'inol',
    title: 'INOL',
    summary: 'Selected-window stimulus-adjusted INOL with phase-adjusted target ranges, ramp-up grace, uncertainty bands, and volume/intensity trend pressure.',
    formula: `raw_set_INOL = reps / (100 * sqrt((1 - min(I, 0.995))^2 + 0.02^2))
raw_weekly_INOL = sum(raw_set_INOL * sets)
adjusted_weekly_INOL = raw_weekly_INOL * lift_stimulus_coefficient
TargetRange_l,w = BaseRange_l * PhaseMultiplier_w
DisplayRange = TargetRange widened for small selected windows
TrendPressure = 0.60*volume_spike + 0.40*RI_spike
I = weight / E_now (per set)`,
    variables: [
      { name: 'reps', description: 'Repetitions in the set' },
      { name: 'I', description: 'Intensity ratio (weight / estimated max)' },
      { name: 'lift_stimulus_coefficient', description: 'Lift-profile multiplier from 1 to 2; baseline is 1.0' },
    ],
    thresholds: [
      { label: 'Squat', value: '1.6 - 3.5', flag: 'Default productive range; profile overrides may change this' },
      { label: 'Bench', value: '2.0 - 5.0', flag: 'Default productive range; profile overrides may change this' },
      { label: 'Deadlift', value: '1.0 - 2.5', flag: 'Default productive range; profile overrides may change this' },
    ],
  },
  {
    id: 'acwr',
    title: 'ACWR (Acute:Chronic Workload Ratio)',
    summary: 'Per-dimension workload ratio with weighted composite. Uses daily EWMA loads and labels that describe workload pattern, not injury prediction.',
    formula: `EWMA_acute_d,t = 0.25 * load_d,t + 0.75 * EWMA_acute_d,t-1
EWMA_chronic_d,t = (2/29) * load_d,t + (27/29) * EWMA_chronic_d,t-1
ACWR_d = EWMA_acute_d,t / EWMA_chronic_d,t
Composite = 0.30*axial + 0.30*neural + 0.25*peripheral + 0.15*systemic`,
    variables: [
      { name: 'load_d,t', description: 'Daily load in dimension d on day t' },
      { name: 'EWMA_acute', description: '7-day acute EWMA seeded from the first 7 days' },
      { name: 'EWMA_chronic', description: '28-day chronic EWMA seeded from the first 7 days' },
    ],
    thresholds: [
      { label: 'Detraining trend', value: '< 0.80', flag: 'Load is trending down' },
      { label: 'Steady load', value: '0.80 - 1.30', flag: 'Stable workload pattern' },
      { label: 'Rapid increase', value: '1.30 - 1.50', flag: 'Recent workload is rising quickly' },
      { label: 'Load spike', value: '> 1.50', flag: 'Large short-term workload jump' },
    ],
  },
  {
    id: 'banister_ffm',
    title: 'Banister Fitness-Fatigue Model',
    summary: 'Daily normalized dimension load drives CTL, ATL, and TSB. Future peaking projections use the same normalized load units as historical data.',
    formula: `load_t = 100 * (0.30*F_axial/B_axial + 0.30*F_neural/B_neural + 0.25*F_peripheral/B_peripheral + 0.15*F_systemic/B_systemic)
CTL_t = (2/43) * load_t + (1 - 2/43) * CTL_t-1
ATL_t = (2/8) * load_t + (1 - 2/8) * ATL_t-1
TSB_t = CTL_t - ATL_t
CTL_0 = ATL_0 = mean(load first 14 days)`,
    variables: [
      { name: 'load_t', description: 'Composite daily fatigue load' },
      { name: 'CTL', description: 'Chronic training load / fitness' },
      { name: 'ATL', description: 'Acute training load / fatigue' },
      { name: 'TSB', description: 'Training stress balance, or form' },
    ],
    thresholds: [
      { label: 'Deep overload', value: '< -30', flag: 'Very high accumulated fatigue' },
      { label: 'Productive overreach', value: '-30 to -10', flag: 'Heavy but useful overload' },
      { label: 'Building', value: '-10 to +5', flag: 'Fitness is building' },
      { label: 'Peaking window', value: '+5 to +15', flag: 'Best readiness for platform work' },
      { label: 'Detraining risk', value: '> +15', flag: 'Too little stimulus / too much freshness' },
    ],
  },
  {
    id: 'monotony_strain',
    title: 'Foster Monotony & Strain',
    summary: 'Weekly load consistency and accumulated strain. Catches repeated moderate loading that ACWR can miss.',
    formula: `Monotony = mean(daily_load) / max(SD(daily_load), 0.10*mean(daily_load), load_floor)
Monotony_display = min(Monotony, 7.0)
Strain = weekly_load * Monotony_display
StrainIndex = Strain / rolling_4wk_median(Strain)`,
    variables: [
      { name: 'daily_load_week', description: 'Composite daily loads inside one training week' },
      { name: 'weekly_load', description: 'Sum of daily loads for the week' },
      { name: 'Monotony_week', description: 'Load consistency ratio for the week' },
      { name: 'Strain_week', description: 'Weekly load multiplied by monotony' },
    ],
    thresholds: [
      { label: 'High monotony', value: '> 2.0', flag: 'Repeated similar loading across the week' },
      { label: 'Strain spike', value: '> rolling 4-week median x 1.5', flag: 'Weekly strain jumped sharply' },
    ],
  },
  {
    id: 'decoupling',
    title: 'Strength-Fatigue Decoupling',
    summary: 'Trailing 3-week divergence between SBD e1RM trend and fatigue-index trend.',
    formula: `Decoupling = slope(e1RM_total, 3wk) - slope(FI, 3wk)
e1RM slope is normalized to %/wk
FI slope is normalized to percentage points / wk`,
    variables: [
      { name: 'e1RM_total', description: 'Weekly sum of best squat, bench, and deadlift e1RM estimates' },
      { name: 'FI', description: 'Fatigue index score for the week-end window' },
      { name: 'slope', description: 'Three-point linear slope over trailing weeks' },
    ],
    thresholds: [
      { label: 'Fatigue dominant', value: '< 0', flag: 'Strength is not outpacing fatigue' },
      { label: 'Sustained negative', value: '< 0 for 3 consecutive windows', flag: 'decoupling_fatigue_dominant' },
    ],
  },
  {
    id: 'taper_quality',
    title: 'Taper Quality Score',
    summary: 'Weighted score for how well the final taper preserves intensity while reducing volume and fatigue.',
    formula: `TQS = 0.30 * V_reduction + 0.25 * I_maintained + 0.25 * F_trend + 0.20 * T_SB
V_reduction = clamp((pre_taper_peak_volume - taper_weekly_volume) / (pre_taper_peak_volume * 0.5), 0, 1)
I_maintained = 1 if taper top-set intensity >= 0.95 * pre-taper else linear falloff
F_trend = 1 if fatigue is trending down, 0 if flat, negative if rising
T_SB = clamp((TSB_today + 5) / 20, 0, 1)`,
    variables: [
      { name: 'pre_taper_peak_volume', description: 'Max weekly composite volume in the 4 weeks before taper start' },
      { name: 'taper_weekly_volume', description: 'Average weekly composite volume during the taper window' },
      { name: 'top_set_intensity', description: 'Highest relative intensity hit during taper vs. pre-taper' },
      { name: 'TSB_today', description: 'Current Banister form score' },
    ],
    thresholds: [
      { label: 'Poor', value: '< 40', flag: 'Taper is not producing a good peaking signal' },
      { label: 'Acceptable', value: '40 - 59', flag: 'Serviceable but not ideal' },
      { label: 'Good', value: '60 - 79', flag: 'Strong taper pattern' },
      { label: 'Excellent', value: '>= 80', flag: 'Very strong taper pattern' },
    ],
  },
  {
    id: 'ri_distribution',
    title: 'Relative Intensity Distribution',
    summary: 'Buckets working sets by ratio of weight to current estimated max.',
    formula: `RI = weight / E_now
Heavy: RI > 0.85
Moderate: 0.70 <= RI <= 0.85
Light: RI < 0.70`,
    variables: [
      { name: 'weight', description: 'Load in kg' },
      { name: 'E_now', description: 'Current estimated 1RM for that lift' },
      { name: 'RI', description: 'Relative intensity ratio' },
    ],
  },
  {
    id: 'specificity_ratio',
    title: 'Specificity Ratio',
    summary: 'Measures direct and broad powerlifting specificity against the selected target competition timeline. Only executed sets are counted toward the ratio.',
    formula: `SR_narrow = SBD sets / total sets
SR_broad = (SBD + secondary category) / total sets
Expected band selected by weeks_to_comp:
  16+ weeks  -> narrow 0.30-0.50, broad 0.60-0.75
  12-16 weeks -> narrow 0.40-0.55, broad 0.65-0.80
  8-12 weeks  -> narrow 0.50-0.65, broad 0.75-0.85
  4-8 weeks   -> narrow 0.60-0.75, broad 0.80-0.90
  0-4 weeks   -> narrow 0.70-0.85, broad 0.85-0.95`,
    variables: [
      { name: 'SBD sets', description: 'Executed sets of squat, bench, or deadlift' },
      { name: 'secondary', description: 'Same-category exercises actually performed (e.g. close-grip bench)' },
      { name: 'total sets', description: 'All working sets actually executed across all exercises' },
      { name: 'weeks_to_comp', description: 'Weeks remaining until the next competition, if one exists' },
    ],
  },
  {
    id: 'readiness_score',
    title: 'Readiness Score',
    summary: 'Composite score predicting training readiness. Missing data re-weights available components without penalizing. Performance trend component only uses executed sets.',
    formula: `TrainingReadiness = 100 * (1 - weighted_penalty(fatigue, rpe_drift, performance_trend))
ExternalReadiness = 100 * (1 - weighted_penalty(wellness, bodyweight))
OverallReadiness = 0.70*TrainingReadiness + 0.30*ExternalReadiness`,
    variables: [
      { name: 'F_norm', description: 'Normalized fatigue index (0-1)' },
      { name: 'D_rpe', description: 'RPE drift from phase target' },
      { name: 'W_subj', description: 'Subjective wellness (1 - mean wellness / 5)' },
      { name: 'P_trend', description: 'Negative short-term e1RM trend penalty' },
      { name: 'S_bw', description: 'Cut-aware bodyweight deviation or stability penalty' },
      { name: 'readiness_confidence', description: 'Ratio of available weights to total possible weights' },
    ],
    thresholds: [
      { label: 'Green', value: '> 75', flag: 'Ready to train' },
      { label: 'Yellow', value: '50 - 75', flag: 'Proceed with caution' },
      { label: 'Red', value: '< 50', flag: 'Recovery priority' },
    ],
  },
  {
    id: 'dots_score',
    title: 'DOTS Score',
    summary: 'Strength-to-bodyweight coefficient using polynomial formula with sex-specific coefficients. Best e1RM per session only considers executed sets.',
    formula: `DOTS = 500 * total / (a + b*bw + c*bw^2 + d*bw^3 + e*bw^4)`,
    variables: [
      { name: 'total', description: 'Squat + Bench + Deadlift total (kg) from best executed sets' },
      { name: 'bw', description: 'Bodyweight in kg' },
      { name: 'a-e', description: 'Sex-specific polynomial coefficients' },
    ],
  },
  {
    id: 'ipf_gl_score',
    title: 'IPF GL Score',
    summary: 'IPF relative scoring coefficient for classic powerlifting totals or classic bench-only results. Best results only consider executed sets.',
    formula: `GL = result * 100 / (A - B * e^(-C * bw))`,
    variables: [
      { name: 'result', description: 'SBD total for classic powerlifting, or bench result for bench-only scoring, from best executed sets' },
      { name: 'bw', description: 'Bodyweight in kg' },
      { name: 'A-C', description: 'Sex- and discipline-specific coefficients' },
    ],
  },
  {
    id: 'rpe_drift',
    title: 'RPE Drift',
    summary: 'Residual regression comparing actual RPE to phase target midpoint. Only executed sets contribute to avg_rpe.',
    formula: `residual = avg_rpe - phase_target_midpoint
slope = Theil-Sen(residual ~ week)
kendall_tau = KendallTau(week, residual)
fit_quality = 1 - MAD(residuals) / MAD(series)
slope >= 0.1 -> fatigue
slope <= -0.1 -> adaptation`,
    variables: [
      { name: 'avg_rpe', description: 'Average session RPE from executed sets' },
      { name: 'phase_target_midpoint', description: '(target_rpe_min + target_rpe_max) / 2' },
      { name: 'slope', description: 'Theil-Sen regression slope over time' },
      { name: 'kendall_tau', description: 'Rank correlation between week and RPE residuals' },
      { name: 'fit_quality', description: 'Normalized MAD fit quality (0-1)' },
    ],
    thresholds: [
      { label: 'Fatigue', value: 'slope >= 0.1', flag: 'RPE rising at same loads' },
      { label: 'Adaptation', value: 'slope <= -0.1', flag: 'Getting stronger at same loads' },
      { label: 'Stable', value: '|slope| < 0.1', flag: 'No significant trend' },
    ],
  },
  {
    id: 'compliance',
    title: 'Compliance',
    summary: 'Ratio of work completed vs planned. Includes session attendance, sets performed, and total volume load. All weeks counted — deloads and programmed breaks are NOT excluded.',
    formula: `session_compliance = (completed_sessions / planned_sessions) * 100
set_compliance = (executed_sets / planned_sets) * 100
volume_compliance = (executed_volume / planned_volume) * 100

All metrics are aggregated across the selected analysis window.`,
    variables: [
      { name: 'completed_sessions', description: 'Sessions with status logged or completed' },
      { name: 'planned_sessions', description: 'Total sessions in the window' },
      { name: 'executed_sets', description: 'Total sets with status completed or failed' },
      { name: 'planned_sets', description: 'Total sets originally programmed' },
      { name: 'executed_volume', description: 'Sum of sets * reps * kg for executed work' },
      { name: 'planned_volume', description: 'Sum of sets * reps * kg for planned work' },
    ],
  },
]
