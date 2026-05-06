import api from './client'

export interface InsufficientDataResponse {
  status: 'insufficient_data'
  reason: string
}

export interface BanisterSeriesPoint {
  date: string
  ctl: number
  atl: number
  tsb: number
}

export interface BanisterAnalysis {
  ctl_today: number
  atl_today: number
  tsb_today: number
  tsb_label: string
  series: BanisterSeriesPoint[]
  load_baselines?: Record<string, number>
  model?: string
}

export interface MonotonyStrainRow {
  week_start: string
  monotony: number
  monotony_raw?: number
  strain: number
  strain_index?: number | null
  nonzero_training_days?: number
  flags: string[]
}

export interface DecouplingPoint {
  week_start: string
  decoupling: number
  e1rm_slope_pct_per_week: number
  fi_slope_pct_points_per_week: number
}

export interface DecouplingAnalysis {
  current: DecouplingPoint | null
  series: DecouplingPoint[]
  flags: string[]
}

export interface TaperQualityAnalysis {
  score: number
  label: 'poor' | 'acceptable' | 'good' | 'excellent'
  weeks_to_comp: number
  components: {
    volume_reduction: number
    intensity_maintained: number
    fatigue_trend: number
    tsb: number
  }
}

export interface ProjectionCalibration {
  calibrated: boolean
  meets: number
  median_prr: number | null
  lambda_multiplier: number | null
}

export interface VolumeLandmark {
  mv: number | null
  mev: number | null
  mav: number | null
  mrv: number | null
  confidence: 'low' | 'medium' | 'high'
}

export interface AnalyticsAlert {
  severity: 'info' | 'caution' | 'warning'
  source: 'acwr' | 'fatigue' | 'readiness' | 'projection' | 'specificity' | 'banister' | 'decoupling' | 'monotony'
  message: string
  raw_detail: string
}

export interface PeakingTimelineSeriesPoint {
  date: string
  actual_tsb: number | null
  projected_tsb: number | null
}

export interface PeakingTimelineSpecificityPoint {
  date: string
  narrow: number
  broad: number
  weeks_to_comp: number
  expected_band?: {
    weeks_to_comp: number | null
    narrow: { min: number; max: number }
    broad: { min: number; max: number }
  } | null
}

export interface PeakingTimelineBandSegment {
  label: string
  start_date: string
  end_date: string
  narrow: { min: number; max: number }
  broad: { min: number; max: number }
}

export interface PeakingTimeline {
  status: 'on_track' | 'misaligned' | 'significant_deviation' | 'insufficient_data'
  status_color: 'green' | 'yellow' | 'red' | 'gray'
  status_label: string
  status_message: string
  reason?: string
  comp_date: string | null
  current_date: string
  current_tsb: number | null
  peak_date: string | null
  peak_delta_days: number | null
  peak_type?: 'inside_window' | 'not_reached'
  closest_peak_date?: string | null
  closest_projected_tsb?: number | null
  future_unresolved_sets?: number
  peak_window: { min: number; max: number }
  series: PeakingTimelineSeriesPoint[]
  specificity_points: PeakingTimelineSpecificityPoint[]
  specificity_bands: PeakingTimelineBandSegment[]
}

export interface WeeklyAnalysis {
  week: number
  selected_week_start?: number | null
  selected_week_end?: number | null
  selected_week_count?: number | null
  window_start?: string | null
  window_end?: string | null
  block: string
  lifts: Record<string, {
    progression_rate_kg_per_week?: number | null
    fit_quality?: number | null
    kendall_tau?: number | null
    r2?: number | null
    r_squared?: number | null
    volume_change_pct?: number
    intensity_change_pct?: number
    failed_sets?: number
    rpe_trend?: string
  }>
  fatigue_index: number | null
  fatigue_components: {
    failed_compound_ratio?: number
    composite_spike?: number
    failure_stress?: number
    acute_spike_stress?: number
    rpe_stress?: number
    chronic_load_stress?: number
    overload_streak?: number
    intensity_density_stress?: number
    monotony_stress?: number
    fatigue_model?: string
    current_state_fi?: number
    window_weighted_fi?: number
    latest_week_fi?: number
    window_mean_fi?: number
    window_peak_fi?: number
    reservoir_stress?: number
    reservoir_dimension_stress?: Record<string, number>
    reservoir_max_dimension_stress?: number
    reservoir_weighted_stress?: number
    fatigue_window_weeks?: number
    fatigue_context_weeks_used?: number
    fatigue_context_days_used?: number
    fatigue_context_confidence?: string
  } | null
  compliance: {
    phase: string
    planned: number
    completed: number
    pct: number
  } | null
  current_maxes: {
    squat?: number
    bench?: number
    deadlift?: number
    method?: string
  } | null
  estimated_dots: number | null
  estimated_dots_reason?: string | null
  projections: Array<{
    total: number
    confidence: number
    weeks_to_comp?: number
    method?: string
    comp_name?: string
  }>
  projection_reason: string | null
  projection_calibration?: ProjectionCalibration
  flags: string[]
  sessions_analyzed: number
  exercise_stats: Record<string, {
    total_sets: number
    total_volume: number
    max_kg: number
  }> | null
  deload_info?: {
    deload_weeks: number[]
    break_weeks: number[]
    effective_training_weeks: number
  }
  banister?: BanisterAnalysis | InsufficientDataResponse
  monotony_strain?: {
    weekly: MonotonyStrainRow[]
  }
  inol?: {
    per_lift_per_week: Record<string, Record<string, number>>
    /** Average INOL per lift across the analysis window. */
    avg_inol: Record<string, number>
    raw_per_lift_per_week?: Record<string, Record<string, number>>
    /** Average unadjusted INOL before lift-specific stimulus coefficients. */
    raw_avg_inol?: Record<string, number>
    stimulus_coefficients?: Record<string, number>
    thresholds?: Record<string, { low: number; high: number }>
    phase_adjusted_thresholds?: Record<string, {
      low: number
      high: number
      display_low: number
      display_high: number
      phase_multiplier: number
    }>
    trend_pressure?: Record<string, {
      value: number
      volume_ratio: number
      ri_ratio: number
    }>
    ramp_up_grace?: Record<string, boolean>
    flags: string[]
  } | null
  acwr?: {
    composite: number | null
    composite_zone: string
    composite_label?: string | null
    dimensions: Record<string, { value: number | null; zone: string; label?: string }>
  } | { status: 'insufficient_data'; reason: string } | null
  ri_distribution?: {
    overall: Record<string, { count: number; pct: number }>
    per_lift: Record<string, Record<string, { count: number; pct: number }>>
  }
  decoupling?: DecouplingAnalysis | InsufficientDataResponse
  specificity_ratio?: {
    narrow: number
    broad: number
    total_sets: number
    sbd_sets: number
    secondary_sets?: number
    expected_band?: {
      weeks_to_comp: number | null
      narrow: { min: number; max: number }
      broad: { min: number; max: number }
    } | null
    narrow_status?: 'below_expected' | 'within_expected' | 'above_expected' | 'unknown'
    broad_status?: 'below_expected' | 'within_expected' | 'above_expected' | 'unknown'
    flags?: string[]
  }
  specificity_target_competition?: {
    name?: string
    date?: string
    selection_reason?: string
    [key: string]: unknown
  } | null
  volume_landmarks?: Record<'squat' | 'bench' | 'deadlift', VolumeLandmark | InsufficientDataResponse>
  readiness_score?: {
    score: number
    training_score?: number
    external_score?: number
    zone: string
    components: {
      fatigue_norm?: number
      rpe_drift?: number
      wellness?: number
      performance_trend?: number
      bw_deviation?: number
    }
    readiness_confidence?: number
    training_readiness_confidence?: number
    external_readiness_confidence?: number
  }
  fatigue_dimensions?: {
    weekly: Record<string, { axial: number; neural: number; peripheral: number; systemic: number }>
    acwr: Record<string, any>
    spike: Record<string, any>
  }
  taper_quality?: TaperQualityAnalysis | InsufficientDataResponse | null
  attempt_selection?: Record<string, {
    opener: number
    second: number
    third: number
  }> & { total?: number; attempt_pct_used?: { opener: number; second: number; third: number } }
  alerts: AnalyticsAlert[]
  peaking_timeline?: PeakingTimeline
}

export type AnalysisWindowKey =
  | 'current'
  | 'previous_1'
  | 'previous_2'
  | 'previous_4'
  | 'previous_8'
  | 'block'

export interface AnalysisWindow {
  key: AnalysisWindowKey
  label: string
  start: string
  end: string
  weekStart: number
  weekEnd: number
  weeks: number
  currentWeek: number
}

export interface WeeklyAnalysisBundle {
  schemaVersion: number
  asOfDate: string
  generatedAt: string
  cached: boolean
  windows: Record<AnalysisWindowKey, AnalysisWindow>
  results: Record<AnalysisWindowKey, WeeklyAnalysis>
}

export interface CorrelationFinding {
  exercise: string
  lift: 'squat' | 'bench' | 'deadlift'
  correlation_direction: 'positive' | 'negative' | 'unclear'
  strength: 'strong' | 'moderate' | 'weak'
  reasoning: string
  caveat: string
}

export interface CorrelationReport {
  findings: CorrelationFinding[]
  summary: string
  generated_at: string
  window_start: string
  weeks: number
  cached: boolean
  insufficient_data?: boolean
  insufficient_data_reason?: string
}

function normalizeCorrelationReport(data: unknown): CorrelationReport {
  const report = (data && typeof data === 'object') ? data as Partial<CorrelationReport> : {}
  return {
    findings: Array.isArray(report.findings) ? report.findings : [],
    summary: typeof report.summary === 'string' ? report.summary : '',
    generated_at: typeof report.generated_at === 'string' ? report.generated_at : '',
    window_start: typeof report.window_start === 'string' ? report.window_start : '',
    weeks: typeof report.weeks === 'number' ? report.weeks : 0,
    cached: Boolean(report.cached),
    insufficient_data: Boolean(report.insufficient_data),
    insufficient_data_reason: typeof report.insufficient_data_reason === 'string' ? report.insufficient_data_reason : '',
  }
}

export interface ProgramEvaluationSmallChange {
  change: string
  why: string
  risk: string
  priority: 'low' | 'moderate' | 'high'
}

export interface ProgramEvaluationExternalFactor {
  factor: string
  impact: 'low' | 'moderate' | 'high'
  reason: string
  separate_from_program: boolean
}

export interface ProgramEvaluationCompAlignment {
  competition: string
  role: 'primary' | 'practice'
  weeks_to_comp?: number | null
  alignment: 'good' | 'mixed' | 'poor'
  reason: string
}

export interface ProgramEvaluationGoalStatus {
  goal: string
  priority: 'primary' | 'secondary' | 'optional'
  status: 'achieved' | 'on_track' | 'at_risk' | 'off_track' | 'unclear'
  reason: string
}

export interface ProgramEvaluationCompetitionStrategy {
  competition: string
  priority: 'prioritize' | 'supporting' | 'practice' | 'deprioritize' | 'drop'
  approach: 'all_out' | 'qualify_only' | 'minimum_total' | 'podium_push' | 'train_through' | 'conservative_pr' | 'drop'
  reason: string
  alternative_strategies?: Array<{
    approach: 'all_out' | 'qualify_only' | 'minimum_total' | 'podium_push' | 'train_through' | 'conservative_pr' | 'drop'
    target_total_kg?: number | null
    target_weight_class_kg?: number | null
    reason: string
  }>
}

export interface ProgramEvaluationWeightClassOption {
  weight_class_kg: number
  suitability: 'best' | 'viable' | 'risky'
  reason: string
}

export interface ProgramEvaluationWeightClassStrategy {
  recommendation: string
  recommended_weight_class_kg: number | null
  viable_options: ProgramEvaluationWeightClassOption[]
}

export interface ProgramEvaluationReport {
  stance: 'continue' | 'monitor' | 'adjust' | 'critical'
  summary: string
  what_is_working: string[]
  what_is_not_working: string[]
  competition_alignment: ProgramEvaluationCompAlignment[]
  goal_status: ProgramEvaluationGoalStatus[]
  competition_strategy: ProgramEvaluationCompetitionStrategy[]
  weight_class_strategy: ProgramEvaluationWeightClassStrategy
  small_changes: ProgramEvaluationSmallChange[]
  external_factors: ProgramEvaluationExternalFactor[]
  monitoring_focus: string[]
  conclusion: string
  insufficient_data?: boolean
  insufficient_data_reason?: string
  generated_at: string
  window_start: string
  weeks: number
  cached: boolean
}

function normalizeProgramEvaluation(data: unknown): ProgramEvaluationReport {
  const report = (data && typeof data === 'object') ? data as Partial<ProgramEvaluationReport> : {}
  const weightClassStrategy = (report.weight_class_strategy && typeof report.weight_class_strategy === 'object')
    ? report.weight_class_strategy
    : undefined

  return {
    stance: report.stance ?? 'monitor',
    summary: typeof report.summary === 'string' ? report.summary : '',
    what_is_working: Array.isArray(report.what_is_working) ? report.what_is_working : [],
    what_is_not_working: Array.isArray(report.what_is_not_working) ? report.what_is_not_working : [],
    competition_alignment: Array.isArray(report.competition_alignment) ? report.competition_alignment : [],
    goal_status: Array.isArray(report.goal_status) ? report.goal_status : [],
    competition_strategy: Array.isArray(report.competition_strategy) ? report.competition_strategy : [],
    weight_class_strategy: {
      recommendation: typeof weightClassStrategy?.recommendation === 'string' ? weightClassStrategy.recommendation : '',
      recommended_weight_class_kg:
        typeof weightClassStrategy?.recommended_weight_class_kg === 'number'
          ? weightClassStrategy.recommended_weight_class_kg
          : null,
      viable_options: Array.isArray(weightClassStrategy?.viable_options) ? weightClassStrategy.viable_options : [],
    },
    small_changes: Array.isArray(report.small_changes) ? report.small_changes : [],
    external_factors: Array.isArray(report.external_factors) ? report.external_factors : [],
    monitoring_focus: Array.isArray(report.monitoring_focus) ? report.monitoring_focus : [],
    conclusion: typeof report.conclusion === 'string' ? report.conclusion : '',
    insufficient_data: Boolean(report.insufficient_data),
    insufficient_data_reason: typeof report.insufficient_data_reason === 'string' ? report.insufficient_data_reason : '',
    generated_at: typeof report.generated_at === 'string' ? report.generated_at : '',
    window_start: typeof report.window_start === 'string' ? report.window_start : '',
    weeks: typeof report.weeks === 'number' ? report.weeks : 0,
    cached: Boolean(report.cached),
  }
}

export async function fetchWeeklyAnalysis(
  weeks = 1,
  block = 'current',
  windowStart?: string,
  windowEnd?: string,
  weekStart?: number,
  weekEnd?: number,
  refDate?: string,
): Promise<WeeklyAnalysis> {
  const params = new URLSearchParams({
    weeks: String(weeks),
    block,
  })
  if (windowStart) params.set('windowStart', windowStart)
  if (windowEnd) params.set('windowEnd', windowEnd)
  if (weekStart) params.set('weekStart', String(weekStart))
  if (weekEnd) params.set('weekEnd', String(weekEnd))
  if (refDate) params.set('refDate', refDate)
  const res = await api.get(`/analytics/analysis/weekly?${params.toString()}`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}

export async function fetchWeeklyAnalysisBundle(asOfDate?: string): Promise<WeeklyAnalysisBundle> {
  const params = new URLSearchParams()
  if (asOfDate) params.set('asOfDate', asOfDate)
  const qs = params.toString()
  const res = await api.get(`/analytics/analysis/weekly-bundle${qs ? `?${qs}` : ''}`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}

export async function fetchCorrelationReport(
  weeks: number,
  block = 'current',
  refresh = false,
): Promise<CorrelationReport> {
  const res = await api.get(
    `/analytics/correlation?weeks=${weeks}&block=${encodeURIComponent(block)}&refresh=${refresh}`,
  )
  const body = res.data
  if (body.error) throw new Error(body.error)
  return normalizeCorrelationReport(body.data)
}

export async function fetchProgramEvaluation(refresh = false): Promise<ProgramEvaluationReport> {
  const apiBase = import.meta.env.VITE_API_BASE_URL || '/api'
  const res = await fetch(`${apiBase}/analytics/program-evaluation?refresh=${refresh}`, {
    headers: { 'Content-Type': 'application/json' },
  })
  const body = await res.json()
  if (body.error) throw new Error(body.error)
  return normalizeProgramEvaluation(body.data)
}
