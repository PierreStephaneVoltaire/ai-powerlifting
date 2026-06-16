import { logger } from '../utils/logger'
import {
  BatchWriteCommand,
  DeleteCommand,
  GetCommand,
  PutCommand,
  QueryCommand,
} from '@aws-sdk/lib-dynamodb'
import { createHash } from 'crypto'
import { docClient, POWERLIFTING_GOALS_TABLE } from '../db/dynamo'
import type { AgeCategory, AthleteGoal, Competition, LiftResults, Program, Session, WeightEntry } from '@powerlifting/types'

const GOAL_TYPE_VALUES: ReadonlyArray<string> = [
  'hit_total',
  'qualify_for_federation',
  'peak_for_meet',
  'conservative_pr',
  'competition_exposure',
  'improve_dots',
  'improve_ipf_gl',
  'custom',
]

const GOAL_PRIORITY_VALUES: ReadonlyArray<string> = ['primary', 'secondary', 'optional']

const AGE_CATEGORY_VALUES: ReadonlyArray<AgeCategory> = [
  'open',
  'subjunior',
  'junior',
  'master1',
  'master2',
  'master3',
  'master4',
]

function newGoalId(): string {
  return `goal-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`
}

function normalizeGoalType(value: unknown): AthleteGoal['goal_type'] {
  return (GOAL_TYPE_VALUES as ReadonlyArray<string>).includes(String(value))
    ? (value as AthleteGoal['goal_type'])
    : 'custom'
}

function normalizeGoalPriority(value: unknown): AthleteGoal['priority'] {
  return (GOAL_PRIORITY_VALUES as ReadonlyArray<string>).includes(String(value))
    ? (value as AthleteGoal['priority'])
    : 'secondary'
}

function normalizeGoal(raw: unknown): AthleteGoal | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const id = typeof r.id === 'string' && r.id.length > 0 ? r.id : newGoalId()
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

export type DataQualitySeverity = 'info' | 'warning' | 'critical'

export interface DataQualityFlag {
  code: string
  label: string
  severity: DataQualitySeverity
}

export interface BlockCompetitionLink {
  name: string
  date: string
  status: string
  mapping: 'in_range' | 'within_30_days_after'
  distanceDays: number
  competition: Competition
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
  results: LiftResults | null
  dots: number | null
  ipfGl: number | null
  ipfGlMode: 'classic_powerlifting' | null
  projectedAtTMinus1w: LiftResults | null
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

export interface BlockAnalysisBundle<T = unknown> {
  schemaVersion: number
  generatedAt: string
  cached: boolean
  sourceFingerprint: string
  block: ProgramBlockIndexEntry
  weekly: T
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
  competitions: Array<{
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
  goals: Array<{
    id: string
    title: string
    goalType: string
    priority: string
    targetTotalKg?: number | null
    targetDots?: number | null
    targetIpfGl?: number | null
    targetDate?: string
    targetCompetitionIds?: string[]
  }>
}

export interface BlockComparisonContext {
  sessions: Session[]
  weightLog: WeightEntry[]
  competitions: Competition[]
  goals: AthleteGoal[]
  sex: 'male' | 'female'
  fallbackBodyweightKg: number | null
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
  exerciseRoi: Array<{
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
  correlationFindings: Array<{
    blockKey: string
    label: string
    exercise: string
    lift: string
    direction: 'positive' | 'negative' | 'unclear'
    strength: 'weak' | 'moderate' | 'strong'
    reasoning: string
    caveat: string
  }>
  patternSignals: Array<{
    kind: 'roi' | 'training_response' | 'fatigue' | 'compliance' | 'data_quality'
    finding: string
    evidence: string
    confidence: 'low' | 'medium' | 'high'
  }>
  liftDoseResponse: Array<{
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
  trainingDayResponse: Array<{
    blockKey: string
    label: string
    completedWeeks: number
    totalTrainingDays: number
    avgTrainingDaysPerWeek: number | null
    strengthDeltaKg: number | null
    compliancePct: number | null
  }>
  trendSeries: Array<{
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

export interface AiBlockComparisonResult {
  schemaVersion: number
  generatedAt: string
  cached: boolean
  selectedBlockKeys: string[]
  sourceFingerprint: string
  report: Record<string, unknown>
  deterministic: BlockComparisonResult
}

const CACHE_SCHEMA_VERSION = 1
const ANALYSIS_CACHE_TABLE = process.env.ANALYSIS_CACHE_TABLE_NAME || 'if-powerlifting-analysis-cache'
const MAX_SHARD_CHARS = 350_000
// Past blocks are permanent (no TTL). Current block uses 7 days.
const CURRENT_BLOCK_TTL_DAYS = 7
const DEFAULT_BLOCK = 'current'

type InvokeTool = (toolName: string, args: Record<string, unknown>) => Promise<unknown>

const RPE_TABLE_PRIMARY = new Map<string, number>([
  ['1-10', 1.000], ['2-10', 0.960], ['3-10', 0.930], ['4-10', 0.900], ['5-10', 0.880], ['6-10', 0.860],
  ['1-9', 1.000], ['2-9', 0.940], ['3-9', 0.900], ['4-9', 0.870], ['5-9', 0.845], ['6-9', 0.825],
  ['1-8', 1.000], ['2-8', 0.920], ['3-8', 0.875], ['4-8', 0.845], ['5-8', 0.815], ['6-8', 0.795],
  ['1-7', 1.000], ['2-7', 0.900], ['3-7', 0.850], ['4-7', 0.820], ['5-7', 0.795], ['6-7', 0.775],
  ['1-6', 1.000], ['2-6', 0.880], ['3-6', 0.830], ['4-6', 0.800], ['5-6', 0.775], ['6-6', 0.755],
])

const CONSERVATIVE_REP_PCT: Record<number, number> = {
  1: 1.000,
  2: 0.955,
  3: 0.925,
  4: 0.898,
  5: 0.875,
}

const DOTS_COEFFICIENTS = {
  male: { a: -307.75076, b: 24.0900756, c: -0.1918759221, d: 0.0007391293, e: -0.000001093 },
  female: { a: -57.96288, b: 13.6175032, c: -0.1126655495, d: 0.0005158568, e: -0.0000010706 },
}

const IPF_GL_COEFFICIENTS = {
  classic_powerlifting: {
    male: { a: 1199.72839, b: 1025.18162, c: 0.00921 },
    female: { a: 610.32796, b: 1045.59282, c: 0.03048 },
  },
}

function normalizeBlock(block?: string | null): string {
  const value = typeof block === 'string' ? block.trim() : ''
  return value || DEFAULT_BLOCK
}

function blockKeyFor(block: string): string {
  if (block === DEFAULT_BLOCK) return DEFAULT_BLOCK
  return `block_${createHash('sha1').update(block).digest('hex').slice(0, 14)}`
}

function cachePk(userPk: string): string {
  return `analysis#${userPk}`
}

function blockAnalysisSk(blockKey: string): string {
  return `block_analysis#v${CACHE_SCHEMA_VERSION}#${blockKey}`
}

function blockProgramEvaluationSk(blockKey: string): string {
  return `block_program_eval#v${CACHE_SCHEMA_VERSION}#${blockKey}`
}

function blockCorrelationSk(blockKey: string): string {
  return `block_correlation#v${CACHE_SCHEMA_VERSION}#${blockKey}`
}

function blockAiComparisonSk(fingerprint: string): string {
  return `block_compare_ai#v${CACHE_SCHEMA_VERSION}#${fingerprint.slice(0, 40)}`
}

function partSk(baseSk: string, index: number): string {
  return `${baseSk}#part#${String(index).padStart(3, '0')}`
}

function expiresAt(isCurrent: boolean): number | undefined {
  if (!isCurrent) return undefined
  return Math.floor(Date.now() / 1000) + CURRENT_BLOCK_TTL_DAYS * 24 * 60 * 60
}

function encodePayload(bundle: BlockAnalysisBundle): string {
  return JSON.stringify({ ...bundle, cached: false })
}

function decodePayload(payload: string): BlockAnalysisBundle {
  return JSON.parse(payload) as BlockAnalysisBundle
}

function encodeJsonPayload(value: unknown): string {
  return JSON.stringify(value)
}

function decodeJsonPayload<T>(payload: string): T {
  return JSON.parse(payload) as T
}

function chunkString(value: string, chunkSize: number): string[] {
  const chunks: string[] = []
  for (let index = 0; index < value.length; index += chunkSize) {
    chunks.push(value.slice(index, index + chunkSize))
  }
  return chunks
}
async function batchDelete(tableName: string, keys: Array<{ pk: string; sk: string }>): Promise<void> {
  for (let index = 0; index < keys.length; index += 25) {
    const batch = keys.slice(index, index + 25)
    if (!batch.length) continue
    await docClient.send(new BatchWriteCommand({
      RequestItems: {
        [tableName]: batch.map((Key) => ({ DeleteRequest: { Key } })),
      },
    }))
  }
}

async function deleteBundleObject(pk: string, sk: string): Promise<void> {
  await docClient.send(new DeleteCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Key: { pk, sk },
  }))

  const partKeys: Array<{ pk: string; sk: string }> = []
  let ExclusiveStartKey: Record<string, unknown> | undefined
  do {
    const response = await docClient.send(new QueryCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: {
        ':pk': pk,
        ':prefix': `${sk}#part#`,
      },
      ProjectionExpression: 'pk, sk',
      ExclusiveStartKey,
    }))
    for (const item of response.Items || []) {
      if (typeof item.pk === 'string' && typeof item.sk === 'string') {
        partKeys.push({ pk: item.pk, sk: item.sk })
      }
    }
    ExclusiveStartKey = response.LastEvaluatedKey
  } while (ExclusiveStartKey)

  await batchDelete(ANALYSIS_CACHE_TABLE, partKeys)
}

function parseDate(value?: string | null): Date | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const date = new Date(`${value}T00:00:00.000Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date.getTime())
  next.setUTCDate(next.getUTCDate() + days)
  return next
}

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / (24 * 60 * 60 * 1000))
}

function isCompletedSession(session: Session): boolean {
  return Boolean(session.completed || session.status === 'logged' || session.status === 'completed')
}

function hasResults(results?: LiftResults | null): results is LiftResults {
  return Boolean(results && Number(results.total_kg || 0) > 0)
}

function totalFromStrength(strength: Omit<BlockStrengthSummary, 'total'>): number | null {
  const squat = strength.squat ?? 0
  const bench = strength.bench ?? 0
  const deadlift = strength.deadlift ?? 0
  const total = squat + bench + deadlift
  return total > 0 ? Number(total.toFixed(1)) : null
}

function roundOrNull(value: number | null | undefined, digits = 1): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function programWeightLog(program: Program): WeightEntry[] {
  const entries = (program as Program & { weight_log?: WeightEntry[] }).weight_log
  return Array.isArray(entries) ? entries : []
}

function blockWeightLog(program: Program, startDate: string, endDate: string): WeightEntry[] {
  return programWeightLog(program)
    .filter((entry) =>
      typeof entry.date === 'string' &&
      typeof entry.kg === 'number' &&
      Number.isFinite(entry.kg) &&
      entry.kg > 0 &&
      entry.date >= startDate &&
      entry.date <= endDate,
    )
    .sort((a, b) => a.date.localeCompare(b.date))
}

function sourceHash(value: unknown): string {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex')
}

function phaseBlock(phase: { block?: string | null }): string {
  return normalizeBlock(phase.block)
}

function blockSessions(program: Program, block: string): Session[] {
  return (program.sessions ?? []).filter((session) => normalizeBlock(session.block) === block)
}

function analysisScopedCurrentEntry(program: Program, entry: ProgramBlockIndexEntry): ProgramBlockIndexEntry {
  if (!entry.isCurrent) return entry

  const today = isoDate(new Date())
  const allSessions = blockSessions(program, entry.block).sort((a, b) => a.date.localeCompare(b.date))
  const datedSessions = allSessions.filter((session) => parseDate(session.date))
  const inScope = datedSessions.filter((session) => session.date <= today)
  const completed = datedSessions.filter(isCompletedSession)
  const scopedSessions = inScope.length ? inScope : completed
  const endDate = scopedSessions[scopedSessions.length - 1]?.date ?? (entry.startDate <= today ? today : entry.startDate)
  const weekNumbers = scopedSessions
    .map((session) => Number(session.week_number || 0))
    .filter((week) => week > 0)
  const weekStart = weekNumbers.length ? Math.min(...weekNumbers) : entry.weekStart
  const weekEnd = weekNumbers.length ? Math.max(...weekNumbers) : weekStart
  const phases = blockPhases(program, entry.block)
  const scopedCompetitions: Competition[] = []
  const scopedGoals: AthleteGoal[] = []
  const sourceFingerprint = blockSourceFingerprint(program, entry.block, scopedSessions, phases, scopedCompetitions, scopedGoals)
  const dataQualityFlags = buildDataQualityFlags(program, scopedSessions, entry.startDate, endDate, null, entry.blockKey)

  return {
    ...entry,
    endDate,
    weekStart,
    weekEnd,
    weekCount: Math.max(1, weekEnd - weekStart + 1),
    completedSessions: scopedSessions.filter(isCompletedSession).length,
    plannedSessions: scopedSessions.filter((session) => !isCompletedSession(session) && session.status !== 'skipped').length,
    totalSessions: scopedSessions.length,
    linkedCompetition: null,
    trainingOnly: true,
    comparisonEligible: false,
    sourceFingerprint,
    dataQualityFlags,
  }
}

export function analysisScopedBlockEntry(program: Program, entry: ProgramBlockIndexEntry): ProgramBlockIndexEntry {
  return entry.isCurrent ? analysisScopedCurrentEntry(program, entry) : entry
}

function blockPhases(program: Program, block: string) {
  return (program.phases ?? []).filter((phase) => phaseBlock(phase) === block)
}

function blockDietNotes(program: Program, startDate: string, endDate: string) {
  return (program.diet_notes ?? []).filter((note) => note.date >= startDate && note.date <= endDate)
}

function blockProgramNotes(program: Program, startDate: string, endDate: string) {
  return (program.meta?.block_notes ?? [])
    .filter((note) => {
      const noteDate = note.date || note.updated_at?.slice(0, 10) || ''
      return noteDate >= startDate && noteDate <= endDate
    })
    .map((note) => ({
      ...note,
      date: note.date || note.updated_at?.slice(0, 10) || startDate,
    }))
    .sort((a, b) => a.date.localeCompare(b.date))
}

function blockProjectionReferenceDate(entry: ProgramBlockIndexEntry): string {
  const competitionDate = parseDate(entry.linkedCompetition?.date ?? null)
  if (!competitionDate) return entry.endDate
  const dayBeforeCompetition = isoDate(addDays(competitionDate, -1))
  return entry.endDate && entry.endDate < dayBeforeCompetition ? entry.endDate : dayBeforeCompetition
}

function goalTargetCompetitionDates(goal: AthleteGoal): string[] {
  const dates = new Set<string>()
  if (Array.isArray(goal.target_competition_ids)) {
    for (const id of goal.target_competition_ids) {
      if (typeof id === 'string' && id.trim()) dates.add(id.trim())
    }
  }
  if (typeof goal.target_date === 'string' && goal.target_date.trim()) {
    dates.add(goal.target_date.trim())
  }
  return [...dates]
}

export async function loadGoals(pk: string): Promise<AthleteGoal[]> {
  const items: Record<string, unknown>[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new QueryCommand({
      TableName: POWERLIFTING_GOALS_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: { ':pk': pk, ':prefix': 'GOAL#' },
      ExclusiveStartKey: lastKey,
    }))
    for (const it of resp.Items ?? []) items.push(it as Record<string, unknown>)
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)
  return items
    .map((it) => {
      const { sk: _sk, pk: _pk, created_at: _c, updated_at: _u, target_competition_ids: _t, ...rest } = it as Record<string, unknown>
      return normalizeGoal(rest)
    })
    .filter((g): g is AthleteGoal => g !== null)
}

function goalsForCompetitions(goals: AthleteGoal[], competitions: Competition[]): AthleteGoal[] {
  const competitionDates = new Set(
    competitions
      .map((competition) => competition.date)
      .filter((date): date is string => typeof date === 'string' && date.trim().length > 0),
  )
  const competitionNames = new Set(
    competitions
      .map((competition) => competition.name)
      .filter((name): name is string => typeof name === 'string' && name.trim().length > 0),
  )
  if (!competitionDates.size && !competitionNames.size) return goals
  return goals.filter((goal) => {
    if (goal.target_competition_ids?.length) {
      return goal.target_competition_ids.some((id) => {
        if (typeof id !== 'string') return false
        return competitionDates.has(id) || competitionNames.has(id)
      })
    }
    const dates = goalTargetCompetitionDates(goal)
    if (dates.length) {
      return dates.some((date) => competitionDates.has(date))
    }
    if (goal.target_date && competitionDates.has(goal.target_date)) return true
    return false
  })
}

function blockCompetitionWindow(
  program: Program,
  startDate: string,
  endDate: string,
  linkedCompetition: BlockCompetitionLink | null,
): Competition[] {
  const start = parseDate(startDate)
  const end = parseDate(linkedCompetition?.date ?? endDate)
  const competitionsByKey = new Map<string, Competition>()

  if (start && end) {
    for (const competition of program.competitions ?? []) {
      const competitionDate = parseDate(competition.date)
      if (!competitionDate || competitionDate < start || competitionDate > end) continue
      competitionsByKey.set(`${competition.date}:${competition.name}`, competition)
    }
  }

  if (linkedCompetition) {
    competitionsByKey.set(`${linkedCompetition.competition.date}:${linkedCompetition.competition.name}`, linkedCompetition.competition)
  }

  return [...competitionsByKey.values()].sort((a, b) => a.date.localeCompare(b.date))
}

function firstNumericGoalTarget(goals: AthleteGoal[], field: keyof Pick<AthleteGoal, 'target_total_kg' | 'target_dots' | 'target_ipf_gl'>): number | undefined {
  for (const goal of goals) {
    const value = goal[field]
    if (typeof value === 'number' && Number.isFinite(value) && value > 0) return value
  }
  return undefined
}

function blockScopedMeta(
  program: Program,
  entry: ProgramBlockIndexEntry,
  analysisEndDate: string,
  competitions: Competition[],
  goals: AthleteGoal[],
): Program['meta'] {
  const primaryCompetition = competitions.find((competition) => competition.date === entry.linkedCompetition?.date) ?? competitions[0]
  const meta: Record<string, unknown> = {
    ...program.meta,
    program_start: entry.startDate || program.meta.program_start,
    comp_date: primaryCompetition?.date ?? '',
    current_body_weight_kg: primaryCompetition?.body_weight_kg ?? program.meta.current_body_weight_kg,
    weight_class_kg: primaryCompetition?.weight_class_kg ?? program.meta.weight_class_kg,
  }

  if (!entry.isCurrent) {
    const targets = primaryCompetition?.targets
    if (targets) {
      meta.target_squat_kg = targets.squat_kg
      meta.target_bench_kg = targets.bench_kg
      meta.target_dl_kg = targets.deadlift_kg
      meta.target_total_kg = targets.total_kg
    } else {
      delete meta.target_squat_kg
      delete meta.target_bench_kg
      delete meta.target_dl_kg
      const goalTargetTotal = firstNumericGoalTarget(goals, 'target_total_kg')
      if (goalTargetTotal) meta.target_total_kg = goalTargetTotal
      else delete meta.target_total_kg
    }
  }

  return meta as unknown as Program['meta']
}

function blockStartMaxes(program: Program, blockKey: string): BlockStartMaxEntry | null {
  const startMaxes = (program.meta as { block_start_maxes?: Record<string, BlockStartMaxEntry> })?.block_start_maxes
  const entry = startMaxes?.[blockKey]
  if (!entry || typeof entry !== 'object') return null
  const squat = typeof entry.squat_kg === 'number' ? entry.squat_kg : null
  const bench = typeof entry.bench_kg === 'number' ? entry.bench_kg : null
  const deadlift = typeof entry.deadlift_kg === 'number' ? entry.deadlift_kg : null
  return {
    squat_kg: squat,
    bench_kg: bench,
    deadlift_kg: deadlift,
    total_kg: typeof entry.total_kg === 'number' ? entry.total_kg : totalFromStrength({ squat, bench, deadlift }),
    source: 'manual',
    updated_at: typeof entry.updated_at === 'string' ? entry.updated_at : '',
  }
}

function blockSourceFingerprint(
  program: Program,
  block: string,
  sessions: Session[],
  phases: Program['phases'],
  competitions: Competition[],
  goals: AthleteGoal[],
): string {
  const dated = sessions
    .map((session) => ({
      id: session.id ?? null,
      date: session.date,
      week: session.week,
      week_number: session.week_number,
      block: normalizeBlock(session.block),
      status: session.status ?? null,
      completed: Boolean(session.completed),
      session_rpe: session.session_rpe ?? null,
      body_weight_kg: session.body_weight_kg ?? null,
      wellness: session.wellness ?? null,
      exercises: session.exercises ?? [],
      planned_exercises: session.planned_exercises ?? [],
    }))
    .sort((a, b) => `${a.date}:${a.id ?? ''}`.localeCompare(`${b.date}:${b.id ?? ''}`))

  const dates = dated.map((session) => session.date).filter(Boolean)
  const startDate = dates[0] ?? ''
  const endDate = dates[dates.length - 1] ?? ''

  return sourceHash({
    block,
    block_start_maxes: blockStartMaxes(program, blockKeyFor(block)),
    meta: {
      sex: program.meta?.sex ?? null,
      manual_maxes: program.meta?.manual_maxes ?? null,
      current_body_weight_kg: program.meta?.current_body_weight_kg ?? null,
      target_squat_kg: program.meta?.target_squat_kg ?? null,
      target_bench_kg: program.meta?.target_bench_kg ?? null,
      target_dl_kg: program.meta?.target_dl_kg ?? null,
      target_total_kg: program.meta?.target_total_kg ?? null,
    },
    competitions,
    goals,
    block_notes: startDate && endDate ? blockProgramNotes(program, startDate, endDate) : [],
    diet_notes: startDate && endDate ? blockDietNotes(program, startDate, endDate) : [],
    lift_profiles: program.lift_profiles ?? [],
    phases,
    sessions: dated,
  })
}

function linkCompetitionForBlock(block: { startDate: string; endDate: string }, competitions: Competition[]): BlockCompetitionLink | null {
  const start = parseDate(block.startDate)
  const end = parseDate(block.endDate)
  if (!start || !end) return null

  const completed = competitions
    .filter((competition) => competition.status === 'completed')
    .map((competition) => ({ competition, date: parseDate(competition.date) }))
    .filter((item): item is { competition: Competition; date: Date } => item.date !== null)

  const inRange = completed
    .filter((item) => item.date >= start && item.date <= end)
    .map((item) => ({
      ...item,
      mapping: 'in_range' as const,
      distanceDays: Math.abs(daysBetween(item.date, end)),
    }))

  const afterWindowEnd = addDays(end, 30)
  const after = completed
    .filter((item) => item.date > end && item.date <= afterWindowEnd)
    .map((item) => ({
      ...item,
      mapping: 'within_30_days_after' as const,
      distanceDays: daysBetween(end, item.date),
    }))

  const candidates = (inRange.length ? inRange : after).sort((a, b) => a.distanceDays - b.distanceDays)
  const match = candidates[0]
  if (!match) return null

  return {
    name: match.competition.name,
    date: match.competition.date,
    status: match.competition.status,
    mapping: match.mapping,
    distanceDays: match.distanceDays,
    competition: match.competition,
  }
}

function flag(code: string, label: string, severity: DataQualitySeverity = 'warning'): DataQualityFlag {
  return { code, label, severity }
}

function buildDataQualityFlags(
  program: Program,
  sessions: Session[],
  startDate: string,
  endDate: string,
  linkedCompetition: BlockCompetitionLink | null,
  blockKey: string,
): DataQualityFlag[] {
  const flags: DataQualityFlag[] = []
  const completed = sessions.filter(isCompletedSession)

  if (!linkedCompetition) {
    flags.push(flag('training_only', 'No completed competition linked', 'info'))
  } else {
    const competition = linkedCompetition.competition
    if (!hasResults(competition.results)) {
      flags.push(flag('missing_comp_results', 'Missing competition results', 'critical'))
    }
    if (!competition.body_weight_kg || competition.body_weight_kg <= 0) {
      flags.push(flag('missing_comp_bodyweight', 'Missing competition bodyweight'))
    }
    if (!competition.post_meet_report) {
      flags.push(flag('missing_post_meet_report', 'Missing post-meet report'))
    }
    if (!competition.projected_at_t_minus_1w && !competition.results?.projected_at_t_minus_1w) {
      flags.push(flag('missing_t_minus_1_projection', 'Missing T-minus-1 projection'))
    }
    if (!competition.results?.prr) {
      flags.push(flag('missing_prr', 'Missing PRR calibration'))
    }
  }

  const strength = estimateBlockStrength(sessions, startDate, endDate, blockStartMaxes(program, blockKey))
  if (strength.startStrength.squat === null || strength.startStrength.bench === null || strength.startStrength.deadlift === null) {
    flags.push(flag('missing_start_maxes', 'Missing complete start maxes'))
  }

  if (completed.length > 0) {
    const bodyweightEntries = completed.filter((session) => typeof session.body_weight_kg === 'number' && session.body_weight_kg > 0).length
    if (bodyweightEntries / completed.length < 0.5) {
      flags.push(flag('sparse_bodyweight', 'Sparse bodyweight logging', 'info'))
    }

    const wellnessEntries = completed.filter((session) => Boolean(session.wellness)).length
    if (wellnessEntries / completed.length < 0.5) {
      flags.push(flag('sparse_wellness', 'Sparse wellness logging', 'info'))
    }
  }

  if (!blockDietNotes(program, startDate, endDate).length) {
    flags.push(flag('sparse_diet', 'No diet notes inside block', 'info'))
  }

  const liftProfiles = program.lift_profiles ?? []
  const hasIncompleteLiftProfile = ['squat', 'bench', 'deadlift'].some((lift) => {
    const profile = liftProfiles.find((entry) => entry.lift === lift)
    return !profile || profile.stimulus_coefficient == null || !profile.primary_muscle || !profile.volume_tolerance
  })
  if (hasIncompleteLiftProfile) {
    flags.push(flag('missing_glossary_fatigue_metadata', 'Missing muscle or fatigue metadata', 'info'))
  }

  return flags
}

export async function listBlockCacheStatuses(userPk: string): Promise<Map<string, { sourceFingerprint?: string; generatedAt?: string }>> {
  const pk = cachePk(userPk)
  const statuses = new Map<string, { sourceFingerprint?: string; generatedAt?: string }>()
  try {
    let ExclusiveStartKey: Record<string, unknown> | undefined
    do {
      const response = await docClient.send(new QueryCommand({
        TableName: ANALYSIS_CACHE_TABLE,
        KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
        ExpressionAttributeValues: {
          ':pk': pk,
          ':prefix': `block_analysis#v${CACHE_SCHEMA_VERSION}#`,
        },
        ProjectionExpression: 'block_key, source_fingerprint, generated_at',
        ExclusiveStartKey,
      }))
      for (const item of response.Items || []) {
        if (typeof item.block_key === 'string') {
          statuses.set(item.block_key, {
            sourceFingerprint: typeof item.source_fingerprint === 'string' ? item.source_fingerprint : undefined,
            generatedAt: typeof item.generated_at === 'string' ? item.generated_at : undefined,
          })
        }
      }
      ExclusiveStartKey = response.LastEvaluatedKey
    } while (ExclusiveStartKey)
  } catch (error) {
    logger.warn({ err: error, userPk }, 'Block analysis cache status read failed')
  }
  return statuses
}

export async function listBlockProgramEvaluationCacheStatuses(userPk: string): Promise<Map<string, { sourceFingerprint?: string; generatedAt?: string }>> {
  const pk = cachePk(userPk)
  const statuses = new Map<string, { sourceFingerprint?: string; generatedAt?: string }>()
  try {
    let ExclusiveStartKey: Record<string, unknown> | undefined
    do {
      const response = await docClient.send(new QueryCommand({
        TableName: ANALYSIS_CACHE_TABLE,
        KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
        ExpressionAttributeValues: {
          ':pk': pk,
          ':prefix': `block_program_eval#v${CACHE_SCHEMA_VERSION}#`,
        },
        ProjectionExpression: 'block_key, source_fingerprint, generated_at',
        ExclusiveStartKey,
      }))
      for (const item of response.Items || []) {
        if (typeof item.block_key === 'string') {
          statuses.set(item.block_key, {
            sourceFingerprint: typeof item.source_fingerprint === 'string' ? item.source_fingerprint : undefined,
            generatedAt: typeof item.generated_at === 'string' ? item.generated_at : undefined,
          })
        }
      }
      ExclusiveStartKey = response.LastEvaluatedKey
    } while (ExclusiveStartKey)
  } catch (error) {
    logger.warn({ err: error, userPk }, 'Block program evaluation cache status read failed')
  }
  return statuses
}

export async function buildCurrentProgramBlockIndex(userPk: string, program: Program, allGoals?: AthleteGoal[]): Promise<ProgramBlockIndexEntry[]> {
  const cacheStatuses = await listBlockCacheStatuses(userPk)
  const evalCacheStatuses = await listBlockProgramEvaluationCacheStatuses(userPk)
  const goals = allGoals ?? (userPk ? await loadGoals(userPk) : [])
  const groups = new Map<string, Session[]>()
  for (const session of program.sessions ?? []) {
    const block = normalizeBlock(session.block)
    const existing = groups.get(block) ?? []
    existing.push(session)
    groups.set(block, existing)
  }

  const blocks = Array.from(groups.entries()).map(([block, sessions]) => {
    const sorted = [...sessions].sort((a, b) => a.date.localeCompare(b.date))
    const datedSessions = sorted.filter((session) => parseDate(session.date))
    const startDate = datedSessions[0]?.date ?? sorted[0]?.date ?? ''
    const endDate = datedSessions[datedSessions.length - 1]?.date ?? sorted[sorted.length - 1]?.date ?? ''
    const weekNumbers = sorted.map((session) => Number(session.week_number || 0)).filter((week) => week > 0)
    const weekStart = weekNumbers.length ? Math.min(...weekNumbers) : 1
    const weekEnd = weekNumbers.length ? Math.max(...weekNumbers) : weekStart
    const phases = blockPhases(program, block)
    const blockKey = blockKeyFor(block)
    const linkedCompetition = linkCompetitionForBlock({ startDate, endDate }, program.competitions ?? [])
    const scopedCompetitions = blockCompetitionWindow(program, startDate, endDate, linkedCompetition)
    const scopedGoals = goalsForCompetitions(goals, scopedCompetitions)
    const sourceFingerprint = blockSourceFingerprint(program, block, sorted, phases, scopedCompetitions, scopedGoals)
    const dataQualityFlags = buildDataQualityFlags(program, sorted, startDate, endDate, linkedCompetition, blockKey)
    const cacheStatus = cacheStatuses.get(blockKey)
    const evalCacheStatus = evalCacheStatuses.get(blockKey)
    const results = linkedCompetition?.competition.results

    const entry: ProgramBlockIndexEntry = {
      blockKey,
      block,
      label: block === DEFAULT_BLOCK ? 'Current' : block,
      isCurrent: block === DEFAULT_BLOCK,
      startDate,
      endDate,
      weekStart,
      weekEnd,
      weekCount: Math.max(1, weekEnd - weekStart + 1),
      completedSessions: sorted.filter(isCompletedSession).length,
      plannedSessions: sorted.filter((session) => !isCompletedSession(session) && session.status !== 'skipped').length,
      totalSessions: sorted.length,
      phases: phases.map((phase) => ({
        name: phase.name,
        intent: phase.intent,
        start_week: phase.start_week,
        end_week: phase.end_week,
      })),
      sourceFingerprint,
      linkedCompetition,
      trainingOnly: !linkedCompetition,
      comparisonEligible: Boolean(linkedCompetition && hasResults(results)),
      dataQualityFlags,
    }
    const cacheFingerprint = analysisScopedBlockEntry(program, entry).sourceFingerprint

    return {
      ...entry,
      cacheStatus: {
        cached: cacheStatus?.sourceFingerprint === cacheFingerprint || (block !== DEFAULT_BLOCK && Boolean(cacheStatus)),
        generatedAt: cacheStatus?.generatedAt,
      },
      programEvaluationCacheStatus: {
        cached: evalCacheStatus?.sourceFingerprint === cacheFingerprint || (block !== DEFAULT_BLOCK && Boolean(evalCacheStatus)),
        generatedAt: evalCacheStatus?.generatedAt,
      },
    } satisfies ProgramBlockIndexEntry
  })

  return blocks.sort((a, b) => {
    if (a.isCurrent !== b.isCurrent) return a.isCurrent ? 1 : -1
    return a.startDate.localeCompare(b.startDate)
  })
}

export async function getCachedBlockAnalysisBundle(
  userPk: string,
  blockKey: string,
  _expectedSourceFingerprint?: string,
  _options?: { allowStale?: boolean },
): Promise<BlockAnalysisBundle | null> {
  try {
    const pk = cachePk(userPk)
    
    // Find the latest version of this block analysis.
    // FilterExpression cannot reference primary key attributes (sk) — blockKey filtering
    // is done via the KeyConditionExpression prefix so DynamoDB uses the primary key index.
    const response = await docClient.send(new QueryCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: {
        ':pk': pk,
        ':prefix': `block_analysis#v${CACHE_SCHEMA_VERSION}#${blockKey}`,
      },
    }))

    const items = response.Items || []
    if (!items.length) return null

    // Sort by schema_version desc, then generated_at desc
    const sorted = items.sort((a, b) => {
      const vA = Number(a.schema_version || 0)
      const vB = Number(b.schema_version || 0)
      if (vA !== vB) return vB - vA
      return String(b.generated_at || '').localeCompare(String(a.generated_at || ''))
    })

    const item = sorted[0]
    const sk = item.sk as string

    // Support new plain-JSON payload and legacy gzip+base64 for backward compat
    let payloadStr = typeof item.payload === 'string' ? item.payload : ''
    const shardCount = Number(item.shard_count || 0)

    if (!payloadStr && shardCount > 0) {
      const parts = await Promise.all(
        Array.from({ length: shardCount }, async (_, index) => {
          const part = await docClient.send(new GetCommand({
            TableName: ANALYSIS_CACHE_TABLE,
            Key: { pk, sk: partSk(sk, index) },
          }))
          return String(part.Item?.payload ?? '')
        }),
      )
      payloadStr = parts.join('')
    }

    // Legacy: decode gzip+base64 if payload is absent but payload_gzip_b64 exists
    if (!payloadStr) {
      const legacyB64 = typeof item.payload_gzip_b64 === 'string' ? item.payload_gzip_b64 : ''
      if (legacyB64) {
        try {
          const { gunzipSync } = await import('zlib')
          payloadStr = gunzipSync(Buffer.from(legacyB64, 'base64')).toString('utf8')
        } catch {
          return null
        }
      }
    }

    if (!payloadStr) return null
    const bundle = decodePayload(payloadStr)
    if (bundle.block.blockKey !== blockKey) return null
    return { ...bundle, cached: true }
  } catch (error) {
    logger.warn({ err: error, userPk, blockKey }, 'Block analysis cache read failed')
    return null
  }
}

export async function putCachedBlockAnalysisBundle(userPk: string, bundle: BlockAnalysisBundle): Promise<void> {
  try {
    const pk = cachePk(userPk)
    const sk = blockAnalysisSk(bundle.block.blockKey)
    const encoded = encodePayload(bundle)
    const isCurrent = bundle.block.isCurrent
    const expiry = expiresAt(isCurrent)

    await deleteBundleObject(pk, sk)

    if (encoded.length <= MAX_SHARD_CHARS) {
      const item: Record<string, unknown> = {
        pk,
        sk,
        schema_version: CACHE_SCHEMA_VERSION,
        block_key: bundle.block.blockKey,
        block_label: bundle.block.label,
        source_fingerprint: bundle.sourceFingerprint,
        generated_at: bundle.generatedAt,
        payload: encoded,
      }
      if (expiry !== undefined) item.expires_at = expiry
      await docClient.send(new PutCommand({ TableName: ANALYSIS_CACHE_TABLE, Item: item }))
      return
    }

    const chunks = chunkString(encoded, MAX_SHARD_CHARS)
    const manifestItem: Record<string, unknown> = {
      pk,
      sk,
      schema_version: CACHE_SCHEMA_VERSION,
      block_key: bundle.block.blockKey,
      block_label: bundle.block.label,
      source_fingerprint: bundle.sourceFingerprint,
      generated_at: bundle.generatedAt,
      shard_count: chunks.length,
    }
    if (expiry !== undefined) manifestItem.expires_at = expiry
    await docClient.send(new PutCommand({ TableName: ANALYSIS_CACHE_TABLE, Item: manifestItem }))

    for (let index = 0; index < chunks.length; index += 25) {
      const batch = chunks.slice(index, index + 25)
      await docClient.send(new BatchWriteCommand({
        RequestItems: {
          [ANALYSIS_CACHE_TABLE]: batch.map((payload, batchIndex) => ({
            PutRequest: {
              Item: {
                pk,
                sk: partSk(sk, index + batchIndex),
                payload,
                ...(expiry !== undefined ? { expires_at: expiry } : {}),
              },
            },
          })),
        },
      }))
    }
  } catch (error) {
    logger.warn({ err: error, userPk, blockKey: bundle.block.blockKey }, 'Block analysis cache write failed')
  }
}

async function getCachedJsonPayload<T>(
  userPk: string,
  sk: string,
  expectedSourceFingerprint?: string,
  options?: { allowStale?: boolean },
): Promise<T | null> {
  try {
    const pk = cachePk(userPk)
    const response = await docClient.send(new GetCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      Key: { pk, sk },
    }))
    const item = response.Item
    if (!item) return null
    if (
      expectedSourceFingerprint
      && options?.allowStale !== true
      && item.source_fingerprint !== expectedSourceFingerprint
    ) {
      return null
    }

    // New plain JSON payload
    let payloadStr = typeof item.payload === 'string' ? item.payload : ''
    const shardCount = Number(item.shard_count || 0)

    if (!payloadStr && shardCount > 0) {
      const parts = await Promise.all(
        Array.from({ length: shardCount }, async (_, index) => {
          const part = await docClient.send(new GetCommand({
            TableName: ANALYSIS_CACHE_TABLE,
            Key: { pk, sk: partSk(sk, index) },
          }))
          return String(part.Item?.payload ?? '')
        }),
      )
      payloadStr = parts.join('')
    }

    // Legacy gzip fallback
    if (!payloadStr) {
      const legacyB64 = typeof item.payload_gzip_b64 === 'string' ? item.payload_gzip_b64 : ''
      if (legacyB64) {
        try {
          const { gunzipSync } = await import('zlib')
          payloadStr = gunzipSync(Buffer.from(legacyB64, 'base64')).toString('utf8')
        } catch {
          return null
        }
      }
    }

    return payloadStr ? decodeJsonPayload<T>(payloadStr) : null
  } catch (error) {
    logger.warn({ err: error, userPk, sk }, 'Block JSON cache read failed')
    return null
  }
}

export async function getCachedBlockProgramEvaluationReport(
  userPk: string,
  blockKey: string,
): Promise<Record<string, unknown> | null> {
  const cached = await getCachedJsonPayload<Record<string, unknown>>(
    userPk,
    blockProgramEvaluationSk(blockKey),
  )
  return cached ? { ...cached, cached: true } : null
}

export async function getCachedBlockCorrelationReport(
  userPk: string,
  blockKey: string,
): Promise<Record<string, unknown> | null> {
  const cached = await getCachedJsonPayload<Record<string, unknown>>(
    userPk,
    blockCorrelationSk(blockKey),
  )
  return cached ? { ...cached, cached: true } : null
}

async function putCachedJsonPayload(
  userPk: string,
  sk: string,
  payloadValue: unknown,
  metadata: {
    sourceFingerprint: string
    blockKey?: string
    blockLabel?: string
    isCurrent?: boolean
  },
): Promise<void> {
  try {
    const pk = cachePk(userPk)
    const encoded = encodeJsonPayload(payloadValue)
    const expiry = expiresAt(metadata.isCurrent ?? false)

    await deleteBundleObject(pk, sk)

    const baseItem: Record<string, unknown> = {
      pk,
      sk,
      schema_version: CACHE_SCHEMA_VERSION,
      source_fingerprint: metadata.sourceFingerprint,
      generated_at: new Date().toISOString(),
    }
    if (expiry !== undefined) baseItem.expires_at = expiry
    if (metadata.blockKey) baseItem.block_key = metadata.blockKey
    if (metadata.blockLabel) baseItem.block_label = metadata.blockLabel

    if (encoded.length <= MAX_SHARD_CHARS) {
      await docClient.send(new PutCommand({
        TableName: ANALYSIS_CACHE_TABLE,
        Item: { ...baseItem, payload: encoded },
      }))
      return
    }

    const chunks = chunkString(encoded, MAX_SHARD_CHARS)
    await docClient.send(new PutCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      Item: { ...baseItem, shard_count: chunks.length },
    }))

    for (let index = 0; index < chunks.length; index += 25) {
      const batch = chunks.slice(index, index + 25)
      await docClient.send(new BatchWriteCommand({
        RequestItems: {
          [ANALYSIS_CACHE_TABLE]: batch.map((payload, batchIndex) => ({
            PutRequest: {
              Item: {
                pk,
                sk: partSk(sk, index + batchIndex),
                payload,
                ...(expiry !== undefined ? { expires_at: expiry } : {}),
              },
            },
          })),
        },
      }))
    }
  } catch (error) {
    logger.warn({ err: error, userPk, sk }, 'Block JSON cache write failed')
  }
}

function canonicalLift(name: string): 'squat' | 'bench' | 'deadlift' | null {
  const lower = name.toLowerCase().trim()
  if (!lower) return null
  if ((lower === 'squat' || lower.includes('squat')) && !lower.includes('split') && !lower.includes('hack')) return 'squat'
  if (lower === 'bench' || lower === 'bench press') return 'bench'
  if ((lower === 'deadlift' || lower.includes('deadlift')) && !lower.includes('romanian') && !lower.includes('rdl')) return 'deadlift'
  return null
}

function estimateE1rm(kg: number | null | undefined, reps: number | null | undefined, rpe?: number | null): number | null {
  if (!kg || !Number.isFinite(kg) || kg <= 0 || !reps || reps <= 0) return null
  if (typeof rpe === 'number' && Number.isFinite(rpe)) {
    const pct = RPE_TABLE_PRIMARY.get(`${Math.trunc(reps)}-${Math.trunc(rpe)}`)
    return pct ? kg / pct : null
  }
  const pct = CONSERVATIVE_REP_PCT[Math.trunc(reps)]
  return pct ? kg / pct : null
}

function estimateBlockStrength(sessions: Session[], startDate: string, endDate: string, manualStartMaxes?: BlockStartMaxEntry | null): {
  startStrength: BlockStrengthSummary
  endStrength: BlockStrengthSummary
  strengthDelta: BlockStrengthSummary
  startMaxesSource: 'manual' | 'session_estimated'
} {
  const records: Array<{ lift: 'squat' | 'bench' | 'deadlift'; date: string; e1rm: number }> = []
  for (const session of sessions.filter(isCompletedSession)) {
    for (const exercise of session.exercises ?? []) {
      const lift = canonicalLift(exercise.name)
      if (!lift) continue
      const e1rm = estimateE1rm(exercise.kg, exercise.reps, (exercise as { rpe?: number | null }).rpe ?? session.session_rpe)
      if (e1rm != null) records.push({ lift, date: session.date, e1rm })
    }
  }

  const start = parseDate(startDate)
  const end = parseDate(endDate)
  const startCutoff = start ? isoDate(addDays(start, 21)) : startDate
  const endCutoff = end ? isoDate(addDays(end, -21)) : endDate
  const pick = (lift: 'squat' | 'bench' | 'deadlift', mode: 'start' | 'end'): number | null => {
    const liftRecords = records.filter((record) => record.lift === lift).sort((a, b) => a.date.localeCompare(b.date))
    if (!liftRecords.length) return null
    const windowRecords = mode === 'start'
      ? liftRecords.filter((record) => record.date <= startCutoff)
      : liftRecords.filter((record) => record.date >= endCutoff)
    const selected = windowRecords.length ? windowRecords : mode === 'start' ? [liftRecords[0]] : [liftRecords[liftRecords.length - 1]]
    return roundOrNull(Math.max(...selected.map((record) => record.e1rm)), 1)
  }

  const startStrength: BlockStrengthSummary = {
    squat: manualStartMaxes?.squat_kg ?? pick('squat', 'start'),
    bench: manualStartMaxes?.bench_kg ?? pick('bench', 'start'),
    deadlift: manualStartMaxes?.deadlift_kg ?? pick('deadlift', 'start'),
    total: null,
  }
  startStrength.total = totalFromStrength(startStrength)

  const endStrength: BlockStrengthSummary = {
    squat: pick('squat', 'end'),
    bench: pick('bench', 'end'),
    deadlift: pick('deadlift', 'end'),
    total: null,
  }
  endStrength.total = totalFromStrength(endStrength)

  const strengthDelta: BlockStrengthSummary = {
    squat: startStrength.squat != null && endStrength.squat != null ? roundOrNull(endStrength.squat - startStrength.squat, 1) : null,
    bench: startStrength.bench != null && endStrength.bench != null ? roundOrNull(endStrength.bench - startStrength.bench, 1) : null,
    deadlift: startStrength.deadlift != null && endStrength.deadlift != null ? roundOrNull(endStrength.deadlift - startStrength.deadlift, 1) : null,
    total: startStrength.total != null && endStrength.total != null ? roundOrNull(endStrength.total - startStrength.total, 1) : null,
  }

  return {
    startStrength,
    endStrength,
    strengthDelta,
    startMaxesSource: manualStartMaxes ? 'manual' : 'session_estimated',
  }
}

function calculateDots(totalKg: number, bodyweightKg: number, sex: 'male' | 'female'): number | null {
  if (totalKg <= 0 || bodyweightKg <= 0) return null
  const c = DOTS_COEFFICIENTS[sex]
  const denominator = c.a + c.b * bodyweightKg + c.c * bodyweightKg ** 2 + c.d * bodyweightKg ** 3 + c.e * bodyweightKg ** 4
  if (Math.abs(denominator) < 1e-12) return null
  return Number(((500 / denominator) * totalKg).toFixed(2))
}

function calculateIpfGl(totalKg: number, bodyweightKg: number, sex: 'male' | 'female'): number | null {
  if (totalKg <= 0 || bodyweightKg <= 0) return null
  const coeff = IPF_GL_COEFFICIENTS.classic_powerlifting[sex]
  const denominator = coeff.a - coeff.b * Math.exp(-coeff.c * bodyweightKg)
  if (Math.abs(denominator) < 1e-12) return null
  return Number(((totalKg * 100) / denominator).toFixed(2))
}

function liftResultsFromWeeklyProjection(weekly: unknown, linkedCompetition: BlockCompetitionLink | null): LiftResults | null {
  const report = recordFromUnknown(weekly)
  const projections = Array.isArray(report.projections) ? report.projections : []
  const projection = projections.find((item) => {
    const record = recordFromUnknown(item)
    return linkedCompetition?.name && record.comp_name === linkedCompetition.name
  }) ?? projections[0]
  const projectionRecord = recordFromUnknown(projection)
  const lifts = recordFromUnknown(projectionRecord.lifts)
  const liftValue = (lift: 'squat' | 'bench' | 'deadlift'): number => {
    const liftRecord = recordFromUnknown(lifts[lift])
    const projected = Number(liftRecord.projected ?? projectionRecord[lift])
    return Number.isFinite(projected) && projected > 0 ? Math.round(projected * 10) / 10 : 0
  }
  const squat = liftValue('squat')
  const bench = liftValue('bench')
  const deadlift = liftValue('deadlift')
  const total = Number(projectionRecord.total)
  if (squat <= 0 && bench <= 0 && deadlift <= 0 && (!Number.isFinite(total) || total <= 0)) return null
  return {
    squat_kg: squat,
    bench_kg: bench,
    deadlift_kg: deadlift,
    total_kg: Number.isFinite(total) && total > 0
      ? Math.round(total * 10) / 10
      : Math.round((squat + bench + deadlift) * 10) / 10,
  }
}

function summarizeCompetitionOutcome(
  program: Program,
  linkedCompetition: BlockCompetitionLink | null,
  fallbackProjection?: LiftResults | null,
): BlockCompetitionOutcome | null {
  if (!linkedCompetition) return null
  const competition = linkedCompetition.competition
  const results = hasResults(competition.results) ? competition.results : null
  const bodyweightKg = competition.body_weight_kg && competition.body_weight_kg > 0 ? competition.body_weight_kg : null
  const sex = program.meta?.sex === 'female' ? 'female' : 'male'
  const total = results?.total_kg ?? null
  const projectedAtTMinus1w = competition.results?.projected_at_t_minus_1w ?? competition.projected_at_t_minus_1w ?? fallbackProjection ?? null
  let projectionAccuracy: BlockCompetitionOutcome['projectionAccuracy'] = null

  if (results && projectedAtTMinus1w) {
    projectionAccuracy = {}
    for (const key of ['squat_kg', 'bench_kg', 'deadlift_kg', 'total_kg'] as const) {
      const actualKg = Number(results[key] || 0)
      const projectedKg = Number(projectedAtTMinus1w[key] || 0)
      if (actualKg > 0 && projectedKg > 0) {
        projectionAccuracy[key] = {
          actualKg,
          projectedKg,
          deltaKg: roundOrNull(actualKg - projectedKg, 1) ?? 0,
          deltaPct: roundOrNull(((actualKg - projectedKg) / projectedKg) * 100, 1),
        }
      }
    }
  }

  return {
    competitionName: competition.name,
    competitionDate: competition.date,
    bodyweightKg,
    results,
    dots: total && bodyweightKg ? calculateDots(total, bodyweightKg, sex) : null,
    ipfGl: total && bodyweightKg ? calculateIpfGl(total, bodyweightKg, sex) : null,
    ipfGlMode: total && bodyweightKg ? 'classic_powerlifting' : null,
    projectedAtTMinus1w,
    projectionAccuracy,
    prr: competition.results?.prr ?? null,
    postMeetReportCaptured: Boolean(competition.post_meet_report),
  }
}

function hasCompletedSbdSessionOnDate(sessions: Session[], date: string): boolean {
  const lifts = new Set<string>()
  for (const session of sessions) {
    if (session.date !== date || !isCompletedSession(session)) continue
    for (const exercise of session.exercises ?? []) {
      const lift = canonicalLift(exercise.name)
      if (lift) lifts.add(lift)
    }
  }
  return lifts.has('squat') && lifts.has('bench') && lifts.has('deadlift')
}

function syntheticCompetitionSession(entry: ProgramBlockIndexEntry, sessions: Session[]): Session | null {
  const competition = entry.linkedCompetition?.competition
  const results = competition?.results
  if (!competition || !hasResults(results)) return null
  if (hasCompletedSbdSessionOnDate(sessions, competition.date)) return null
  const template = [...sessions].reverse().find((session) => session.phase) ?? sessions[0]
  return {
    id: `synthetic_comp_${entry.blockKey}_${competition.date}`,
    date: competition.date,
    day: 'Competition',
    week: `W${entry.weekEnd} (Competition)`,
    week_number: entry.weekEnd,
    phase: template?.phase ?? ({
      name: 'Competition',
      intent: 'competition',
      start_week: entry.weekEnd,
      end_week: entry.weekEnd,
      block: entry.block,
    } as Session['phase']),
    block: entry.block,
    status: 'completed',
    completed: true,
    planned_exercises: [],
    exercises: [
      { name: 'Squat', sets: 1, reps: 1, kg: results.squat_kg, notes: 'Synthetic competition result', set_statuses: ['completed'] },
      { name: 'Bench Press', sets: 1, reps: 1, kg: results.bench_kg, notes: 'Synthetic competition result', set_statuses: ['completed'] },
      { name: 'Deadlift', sets: 1, reps: 1, kg: results.deadlift_kg, notes: 'Synthetic competition result', set_statuses: ['completed'] },
    ],
    session_notes: `Synthetic meet result imported from ${competition.name}.`,
    session_rpe: 10,
    body_weight_kg: competition.body_weight_kg ?? null,
  }
}

function analysisSessionsForBlock(program: Program, entry: ProgramBlockIndexEntry, options?: { includeSyntheticCompetition?: boolean }): Session[] {
  const analysisEndDate = entry.linkedCompetition?.date ?? entry.endDate
  const sessions = blockSessions(program, entry.block)
    .filter((session) => {
      if (!session.date) return false
      if (entry.startDate && session.date < entry.startDate) return false
      if (analysisEndDate && session.date > analysisEndDate) return false
      return true
    })
  if (options?.includeSyntheticCompetition === false) return sessions
  const synthetic = syntheticCompetitionSession(entry, sessions)
  return synthetic ? [...sessions, synthetic].sort((a, b) => a.date.localeCompare(b.date)) : sessions
}

function recordFromUnknown(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

function analyticsSummaryFromWeekly(weekly: unknown): BlockHistoricalSummary['analyticsSummary'] {
  const report = recordFromUnknown(weekly)
  const compliance = recordFromUnknown(report.compliance)
  const acwr = recordFromUnknown(report.acwr)
  const exerciseStats = recordFromUnknown(report.exercise_stats)
  const inol = recordFromUnknown(report.inol)
  const avgInol = recordFromUnknown(inol.avg_inol)
  const muscleMap = recordFromUnknown(report.muscle_map ?? report.muscle_group_avg_weekly ?? report.muscle_volume)
  const totalVolumeKg = Object.values(exerciseStats).reduce((sum, entry) => {
    const stats = recordFromUnknown(entry)
    const volume = typeof stats.total_volume === 'number' ? stats.total_volume : 0
    return sum + volume
  }, 0)

  return {
    sessionsAnalyzed: typeof report.sessions_analyzed === 'number' ? report.sessions_analyzed : 0,
    compliancePct: typeof compliance.pct === 'number' ? compliance.pct : null,
    fatigueIndex: typeof report.fatigue_index === 'number' ? report.fatigue_index : null,
    acwrComposite: typeof acwr.composite === 'number' ? acwr.composite : null,
    avgInol: Object.fromEntries(Object.entries(avgInol).filter(([, value]) => typeof value === 'number')) as Record<string, number>,
    totalVolumeKg: Math.round(totalVolumeKg),
    muscleMap,
  }
}

function hasPastDateProjectionFailure(bundle: BlockAnalysisBundle, entry: ProgramBlockIndexEntry): boolean {
  if (entry.isCurrent || !entry.linkedCompetition) return false
  const report = recordFromUnknown(bundle.weekly)
  const reason = typeof report.projection_reason === 'string' ? report.projection_reason.toLowerCase() : ''
  if (reason.includes('competition date is in the past')) return true
  const projections = Array.isArray(report.projections) ? report.projections : []
  const outcome = bundle.historical?.competitionOutcome
  return projections.length === 0 && Boolean(outcome?.results) && !outcome?.projectedAtTMinus1w
}

function makeHistoricalSummary(program: Program, entry: ProgramBlockIndexEntry, weekly: unknown): BlockHistoricalSummary {
  const sessions = analysisSessionsForBlock(program, entry)
  const manualStartMaxes = blockStartMaxes(program, entry.blockKey)
  const strength = estimateBlockStrength(sessions, entry.startDate, entry.linkedCompetition?.date ?? entry.endDate, manualStartMaxes)
  const fallbackProjection = liftResultsFromWeeklyProjection(weekly, entry.linkedCompetition)
  return {
    ...strength,
    manualStartMaxes,
    competitionOutcome: summarizeCompetitionOutcome(program, entry.linkedCompetition, fallbackProjection),
    analyticsSummary: analyticsSummaryFromWeekly(weekly),
    missingData: entry.dataQualityFlags,
  }
}

export function buildBlockProgram(program: Program, entry: ProgramBlockIndexEntry, allGoals: AthleteGoal[], options?: { normalizeToCurrent?: boolean; includeSyntheticCompetition?: boolean }): Program {
  const sessions = analysisSessionsForBlock(program, entry, { includeSyntheticCompetition: options?.includeSyntheticCompetition })
  const phases = blockPhases(program, entry.block)
  const normalizeToCurrent = options?.normalizeToCurrent === true
  const analysisEndDate = entry.linkedCompetition?.date ?? entry.endDate
  const rawBlockEndDate = blockSessions(program, entry.block)
    .map((session) => session.date)
    .filter(Boolean)
    .sort()
    .at(-1) ?? entry.endDate
  const competitionContextEndDate = entry.isCurrent && rawBlockEndDate > entry.endDate ? rawBlockEndDate : entry.endDate
  const competitions = blockCompetitionWindow(program, entry.startDate, competitionContextEndDate, entry.linkedCompetition)
  const goals = goalsForCompetitions(allGoals, competitions)
  const meta = blockScopedMeta(program, entry, analysisEndDate, competitions, goals)
  meta.block_notes = blockProgramNotes(program, entry.startDate, analysisEndDate)
  if (normalizeToCurrent) {
    const storedWeekStarts = { ...(program.meta.block_week_start_days ?? {}) }
    const entryWeekStart = storedWeekStarts[entry.block]
    meta.block_week_start_days = {
      ...storedWeekStarts,
      ...(entryWeekStart ? { [DEFAULT_BLOCK]: entryWeekStart } : {}),
    }
  }
  return {
    ...program,
    sessions: normalizeToCurrent
      ? sessions.map((session) => ({ ...session, block: DEFAULT_BLOCK }))
      : sessions,
    phases: normalizeToCurrent
      ? phases.map((phase) => ({ ...phase, block: DEFAULT_BLOCK }))
      : phases,
    competitions,
    goals,
    meta,
    diet_notes: blockDietNotes(program, entry.startDate, analysisEndDate),
    weight_log: blockWeightLog(program, entry.startDate, analysisEndDate),
  } as Program & { weight_log: WeightEntry[] }
}

export function buildBlockComparisonContext(program: Program, rawEntry: ProgramBlockIndexEntry, allGoals: AthleteGoal[]): BlockComparisonContext {
  const scopedEntry = analysisScopedBlockEntry(program, rawEntry)
  const competitions = blockCompetitionWindow(program, rawEntry.startDate, rawEntry.endDate, rawEntry.linkedCompetition)
  const goals = goalsForCompetitions(allGoals, competitions)
  const fallbackBodyweight = competitions.find((competition) => typeof competition.body_weight_kg === 'number' && competition.body_weight_kg > 0)?.body_weight_kg
    ?? program.meta?.current_body_weight_kg
    ?? null

  return {
    sessions: analysisSessionsForBlock(program, scopedEntry, { includeSyntheticCompetition: false }),
    weightLog: blockWeightLog(program, scopedEntry.startDate, scopedEntry.linkedCompetition?.date ?? scopedEntry.endDate),
    competitions,
    goals,
    sex: program.meta?.sex === 'female' ? 'female' : 'male',
    fallbackBodyweightKg: typeof fallbackBodyweight === 'number' && fallbackBodyweight > 0 ? fallbackBodyweight : null,
  }
}

export async function getOrCreateBlockAnalysisBundle(
  userPk: string,
  program: Program,
  blockKey: string,
  invokeTool: InvokeTool,
  refresh = false,
  cacheOnly = false,
  allGoals?: AthleteGoal[],
): Promise<BlockAnalysisBundle | null> {
  const goals = allGoals ?? await loadGoals(userPk)
  const blocks = await buildCurrentProgramBlockIndex(userPk, program, goals)
  const rawEntry = blocks.find((block) => block.blockKey === blockKey)
  if (!rawEntry) return null
  const entry = analysisScopedBlockEntry(program, rawEntry)

  if (!refresh || cacheOnly) {
    const cached = await getCachedBlockAnalysisBundle(userPk, blockKey)
    if (cached && (cacheOnly || !hasPastDateProjectionFailure(cached, entry))) {
      if (!entry.isCurrent) {
        logger.info({ userPk, blockKey, cached: true }, 'Block analysis cache hit')
      }
      return cached
    }
  }
  if (cacheOnly) return null

  logger.info({ userPk, blockKey, isCurrent: entry.isCurrent, weeks: entry.weekCount }, 'Computing block analysis')

  const programForBlock = buildBlockProgram(program, entry, goals, { includeSyntheticCompetition: false })
  const sessions = programForBlock.sessions ?? []
  const analysisEndDate = blockProjectionReferenceDate(entry)
  const weekly = await invokeTool('weekly_analysis', {
    weeks: entry.weekCount,
    block: entry.block,
    window_start: entry.startDate,
    window_end: analysisEndDate,
    ref_date: analysisEndDate,
    week_start: entry.weekStart,
    week_end: entry.weekEnd,
    refresh_program: false,
    program: programForBlock,
    sessions,
    pk: userPk,
  })

  const bundle: BlockAnalysisBundle = {
    schemaVersion: CACHE_SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    cached: false,
    sourceFingerprint: entry.sourceFingerprint,
    block: {
      ...entry,
      cacheStatus: { cached: true, generatedAt: new Date().toISOString() },
    },
    weekly,
    historical: makeHistoricalSummary(program, entry, weekly),
  }
  await putCachedBlockAnalysisBundle(userPk, bundle)
  return bundle
}

export async function getOrCreateBlockProgramEvaluation(
  userPk: string,
  program: Program,
  blockKey: string,
  invokeTool: InvokeTool,
  refresh = false,
  cacheOnly = false,
  allGoals?: AthleteGoal[],
): Promise<Record<string, unknown> | null> {
  const goals = allGoals ?? await loadGoals(userPk)
  const blocks = await buildCurrentProgramBlockIndex(userPk, program, goals)
  const rawEntry = blocks.find((block) => block.blockKey === blockKey)
  if (!rawEntry) return null
  const entry = analysisScopedBlockEntry(program, rawEntry)

  const sk = blockProgramEvaluationSk(blockKey)
  if (!refresh) {
    const cached = await getCachedJsonPayload<Record<string, unknown>>(userPk, sk, entry.sourceFingerprint)
    if (cached) {
      return {
        ...cached,
        cached: true,
        window_start: cached.window_start ?? entry.startDate,
      }
    }
  }

  if (cacheOnly) {
    return {
      insufficient_data: true,
      insufficient_data_reason: 'No cached program analysis exists for this block. Generate it to run AI analysis.',
      cache_miss: true,
      cached: false,
      generated_at: '',
      window_start: entry.startDate,
      weeks: 0,
    }
  }

  const analysisSessions = analysisSessionsForBlock(program, entry, { includeSyntheticCompetition: false })
  const completedWeeks = new Set(
    analysisSessions
      .filter(isCompletedSession)
      .map((session) => Number(session.week_number || 0))
      .filter((week) => week > 0),
  )

  if (completedWeeks.size < 4) {
    return {
      insufficient_data: true,
      insufficient_data_reason: 'At least 4 completed weeks are required for a useful block program evaluation.',
      cached: false,
      generated_at: '',
      window_start: entry.startDate,
      weeks: completedWeeks.size,
    }
  }

  const rawReport = recordFromUnknown(await invokeTool('block_program_evaluation', {
    program: buildBlockProgram(program, entry, goals, { normalizeToCurrent: true, includeSyntheticCompetition: false }),
    pk: userPk,
  }))
  const generatedAt = new Date().toISOString()
  const report: Record<string, unknown> = {
    ...rawReport,
    cached: false,
    generated_at: typeof rawReport.generated_at === 'string' && rawReport.generated_at
      ? rawReport.generated_at
      : generatedAt,
    window_start: entry.startDate,
    weeks: completedWeeks.size,
  }

  await putCachedJsonPayload(userPk, sk, report, {
    sourceFingerprint: entry.sourceFingerprint,
    blockKey,
    blockLabel: entry.label,
    isCurrent: entry.isCurrent,
  })
  return report
}

export async function getOrCreateBlockCorrelationReport(
  userPk: string,
  program: Program,
  blockKey: string,
  invokeTool: InvokeTool,
  refresh = false,
  cacheOnly = false,
  allGoals?: AthleteGoal[],
): Promise<Record<string, unknown> | null> {
  const goals = allGoals ?? await loadGoals(userPk)
  const blocks = await buildCurrentProgramBlockIndex(userPk, program, goals)
  const rawEntry = blocks.find((block) => block.blockKey === blockKey)
  if (!rawEntry) return null
  const entry = analysisScopedBlockEntry(program, rawEntry)

  const sk = blockCorrelationSk(blockKey)
  if (!refresh) {
    const cached = await getCachedJsonPayload<Record<string, unknown>>(userPk, sk)
    if (cached) {
      return {
        ...cached,
        cached: true,
        window_start: cached.window_start ?? entry.startDate,
        weeks: cached.weeks ?? entry.weekCount,
      }
    }
  }

  if (cacheOnly) {
    return {
      findings: [],
      summary: '',
      insufficient_data: true,
      insufficient_data_reason: 'No cached ROI correlation report exists for this block. Generate it to run AI analysis.',
      cache_miss: true,
      cached: false,
      generated_at: '',
      window_start: entry.startDate,
      weeks: entry.weekCount,
    }
  }

  const programForBlock = buildBlockProgram(program, entry, goals, {
    normalizeToCurrent: true,
    includeSyntheticCompetition: false,
  })
  const report = recordFromUnknown(await invokeTool('block_correlation_analysis', {
    weeks: entry.weekCount,
    window_start: entry.startDate,
    program: programForBlock,
    sessions: programForBlock.sessions ?? [],
    pk: userPk,
  }))

  await putCachedJsonPayload(userPk, sk, report, {
    sourceFingerprint: entry.sourceFingerprint,
    blockKey,
    blockLabel: entry.label,
    isCurrent: entry.isCurrent,
  })
  return report
}

function projectionTotalDelta(outcome: BlockCompetitionOutcome | null): number | null {
  const total = outcome?.projectionAccuracy?.total_kg
  return typeof total?.deltaKg === 'number' ? total.deltaKg : null
}

function comparisonCompetitions(context?: BlockComparisonContext): BlockComparisonRow['competitions'] {
  return (context?.competitions ?? []).map((competition) => ({
    name: competition.name,
    date: competition.date,
    status: competition.status,
    federation: competition.federation,
    weightClassKg: typeof competition.weight_class_kg === 'number' ? competition.weight_class_kg : null,
    bodyweightKg: typeof competition.body_weight_kg === 'number' ? competition.body_weight_kg : null,
    targetTotalKg: typeof competition.targets?.total_kg === 'number' ? competition.targets.total_kg : null,
    resultTotalKg: typeof competition.results?.total_kg === 'number' ? competition.results.total_kg : null,
    projectedTotalKg: typeof competition.projected_at_t_minus_1w?.total_kg === 'number'
      ? competition.projected_at_t_minus_1w.total_kg
      : typeof competition.results?.projected_at_t_minus_1w?.total_kg === 'number'
        ? competition.results.projected_at_t_minus_1w.total_kg
        : null,
  }))
}

function comparisonGoals(context?: BlockComparisonContext): BlockComparisonRow['goals'] {
  return (context?.goals ?? []).map((goal) => ({
    id: goal.id,
    title: goal.title,
    goalType: goal.goal_type,
    priority: goal.priority,
    targetTotalKg: typeof goal.target_total_kg === 'number' ? goal.target_total_kg : null,
    targetDots: typeof goal.target_dots === 'number' ? goal.target_dots : null,
    targetIpfGl: typeof goal.target_ipf_gl === 'number' ? goal.target_ipf_gl : null,
    targetDate: goal.target_date,
    targetCompetitionIds: goal.target_competition_ids,
  }))
}

function comparisonRow(bundle: BlockAnalysisBundle, context?: BlockComparisonContext): BlockComparisonRow {
  const outcome = bundle.historical.competitionOutcome
  return {
    blockKey: bundle.block.blockKey,
    label: bundle.block.label,
    startDate: bundle.block.startDate,
    endDate: bundle.block.endDate,
    trainingOnly: bundle.block.trainingOnly,
    competitionName: outcome?.competitionName ?? null,
    competitionDate: outcome?.competitionDate ?? null,
    actualTotalKg: outcome?.results?.total_kg ?? null,
    actualDots: outcome?.dots ?? null,
    actualIpfGl: outcome?.ipfGl ?? null,
    estimatedDots: typeof recordFromUnknown(bundle.weekly).estimated_dots === 'number'
      ? recordFromUnknown(bundle.weekly).estimated_dots
      : null,
    startTotalKg: bundle.historical.startStrength.total,
    endTotalKg: bundle.historical.endStrength.total,
    e1rmDeltaKg: bundle.historical.strengthDelta.total,
    compliancePct: bundle.historical.analyticsSummary.compliancePct,
    fatigueIndex: bundle.historical.analyticsSummary.fatigueIndex,
    acwrComposite: bundle.historical.analyticsSummary.acwrComposite,
    totalVolumeKg: bundle.historical.analyticsSummary.totalVolumeKg,
    avgInol: bundle.historical.analyticsSummary.avgInol,
    projectionTotalDeltaKg: projectionTotalDelta(outcome),
    dataQualityFlags: bundle.historical.missingData,
    competitions: comparisonCompetitions(context),
    goals: comparisonGoals(context),
  }
}

function avg(values: number[]): number | null {
  if (!values.length) return null
  return roundOrNull(values.reduce((sum, value) => sum + value, 0) / values.length, 2)
}

function normalizeExerciseForRoi(name: string): string {
  return name.toLowerCase().trim().replace(/\s+/g, ' ')
}

function isCompetitionLiftExercise(name: string): boolean {
  const normalized = normalizeExerciseForRoi(name)
  return normalized === 'squat' || normalized === 'bench' || normalized === 'bench press' || normalized === 'deadlift'
}

function normalizedDirection(value: unknown): 'positive' | 'negative' | 'unclear' {
  return value === 'positive' || value === 'negative' || value === 'unclear' ? value : 'unclear'
}

function normalizedStrength(value: unknown): 'weak' | 'moderate' | 'strong' {
  return value === 'strong' || value === 'moderate' || value === 'weak' ? value : 'weak'
}

function blockCorrelationFindings(
  bundles: BlockAnalysisBundle[],
  correlationReports?: Map<string, Record<string, unknown> | null>,
): BlockComparisonResult['correlationFindings'] {
  if (!correlationReports?.size) return []
  const labels = new Map(bundles.map((bundle) => [bundle.block.blockKey, bundle.block.label]))
  const findings: BlockComparisonResult['correlationFindings'] = []

  for (const [blockKey, report] of correlationReports.entries()) {
    const rawFindings = Array.isArray(report?.findings) ? report.findings : []
    for (const item of rawFindings) {
      const record = recordFromUnknown(item)
      const exercise = typeof record.exercise === 'string' ? record.exercise.trim() : ''
      const lift = typeof record.lift === 'string' ? record.lift.trim() : ''
      if (!exercise || !lift) continue
      findings.push({
        blockKey,
        label: labels.get(blockKey) ?? blockKey,
        exercise,
        lift,
        direction: normalizedDirection(record.correlation_direction),
        strength: normalizedStrength(record.strength),
        reasoning: typeof record.reasoning === 'string' ? record.reasoning : '',
        caveat: typeof record.caveat === 'string' ? record.caveat : '',
      })
    }
  }

  return findings
}

function exerciseStatsByBlock(bundle: BlockAnalysisBundle): Array<{ exercise: string; sets: number; volumeKg: number }> {
  const stats = recordFromUnknown(recordFromUnknown(bundle.weekly).exercise_stats)
  return Object.entries(stats)
    .map(([exercise, value]) => {
      const entry = recordFromUnknown(value)
      const sets = Number(entry.total_sets ?? 0)
      const volumeKg = Number(entry.total_volume ?? 0)
      return {
        exercise,
        sets: Number.isFinite(sets) ? sets : 0,
        volumeKg: Number.isFinite(volumeKg) ? Math.round(volumeKg) : 0,
      }
    })
    .filter((row) => row.exercise.trim() && !isCompetitionLiftExercise(row.exercise) && (row.sets > 0 || row.volumeKg > 0))
}

function liftDeltaRecord(bundle: BlockAnalysisBundle): Record<string, number | null> {
  return {
    squat: bundle.historical.strengthDelta.squat,
    bench: bundle.historical.strengthDelta.bench,
    deadlift: bundle.historical.strengthDelta.deadlift,
    total: bundle.historical.strengthDelta.total,
  }
}

function buildConsolidatedExerciseRoi(
  bundles: BlockAnalysisBundle[],
  correlationFindings: BlockComparisonResult['correlationFindings'],
): BlockComparisonResult['exerciseRoi'] {
  const rows = new Map<string, {
    displayName: string
    totalSets: number
    totalVolumeKg: number
    blockMap: Map<string, {
      blockKey: string
      label: string
      sets: number
      volumeKg: number
      correlations: Array<{ lift: string; direction: 'positive' | 'negative' | 'unclear'; strength: 'weak' | 'moderate' | 'strong' }>
      liftDeltasKg: Record<string, number | null>
    }>
  }>()

  for (const bundle of bundles) {
    for (const stat of exerciseStatsByBlock(bundle)) {
      const key = normalizeExerciseForRoi(stat.exercise)
      const existing = rows.get(key) ?? {
        displayName: stat.exercise,
        totalSets: 0,
        totalVolumeKg: 0,
        blockMap: new Map(),
      }
      existing.totalSets += stat.sets
      existing.totalVolumeKg += stat.volumeKg
      existing.blockMap.set(bundle.block.blockKey, {
        blockKey: bundle.block.blockKey,
        label: bundle.block.label,
        sets: stat.sets,
        volumeKg: stat.volumeKg,
        correlations: [],
        liftDeltasKg: liftDeltaRecord(bundle),
      })
      rows.set(key, existing)
    }
  }

  for (const finding of correlationFindings) {
    const key = normalizeExerciseForRoi(finding.exercise)
    const row = rows.get(key)
    if (!row) continue
    const block = row.blockMap.get(finding.blockKey)
    if (!block) continue
    block.correlations.push({
      lift: finding.lift,
      direction: finding.direction,
      strength: finding.strength,
    })
  }

  return [...rows.values()]
    .map((row) => {
      const blocks = [...row.blockMap.values()].sort((a, b) => a.label.localeCompare(b.label))
      const correlations = blocks.flatMap((block) => block.correlations)
      const positiveSignals = correlations.filter((item) => item.direction === 'positive').length
      const negativeSignals = correlations.filter((item) => item.direction === 'negative').length
      const unclearSignals = correlations.filter((item) => item.direction === 'unclear').length
      const correlatedLifts = [...new Set(correlations.map((item) => item.lift))].sort()
      const confidence: 'low' | 'medium' | 'high' =
        blocks.length >= 3 && positiveSignals + negativeSignals >= 2
          ? 'high'
          : blocks.length >= 2 && positiveSignals + negativeSignals >= 1
            ? 'medium'
            : 'low'
      const signalText = positiveSignals || negativeSignals || unclearSignals
        ? `${positiveSignals} positive, ${negativeSignals} negative, ${unclearSignals} unclear correlation signal${positiveSignals + negativeSignals + unclearSignals === 1 ? '' : 's'}`
        : 'no correlation finding'
      const liftText = correlatedLifts.length ? ` across ${correlatedLifts.join(', ')}` : ''
      return {
        exercise: row.displayName,
        blockCount: blocks.length,
        totalSets: Math.round(row.totalSets),
        totalVolumeKg: Math.round(row.totalVolumeKg),
        correlatedLifts,
        positiveSignals,
        negativeSignals,
        unclearSignals,
        confidence,
        summary: `${row.displayName} appeared in ${blocks.length} source block${blocks.length === 1 ? '' : 's'} with ${Math.round(row.totalSets)} sets and ${Math.round(row.totalVolumeKg).toLocaleString()} kg volume; ${signalText}${liftText}.`,
        blocks,
      }
    })
    .filter((row) => row.blockCount >= 2 || row.positiveSignals + row.negativeSignals > 0)
    .sort((a, b) => {
      const signalDiff = (b.positiveSignals + b.negativeSignals) - (a.positiveSignals + a.negativeSignals)
      if (signalDiff !== 0) return signalDiff
      if (b.blockCount !== a.blockCount) return b.blockCount - a.blockCount
      return b.totalVolumeKg - a.totalVolumeKg
    })
    .slice(0, 20)
}

function liftStatsFromWeekly(bundle: BlockAnalysisBundle, lift: 'squat' | 'bench' | 'deadlift'): { sets: number; volumeKg: number } {
  const exerciseStats = recordFromUnknown(recordFromUnknown(bundle.weekly).exercise_stats)
  return Object.entries(exerciseStats).reduce((total, [name, value]) => {
    if (canonicalLift(name) !== lift) return total
    const stats = recordFromUnknown(value)
    const sets = Number(stats.total_sets ?? 0)
    const volume = Number(stats.total_volume ?? 0)
    return {
      sets: total.sets + (Number.isFinite(sets) ? sets : 0),
      volumeKg: total.volumeKg + (Number.isFinite(volume) ? volume : 0),
    }
  }, { sets: 0, volumeKg: 0 })
}

function buildLiftDoseResponse(bundles: BlockAnalysisBundle[]): BlockComparisonResult['liftDoseResponse'] {
  const rows: BlockComparisonResult['liftDoseResponse'] = []
  for (const bundle of bundles) {
    const weekly = recordFromUnknown(bundle.weekly)
    const inol = recordFromUnknown(weekly.inol)
    const avgInol = recordFromUnknown(inol.avg_inol)
    const rawAvgInol = recordFromUnknown(inol.raw_avg_inol)
    for (const lift of ['squat', 'bench', 'deadlift'] as const) {
      const stats = liftStatsFromWeekly(bundle, lift)
      const delta = bundle.historical.strengthDelta[lift]
      rows.push({
        blockKey: bundle.block.blockKey,
        label: bundle.block.label,
        lift,
        avgInol: roundOrNull(Number(avgInol[lift]), 2),
        rawAvgInol: roundOrNull(Number(rawAvgInol[lift]), 2),
        sets: Math.round(stats.sets),
        volumeKg: Math.round(stats.volumeKg),
        strengthDeltaKg: delta,
        responsePerSetKg: typeof delta === 'number' && stats.sets > 0 ? roundOrNull(delta / stats.sets, 3) : null,
        responsePer1000Kg: typeof delta === 'number' && stats.volumeKg > 0 ? roundOrNull(delta / (stats.volumeKg / 1000), 3) : null,
      })
    }
  }
  return rows
}

function exerciseVolumeKg(session: Session): number {
  return (session.exercises ?? []).reduce((total, exercise) => {
    const sets = Number(exercise.sets || 0)
    const reps = Number(exercise.reps || 0)
    const kg = Number(exercise.kg || 0)
    return total + (Number.isFinite(sets) && Number.isFinite(reps) && Number.isFinite(kg) ? sets * reps * kg : 0)
  }, 0)
}

function latestBodyweight(
  sessions: Session[],
  fallback: number | null,
  maxDate: string,
  weightLog: WeightEntry[] = [],
): number | null {
  const dated = new Map<string, number>()
  for (const entry of weightLog) {
    if (entry.date <= maxDate && typeof entry.kg === 'number' && Number.isFinite(entry.kg) && entry.kg > 0) {
      dated.set(entry.date, entry.kg)
    }
  }
  for (const session of sessions) {
    if (
      session.status !== 'skipped' &&
      session.date <= maxDate &&
      typeof session.body_weight_kg === 'number' &&
      Number.isFinite(session.body_weight_kg) &&
      session.body_weight_kg > 0
    ) {
      dated.set(session.date, session.body_weight_kg)
    }
  }
  const match = [...dated.entries()].sort(([a], [b]) => b.localeCompare(a))[0]
  return match?.[1] ?? fallback
}

function buildBlockTrendSeries(
  bundle: BlockAnalysisBundle,
  context?: BlockComparisonContext,
): BlockComparisonResult['trendSeries'] {
  const sessions = (context?.sessions ?? [])
    .filter(isCompletedSession)
    .sort((a, b) => a.date.localeCompare(b.date))
  if (!sessions.length) return []

  const grouped = new Map<number, Session[]>()
  for (const session of sessions) {
    const week = Number(session.week_number || 0)
    if (week <= 0) continue
    grouped.set(week, [...(grouped.get(week) ?? []), session])
  }

  const monotonyRows = recordFromUnknown(recordFromUnknown(bundle.weekly).monotony_strain).weekly
  const strainByDate = new Map<string, number>()
  if (Array.isArray(monotonyRows)) {
    for (const row of monotonyRows) {
      const record = recordFromUnknown(row)
      if (typeof record.week_start === 'string' && typeof record.strain === 'number') {
        strainByDate.set(record.week_start, record.strain)
      }
    }
  }

  const carried = {
    squat: bundle.historical.startStrength.squat,
    bench: bundle.historical.startStrength.bench,
    deadlift: bundle.historical.startStrength.deadlift,
  }
  const rows: BlockComparisonResult['trendSeries'] = []

  for (let weekNumber = bundle.block.weekStart; weekNumber <= bundle.block.weekEnd; weekNumber += 1) {
    const weekSessions = (grouped.get(weekNumber) ?? []).sort((a, b) => a.date.localeCompare(b.date))
    const best: Record<'squat' | 'bench' | 'deadlift', number | null> = { squat: null, bench: null, deadlift: null }
    for (const session of weekSessions) {
      for (const exercise of session.exercises ?? []) {
        const lift = canonicalLift(exercise.name)
        if (!lift) continue
        const e1rm = estimateE1rm(exercise.kg, exercise.reps, (exercise as { rpe?: number | null }).rpe ?? session.session_rpe)
        if (e1rm != null && (best[lift] == null || e1rm > Number(best[lift]))) {
          best[lift] = roundOrNull(e1rm, 1)
        }
      }
    }

    for (const lift of ['squat', 'bench', 'deadlift'] as const) {
      if (best[lift] != null) carried[lift] = best[lift]
    }

    const previousWeekStart = rows[rows.length - 1]?.weekStart
    const previousDate = previousWeekStart ? parseDate(previousWeekStart) : null
    const weekStart = weekSessions.map((session) => session.date).sort()[0]
      ?? (previousDate ? isoDate(addDays(previousDate, 7)) : bundle.block.startDate)
    const total = carried.squat != null && carried.bench != null && carried.deadlift != null
      ? roundOrNull(carried.squat + carried.bench + carried.deadlift, 1)
      : null
    const bodyweight = latestBodyweight(sessions, context?.fallbackBodyweightKg ?? null, weekStart, context?.weightLog ?? [])

    rows.push({
      blockKey: bundle.block.blockKey,
      label: bundle.block.label,
      weekNumber,
      weekStart,
      squatKg: carried.squat,
      benchKg: carried.bench,
      deadliftKg: carried.deadlift,
      e1rmTotalKg: total,
      estimatedDots: total != null && bodyweight != null && context
        ? calculateDots(total, bodyweight, context.sex)
        : null,
      volumeKg: Math.round(weekSessions.reduce((sum, session) => sum + exerciseVolumeKg(session), 0)),
      trainingDays: new Set(weekSessions.map((session) => session.date)).size,
      strain: strainByDate.get(weekStart) ?? null,
    })
  }

  return rows
}

function buildTrendSeries(
  bundles: BlockAnalysisBundle[],
  contexts?: Map<string, BlockComparisonContext>,
): BlockComparisonResult['trendSeries'] {
  return bundles.flatMap((bundle) => buildBlockTrendSeries(bundle, contexts?.get(bundle.block.blockKey)))
}

function buildTrainingDayResponse(
  rows: BlockComparisonRow[],
  trendSeries: BlockComparisonResult['trendSeries'],
): BlockComparisonResult['trainingDayResponse'] {
  return rows.map((row) => {
    const series = trendSeries.filter((point) => point.blockKey === row.blockKey)
    const totalTrainingDays = series.reduce((sum, point) => sum + point.trainingDays, 0)
    return {
      blockKey: row.blockKey,
      label: row.label,
      completedWeeks: series.length,
      totalTrainingDays,
      avgTrainingDaysPerWeek: series.length ? roundOrNull(totalTrainingDays / series.length, 2) : null,
      strengthDeltaKg: row.e1rmDeltaKg,
      compliancePct: row.compliancePct,
    }
  })
}

function buildPatternSignals(
  rows: BlockComparisonRow[],
  exerciseRoi: BlockComparisonResult['exerciseRoi'],
  correlationFindings: BlockComparisonResult['correlationFindings'],
  trainingDayResponse: BlockComparisonResult['trainingDayResponse'] = [],
  trendSeries: BlockComparisonResult['trendSeries'] = [],
): BlockComparisonResult['patternSignals'] {
  const patterns: BlockComparisonResult['patternSignals'] = []
  const cachedCorrelationBlocks = new Set(correlationFindings.map((finding) => finding.blockKey))

  if (exerciseRoi.length) {
    const top = exerciseRoi[0]
    patterns.push({
      kind: 'roi',
      finding: `${top.exercise} has the strongest consolidated exercise ROI signal in the source data.`,
      evidence: top.summary,
      confidence: top.confidence,
    })
  }

  const repeatedPositive = exerciseRoi.find((row) => row.blockCount >= 2 && row.positiveSignals >= 2)
  if (repeatedPositive) {
    patterns.push({
      kind: 'roi',
      finding: `${repeatedPositive.exercise} has repeated positive transfer signals across source blocks.`,
      evidence: `${repeatedPositive.positiveSignals} positive correlation findings across ${repeatedPositive.blockCount} blocks; lifts: ${repeatedPositive.correlatedLifts.join(', ') || 'not specified'}.`,
      confidence: repeatedPositive.confidence,
    })
  }

  const completedRows = rows.filter((row) => row.e1rmDeltaKg != null)
  if (completedRows.length >= 2) {
    const best = [...completedRows].sort((a, b) => Number(b.e1rmDeltaKg ?? -Infinity) - Number(a.e1rmDeltaKg ?? -Infinity))[0]
    const worst = [...completedRows].sort((a, b) => Number(a.e1rmDeltaKg ?? Infinity) - Number(b.e1rmDeltaKg ?? Infinity))[0]
    if (best && worst && best.blockKey !== worst.blockKey) {
      patterns.push({
        kind: 'training_response',
        finding: `${best.label} had the strongest total response among source blocks.`,
        evidence: `${best.label}: ${best.e1rmDeltaKg} kg total delta, ${best.compliancePct ?? 'unknown'} compliance, ${Math.round(best.totalVolumeKg).toLocaleString()} kg volume. ${worst.label}: ${worst.e1rmDeltaKg} kg total delta.`,
        confidence: rows.length >= 3 ? 'medium' : 'low',
      })
    }
  }

  const complianceRows = rows.filter((row) => row.compliancePct != null && row.e1rmDeltaKg != null)
  if (complianceRows.length >= 2) {
    const highCompliance = [...complianceRows].sort((a, b) => Number(b.compliancePct) - Number(a.compliancePct))[0]
    const lowCompliance = [...complianceRows].sort((a, b) => Number(a.compliancePct) - Number(b.compliancePct))[0]
    if (highCompliance && lowCompliance && highCompliance.blockKey !== lowCompliance.blockKey) {
      patterns.push({
        kind: 'compliance',
        finding: 'Compliance is a major confound in the lifetime comparison.',
        evidence: `${highCompliance.label}: ${highCompliance.compliancePct?.toFixed(1)}% compliance and ${highCompliance.e1rmDeltaKg} kg total delta. ${lowCompliance.label}: ${lowCompliance.compliancePct?.toFixed(1)}% compliance and ${lowCompliance.e1rmDeltaKg} kg total delta.`,
        confidence: 'medium',
      })
    }
  }

  const missingCorrelationRows = rows.filter((row) => !cachedCorrelationBlocks.has(row.blockKey))
  if (missingCorrelationRows.length) {
    patterns.push({
      kind: 'data_quality',
      finding: 'Some selected blocks do not have ROI correlation reports.',
      evidence: `Missing correlation data for: ${missingCorrelationRows.map((row) => row.label).join(', ')}. Exercise ROI still uses block exercise stats, but pattern confidence is lower without correlation findings.`,
      confidence: 'high',
    })
  }

  const trainingDayRows = trainingDayResponse.filter((row) => row.avgTrainingDaysPerWeek != null && row.strengthDeltaKg != null)
  if (trainingDayRows.length >= 2) {
    const high = [...trainingDayRows].sort((a, b) => Number(b.avgTrainingDaysPerWeek) - Number(a.avgTrainingDaysPerWeek))[0]
    const low = [...trainingDayRows].sort((a, b) => Number(a.avgTrainingDaysPerWeek) - Number(b.avgTrainingDaysPerWeek))[0]
    if (high && low && high.blockKey !== low.blockKey) {
      patterns.push({
        kind: 'training_response',
        finding: 'Average training days per week differs across selected source blocks.',
        evidence: `${high.label}: ${high.avgTrainingDaysPerWeek} days/week and ${high.strengthDeltaKg} kg total delta. ${low.label}: ${low.avgTrainingDaysPerWeek} days/week and ${low.strengthDeltaKg} kg total delta.`,
        confidence: trainingDayRows.length >= 3 ? 'medium' : 'low',
      })
    }
  }

  for (const row of rows) {
    const series = trendSeries.filter((point) => point.blockKey === row.blockKey).sort((a, b) => a.weekNumber - b.weekNumber)
    const firstZeroAfterTraining = series.findIndex((point, index) =>
      index > 0 && point.trainingDays === 0 && series[index - 1].trainingDays > 0
    )
    if (firstZeroAfterTraining >= 0) {
      const zeroRun = series.slice(firstZeroAfterTraining).findIndex((point) => point.trainingDays > 0)
      const zeroWeeks = zeroRun === -1 ? series.length - firstZeroAfterTraining : zeroRun
      if (zeroWeeks >= 2) {
        patterns.push({
          kind: 'training_response',
          finding: `${row.label} has a training-day dropoff in the block-to-date series.`,
          evidence: `Training days fell to 0 starting W${series[firstZeroAfterTraining].weekNumber} (${series[firstZeroAfterTraining].weekStart}) for ${zeroWeeks} consecutive week${zeroWeeks === 1 ? '' : 's'} in the selected source data.`,
          confidence: 'high',
        })
      }
    }
  }

  return patterns
}

function buildRoiSignals(bundles: BlockAnalysisBundle[]): BlockComparisonResult['roiSignals'] {
  return ['squat', 'bench', 'deadlift'].map((lift) => {
    const inolValues: number[] = []
    const deltas: number[] = []
    for (const bundle of bundles) {
      const avgInol = bundle.historical.analyticsSummary.avgInol[lift]
      const delta = bundle.historical.strengthDelta[lift as keyof BlockStrengthSummary]
      if (typeof avgInol === 'number') inolValues.push(avgInol)
      if (typeof delta === 'number') deltas.push(delta)
    }
    const avgInolValue = avg(inolValues)
    const avgDelta = avg(deltas)
    let interpretation = 'Insufficient signal'
    if (avgInolValue != null && avgDelta != null) {
      interpretation = avgDelta > 0
        ? `Positive average e1RM response at ${avgInolValue.toFixed(2)} INOL/wk`
        : `No positive average e1RM response at ${avgInolValue.toFixed(2)} INOL/wk`
    }
    return {
      lift,
      avgInolPerWeek: avgInolValue,
      avgStrengthDeltaKg: avgDelta,
      interpretation,
    }
  })
}

function buildVolumeTolerance(rows: BlockComparisonRow[], bundles: BlockAnalysisBundle[]): BlockComparisonResult['volumeTolerance'] {
  const compLinkedRows = rows.filter((row) => row.actualTotalKg != null)
  const byLift: BlockComparisonResult['volumeTolerance']['byLift'] = {}
  for (const lift of ['squat', 'bench', 'deadlift']) {
    const positive = bundles.filter((bundle) => {
      const delta = bundle.historical.strengthDelta[lift as keyof BlockStrengthSummary]
      return typeof delta === 'number' && delta > 0
    })
    const bestObservedAvgInol = positive.reduce<number | null>((best, bundle) => {
      const value = bundle.historical.analyticsSummary.avgInol[lift]
      if (typeof value !== 'number') return best
      return best == null ? value : Math.max(best, value)
    }, null)
    byLift[lift] = {
      bestObservedAvgInol: roundOrNull(bestObservedAvgInol, 2),
      positiveDeltaBlocks: positive.length,
    }
  }

  if (compLinkedRows.length < 3) {
    return {
      status: 'low_confidence',
      confidence: 'low',
      sampleSize: compLinkedRows.length,
      requiredSampleSize: 3,
      message: `Need at least ${Math.max(0, 3 - compLinkedRows.length)} more comp-linked blocks before estimating volume tolerance.`,
      byLift,
    }
  }

  return {
    status: 'estimated',
    confidence: compLinkedRows.length >= 5 ? 'medium' : 'low',
    sampleSize: compLinkedRows.length,
    requiredSampleSize: 3,
    message: 'Volume tolerance is estimated from observed block-level INOL and strength outcomes.',
    byLift,
  }
}

export function buildBlockComparison(
  bundles: BlockAnalysisBundle[],
  correlationReports?: Map<string, Record<string, unknown> | null>,
  contexts?: Map<string, BlockComparisonContext>,
): BlockComparisonResult {
  const rows = bundles
    .map((bundle) => comparisonRow(bundle, contexts?.get(bundle.block.blockKey)))
    .sort((a, b) => a.startDate.localeCompare(b.startDate))
  const correlationFindings = blockCorrelationFindings(bundles, correlationReports)
  const exerciseRoi = buildConsolidatedExerciseRoi(bundles, correlationFindings)
  const trendSeries = buildTrendSeries(bundles, contexts)
  const trainingDayResponse = buildTrainingDayResponse(rows, trendSeries)
  const point = <T extends number | null>(row: BlockComparisonRow, value: T) => ({
    blockKey: row.blockKey,
    label: row.label,
    value,
  })

  return {
    schemaVersion: CACHE_SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    selectedBlockKeys: rows.map((row) => row.blockKey),
    rows,
    trends: {
      actualTotal: rows.map((row) => point(row, row.actualTotalKg)),
      dots: rows.map((row) => point(row, row.actualDots ?? row.estimatedDots)),
      ipfGl: rows.map((row) => point(row, row.actualIpfGl)),
      e1rmTotal: rows.map((row) => point(row, row.endTotalKg)),
      compliance: rows.map((row) => point(row, row.compliancePct)),
      fatigue: rows.map((row) => point(row, row.fatigueIndex)),
      volume: rows.map((row) => point(row, row.totalVolumeKg)),
    },
    roiSignals: buildRoiSignals(bundles),
    exerciseRoi,
    correlationFindings,
    patternSignals: buildPatternSignals(rows, exerciseRoi, correlationFindings, trainingDayResponse, trendSeries),
    liftDoseResponse: buildLiftDoseResponse(bundles),
    trainingDayResponse,
    trendSeries,
    volumeTolerance: buildVolumeTolerance(rows, bundles),
    missingDataSummary: rows.map((row) => ({
      blockKey: row.blockKey,
      label: row.label,
      flags: row.dataQualityFlags,
    })),
  }
}

function stripRuntimeCacheMarkers(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripRuntimeCacheMarkers)
  if (!value || typeof value !== 'object') return value

  const omittedKeys = new Set([
    'cached',
    'cache_miss',
    'cacheStatus',
    'programEvaluationCacheStatus',
  ])
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !omittedKeys.has(key))
      .map(([key, nested]) => [key, stripRuntimeCacheMarkers(nested)]),
  )
}

function isSavedSupportingReport(report: Record<string, unknown> | null | undefined): report is Record<string, unknown> {
  return Boolean(report && report.cached === true && report.cache_miss !== true)
}

function buildAiComparisonPayload(
  bundles: BlockAnalysisBundle[],
  correlationReports?: Map<string, Record<string, unknown> | null>,
  programEvaluationReports?: Map<string, Record<string, unknown> | null>,
  contexts?: Map<string, BlockComparisonContext>,
): {
  sourceFingerprint: string
  deterministic: BlockComparisonResult
  payload: Record<string, unknown>
} {
  const ordered = [...bundles].sort((a, b) => a.block.startDate.localeCompare(b.block.startDate))
  const deterministic = buildBlockComparison(ordered, correlationReports, contexts)
  const sourceFingerprint = sourceHash({
    selectedBlockKeys: ordered.map((bundle) => bundle.block.blockKey),
    sourceFingerprints: ordered.map((bundle) => bundle.sourceFingerprint),
    correlationFingerprints: [...(correlationReports?.entries() ?? [])].map(([blockKey, report]) => ({
      blockKey,
      generatedAt: typeof report?.generated_at === 'string' ? report.generated_at : '',
      findings: Array.isArray(report?.findings) ? report.findings : [],
    })),
    programEvaluationFingerprints: [...(programEvaluationReports?.entries() ?? [])].map(([blockKey, report]) => ({
      blockKey,
      generatedAt: typeof report?.generated_at === 'string' ? report.generated_at : '',
      report,
    })),
  })

  return {
    sourceFingerprint,
    deterministic,
    payload: {
      schema_version: CACHE_SCHEMA_VERSION,
      generated_at: new Date().toISOString(),
      selected_block_keys: ordered.map((bundle) => bundle.block.blockKey),
      deterministic,
      correlation_reports: stripRuntimeCacheMarkers(Object.fromEntries(
        [...(correlationReports?.entries() ?? [])].map(([blockKey, report]) => [
          blockKey,
          isSavedSupportingReport(report) ? report : null,
        ]),
      )),
      program_evaluation_reports: stripRuntimeCacheMarkers(Object.fromEntries(
        [...(programEvaluationReports?.entries() ?? [])].map(([blockKey, report]) => [
          blockKey,
          isSavedSupportingReport(report) ? report : null,
        ]),
      )),
      blocks: ordered.map((bundle) => ({
        block_analysis: stripRuntimeCacheMarkers(bundle),
        competitions: contexts?.get(bundle.block.blockKey)?.competitions ?? [],
        goals: contexts?.get(bundle.block.blockKey)?.goals ?? [],
        correlation_report: stripRuntimeCacheMarkers(
          isSavedSupportingReport(correlationReports?.get(bundle.block.blockKey))
            ? correlationReports?.get(bundle.block.blockKey)
            : null,
        ),
        program_evaluation_report: stripRuntimeCacheMarkers(
          isSavedSupportingReport(programEvaluationReports?.get(bundle.block.blockKey))
            ? programEvaluationReports?.get(bundle.block.blockKey)
            : null,
        ),
      })),
    },
  }
}

export async function getOrCreateAiBlockComparison(
  userPk: string,
  bundles: BlockAnalysisBundle[],
  invokeTool: InvokeTool,
  refresh = false,
  cacheOnly = false,
  correlationReports?: Map<string, Record<string, unknown> | null>,
  programEvaluationReports?: Map<string, Record<string, unknown> | null>,
  contexts?: Map<string, BlockComparisonContext>,
): Promise<AiBlockComparisonResult> {
  const { sourceFingerprint, deterministic, payload } = buildAiComparisonPayload(
    bundles,
    correlationReports,
    programEvaluationReports,
    contexts,
  )
  const selectedBlockKeys = deterministic.selectedBlockKeys
  const sk = blockAiComparisonSk(sourceFingerprint)

  if (!refresh) {
    const cached = await getCachedJsonPayload<AiBlockComparisonResult>(userPk, sk, sourceFingerprint)
    if (cached) {
      return {
        ...cached,
        cached: true,
        deterministic,
        selectedBlockKeys,
        sourceFingerprint,
      }
    }
    
    try {
      const pk = `analysis#${userPk}`
      const prefix = `block_compare_ai#v${CACHE_SCHEMA_VERSION}#`
      const response = await docClient.send(new QueryCommand({
        TableName: ANALYSIS_CACHE_TABLE,
        KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
        ExpressionAttributeValues: {
          ':pk': pk,
          ':prefix': prefix,
        },
      }))
      
      const items = response.Items || []
      if (items.length > 0) {
        const sorted = items.sort((a, b) => {
          return String(b.generated_at || '').localeCompare(String(a.generated_at || ''))
        })
        const latestItem = sorted[0]
        const fallbackSk = latestItem.sk as string
        const fallbackCached = await getCachedJsonPayload<AiBlockComparisonResult>(userPk, fallbackSk)
        if (fallbackCached) {
           return {
             ...fallbackCached,
             cached: true,
             deterministic,
             selectedBlockKeys,
             sourceFingerprint,
           }
        }
      }
    } catch (error) {
      logger.warn({ err: error, userPk }, 'Block compare fallback cache read failed')
    }
  }

  if (cacheOnly) {
    return {
      schemaVersion: CACHE_SCHEMA_VERSION,
      generatedAt: new Date().toISOString(),
      cached: false,
      selectedBlockKeys,
      sourceFingerprint,
      report: {
        insufficient_data: true,
        insufficient_data_reason: 'No saved multi-block AI comparison exists for this block selection. Generate it to run AI analysis.',
        cache_miss: true,
      },
      deterministic,
    }
  }

  const report = recordFromUnknown(await invokeTool('multi_block_comparison_analysis', {
    payload,
    pk: userPk,
  }))

  const result: AiBlockComparisonResult = {
    schemaVersion: CACHE_SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    cached: false,
    selectedBlockKeys,
    sourceFingerprint,
    report,
    deterministic,
  }

  await putCachedJsonPayload(userPk, sk, result, { sourceFingerprint })
  return result
}
