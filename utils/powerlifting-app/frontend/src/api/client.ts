import axios from 'axios'
import type {
  Program,
  ProgramListItem,
  Session,
  PlannedExercise,
  Exercise,
  MaxEntry,
  WeightEntry,
  GlossaryExercise,
  ApiResponse,
  Phase,
  SupplementPhase,
  DietNote,
  BlockNote,
  Competition,
  AthleteGoal,
  FederationLibrary,
  SessionVideo,
  LiftResults,
  VideoLibraryItem,
  VideoLibraryResponse,
  FatigueProfile,
  LiftProfile,
  SessionWellness,
  ImportPending,
  ImportType,
  MergeStrategy,
  AiTemplateEvaluation,
  Template,
  TemplateListEntry,
  ConflictResolution,
  PostMeetReport,
  WeekStartDay,
} from '@powerlifting/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

function templatePath(sk: string, suffix = ''): string {
  return `/templates/${encodeURIComponent(sk)}${suffix}`
}

// ─── Programs ────────────────────────────────────────────────────────────────

export async function fetchPrograms(): Promise<ProgramListItem[]> {
  const res = await api.get<ApiResponse<ProgramListItem[]>>('/programs')
  return res.data.data
}

export async function fetchProgram(version: string): Promise<Program> {
  const res = await api.get<ApiResponse<Program>>(`/programs/${version}`)
  return res.data.data
}

export async function updateMetaField(
  version: string,
  field: string,
  value: unknown
): Promise<void> {
  await api.put(`/programs/${version}/meta`, { field, value })
}

export async function forkProgram(
  version: string,
  label?: string
): Promise<string> {
  const res = await api.post<ApiResponse<{ version: string }>>(
    `/programs/${version}/fork`,
    { label }
  )
  return res.data.data.version
}

// ─── Sessions ────────────────────────────────────────────────────────────────

export async function createSession(
  version: string,
  session: Partial<Session> & { date: string }
): Promise<Session> {
  const res = await api.post<ApiResponse<{ success: boolean; session: Session }>>(
    `/sessions/${version}`,
    session
  )
  return res.data.data.session
}

export async function deleteSession(
  version: string,
  date: string,
  index: number
): Promise<void> {
  await api.delete(`/sessions/${version}/${date}/${index}`)
}

export async function fetchSession(
  version: string,
  date: string,
  index: number
): Promise<Session | null> {
  const res = await api.get<ApiResponse<Session | null>>(
    `/sessions/${version}/${date}/${index}`
  )
  return res.data.data
}

export async function updateSession(
  version: string,
  date: string,
  index: number,
  session: Session
): Promise<void> {
  await api.put(`/sessions/${version}/${date}/${index}`, session)
}

export async function updatePlannedExercises(
  version: string,
  date: string,
  index: number,
  plannedExercises: PlannedExercise[]
): Promise<void> {
  await api.put(`/programs/${version}/designer/${date}/${index}/planned-exercises`, { planned_exercises: plannedExercises })
}

export async function rescheduleSession(
  version: string,
  date: string,
  index: number,
  newDate: string,
  newDay: string
): Promise<void> {
  await api.patch(`/sessions/${version}/${date}/${index}/reschedule`, {
    newDate,
    newDay,
  })
}

export async function completeSession(
  version: string,
  date: string,
  index: number,
  data: { rpe?: number; bodyWeightKg?: number; notes?: string; wellness?: SessionWellness | null }
): Promise<void> {
  await api.patch(`/sessions/${version}/${date}/${index}/complete`, data)
}

export async function draftSessionNotes(
  version: string,
  date: string,
  index: number,
  data: { session: Session; answers: Record<string, unknown> }
): Promise<{ notes: string }> {
  const res = await api.post<ApiResponse<{ notes: string }>>(
    `/sessions/${version}/${date}/${index}/notes/draft`,
    data
  )
  return res.data.data
}

export interface AutoRegulationResponse {
  status: 'needs_more_info' | 'denied' | 'ready'
  message: string
  follow_up_questions: string[]
  proposed_exercises: Exercise[] | null
  diff: string[]
  reasoning: string
  reasoning_note: string
}

export async function requestAutoRegulation(
  version: string,
  date: string,
  index: number,
  data: {
    session: Session
    exerciseIndex: number
    mode: 'change_exercise' | 'change_weight'
    toggles: Record<string, boolean>
    userMessage: string
    conversation: Array<{ role: 'user' | 'assistant'; content: string }>
  }
): Promise<AutoRegulationResponse> {
  const res = await api.post<ApiResponse<AutoRegulationResponse>>(
    `/sessions/${version}/${date}/${index}/autoregulation`,
    data
  )
  return res.data.data
}

export async function addExercise(
  version: string,
  date: string,
  index: number,
  exercise: Exercise
): Promise<void> {
  await api.post(`/sessions/${version}/${date}/${index}/exercise`, exercise)
}

export async function updateExerciseField(
  version: string,
  date: string,
  index: number,
  exerciseIndex: number,
  field: keyof Exercise,
  value: unknown
): Promise<void> {
  await api.patch(
    `/sessions/${version}/${date}/${index}/exercise/${exerciseIndex}`,
    { field, value }
  )
}

export async function removeExercise(
  version: string,
  date: string,
  index: number,
  exerciseIndex: number
): Promise<void> {
  await api.delete(`/sessions/${version}/${date}/${index}/exercise/${exerciseIndex}`)
}

// ─── Maxes ───────────────────────────────────────────────────────────────────

export async function fetchMaxes(version: string): Promise<{
  targets: { squat_kg: number; bench_kg: number; deadlift_kg: number; total_kg: number }
  history: MaxEntry[]
}> {
  const res = await api.get<
    ApiResponse<{
      targets: { squat_kg: number; bench_kg: number; deadlift_kg: number; total_kg: number }
      history: MaxEntry[]
    }>
  >(`/maxes/${version}`)
  return res.data.data
}

export async function updateTargetMaxes(
  version: string,
  maxes: { squat_kg: number; bench_kg: number; deadlift_kg: number }
): Promise<void> {
  await api.put(`/maxes/${version}`, maxes)
}

export async function updateBodyWeight(
  version: string,
  weightKg: number
): Promise<void> {
  await api.put(`/programs/${version}/body-weight`, { weightKg })
}

export async function updatePhases(
  version: string,
  phases: Phase[],
  block?: string
): Promise<void> {
  const body: { phases: Phase[]; block?: string } = { phases }
  if (block !== undefined) body.block = block
  await api.put(`/programs/${version}/phases`, body)
}

export async function addMaxEntry(
  version: string,
  entry: MaxEntry
): Promise<void> {
  await api.post(`/maxes/${version}/history`, entry)
}

// ─── Weight Log ──────────────────────────────────────────────────────────────

export async function fetchWeightLog(
  version: string
): Promise<WeightEntry[]> {
  const res = await api.get<ApiResponse<{ entries: WeightEntry[] }>>(
    `/weight/${version}`
  )
  return res.data.data.entries
}

export async function addWeightEntry(
  version: string,
  entry: WeightEntry
): Promise<void> {
  await api.post(`/weight/${version}`, entry)
}

export async function removeWeightEntry(
  version: string,
  date: string
): Promise<void> {
  await api.delete(`/weight/${version}/${date}`)
}

// ─── Exercises (Glossary) ────────────────────────────────────────────────────

export async function fetchGlossary(): Promise<GlossaryExercise[]> {
  const res = await api.get<ApiResponse<GlossaryExercise[]>>('/exercises')
  return res.data.data
}

export async function searchExercises(query: string): Promise<GlossaryExercise[]> {
  const res = await api.get<ApiResponse<GlossaryExercise[]>>(
    `/exercises/search?q=${encodeURIComponent(query)}`
  )
  return res.data.data
}

export async function upsertExercise(
  exercise: GlossaryExercise
): Promise<void> {
  if (exercise.id) {
    await api.put(`/exercises/${exercise.id}`, exercise)
  } else {
    await api.post('/exercises', exercise)
  }
}

export async function deleteExercise(exerciseId: string): Promise<void> {
  await api.delete(`/exercises/${exerciseId}`)
}

// ─── Supplements ──────────────────────────────────────────────────────────────

export async function fetchSupplementPhases(
  version: string
): Promise<SupplementPhase[]> {
  const res = await api.get<ApiResponse<SupplementPhase[]>>(`/supplements/${version}`)
  return res.data.data
}

export async function updateSupplementPhases(
  version: string,
  phases: SupplementPhase[]
): Promise<void> {
  await api.put(`/supplements/${version}`, { phases })
}

// ─── Diet Notes ───────────────────────────────────────────────────────────────

export async function fetchDietNotes(version: string): Promise<DietNote[]> {
  const res = await api.get<ApiResponse<DietNote[]>>(`/diet-notes/${version}`)
  return res.data.data
}

export async function updateDietNotes(
  version: string,
  dietNotes: DietNote[]
): Promise<void> {
  await api.put(`/diet-notes/${version}`, { dietNotes })
}

// ─── Block Notes ───────────────────────────────────────────────────────────────

export async function fetchBlockNotes(version: string): Promise<BlockNote[]> {
  const res = await api.get<ApiResponse<BlockNote[]>>(`/block-notes/${version}`)
  return res.data.data
}

export async function updateBlockNotes(
  version: string,
  blockNotes: BlockNote[]
): Promise<void> {
  await api.put(`/block-notes/${version}`, { blockNotes })
}

// ─── Goals ───────────────────────────────────────────────────────────────────

export async function fetchGoals(version: string): Promise<AthleteGoal[]> {
  const res = await api.get<ApiResponse<AthleteGoal[]>>(`/goals/${version}`)
  return res.data.data
}

export async function updateGoals(
  version: string,
  goals: AthleteGoal[],
): Promise<void> {
  await api.put(`/goals/${version}`, { goals })
}

// ─── Federations ─────────────────────────────────────────────────────────────

export async function fetchFederationLibrary(): Promise<FederationLibrary> {
  const res = await api.get<ApiResponse<FederationLibrary>>('/federations')
  return res.data.data
}

export async function updateFederationLibrary(
  library: FederationLibrary,
): Promise<FederationLibrary> {
  const res = await api.put<ApiResponse<FederationLibrary>>('/federations', { library })
  return res.data.data
}

// ─── Competitions ─────────────────────────────────────────────────────────────

export async function fetchCompetitions(version: string): Promise<Competition[]> {
  const res = await api.get<ApiResponse<Competition[]>>(`/competitions/${version}`)
  return res.data.data
}

export async function updateCompetitions(
  version: string,
  competitions: Competition[]
): Promise<void> {
  await api.put(`/competitions/${version}`, { competitions })
}

export async function migrateLastComp(version: string): Promise<Competition[]> {
  const res = await api.post<ApiResponse<Competition[]>>(`/competitions/${version}/migrate`)
  return res.data.data
}

export async function completeCompetition(
  version: string,
  date: string,
  results: LiftResults,
  bodyWeightKg: number,
  postMeetReport?: PostMeetReport
): Promise<Competition> {
  const res = await api.patch<ApiResponse<Competition>>(
    `/competitions/${version}/${date}/complete`,
    { results, bodyWeightKg, postMeetReport }
  )
  return res.data.data
}

// ─── Videos ───────────────────────────────────────────────────────────────────

export async function getVideos(
  version: string = 'current',
  exercise?: string,
  sort: 'newest' | 'oldest' = 'newest'
): Promise<{ videos: VideoLibraryItem[]; exercises: string[] }> {
  const params = new URLSearchParams()
  if (exercise) params.set('exercise', exercise)
  params.set('sort', sort)
  const res = await api.get<ApiResponse<{ videos: VideoLibraryItem[]; exercises: string[] }>>(
    `/videos?version=${version}&${params}`
  )
  return res.data.data
}

export async function removeSessionVideo(
  version: string,
  sessionDate: string,
  videoId: string
): Promise<void> {
  await api.delete(`/videos/${version}/${sessionDate}/${videoId}`)
}

// ─── Lift Profiles ────────────────────────────────────────────────────────────

export interface LiftProfileReview {
  lift: LiftProfile['lift']
  completeness_score: number
  ready_for_coefficient: boolean
  score_explanation?: string
  score_breakdown?: Record<string, {
    score: number
    max: number
    notes?: string[]
  }>
  missing_details: string[]
  suggestions: string[]
  error?: string
}

export type LiftProfileRewriteEstimate = LiftProfile & {
  stimulus_coefficient: number
  stimulus_coefficient_confidence: 'low' | 'medium' | 'high'
  stimulus_coefficient_reasoning: string
  stimulus_coefficient_updated_at: string
  missing_details?: string[]
  error?: string
}

export type LiftProfileRewrite = Pick<
  LiftProfile,
  'lift' | 'style_notes' | 'sticking_points' | 'primary_muscle' | 'volume_tolerance'
> & {
  missing_details?: string[]
  error?: string
}

export type LiftProfileStimulusEstimate = Pick<LiftProfile, 'lift'> & {
  stimulus_coefficient: number
  stimulus_coefficient_confidence: 'low' | 'medium' | 'high'
  stimulus_coefficient_reasoning: string
  stimulus_coefficient_updated_at: string
  ready_for_estimate?: boolean
  estimate_ready_threshold?: number
  completeness_score?: number
  missing_details?: string[]
  error?: string
}

function normalizeLiftProfileReview(
  data: Partial<LiftProfileReview> | null | undefined,
  profile: LiftProfile
): LiftProfileReview {
  if (!data) throw new Error('Empty lift profile review response')
  if (data?.error) throw new Error(String(data.error))
  return {
    lift: data?.lift ?? profile.lift,
    completeness_score: typeof data?.completeness_score === 'number' ? data.completeness_score : 0,
    ready_for_coefficient: Boolean(data?.ready_for_coefficient),
    score_explanation: data?.score_explanation,
    score_breakdown: data?.score_breakdown,
    missing_details: Array.isArray(data?.missing_details) ? data.missing_details : [],
    suggestions: Array.isArray(data?.suggestions) ? data.suggestions : [],
  }
}

export async function updateLiftProfiles(
  version: string,
  liftProfiles: LiftProfile[]
): Promise<void> {
  await api.put(`/programs/${version}/lift-profiles`, { liftProfiles })
}

export async function reviewLiftProfile(profile: LiftProfile): Promise<LiftProfileReview> {
  const res = await api.post<ApiResponse<LiftProfileReview>>(
    '/analytics/lift-profile/review',
    { profile }
  )
  if (res.data.error) throw new Error(String(res.data.error))
  return normalizeLiftProfileReview(res.data.data, profile)
}

export async function rewriteLiftProfile(profile: LiftProfile): Promise<LiftProfileRewrite> {
  const res = await api.post<ApiResponse<LiftProfileRewrite>>(
    '/analytics/lift-profile/rewrite',
    { profile }
  )
  if (res.data.error) throw new Error(String(res.data.error))
  if (res.data.data?.error) throw new Error(String(res.data.data.error))
  return res.data.data
}

export async function estimateLiftProfileStimulus(
  profile: LiftProfile
): Promise<LiftProfileStimulusEstimate> {
  const res = await api.post<ApiResponse<LiftProfileStimulusEstimate>>(
    '/analytics/lift-profile/estimate-stimulus',
    { profile }
  )
  if (res.data.error) throw new Error(String(res.data.error))
  if (res.data.data?.error) throw new Error(String(res.data.data.error))
  return res.data.data
}

export async function rewriteAndEstimateLiftProfile(
  profile: LiftProfile
): Promise<LiftProfileRewriteEstimate> {
  const res = await api.post<ApiResponse<LiftProfileRewriteEstimate>>(
    '/analytics/lift-profile/rewrite-and-estimate',
    { profile }
  )
  if (res.data.error) throw new Error(String(res.data.error))
  if (res.data.data?.error) throw new Error(String(res.data.data.error))
  return res.data.data
}

// ─── Fatigue Profile ──────────────────────────────────────────────────────────

export async function estimateFatigueProfile(exercise: {
  name: string
  category?: string
  equipment?: string
  primary_muscles?: string[]
  secondary_muscles?: string[]
  tertiary_muscles?: string[]
  cues?: string[]
  notes?: string
}): Promise<FatigueProfile & { reasoning: string }> {
  const res = await api.post<ApiResponse<FatigueProfile & { reasoning: string }>>(
    '/analytics/fatigue-profile/estimate',
    exercise
  )
  return res.data.data
}

export async function estimateMuscleGroups(exercise: {
  name: string
  category?: string
  equipment?: string
  cues?: string[]
  notes?: string
  primary_muscles?: string[]
  secondary_muscles?: string[]
  tertiary_muscles?: string[]
  lift_profiles?: LiftProfile[]
}): Promise<{
  primary_muscles: string[]
  secondary_muscles: string[]
  tertiary_muscles: string[]
  reasoning: string
}> {
  const { lift_profiles, ...exercisePayload } = exercise
  const res = await api.post<ApiResponse<{
    primary_muscles: string[]
    secondary_muscles: string[]
    tertiary_muscles: string[]
    reasoning: string
  }>>('/analytics/muscle-groups/estimate', {
    exercise: exercisePayload,
    lift_profiles,
  })
  return res.data.data
}

export async function fetchE1rmMultiplierSuggestions(): Promise<Record<string, {
  lift: string
  suggested_multiplier: number
  current_multiplier: number
  difference: number
  basis: string
  sample_size: number
} | null>> {
  const res = await api.post<ApiResponse<any>>('/analytics/e1rm-multiplier/suggestions')
  return res.data.data
}

// ─── Import ──────────────────────────────────────────────────────────────────

export async function uploadImport(file: File): Promise<{ 
  import_id: string; 
  classification: ImportType | 'ambiguous'; 
  warnings: any[];
  parse_notes: string;
}> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post('/import/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return res.data
}

export async function fetchPendingImport(importId: string): Promise<ImportPending> {
  const res = await api.get(`/import/${importId}`)
  return res.data
}

export async function listPendingImports(type?: ImportType): Promise<ImportPending[]> {
  const res = await api.get('/import/pending', { params: { type } })
  return res.data
}

export async function applyImport(importId: string, body: {
  merge_strategy: MergeStrategy;
  conflict_resolutions?: ConflictResolution[];
  start_date?: string;
  classification_override?: ImportType;
  glossary_overrides?: Record<string, string>;
  confirmed_auto_adds?: Array<Partial<GlossaryExercise>>;
}): Promise<any> {
  const res = await api.post(`/import/${importId}/apply`, body)
  return res.data
}

export async function rejectImport(importId: string, reason?: string): Promise<void> {
  await api.post(`/import/${importId}/reject`, { reason })
}

// ─── Templates ────────────────────────────────────────────────────────────────

export async function fetchTemplates(includeArchived: boolean = false): Promise<TemplateListEntry[]> {
  const res = await api.get('/templates', { params: { includeArchived } })
  return res.data
}

export async function fetchTemplate(sk: string): Promise<Template> {
  const res = await api.get(templatePath(sk))
  return { ...res.data, sk: res.data?.sk ?? sk }
}

export async function createTemplateFromBlock(name: string, program_sk?: string): Promise<{ sk: string }> {
  const res = await api.post('/templates', { name, program_sk })
  return res.data
}

export async function copyTemplate(sk: string, newName: string): Promise<{ sk: string }> {
  const res = await api.post(templatePath(sk, '/copy'), { new_name: newName })
  return res.data
}

export async function archiveTemplate(sk: string): Promise<void> {
  await api.patch(templatePath(sk, '/archive'))
}

export async function unarchiveTemplate(sk: string): Promise<void> {
  await api.patch(templatePath(sk, '/unarchive'))
}

export async function evaluateTemplate(sk: string): Promise<AiTemplateEvaluation> {
  const res = await api.post(templatePath(sk, '/evaluate'))
  return res.data
}

export async function applyTemplate(sk: string, body: {
  target: string;
  start_date?: string;
  week_start_day: WeekStartDay;
}): Promise<any> {
  const res = await api.post(templatePath(sk, '/apply'), body)
  return res.data
}

export async function confirmApplyTemplate(sk: string, body: {
  backfilled_maxes?: Record<string, number>;
  start_date?: string;
  week_start_day: WeekStartDay;
  target?: string;
}): Promise<{ program_sk: string }> {
  const res = await api.post(templatePath(sk, '/apply/confirm'), body)
  return res.data
}

export async function createBlankTemplate(body: {
  name: string
  description?: string
  estimated_weeks?: number
  days_per_week?: number
}): Promise<{ sk: string }> {
  const res = await api.post('/templates/blank', body)
  return res.data
}

export async function updateTemplate(sk: string, template: Template): Promise<void> {
  await api.put(templatePath(sk), template)
}

// ─── Archive & e1RM ─────────────────────────────────────────────────────────

export async function archiveProgram(version: string): Promise<void> {
  await api.patch(`/programs/${version}/archive`)
}

export async function unarchiveProgram(version: string): Promise<void> {
  await api.patch(`/programs/${version}/unarchive`)
}

export async function archiveExercise(id: string): Promise<void> {
  await api.patch(`/exercises/${id}/archive`)
}

export async function unarchiveExercise(id: string): Promise<void> {
  await api.patch(`/exercises/${id}/unarchive`)
}

export async function setExerciseE1rm(id: string, value_kg: number, method: string = 'manual'): Promise<void> {
  await api.post(`/exercises/${id}/e1rm`, { value_kg, method })
}

export async function estimateExerciseE1rm(id: string): Promise<any> {
  const res = await api.post(`/exercises/${id}/estimate-e1rm`)
  return res.data.data
}

export async function estimateExerciseFatigue(id: string): Promise<any> {
  const res = await api.post(`/exercises/${id}/estimate-fatigue`)
  return res.data.data
}

export async function estimateExerciseMuscles(id: string): Promise<any> {
  const res = await api.post(`/exercises/${id}/estimate-muscles`)
  return res.data.data
}

// ─── Stats ───────────────────────────────────────────────────────────────────

export async function fetchStatCategories(): Promise<any> {
  const res = await api.get('/stats/categories')
  return res.data
}

export async function analyzeStats(payload: any): Promise<any> {
  const res = await api.post('/stats/analyze', payload)
  return res.data
}

export default api
