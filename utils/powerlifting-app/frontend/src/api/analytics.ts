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
  selected_session_context?: Array<{
    date?: string
    week_number?: number
    status?: string
    completed?: boolean
    session_notes?: string
    planned_exercises?: Array<Record<string, unknown>>
  }>
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
    missed?: number
    pct: number
    planned_sets?: number
    completed_sets?: number
    set_pct?: number
    planned_reps?: number
    completed_reps?: number
    rep_pct?: number
    planned_volume?: number
    completed_volume?: number
    vol_pct?: number
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

export interface DataQualityFlag {
  code: string
  label: string
  severity: 'info' | 'warning' | 'critical'
}

export interface BlockCompetitionLink {
  name: string
  date: string
  status: string
  mapping: 'in_range' | 'within_30_days_after'
  distanceDays: number
}

export interface ProgramBlockIndexEntry {
  blockKey: string
  block: string
  label: string
  isCurrent: boolean
  startDate: string
  endDate: string
  weekStart: number
  weekEnd: number
  weekCount: number
  completedSessions: number
  plannedSessions: number
  totalSessions: number
  phases: Array<{
    name: string
    intent?: string
    start_week: number
    end_week: number
  }>
  sourceFingerprint: string
  linkedCompetition: BlockCompetitionLink | null
  trainingOnly: boolean
  comparisonEligible: boolean
  dataQualityFlags: DataQualityFlag[]
  cacheStatus?: {
    cached: boolean
    generatedAt?: string
  }
  programEvaluationCacheStatus?: {
    cached: boolean
    generatedAt?: string
  }
}

export interface BlockStrengthSummary {
  squat: number | null
  bench: number | null
  deadlift: number | null
  total: number | null
}

export interface BlockStartMaxEntry {
  squat_kg: number | null
  bench_kg: number | null
  deadlift_kg: number | null
  total_kg: number | null
  source: 'manual'
  updated_at: string
}

export interface BlockCompetitionOutcome {
  competitionName: string
  competitionDate: string
  bodyweightKg: number | null
  results: {
    squat_kg: number
    bench_kg: number
    deadlift_kg: number
    total_kg: number
  } | null
  dots: number | null
  ipfGl: number | null
  ipfGlMode: 'classic_powerlifting' | null
  projectedAtTMinus1w: {
    squat_kg: number
    bench_kg: number
    deadlift_kg: number
    total_kg: number
  } | null
  projectionAccuracy: Record<string, {
    actualKg: number
    projectedKg: number
    deltaKg: number
    deltaPct: number | null
  }> | null
  prr: unknown | null
  postMeetReportCaptured: boolean
}

export interface BlockHistoricalSummary {
  startStrength: BlockStrengthSummary
  endStrength: BlockStrengthSummary
  strengthDelta: BlockStrengthSummary
  startMaxesSource: 'manual' | 'session_estimated'
  manualStartMaxes: BlockStartMaxEntry | null
  competitionOutcome: BlockCompetitionOutcome | null
  analyticsSummary: {
    sessionsAnalyzed: number
    compliancePct: number | null
    fatigueIndex: number | null
    acwrComposite: number | null
    avgInol: Record<string, number>
    totalVolumeKg: number
    muscleMap: Record<string, unknown>
  }
  missingData: DataQualityFlag[]
}

export interface BlockAnalysisBundle {
  schemaVersion: number
  generatedAt: string
  cached: boolean
  sourceFingerprint: string
  block: ProgramBlockIndexEntry
  weekly: WeeklyAnalysis
  historical: BlockHistoricalSummary
}

export interface BlockComparisonRow {
  blockKey: string
  label: string
  startDate: string
  endDate: string
  trainingOnly: boolean
  competitionName: string | null
  competitionDate: string | null
  actualTotalKg: number | null
  actualDots: number | null
  actualIpfGl: number | null
  estimatedDots: number | null
  startTotalKg: number | null
  endTotalKg: number | null
  e1rmDeltaKg: number | null
  compliancePct: number | null
  fatigueIndex: number | null
  acwrComposite: number | null
  totalVolumeKg: number
  avgInol: Record<string, number>
  projectionTotalDeltaKg: number | null
  dataQualityFlags: DataQualityFlag[]
  competitions?: Array<{
    name: string
    date: string
    status: string
    federation?: string
    weightClassKg?: number | null
    bodyweightKg?: number | null
    targetTotalKg?: number | null
    resultTotalKg?: number | null
    projectedTotalKg?: number | null
  }>
  goals?: Array<{
    id: string
    title: string
    goalType: string
    priority: string
    targetTotalKg?: number | null
    targetDots?: number | null
    targetIpfGl?: number | null
    targetDate?: string
    targetCompetitionDates: string[]
    strategyMode?: string
    riskTolerance?: string
  }>
}

export interface BlockComparisonResult {
  schemaVersion: number
  generatedAt: string
  selectedBlockKeys: string[]
  rows: BlockComparisonRow[]
  trends: {
    actualTotal: Array<{ blockKey: string; label: string; value: number | null }>
    dots: Array<{ blockKey: string; label: string; value: number | null }>
    ipfGl: Array<{ blockKey: string; label: string; value: number | null }>
    e1rmTotal: Array<{ blockKey: string; label: string; value: number | null }>
    compliance: Array<{ blockKey: string; label: string; value: number | null }>
    fatigue: Array<{ blockKey: string; label: string; value: number | null }>
    volume: Array<{ blockKey: string; label: string; value: number }>
  }
  roiSignals: Array<{
    lift: string
    avgInolPerWeek: number | null
    avgStrengthDeltaKg: number | null
    interpretation: string
  }>
  exerciseRoi?: Array<{
    exercise: string
    blockCount: number
    totalSets: number
    totalVolumeKg: number
    correlatedLifts: string[]
    positiveSignals: number
    negativeSignals: number
    unclearSignals: number
    confidence: 'low' | 'medium' | 'high'
    summary: string
    blocks: Array<{
      blockKey: string
      label: string
      sets: number
      volumeKg: number
      correlations: Array<{
        lift: string
        direction: 'positive' | 'negative' | 'unclear'
        strength: 'weak' | 'moderate' | 'strong'
      }>
      liftDeltasKg: Record<string, number | null>
    }>
  }>
  correlationFindings?: Array<{
    blockKey: string
    label: string
    exercise: string
    lift: string
    direction: 'positive' | 'negative' | 'unclear'
    strength: 'weak' | 'moderate' | 'strong'
    reasoning: string
    caveat: string
  }>
  patternSignals?: Array<{
    kind: 'roi' | 'training_response' | 'fatigue' | 'compliance' | 'data_quality'
    finding: string
    evidence: string
    confidence: 'low' | 'medium' | 'high'
  }>
  liftDoseResponse?: Array<{
    blockKey: string
    label: string
    lift: 'squat' | 'bench' | 'deadlift'
    avgInol: number | null
    rawAvgInol: number | null
    sets: number
    volumeKg: number
    strengthDeltaKg: number | null
    responsePerSetKg: number | null
    responsePer1000Kg: number | null
  }>
  trainingDayResponse?: Array<{
    blockKey: string
    label: string
    completedWeeks: number
    totalTrainingDays: number
    avgTrainingDaysPerWeek: number | null
    strengthDeltaKg: number | null
    compliancePct: number | null
  }>
  trendSeries?: Array<{
    blockKey: string
    label: string
    weekNumber: number
    weekStart: string
    squatKg: number | null
    benchKg: number | null
    deadliftKg: number | null
    e1rmTotalKg: number | null
    estimatedDots: number | null
    volumeKg: number
    trainingDays: number
    strain: number | null
  }>
  volumeTolerance: {
    status: 'low_confidence' | 'estimated'
    confidence: 'low' | 'medium'
    sampleSize: number
    requiredSampleSize: number
    message: string
    byLift: Record<string, {
      bestObservedAvgInol: number | null
      positiveDeltaBlocks: number
    }>
  }
  missingDataSummary: Array<{
    blockKey: string
    label: string
    flags: DataQualityFlag[]
  }>
}

export interface AiBlockComparisonReport {
  overall_summary?: string
  similarities?: unknown[]
  differences?: unknown[]
  what_works?: unknown[]
  what_does_not_work?: unknown[]
  lift_specific_insights?: unknown[]
  multi_block_exercise_roi?: unknown[]
  cross_block_correlations?: unknown[]
  pattern_detections?: unknown[]
  volume_dose_response?: unknown[]
  bodyweight_relationships?: unknown[]
  training_day_frequency?: unknown[]
  best_value_blocks?: unknown[]
  projection_accuracy?: unknown[]
  progress_dropoff_points?: unknown[]
  fatigue_patterns?: unknown[]
  data_limits?: unknown[]
  insufficient_data?: boolean
  insufficient_data_reason?: string
  [key: string]: unknown
}

export interface AiBlockComparisonResult {
  schemaVersion: number
  generatedAt: string
  cached: boolean
  selectedBlockKeys: string[]
  sourceFingerprint: string
  report: AiBlockComparisonReport
  deterministic: BlockComparisonResult
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
  cache_miss?: boolean
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
    cache_miss: Boolean((report as Partial<CorrelationReport> & { cache_miss?: boolean }).cache_miss),
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
  cache_miss?: boolean
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
    cache_miss: Boolean((report as Partial<ProgramEvaluationReport> & { cache_miss?: boolean }).cache_miss),
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

export async function fetchProgramBlocks(): Promise<ProgramBlockIndexEntry[]> {
  const res = await api.get('/analytics/blocks')
  const body = res.data
  console.log(body)
  if (body.error) throw new Error(body.error)
  return body.data
}

export async function fetchBlockAnalysis(blockKey: string, refresh = false, cacheOnly = false): Promise<BlockAnalysisBundle> {
  const params = new URLSearchParams({
    refresh: String(refresh),
    cacheOnly: String(cacheOnly),
  })
  const res = await api.get(`/analytics/blocks/${encodeURIComponent(blockKey)}/analysis?${params.toString()}`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}

export async function fetchBlockProgramEvaluation(
  blockKey: string,
  refresh = false,
  cacheOnly = false,
): Promise<ProgramEvaluationReport> {
  const params = new URLSearchParams({
    refresh: String(refresh),
    cacheOnly: String(cacheOnly),
  })
  const res = await api.get(`/analytics/blocks/${encodeURIComponent(blockKey)}/program-evaluation?${params.toString()}`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return normalizeProgramEvaluation(body.data)
}

export async function updateBlockStartMaxes(
  blockKey: string,
  maxes: Pick<BlockStartMaxEntry, 'squat_kg' | 'bench_kg' | 'deadlift_kg'>,
): Promise<BlockStartMaxEntry> {
  const res = await api.put(`/analytics/blocks/${encodeURIComponent(blockKey)}/start-maxes`, maxes)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}

export async function fetchBlockComparison(options: {
  blockKeys?: string[]
  includeCurrentFullBlock?: boolean
  includeTrainingOnly?: boolean
  cacheOnly?: boolean
}): Promise<BlockComparisonResult> {
  const res = await api.post('/analytics/block-comparison', options)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}

export async function fetchAiBlockComparison(options: {
  blockKeys?: string[]
  refresh?: boolean
  cacheOnly?: boolean
}): Promise<AiBlockComparisonResult> {
  const res = await api.post('/analytics/block-comparison/ai', options)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}

export async function fetchCorrelationReport(
  weeks: number,
  block = 'current',
  refresh = false,
  cacheOnly = false,
): Promise<CorrelationReport> {
  const params = new URLSearchParams({
    weeks: String(weeks),
    block,
    refresh: String(refresh),
    cacheOnly: String(cacheOnly),
  })
  const res = await api.get(`/analytics/correlation?${params.toString()}`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return normalizeCorrelationReport(body.data)
}

export async function fetchBlockCorrelationReport(
  blockKey: string,
  options: { refresh?: boolean; cacheOnly?: boolean } = {},
): Promise<CorrelationReport> {
  const params = new URLSearchParams({
    refresh: String(Boolean(options.refresh)),
    cacheOnly: String(Boolean(options.cacheOnly)),
  })
  const res = await api.get(`/analytics/blocks/${encodeURIComponent(blockKey)}/correlation?${params.toString()}`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return normalizeCorrelationReport(body.data)
}

export async function fetchProgramEvaluation(refresh = false, cacheOnly = false): Promise<ProgramEvaluationReport> {
  const params = new URLSearchParams({
    refresh: String(refresh),
    cacheOnly: String(cacheOnly),
  })
  const res = await api.get(`/analytics/program-evaluation?${params.toString()}`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return normalizeProgramEvaluation(body.data)
}

/**
 * Trigger full regeneration of all current-block analysis caches:
 * 6 weekly windows, AI correlation, program evaluation, and markdown export.
 * Never invalidates past-block or lifetime-compare caches.
 */
export async function regenerateAnalysis(): Promise<{ success: boolean; generatedAt: string }> {
  const res = await api.post('/analytics/analysis/regenerate')
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}

/**
 * Re-generate a specific past block's analysis, correlation, and program evaluation.
 * Portal-only action — not triggered by the bulk regenerate.
 */
export async function regenerateBlockAnalysis(blockKey: string): Promise<{ success: boolean; generatedAt: string }> {
  const res = await api.post(`/analytics/blocks/${encodeURIComponent(blockKey)}/regenerate`)
  const body = res.data
  if (body.error) throw new Error(body.error)
  return body.data
}
