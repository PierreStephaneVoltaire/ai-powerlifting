
export interface ProgramMeta {
  program_name: string
  program_start: string         // YYYY-MM-DD
  comp_date: string             // YYYY-MM-DD
  federation: string
  practicing_for: string
  version_label: string
  sex?: Sex
  weight_class_kg: number
  weight_class_confirm_by: string
  current_body_weight_kg: number
  current_body_weight_lb: number
  target_squat_kg: number
  target_bench_kg: number
  target_dl_kg: number
  target_total_kg: number
  attempt_pct?: {
    opener: number   // default 0.90
    second: number   // default 0.955
    third: number    // default 1.00
  }
  training_notes: string[]
  change_log: ChangeLogEntry[]
  block_notes: BlockNote[]
  updated_at: string
  last_comp: LastComp
  height_cm?: number
  arm_wingspan_cm?: number
  leg_length_cm?: number
  manual_maxes?: {
    squat: number
    bench: number
    deadlift: number
  }
  block_start_maxes?: Record<string, {
    squat_kg: number | null
    bench_kg: number | null
    deadlift_kg: number | null
    total_kg: number | null
    source: 'manual'
    updated_at: string
  }>
  lift_attempt_settings?: Record<string, {
    max: number
    incremental: boolean
    increment: number
  }>
  archived?: boolean
  archived_at?: string | null
  template_lineage?: TemplateLineage
  program_week_start_day?: WeekStartDay
  block_week_start_days?: Record<string, WeekStartDay>
}

export type WeekStartDay =
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday'

export interface TemplateLineage {
  applied_template_sk: string
  applied_at: string
  week_start_day: WeekStartDay
  start_date: string
}

export interface ChangeLogEntry {
  action: string
  source?: string
  date: string
  note?: string
}

export interface BlockNote {
  date: string
  notes: string
  updated_at: string
  block?: string
}

export interface LastComp {
  date: string
  body_weight_kg: number
  body_weight_lb: number
  weight_class_kg: number
  results: LiftResults
  past_comp_day_protocol: CompDayProtocol
}

export interface LiftResults {
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
  total_kg: number
}

export interface CompDayProtocol {
  caffeine_total_mg: number
  caffeine_sequence: CaffeineStep[]
  carbs: string
  l_theanine: string
  outcome: string
  notes: string
}

export interface CaffeineStep {
  timing: string
  dose_mg: number
  notes: string
}

export interface Phase {
  name: string
  intent: string
  start_week: number
  end_week: number
  target_rpe_min?: number
  target_rpe_max?: number
  days_per_week?: number
  notes?: string
  block?: string   // Training block identifier. Default: "current". Mirrors Session.block.
}

export interface FederationRecord {
  id: string
  name: string
  abbreviation?: string
  region?: string
  notes?: string
  status: 'active' | 'archived'
  membership_paid?: boolean
  membership_cost?: number | null
  membership_paid_date?: string | null
  membership_expiry_date?: string | null
  created_at: string
  updated_at: string
}

export interface QualificationStandard {
  id: string
  federation_id: string
  competition_name?: string
  season_year: number
  sex: 'male' | 'female'
  equipment: 'raw' | 'wraps' | 'single-ply' | 'multi-ply'
  event: 'sbd' | 'bench-only' | 'deadlift-only'
  age_class?: string
  division?: string
  weight_class_kg: number
  required_total_kg: number
  qualifying_start_date?: string
  qualifying_end_date?: string
  source_url?: string
  source_label?: string
  source_type: 'user_entered'
  status: 'active' | 'archived'
  updated_at: string
}

export interface FederationLibrary {
  pk: string
  sk: string
  updated_at: string
  federations: FederationRecord[]
  qualification_standards: QualificationStandard[]
}


export interface Competition {
  name: string
  date: string
  federation: string
  counts_toward_federation_ids?: string[]  // Extra federations that accept this meet for goal eligibility
  location?: string
  hotel_required?: boolean
  status: 'confirmed' | 'optional' | 'completed' | 'skipped'
  weight_class_kg: number
  body_weight_kg?: number  // Actual weigh-in weight for completed competitions
  qualifying_standard_id?: string  // deprecated: goals own qualification standards
  qualifying_total_kg?: number  // deprecated: goals own qualifying totals
  attempt_strategy_mode?: AttemptStrategyMode  // deprecated: goals own meet strategy
  targets?: LiftResults    // For upcoming competitions
  projected_at_t_minus_1w?: LiftResults
  projection_snapshot_date?: string
  results?: CompetitionResults    // For completed competitions
  post_meet_report?: PostMeetReport
  notes?: string
  decision_date?: string | null
  between_comp_plan?: BetweenCompPlan
  comp_day_protocol?: CompDayProtocol
}

export interface CompetitionPrr {
  squat: number | null
  bench: number | null
  deadlift: number | null
  total: number | null
}

export interface CompetitionResults extends LiftResults {
  projected_at_t_minus_1w?: LiftResults
  prr?: CompetitionPrr
}

export type CompetitionLift = 'squat' | 'bench' | 'deadlift'
export type CompetitionAttemptResult = 'made' | 'missed' | 'not_taken'
export type CompetitionMissCategory =
  | 'strength'
  | 'judged_technical'
  | 'command'
  | 'attempt_selection'
  | 'pain'
  | 'fatigue'
  | 'equipment'
  | 'other'
export type CompetitionMissReason =
  | 'strength_failure'
  | 'technical_failure'
  | 'command_failure'
  | 'grip'
  | 'depth'
  | 'pause'
  | 'lockout'
  | 'balance'
  | 'pain'
  | 'fatigue'
  | 'misload_bad_attempt_selection'
  | 'equipment_issue'

export interface CompetitionAttempt {
  lift: CompetitionLift
  attempt_number: 1 | 2 | 3
  kg: number | null
  result: CompetitionAttemptResult
  miss_reasons: CompetitionMissReason[]
  miss_category: CompetitionMissCategory | null
}

export interface PostMeetReport {
  attempts: CompetitionAttempt[]
  sleep_hours: number | null
  travel_notes: string
  warmup_timing: string
  pre_meet_food: string
  during_meet_food: string
  caffeine_mg: number | null
  caffeine_timing: string
  equipment_issues: string
  commands_missed: string
  attempt_selection_grade: 1 | 2 | 3 | 4 | 5 | null
  notes: string
}

export interface BetweenCompPlan {
  rest: string
  ramp_back: string
  diet: string
  weight_class: string
  inflammation: string
}


export interface Exercise {
  id?: string
  name: string
  sets: number
  reps: number
  kg: number | null
  notes: string
  failed?: boolean          // deprecated — kept for backwards compat
  failed_sets?: boolean[]   // per-set: [false, false, true, false] = set 3 failed
  set_statuses?: SetStatus[] // per-set execution state; failed_sets is derived for legacy readers
  failed_set_reasons?: FailedSetReason[][] // per failed set, aligned to set_statuses
  load_source?: LoadSource
  rpe_target?: number | null
  rpe?: number | null       // executed RPE for the exercise (4-10, 0.5 increments)
}

export type SetStatus = 'pending' | 'completed' | 'failed' | 'skipped'
export type FailedSetReason =
  | 'strength_failure'
  | 'technical_failure'
  | 'command_failure'
  | 'grip'
  | 'depth'
  | 'pause'
  | 'lockout'
  | 'balance'
  | 'pain'
  | 'fatigue'
  | 'misload_bad_attempt_selection'
export type LoadSource = 'absolute' | 'rpe' | 'percentage' | 'unresolvable'
export type LoadType = LoadSource

export interface PlannedExercise {
  id?: string
  name: string
  sets: number
  reps: number
  kg: number | null
  load_source?: LoadSource
  rpe_target?: number | null
}

export type SessionStatus = 'planned' | 'logged' | 'completed' | 'skipped'

export type WellnessScore = 1 | 2 | 3 | 4 | 5

export interface SessionWellness {
  sleep: WellnessScore
  soreness: WellnessScore
  mood: WellnessScore
  stress: WellnessScore
  energy: WellnessScore
  recorded_at: string
}

export interface Session {
  id?: string
  date: string              // YYYY-MM-DD
  day: string               // 'Friday' etc
  week: string              // 'W1 (Warmup)' — raw label from DynamoDB
  week_number: number       // parsed integer, derived on load by backend transform
  phase: Phase              // resolved from program.phases on load by backend transform
  block?: string            // Training block identifier. Default: "current". Archived blocks get user-chosen names.
  status?: SessionStatus
  completed: boolean
  planned_exercises?: PlannedExercise[]
  exercises: Exercise[]
  session_notes: string
  session_rpe: number | null
  body_weight_kg: number | null
  wellness?: SessionWellness
  videos?: SessionVideo[]   // Optional video attachments
  pain_log?: unknown[]
}


export interface SessionVideo {
  video_id: string
  s3_key: string
  thumbnail_s3_key?: string
  /** @deprecated Frontend now resolves this from s3_key via VITE_CLOUDFRONT_MEDIA_BASE_URL */
  video_url?: string
  /** @deprecated Frontend now resolves this from thumbnail_s3_key via VITE_CLOUDFRONT_MEDIA_BASE_URL */
  thumbnail_url?: string
  exercise_name?: string
  set_number?: number
  notes?: string
  uploaded_at: string
  thumbnail_status?: 'pending' | 'ready' | 'failed'
}


export interface VideoLibraryItem {
  video: SessionVideo
  session_date: string
  day: string
  week_number: number
  phase_name: string
  exercise_sets: number
  exercise_reps: number
  exercise_kg: number | null
}

export interface VideoLibraryResponse {
  videos: VideoLibraryItem[]
  exercises: string[]
}

export type VideoSort = 'newest' | 'oldest' | 'volume' | 'weight'


export interface Program {
  pk: string
  sk: string
  meta: ProgramMeta
  phases: Phase[]
  sessions: Session[]
  competitions: Competition[]
  diet_notes: DietNote[]
  supplements: Supplement[]
  supplement_phases: SupplementPhase[]
  lift_profiles?: LiftProfile[]
  current_maxes?: {
    squat: number | null
    bench: number | null
    deadlift: number | null
    method: string
  }
}

export interface DietNote {
  date: string
  notes: string
  avg_daily_calories?: number
  avg_protein_g?: number
  avg_carb_g?: number
  avg_fat_g?: number
  avg_sleep_hours?: number
  water_intake?: number
  water_unit?: 'litres' | 'cups'
  consistent?: boolean
}


export interface LiftProfile {
  lift: 'squat' | 'bench' | 'deadlift'
  style_notes: string         // free-form technique/setup description
  sticking_points: string     // where in the lift they struggle most
  primary_muscle: string      // e.g. "quad dominant", "tricep dominant"
  volume_tolerance: 'low' | 'moderate' | 'high'
  e1rm_multiplier?: number    // manual correction for raw estimates (0.85-1.10)
  stimulus_coefficient?: number
  stimulus_coefficient_reasoning?: string
  stimulus_coefficient_confidence?: 'low' | 'medium' | 'high'
  stimulus_coefficient_updated_at?: string
  inol_low_threshold?: number
  inol_high_threshold?: number
}

export interface Supplement {
  name: string
  dose: string
}

export interface SupplementPhase {
  phase: number
  phase_name: string
  notes: string
  items: (Supplement & { notes?: string })[]
  peak_week_protocol?: Record<string, string>  // Dynamic key-value pairs (caffeine, creatine_timing, etc.)
  block?: string          // Training block identifier. Default: "current"
  start_week?: number     // Week range start (from block's sessions)
  end_week?: number       // Week range end (from block's sessions)
}


export interface MaxEntry {
  date: string
  squat_kg: number | null
  bench_kg: number | null
  deadlift_kg: number | null
  total_kg: number | null
  bodyweight_kg: number | null
  context: string
}


export interface WeightEntry {
  date: string
  kg: number
}


export type MuscleGroup =
  | 'quads' | 'hamstrings' | 'glutes' | 'calves' | 'tibialis_anterior' | 'hip_flexors' | 'adductors'
  | 'chest' | 'triceps' | 'front_delts' | 'side_delts' | 'rear_delts'
  | 'lats' | 'traps' | 'rhomboids' | 'teres_major'
  | 'biceps' | 'forearms'
  | 'erectors' | 'lower_back' | 'core' | 'obliques' | 'serratus'

export type ExerciseCategory =
  | 'squat' | 'bench' | 'deadlift'
  | 'back' | 'chest' | 'arm' | 'legs' | 'core' | 'lower_back'

export type Equipment =
  | 'barbell' | 'dumbbell' | 'cable' | 'machine'
  | 'bodyweight' | 'hex_bar' | 'bands' | 'kettlebell'

export type FatigueCategory = 'primary_axial' | 'primary_upper' | 'secondary' | 'accessory'

export interface FatigueProfile {
  axial: number       // 0.0-1.0, spinal compression loading
  neural: number      // 0.0-1.0, CNS demand baseline
  peripheral: number  // 0.0-1.0, local muscle damage potential
  systemic: number    // 0.0-1.0, cardiovascular/metabolic demand
}

export type FatigueProfileSource = 'ai_estimated' | 'manual'

export interface E1rmEstimate {
  value_kg: number
  method: 'manual' | 'ai_backfill' | 'logged'
  basis: string
  confidence: 'high' | 'medium' | 'low'
  set_at: string
  manually_overridden: boolean
}

export interface GlossaryExercise {
  id: string
  name: string
  category: ExerciseCategory
  fatigue_category: FatigueCategory
  primary_muscles: MuscleGroup[]
  secondary_muscles: MuscleGroup[]
  tertiary_muscles?: MuscleGroup[]
  equipment: Equipment
  description: string
  how_to_perform: string
  why_do_it: string
  video_url?: string
  fatigue_profile?: FatigueProfile
  fatigue_profile_source?: FatigueProfileSource
  fatigue_profile_reasoning?: string | null
  e1rm_estimate?: E1rmEstimate
  archived?: boolean
}


export interface Template {
  pk: string
  sk: string
  meta: TemplateMeta
  phases: TemplatePhase[]
  sessions: TemplateSession[]
  glossary_resolution: GlossaryResolution
  required_maxes: string[] // glossary_ids
}

export interface TemplateMeta {
  name: string
  source_filename?: string
  source_file_hash?: string
  description: string
  estimated_weeks: number
  days_per_week: number
  created_at: string
  updated_at: string
  archived: boolean
  author?: string
  author_pk?: string
  published: boolean
  published_at?: string
  import_job_id?: string
  derived_from_template_sk?: string
  derived_from_program_sk?: string
  ai_evaluation?: AiTemplateEvaluation
}

export interface TemplateEvaluationSuggestion {
  type: string
  week?: number | null
  phase?: string | null
  exercise?: string | null
  rationale: string
}

export interface AiTemplateEvaluation {
  stance: string
  summary: string
  strengths: string[]
  weaknesses: string[]
  suggestions: TemplateEvaluationSuggestion[]
  projected_readiness_at_comp?: number
  data_citations?: string[]
  context_snapshot: any
}

export interface TemplatePhase {
  name: string
  week_start: number
  week_end: number
  target_rpe_min?: number
  target_rpe_max?: number
  intent: string
}

export interface TemplateSession {
  id: string
  week_number: number
  day_of_week: string
  day_index: number
  label: string
  exercises: TemplateExercise[]
}

export interface TemplateExercise {
  name: string
  glossary_id?: string
  sets: number
  reps: number
  load_type: LoadType
  load_value: number | null
  rpe_target: number | null
  notes: string
}

export interface GlossaryResolution {
  resolved: string[]
  unresolved: string[]
  auto_added: string[]
  resolution_status: 'resolved' | 'partial' | 'unresolved'
}

export interface TemplateListEntry {
  sk: string
  name: string
  source_filename?: string
  source_file_hash?: string
  estimated_weeks: number
  days_per_week: number
  archived: boolean
  author?: string
  author_pk?: string
  published: boolean
  published_at?: string
  import_job_id?: string
  created_at: string
  updated_at: string
}

export type TemplateImportJobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface TemplateImportJob {
  job_id: string
  status: TemplateImportJobStatus
  filename?: string
  template_sk?: string
  warnings?: any[]
  error?: string
  author?: string
  author_pk?: string
  created_at?: string
  updated_at?: string
}


export type ImportType = 'template' | 'session_import'
export type ImportStatus = 'awaiting_review' | 'applied' | 'rejected'
export type MergeStrategy = 'append' | 'overwrite_future' | 'selective'

export interface ImportWarning {
  type: string
  message: string
  severity: 'low' | 'medium' | 'high'
}

export interface AiParseResult {
  phases: any[]
  sessions: any[]
  required_maxes: string[]
  warnings: ImportWarning[]
  raw_output?: string
  parse_notes?: string
}

export interface ConflictResolution {
  session_date: string
  action: 'skip' | 'overwrite' | 'merge'
}

export interface ImportPending {
  pk: string
  sk: string
  import_id: string
  import_type: ImportType
  status: ImportStatus
  source_filename: string
  source_file_hash: string
  source_sheet_name?: string
  classification: 'template' | 'session_import' | 'ambiguous'
  uploaded_at: string
  expires_at: string
  ttl: number
  ai_parse_result: AiParseResult
  merge_strategy?: MergeStrategy
  conflict_resolutions?: ConflictResolution[]
  applied_at?: string
  rejected_at?: string
  rejection_reason?: string
}


export type PlateUnit = 'kg' | 'lb'

export interface PlateLoadout {
  plates: number[]          // one side, descending order
  totalKg: number
  perSideKg: number
  remainder: number         // leftover that could not be loaded (should be ~0)
  achievable: boolean
}


export type Sex = 'male' | 'female'

export interface DotsResult {
  dots: number
  total_kg: number
  bodyweight_kg: number
  sex: Sex
}


export interface ApiResponse<T> {
  data: T
  error?: string
}

export interface ProgramListItem {
  version: string           // 'v001' or 'current'
  sk: string                // 'program#v001'
  comp_date: string
  updated_at: string
  version_label: string
  is_current?: boolean      // true if this is the current/active version
  archived?: boolean
}


export interface GlossaryStore {
  pk: string
  sk: string
  exercises: GlossaryExercise[]
  updated_at: string
}


export interface MaxHistoryStore {
  pk: string
  sk: string
  entries: MaxEntry[]
  updated_at: string
}


export interface WeightLogStore {
  pk: string
  sk: string
  entries: WeightEntry[]
  updated_at: string
}


export interface FatigueAnalyticsFields {
  fatigue_model?: string
  current_state_fi?: number
  window_weighted_fi?: number
  window_mean_fi?: number
  window_peak_fi?: number
  reservoir_stress?: number
  reservoir_dimension_stress?: Record<string, number>
  reservoir_max_dimension_stress?: number
  reservoir_weighted_stress?: number
}

export interface InolPhaseAdjustedThreshold {
  low: number
  high: number
  display_low: number
  display_high: number
  phase_multiplier: number
}

export interface InolTrendPressure {
  value: number
  volume_ratio: number
  ri_ratio: number
}

export interface InolAnalyticsFields {
  phase_adjusted_thresholds?: Record<string, InolPhaseAdjustedThreshold>
  trend_pressure?: Record<string, InolTrendPressure>
}

export interface ReadinessAnalyticsFields {
  training_score?: number
  external_score?: number
  training_readiness_confidence?: number
  external_readiness_confidence?: number
}


export type CompEventType = 'full_power' | 'bench_only' | 'deadlift_only' | 'unknown' | null
export type CompTestingStatus = 'tested' | 'untested' | 'unknown'
export type CompRegistrationStatus = 'open' | 'closed' | 'unknown'

export interface AttemptSelectionAttempt {
  lift: CompetitionLift
  attempt_1: number | null
  attempt_2: number | null
  attempt_3: number | null
}

export type AttemptSelection = AttemptSelectionAttempt[]

export interface MasterCompetition {
  name: string
  start_date: string
  end_date: string | null
  federation_label: string | null
  federation_slug: string | null
  federation_website_url: string | null
  venue_name: string | null
  venue_address: string | null
  venue_city: string | null
  venue_state: string | null
  venue_country: string | null
  venue_postal_code: string | null
  website_url: string | null
  testing_status: CompTestingStatus
  registration_status: CompRegistrationStatus
  registration_url: string | null
  registration_end_date: string | null
  source_url: string | null
  source_name: string | null
  last_verified_at: string | null
  slug: string | null
  cancelled: boolean
  is_sample_data: boolean
  created_at: string
  updated_at: string
}

export interface UserCompetition {
  master_id: string
  name: string
  start_date: string
  end_date: string | null
  federation_label: string
  federation_slug: string | null
  federation_website_url: string | null
  venue_name: string | null
  venue_address: string | null
  venue_city: string | null
  venue_state: string | null
  venue_country: string | null
  venue_postal_code: string | null
  website_url: string | null
  testing_status: CompTestingStatus
  registration_status: CompRegistrationStatus
  registration_url: string | null
  registration_end_date: string | null
  source_url: string | null
  source_name: string | null
  last_verified_at: string | null
  event_type: CompEventType
  cancelled: boolean
  user_status: 'available' | 'optional' | 'confirmed' | 'completed' | 'skipped'
  weight_class_kg: number | null
  body_weight_kg: number | null
  targets: LiftResults | null
  results: CompetitionResults | null
  post_meet_report: PostMeetReport | null
  hotel_required: boolean
  counts_toward_federation_ids: string[]
  between_comp_plan: BetweenCompPlan | null
  comp_day_protocol: CompDayProtocol | null
  decision_date: string | null
  attempt_selection: AttemptSelection | null
  attempt_strategy_mode: AttemptStrategyMode | null
  qualifying_standard_id: string | null
  qualifying_total_kg: number | null
  projected_at_t_minus_1w: LiftResults | null
  projection_snapshot_date: string | null
  notes: string
  created_at: string
  updated_at: string
}

export type AttemptStrategyMode =
  | 'max_total'
  | 'qualify'
  | 'minimum_total'
  | 'podium'
  | 'train_through'
  | 'conservative_pr'

export type AgeCategory =
  | 'open'
  | 'subjunior'
  | 'junior'
  | 'master1'
  | 'master2'
  | 'master3'
  | 'master4'

export const AGE_CATEGORY_OPTIONS: ReadonlyArray<{ value: AgeCategory; label: string }> = [
  { value: 'open', label: 'Open' },
  { value: 'subjunior', label: 'Sub-Junior' },
  { value: 'junior', label: 'Junior' },
  { value: 'master1', label: 'Master 1' },
  { value: 'master2', label: 'Master 2' },
  { value: 'master3', label: 'Master 3' },
  { value: 'master4', label: 'Master 4' },
]

export const AGE_CATEGORY_ORDER: Record<AgeCategory, number> = {
  subjunior: 0,
  junior: 1,
  open: 2,
  master1: 3,
  master2: 4,
  master3: 5,
  master4: 6,
}

export const AGE_CATEGORY_VALUES: ReadonlyArray<AgeCategory> = [
  'open',
  'subjunior',
  'junior',
  'master1',
  'master2',
  'master3',
  'master4',
]


export type GoalType =
  | 'hit_total'
  | 'qualify_for_federation'
  | 'peak_for_meet'
  | 'conservative_pr'
  | 'competition_exposure'
  | 'improve_dots'
  | 'improve_ipf_gl'
  | 'custom'

export const GOAL_TYPE_VALUES: ReadonlyArray<GoalType> = [
  'hit_total',
  'qualify_for_federation',
  'peak_for_meet',
  'conservative_pr',
  'competition_exposure',
  'improve_dots',
  'improve_ipf_gl',
  'custom',
]

export const GOAL_TYPE_OPTIONS: ReadonlyArray<{ value: GoalType; label: string }> = [
  { value: 'hit_total', label: 'Hit Total' },
  { value: 'qualify_for_federation', label: 'Qualify for Federation' },
  { value: 'peak_for_meet', label: 'Peak for Meet' },
  { value: 'conservative_pr', label: 'Conservative PR' },
  { value: 'competition_exposure', label: 'Competition Exposure' },
  { value: 'improve_dots', label: 'Improve DOTS' },
  { value: 'improve_ipf_gl', label: 'Improve IPF GL' },
  { value: 'custom', label: 'Custom' },
]

export type GoalPriority = 'primary' | 'secondary' | 'optional'

export const GOAL_PRIORITY_VALUES: ReadonlyArray<GoalPriority> = ['primary', 'secondary', 'optional']

export const GOAL_PRIORITY_OPTIONS: ReadonlyArray<{ value: GoalPriority; label: string }> = [
  { value: 'primary', label: 'Primary' },
  { value: 'secondary', label: 'Secondary' },
  { value: 'optional', label: 'Optional' },
]

export const TARGET_COMPETITION_STATUSES: ReadonlyArray<'optional' | 'confirmed' | 'completed' | 'skipped'> = [
  'optional',
  'confirmed',
  'completed',
  'skipped',
]

export interface AthleteGoal {
  id: string
  title: string
  goal_type: GoalType
  priority: GoalPriority
  target_date?: string
  target_competition_ids?: string[]
  target_total_kg?: number
  target_dots?: number
  target_ipf_gl?: number
  target_federation_ids?: string[]
  target_weight_class_kg?: number[]
  age_class?: AgeCategory
  notes?: string
}

export function normalizeGoalType(value: unknown): GoalType {
  return (GOAL_TYPE_VALUES as ReadonlyArray<string>).includes(String(value))
    ? (value as GoalType)
    : 'custom'
}

export function normalizeGoalPriority(value: unknown): GoalPriority {
  return (GOAL_PRIORITY_VALUES as ReadonlyArray<string>).includes(String(value))
    ? (value as GoalPriority)
    : 'secondary'
}

export function normalizeGoal(raw: unknown): AthleteGoal | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const id = typeof r.id === 'string' && r.id.length > 0 ? r.id : randomId()
  const title = typeof r.title === 'string' ? r.title : ''
  const goalType = normalizeGoalType(r.goal_type)
  const priority = normalizeGoalPriority(r.priority)
  const out: AthleteGoal = { id, title, goal_type: goalType, priority }

  if (typeof r.target_date === 'string' && r.target_date) out.target_date = r.target_date
  if (Array.isArray(r.target_competition_ids)) {
    const ids = r.target_competition_ids.filter((v): v is string => typeof v === 'string' && v.length > 0)
    if (ids.length) out.target_competition_ids = [...new Set(ids)]
  }
  if (typeof r.target_total_kg === 'number' && Number.isFinite(r.target_total_kg) && r.target_total_kg > 0) {
    out.target_total_kg = r.target_total_kg
  }
  if (typeof r.target_dots === 'number' && Number.isFinite(r.target_dots) && r.target_dots > 0) {
    out.target_dots = r.target_dots
  }
  if (typeof r.target_ipf_gl === 'number' && Number.isFinite(r.target_ipf_gl) && r.target_ipf_gl > 0) {
    out.target_ipf_gl = r.target_ipf_gl
  }
  if (Array.isArray(r.target_federation_ids)) {
    const ids = r.target_federation_ids.filter((v): v is string => typeof v === 'string' && v.length > 0)
    if (ids.length) out.target_federation_ids = [...new Set(ids)]
  }
  if (Array.isArray(r.target_weight_class_kg)) {
    const wcs = r.target_weight_class_kg.filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0)
    if (wcs.length) out.target_weight_class_kg = [...new Set(wcs)]
  }
  if (typeof r.age_class === 'string' && AGE_CATEGORY_VALUES.includes(r.age_class as AgeCategory)) {
    out.age_class = r.age_class as AgeCategory
  }
  if (typeof r.notes === 'string') out.notes = r.notes

  return out
}

function randomId(): string {
  return `goal-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`
}

export type FederationSex = 'male' | 'female'

export const FEDERATION_SEX_VALUES: ReadonlyArray<FederationSex> = ['male', 'female']

export type FederationLevel = 'national' | 'regional'

export const FEDERATION_LEVEL_OPTIONS: ReadonlyArray<{ value: FederationLevel; label: string }> = [
  { value: 'national', label: 'National' },
  { value: 'regional', label: 'Regional' },
]

export const FEDERATION_LEVEL_VALUES: ReadonlyArray<FederationLevel> = ['national', 'regional']

export interface FederationStandardEntry {
  id: string
  sex?: FederationSex
  age_class?: AgeCategory
  weight_class?: string
  level?: FederationLevel
  category?: string
  qualifying_total: number
}

export interface FederationStandard {
  start_date: string
  end_date: string
  entries: FederationStandardEntry[]
}

export type FederationStandardUnit = 'kg' | 'dots'

export interface FederationDisplayOptions {
  show_sex: boolean
  show_age_class: boolean
  show_weight_class: boolean
  show_category: boolean
}

export const DEFAULT_FEDERATION_DISPLAY_OPTIONS: FederationDisplayOptions = {
  show_sex: true,
  show_age_class: true,
  show_weight_class: true,
  show_category: true,
}

export interface MasterFederation {
  pk: string
  sk: string
  name: string
  abbreviation: string | null
  region: string | null
  website_url: string | null
  status: 'active' | 'archived'
  source_slug: string | null
  has_standards: boolean
  standard_unit: FederationStandardUnit | null
  standards: Record<string, FederationStandard>
  display_options?: FederationDisplayOptions
  parent_federation_abbr?: string | null
  membership_group?: string[]
  created_at: string
  updated_at: string
}

export interface StoredGoal extends AthleteGoal {
  id: string
  target_competition_ids?: string[]
  created_at: string
  updated_at: string
}

export interface UserCompetitionUpdate {
  user_status?: 'available' | 'optional' | 'confirmed' | 'completed' | 'skipped'
  weight_class_kg?: number | null
  body_weight_kg?: number | null
  targets?: LiftResults | null
  results?: CompetitionResults | null
  post_meet_report?: PostMeetReport | null
  hotel_required?: boolean
  counts_toward_federation_ids?: string[]
  between_comp_plan?: BetweenCompPlan | null
  comp_day_protocol?: CompDayProtocol | null
  decision_date?: string | null
  attempt_selection?: AttemptSelection | null
  attempt_strategy_mode?: AttemptStrategyMode | null
  qualifying_standard_id?: string | null
  qualifying_total_kg?: number | null
  projected_at_t_minus_1w?: LiftResults | null
  projection_snapshot_date?: string | null
  notes?: string
}

export type BudgetCategory =
  | 'equipment'
  | 'supplement'
  | 'gym_membership'
  | 'federation_membership'
  | 'coaching'
  | 'app_subscription'
  | 'competition_entry'
  | 'transport'
  | 'accommodation'
  | 'food_comp_day'
  | 'food_weigh_in'
  | 'food_prep'
  | 'recovery'
  | 'other'

export const BUDGET_CATEGORY_VALUES: ReadonlyArray<BudgetCategory> = [
  'equipment',
  'supplement',
  'gym_membership',
  'federation_membership',
  'coaching',
  'app_subscription',
  'competition_entry',
  'transport',
  'accommodation',
  'food_comp_day',
  'food_weigh_in',
  'food_prep',
  'recovery',
  'other',
]

export const BUDGET_CATEGORY_OPTIONS: ReadonlyArray<{ value: BudgetCategory; label: string }> = [
  { value: 'equipment', label: 'Equipment' },
  { value: 'supplement', label: 'Supplement' },
  { value: 'gym_membership', label: 'Gym membership' },
  { value: 'federation_membership', label: 'Federation membership' },
  { value: 'coaching', label: 'Coaching' },
  { value: 'app_subscription', label: 'App subscription' },
  { value: 'competition_entry', label: 'Competition entry' },
  { value: 'transport', label: 'Transport' },
  { value: 'accommodation', label: 'Accommodation' },
  { value: 'food_comp_day', label: 'Food — comp day' },
  { value: 'food_weigh_in', label: 'Food — weigh-in' },
  { value: 'food_prep', label: 'Food — prep' },
  { value: 'recovery', label: 'Recovery' },
  { value: 'other', label: 'Other' },
]

export type BudgetPriorityTier = 'MANDATORY' | 'IMPORTANT' | 'OPTIONAL'

export const BUDGET_PRIORITY_TIER_VALUES: ReadonlyArray<BudgetPriorityTier> = [
  'MANDATORY',
  'IMPORTANT',
  'OPTIONAL',
]

export const BUDGET_PRIORITY_TIER_OPTIONS: ReadonlyArray<{ value: BudgetPriorityTier; label: string }> = [
  { value: 'MANDATORY', label: 'Mandatory' },
  { value: 'IMPORTANT', label: 'Important' },
  { value: 'OPTIONAL', label: 'Optional' },
]

export type BudgetRecurrence = 'ONE_TIME' | 'MONTHLY' | 'QUARTERLY' | 'ANNUAL'

export const BUDGET_RECURRENCE_VALUES: ReadonlyArray<BudgetRecurrence> = [
  'ONE_TIME',
  'MONTHLY',
  'QUARTERLY',
  'ANNUAL',
]

export const BUDGET_RECURRENCE_OPTIONS: ReadonlyArray<{ value: BudgetRecurrence; label: string }> = [
  { value: 'ONE_TIME', label: 'One-time' },
  { value: 'MONTHLY', label: 'Monthly' },
  { value: 'QUARTERLY', label: 'Quarterly' },
  { value: 'ANNUAL', label: 'Annual' },
]

export type BudgetDatePrecision = 'exact' | 'month'

export const BUDGET_DATE_PRECISION_VALUES: ReadonlyArray<BudgetDatePrecision> = ['exact', 'month']

export interface BudgetItem {
  id: string
  user_pk: string
  name: string
  category: BudgetCategory
  priority_tier: BudgetPriorityTier
  cost: number
  currency: string
  recurrence: BudgetRecurrence
  date_precision: BudgetDatePrecision
  start_date: string
  end_date: string | null
  comp_linked: boolean
  competition_id: string | null
  purchased: boolean
  purchased_date: string | null
  notes: string | null
  photo_s3_key: string | null
  cut_by_ai: boolean
  created_at: string
  updated_at: string
}

export interface BudgetConfig {
  user_pk: string
  monthly_cap: number
  currency: string
  notes: string | null
  updated_at: string
}

export interface BudgetStore {
  config: BudgetConfig
  items: BudgetItem[]
}

export interface BudgetPriorityBreakdown {
  count: number
  total: number
}

export interface BudgetSummary {
  monthly_cap: number
  currency: string
  spent_this_month: number
  recurring_monthly_total: number
  items_by_priority: {
    MANDATORY: BudgetPriorityBreakdown
    IMPORTANT: BudgetPriorityBreakdown
    OPTIONAL: BudgetPriorityBreakdown
  }
  upcoming_one_time: BudgetItem[]
}


export type BudgetPriority = 'buy_now' | 'buy_later' | 'optional' | 'drop'

export const BUDGET_PRIORITY_VALUES: ReadonlyArray<BudgetPriority> = [
  'buy_now',
  'buy_later',
  'optional',
  'drop',
]

export const BUDGET_PRIORITY_OPTIONS: ReadonlyArray<{ value: BudgetPriority; label: string }> = [
  { value: 'buy_now', label: 'Buy now' },
  { value: 'buy_later', label: 'Buy later' },
  { value: 'optional', label: 'Optional' },
  { value: 'drop', label: 'Drop' },
]

export type EquipmentCondition = 'good' | 'worn' | 'needs_replacement' | 'unknown'

export const EQUIPMENT_CONDITION_VALUES: ReadonlyArray<EquipmentCondition> = [
  'good',
  'worn',
  'needs_replacement',
  'unknown',
]

export const EQUIPMENT_CONDITION_OPTIONS: ReadonlyArray<{ value: EquipmentCondition; label: string }> = [
  { value: 'good', label: 'Good' },
  { value: 'worn', label: 'Worn' },
  { value: 'needs_replacement', label: 'Needs replacement' },
  { value: 'unknown', label: 'Unknown' },
]

export interface BudgetTimelineEntry {
  item_id: string
  name: string
  category: BudgetCategory
  priority: BudgetPriority
  suggested_date: string
  cost: number
  reason: string
}

export interface BudgetTimelineMonth {
  month: string
  due: number
  budget: number
  remaining: number
  entries: BudgetTimelineEntry[]
}

export interface BudgetTimeline {
  months: BudgetTimelineMonth[]
  notes: string[]
}


export interface BudgetAiLockedItem {
  item_id: string
  name: string
  note: string
  purchased: boolean
}

export interface BudgetAiCutItem {
  item_id: string
  name: string
  cost: number
  reason: string
  rank: number
}

export interface BudgetAiGap {
  description: string
  severity: 'info' | 'warning'
}

export interface BudgetAiAnalysis {
  overall_assessment: string
  locked_in: BudgetAiLockedItem[]
  suggested_cuts: BudgetAiCutItem[]
  gaps: BudgetAiGap[]
  coach_note: string
  insufficient_data: boolean
  insufficient_data_reason: string
  cached: boolean
  generated_at: string
}


// =============================================================================
// Epic 3 — Onboarding (role / athlete basics / profile)
// =============================================================================

export type Role = 'athlete' | 'coach' | 'handler'

export const ROLE_VALUES: ReadonlyArray<Role> = ['athlete', 'coach', 'handler']

export const ROLE_LABELS: Record<Role, string> = {
  athlete: 'Athlete',
  coach: 'Coach',
  handler: 'Handler',
}

export interface TrainingMaxes {
  squat_kg: number
  bench_kg: number
  deadlift_kg: number
}

export interface AthleteBasics {
  sex: Sex
  bodyweight_kg: number
  country: string          // ISO 3166-1 alpha-2; informational. Federations are the source of truth for weight classes.
  region: string           // Freeform state/province (e.g. "CA", "Ontario"); no subdivision list validation.
  training_maxes: TrainingMaxes
}

export interface OnboardingState {
  athlete_basics_complete: boolean
  profile_complete: boolean
  roles: Role[]
  active_role: Role
}

export interface OnboardingStatus {
  is_onboarded: boolean
  next_step: 'role' | 'profile' | 'athlete_basics' | 'done' | null
  state: OnboardingState
  has_athlete_basics: boolean
}
