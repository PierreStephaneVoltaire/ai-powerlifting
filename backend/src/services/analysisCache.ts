import { logger } from '../utils/logger'
import crypto from 'crypto'
import {
  BatchWriteCommand,
  DeleteCommand,
  GetCommand,
  PutCommand,
  QueryCommand,
  UpdateCommand,
} from '@aws-sdk/lib-dynamodb'
import { docClient, POWERLIFTING_GOALS_TABLE } from '../db/dynamo'
import type { AthleteGoal, Program, Session, WeightEntry } from '@powerlifting/types'

export type AnalysisWindowKey =
  | 'current'
  | 'previous_1'
  | 'previous_2'
  | 'previous_4'
  | 'previous_8'
  | 'block'

export type AnalysisSectionKey =
  | 'overview'
  | 'fatigue_readiness'
  | 'peaking'
  | 'workload'
  | 'alerts'
  | 'ai_correlation'
  | 'program_evaluation'

export type AnalysisJobStatus = 'pending' | 'running' | 'complete' | 'error'

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

export interface WeeklyAnalysisBundle<T = unknown> {
  schemaVersion: number
  asOfDate: string
  generatedAt: string
  cached: boolean
  windows: Record<AnalysisWindowKey, AnalysisWindow>
  results: Record<AnalysisWindowKey, T>
}

export interface CachedAnalysisSection<T = unknown> {
  schemaVersion: number
  asOfDate: string
  windowKey: AnalysisWindowKey
  sectionKey: AnalysisSectionKey
  sourceFingerprint: string
  generatedAt: string
  payload: T
  cached: boolean
}

export interface AnalysisSectionStatus<T = unknown> {
  sectionKey: AnalysisSectionKey
  status: AnalysisJobStatus | 'missing'
  generatedAt?: string
  updatedAt?: string
  error?: string
  sourceFingerprint?: string
  cached: boolean
  payload?: T
}

export interface AnalysisSectionJob {
  sectionKey: AnalysisSectionKey
  status: AnalysisJobStatus
  asOfDate: string
  windowKey: AnalysisWindowKey
  sourceFingerprint: string
  queuedAt: string
  updatedAt: string
  startedAt?: string
  completedAt?: string
  error?: string
  attempts?: number
}

const CACHE_SCHEMA_VERSION = 5
const SECTION_CACHE_SCHEMA_VERSION = 6
const SECTION_CACHE_VERSION = 'v1'
const ANALYSIS_CACHE_TABLE = process.env.ANALYSIS_CACHE_TABLE_NAME || 'if-powerlifting-analysis-cache'
// Current-block window caches expire after 7 days. Past-block caches have no TTL.
const CACHE_TTL_DAYS = 7
// Shard size: keep individual DynamoDB string attributes under 400KB.
// ~350_000 JSON chars is a safe ceiling before sharding kicks in.
const MAX_SHARD_CHARS = 350_000

const WINDOW_SPECS: Array<{ key: AnalysisWindowKey; label: string; mode: number | 'current' | 'block' }> = [
  { key: 'current', label: 'Current Week', mode: 'current' },
  { key: 'previous_1', label: 'Previous Week', mode: 1 },
  { key: 'previous_2', label: 'Previous 2 Weeks', mode: 2 },
  { key: 'previous_4', label: 'Previous 4 Weeks', mode: 4 },
  { key: 'previous_8', label: 'Previous 8 Weeks', mode: 8 },
  { key: 'block', label: 'Full Block', mode: 'block' },
]

export const ALL_WINDOW_KEYS: AnalysisWindowKey[] = WINDOW_SPECS.map((spec) => spec.key)

// Windows that receive correlation AI analysis (4+ weeks needed)
export const CORRELATION_WINDOW_KEYS: AnalysisWindowKey[] = ['previous_4', 'previous_8', 'block']
export const DETERMINISTIC_SECTION_KEYS: AnalysisSectionKey[] = [
  'overview',
  'fatigue_readiness',
  'peaking',
  'workload',
  'alerts',
]
export const AI_SECTION_KEYS: AnalysisSectionKey[] = ['ai_correlation', 'program_evaluation']
export const ALL_SECTION_KEYS: AnalysisSectionKey[] = [...DETERMINISTIC_SECTION_KEYS, ...AI_SECTION_KEYS]

type WeekStartDay =
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday'

const WEEK_START_DAYS: WeekStartDay[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

const UTC_DAY_INDEX: Record<WeekStartDay, number> = {
  Sunday: 0,
  Monday: 1,
  Tuesday: 2,
  Wednesday: 3,
  Thursday: 4,
  Friday: 5,
  Saturday: 6,
}

const MS_PER_DAY = 24 * 60 * 60 * 1000

function normalizeWeekStartDay(value: unknown, fallback: WeekStartDay): WeekStartDay {
  return typeof value === 'string' && WEEK_START_DAYS.includes(value as WeekStartDay)
    ? value as WeekStartDay
    : fallback
}

function weekStartForBlock(program: Program, block = 'current'): WeekStartDay {
  const blockValue = block || 'current'
  const stored = program.meta?.block_week_start_days?.[blockValue]
  if (stored) return normalizeWeekStartDay(stored, 'Monday')
  return 'Monday'
}

function parseIsoDate(value: string): Date {
  return new Date(`${value}T00:00:00.000Z`)
}

function formatIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

function addDaysIso(value: string, days: number): string {
  const date = parseIsoDate(value)
  date.setUTCDate(date.getUTCDate() + days)
  return formatIsoDate(date)
}

function diffDays(end: string, start: string): number {
  return Math.floor((parseIsoDate(end).getTime() - parseIsoDate(start).getTime()) / MS_PER_DAY)
}

function maxIso(a: string, b: string): string {
  return a > b ? a : b
}

function parseWeekNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function resolveCurrentWeek(program: Program, asOfDate: string, programStart: string, weekStartDay: WeekStartDay): number {
  const calculatedWeek = trainingWeekForDate(asOfDate, programStart, weekStartDay)
  const calculatedStart = programWeekStartDate(programStart, calculatedWeek, weekStartDay)
  const calculatedEnd = addDaysIso(calculatedStart, 6)
  const dueWeekNumbers = (program.sessions ?? [])
    .filter((session) => (session.block ?? 'current') === 'current')
    .filter((session) =>
      session.date >= calculatedStart &&
      session.date <= calculatedEnd &&
      session.date <= asOfDate
    )
    .map((session) => parseWeekNumber(session.week_number))
    .filter((week): week is number => week !== null)

  if (dueWeekNumbers.length) return Math.max(...dueWeekNumbers)
  return calculatedWeek
}

function programWeekAnchorDate(programStart: string, weekStartDay: WeekStartDay): string {
  const start = parseIsoDate(programStart)
  const currentIndex = start.getUTCDay()
  const targetIndex = UTC_DAY_INDEX[weekStartDay]
  const offset = (currentIndex - targetIndex + 7) % 7
  return addDaysIso(programStart, -offset)
}

function programWeekStartDate(programStart: string, week: number, weekStartDay: WeekStartDay): string {
  return addDaysIso(programWeekAnchorDate(programStart, weekStartDay), (Math.max(1, week) - 1) * 7)
}

function trainingWeekForDate(dateStr: string, programStart: string, weekStartDay: WeekStartDay): number {
  const anchor = programWeekAnchorDate(programStart, weekStartDay)
  return Math.max(1, Math.floor(diffDays(dateStr, anchor) / 7) + 1)
}

export function isIsoDate(value: string | undefined): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
}

export function buildAnalysisWindows(program: Program, asOfDate: string): Record<AnalysisWindowKey, AnalysisWindow> {
  const sessions = program.sessions ?? []
  const programStart = program.meta?.program_start || sessions.find((session) => (session.block ?? 'current') === 'current')?.date || asOfDate
  const weekStartDay = weekStartForBlock(program, 'current')
  const currentWeek = resolveCurrentWeek(program, asOfDate, programStart, weekStartDay)
  const windows = {} as Record<AnalysisWindowKey, AnalysisWindow>

  for (const spec of WINDOW_SPECS) {
    let weekStart: number
    let weekEnd: number

    if (spec.mode === 'current') {
      weekStart = currentWeek
      weekEnd = currentWeek
    } else if (spec.mode === 'block') {
      weekStart = 1
      weekEnd = currentWeek
    } else {
      weekEnd = currentWeek
      weekStart = Math.max(1, currentWeek - spec.mode)
    }

    const weekStartDate = programWeekStartDate(programStart, weekStart, weekStartDay)
    const weekEndDate = addDaysIso(programWeekStartDate(programStart, weekEnd, weekStartDay), 6)
    const start = maxIso(weekStartDate, programStart)
    const end = weekEndDate

    windows[spec.key] = {
      key: spec.key,
      label: spec.label,
      start,
      end,
      weekStart,
      weekEnd,
      weeks: Math.max(1, weekEnd - weekStart + 1),
      currentWeek,
    }
  }

  return windows
}

export function makeWeeklyAnalysisBundle<T>(
  asOfDate: string,
  windows: Record<AnalysisWindowKey, AnalysisWindow>,
  results: Record<AnalysisWindowKey, T>,
): WeeklyAnalysisBundle<T> {
  return {
    schemaVersion: CACHE_SCHEMA_VERSION,
    asOfDate,
    generatedAt: new Date().toISOString(),
    cached: false,
    windows,
    results,
  }
}

// ─── DynamoDB helpers ──────────────────────────────────────────────────────────

function cachePk(userPk: string): string {
  return `analysis#${userPk}`
}

function windowSk(windowKey: AnalysisWindowKey): string {
  return `weekly_analysis#${windowKey}`
}

function analysisSectionSk(asOfDate: string, windowKey: AnalysisWindowKey, sectionKey: AnalysisSectionKey): string {
  return `analysis_section#${SECTION_CACHE_VERSION}#${asOfDate}#${windowKey}#${sectionKey}`
}

function analysisJobSk(asOfDate: string, windowKey: AnalysisWindowKey, sectionKey: AnalysisSectionKey): string {
  return `analysis_job#${SECTION_CACHE_VERSION}#${asOfDate}#${windowKey}#${sectionKey}`
}

function markdownSk(blockKey = 'current'): string {
  return `markdown_export#${blockKey}`
}

function shardSk(baseSk: string, index: number): string {
  return `${baseSk}#shard#${String(index).padStart(3, '0')}`
}

function currentBlockExpiresAt(): number {
  return Math.floor(Date.now() / 1000) + CACHE_TTL_DAYS * 24 * 60 * 60
}

function stableJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`
  const obj = value as Record<string, unknown>
  return `{${Object.keys(obj).sort().map((key) => `${JSON.stringify(key)}:${stableJson(obj[key])}`).join(',')}}`
}

function hashValue(value: unknown): string {
  return crypto.createHash('sha256').update(stableJson(value)).digest('hex')
}

async function fetchGoalsForFingerprint(pk: string): Promise<AthleteGoal[]> {
  const items: Record<string, unknown>[] = []
  let lastKey: Record<string, unknown> | undefined
  do {
    const resp = await docClient.send(new QueryCommand({
      TableName: POWERLIFTING_GOALS_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: { ':pk': pk, ':prefix': 'GOAL#' },
      ProjectionExpression: 'id, title, goal_type, priority, target_date, target_competition_ids, target_total_kg, target_dots, target_ipf_gl, target_federation_ids, target_weight_class_kg, age_class, notes',
      ExclusiveStartKey: lastKey,
    }))
    for (const it of resp.Items ?? []) items.push(it as Record<string, unknown>)
    lastKey = resp.LastEvaluatedKey
  } while (lastKey)
  return items
    .map((it) => {
      const { sk: _sk, pk: _pk, created_at: _c, updated_at: _u, ...rest } = it
      void _sk; void _pk; void _c; void _u
      return rest as unknown as AthleteGoal
    })
    .sort((a, b) => String(a.id).localeCompare(String(b.id)))
}

export async function buildAnalysisSourceFingerprint(
  program: Program,
  window: AnalysisWindow,
  pk: string,
): Promise<string> {
  const currentSessions = (program.sessions ?? [])
    .filter((session) => (session.block ?? 'current') === 'current')
    .filter((session) => session.date <= window.end)
  const scopedWeightLog = ((program as Program & { weight_log?: WeightEntry[] }).weight_log ?? [])
    .filter((entry) => entry.date <= window.end)
  const currentPhases = (program.phases ?? [])
    .filter((phase) => (phase.block ?? 'current') === 'current')
  const goals = await fetchGoalsForFingerprint(pk)
  return hashValue({
    schema: SECTION_CACHE_SCHEMA_VERSION,
    asOfWindow: {
      key: window.key,
      start: window.start,
      end: window.end,
      weekStart: window.weekStart,
      weekEnd: window.weekEnd,
    },
    meta: program.meta ?? {},
    phases: currentPhases,
    sessions: currentSessions,
    competitions: program.competitions ?? [],
    goals,
    lift_profiles: program.lift_profiles ?? [],
    diet_notes: (program as Program & { diet_notes?: unknown[] }).diet_notes ?? [],
    weight_log: scopedWeightLog,
  })
}

async function batchDeleteByPrefix(pk: string, prefix: string): Promise<void> {
  const keys: Array<{ pk: string; sk: string }> = []
  let ExclusiveStartKey: Record<string, unknown> | undefined
  do {
    const response = await docClient.send(new QueryCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: { ':pk': pk, ':prefix': prefix },
      ProjectionExpression: 'pk, sk',
      ExclusiveStartKey,
    }))
    for (const item of response.Items || []) {
      if (typeof item.pk === 'string' && typeof item.sk === 'string') {
        keys.push({ pk: item.pk, sk: item.sk })
      }
    }
    ExclusiveStartKey = response.LastEvaluatedKey
  } while (ExclusiveStartKey)

  for (let i = 0; i < keys.length; i += 25) {
    const batch = keys.slice(i, i + 25)
    if (!batch.length) continue
    await docClient.send(new BatchWriteCommand({
      RequestItems: {
        [ANALYSIS_CACHE_TABLE]: batch.map((Key) => ({ DeleteRequest: { Key } })),
      },
    }))
  }
}

async function putJsonItem(
  pk: string,
  sk: string,
  data: unknown,
  expiresAtUnix: number | undefined,
  extraFields: Record<string, unknown> = {},
): Promise<void> {
  const jsonStr = JSON.stringify(data)

  // Delete old item + any shards with this sk prefix before writing
  await batchDeleteByPrefix(pk, sk)

  const baseItem: Record<string, unknown> = {
    pk,
    sk,
    generated_at: new Date().toISOString(),
    ...extraFields,
  }
  if (expiresAtUnix !== undefined) {
    baseItem.expires_at = expiresAtUnix
  }

  if (jsonStr.length <= MAX_SHARD_CHARS) {
    await docClient.send(new PutCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      Item: { ...baseItem, payload: jsonStr },
    }))
    return
  }

  // Write shard manifest + individual shards
  const shards: string[] = []
  for (let i = 0; i < jsonStr.length; i += MAX_SHARD_CHARS) {
    shards.push(jsonStr.slice(i, i + MAX_SHARD_CHARS))
  }

  await docClient.send(new PutCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Item: { ...baseItem, shard_count: shards.length },
  }))

  for (let i = 0; i < shards.length; i += 25) {
    const batch = shards.slice(i, i + 25)
    await docClient.send(new BatchWriteCommand({
      RequestItems: {
        [ANALYSIS_CACHE_TABLE]: batch.map((shard, batchIdx) => ({
          PutRequest: {
            Item: {
              pk,
              sk: shardSk(sk, i + batchIdx),
              payload: shard,
              ...(expiresAtUnix !== undefined ? { expires_at: expiresAtUnix } : {}),
            },
          },
        })),
      },
    }))
  }
}

async function getJsonItemWithMetadata<T>(
  pk: string,
  sk: string,
): Promise<{ data: T; generatedAt: string; item: Record<string, unknown> } | null> {
  try {
    const response = await docClient.send(new GetCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      Key: { pk, sk },
    }))
    const item = response.Item
    if (!item) return null

    const generatedAt = typeof item.generated_at === 'string' ? item.generated_at : ''

    // Sharded item
    const shardCount = Number(item.shard_count || 0)
    if (shardCount > 0) {
      const parts = await Promise.all(
        Array.from({ length: shardCount }, async (_, index) => {
          const part = await docClient.send(new GetCommand({
            TableName: ANALYSIS_CACHE_TABLE,
            Key: { pk, sk: shardSk(sk, index) },
          }))
          return String(part.Item?.payload ?? '')
        }),
      )
      const joined = parts.join('')
      if (!joined) return null
      return { data: JSON.parse(joined) as T, generatedAt, item }
    }

    // Inline item
    const payload = item.payload
    if (typeof payload !== 'string' || !payload) return null
    return { data: JSON.parse(payload) as T, generatedAt, item }
  } catch {
    return null
  }
}

async function getJsonItem<T>(pk: string, sk: string): Promise<{ data: T; generatedAt: string } | null> {
  const result = await getJsonItemWithMetadata<T>(pk, sk)
  return result ? { data: result.data, generatedAt: result.generatedAt } : null
}

// ─── Window analysis cache (current block only) ───────────────────────────────

export async function getCachedWindowAnalysis(
  userPk: string,
  windowKey: AnalysisWindowKey,
): Promise<{ data: unknown; generatedAt: string } | null> {
  return getJsonItem(cachePk(userPk), windowSk(windowKey))
}

export async function getCachedAllWindowAnalyses(
  userPk: string,
): Promise<{ results: Record<AnalysisWindowKey, unknown>; generatedAt: string } | null> {
  const entries = await Promise.all(
    ALL_WINDOW_KEYS.map(async (key) => ({ key, result: await getCachedWindowAnalysis(userPk, key) })),
  )

  if (entries.some((e) => e.result === null)) return null

  const results = {} as Record<AnalysisWindowKey, unknown>
  let generatedAt = ''
  for (const { key, result } of entries) {
    results[key] = result!.data
    if (!generatedAt) generatedAt = result!.generatedAt
  }
  return { results, generatedAt }
}

export async function putAllCachedWindowAnalyses(
  userPk: string,
  results: Record<AnalysisWindowKey, unknown>,
): Promise<void> {
  const expiry = currentBlockExpiresAt()
  await Promise.all(
    ALL_WINDOW_KEYS.map((key) =>
      putJsonItem(cachePk(userPk), windowSk(key), results[key], expiry),
    ),
  )
}

// ─── Section analysis cache + background job state ────────────────────────────

function isConditionalFailure(error: unknown): boolean {
  return typeof error === 'object'
    && error !== null
    && 'name' in error
    && String((error as { name?: unknown }).name) === 'ConditionalCheckFailedException'
}

function validWindowKey(value: unknown): value is AnalysisWindowKey {
  return ALL_WINDOW_KEYS.includes(value as AnalysisWindowKey)
}

function validSectionKey(value: unknown): value is AnalysisSectionKey {
  return ALL_SECTION_KEYS.includes(value as AnalysisSectionKey)
}

export function normalizeAnalysisWindowKey(value: unknown): AnalysisWindowKey {
  return validWindowKey(value) ? value : 'previous_4'
}

export function normalizeAnalysisSectionKeys(value: unknown, fallback: AnalysisSectionKey[] = DETERMINISTIC_SECTION_KEYS): AnalysisSectionKey[] {
  const raw = Array.isArray(value) ? value : fallback
  const keys = raw.filter(validSectionKey)
  return keys.length ? Array.from(new Set(keys)) : fallback
}

export function splitWeeklyAnalysisSections(weekly: Record<string, unknown>): Record<AnalysisSectionKey, Record<string, unknown>> {
  return {
    overview: {
      week: weekly.week,
      selected_week_start: weekly.selected_week_start,
      selected_week_end: weekly.selected_week_end,
      selected_week_count: weekly.selected_week_count,
      window_start: weekly.window_start,
      window_end: weekly.window_end,
      selected_session_context: weekly.selected_session_context,
      block: weekly.block,
      compliance: weekly.compliance,
      current_maxes: weekly.current_maxes,
      estimated_dots: weekly.estimated_dots,
      estimated_dots_reason: weekly.estimated_dots_reason,
      projections: weekly.projections,
      projection_reason: weekly.projection_reason,
      projection_calibration: weekly.projection_calibration,
      attempt_selection: weekly.attempt_selection,
      sessions_analyzed: weekly.sessions_analyzed,
      deload_info: weekly.deload_info,
    },
    fatigue_readiness: {
      fatigue_index: weekly.fatigue_index,
      fatigue_components: weekly.fatigue_components,
      fatigue_dimensions: weekly.fatigue_dimensions,
      inol: weekly.inol,
      acwr: weekly.acwr,
      ri_distribution: weekly.ri_distribution,
      volume_landmarks: weekly.volume_landmarks,
      readiness_score: weekly.readiness_score,
    },
    peaking: {
      banister: weekly.banister,
      monotony_strain: weekly.monotony_strain,
      decoupling: weekly.decoupling,
      taper_quality: weekly.taper_quality,
      specificity_ratio: weekly.specificity_ratio,
      specificity_target_competition: weekly.specificity_target_competition,
      peaking_timeline: weekly.peaking_timeline,
    },
    workload: {
      lifts: weekly.lifts,
      exercise_stats: weekly.exercise_stats,
    },
    alerts: {
      alerts: weekly.alerts ?? [],
      flags: weekly.flags ?? [],
    },
    ai_correlation: {},
    program_evaluation: {},
  }
}

export async function getCachedAnalysisSection<T = unknown>(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKey: AnalysisSectionKey,
  expectedSourceFingerprint?: string,
): Promise<CachedAnalysisSection<T> | null> {
  const result = await getJsonItemWithMetadata<T>(cachePk(userPk), analysisSectionSk(asOfDate, windowKey, sectionKey))
  if (!result) return null
  const sourceFingerprint = typeof result.item.source_fingerprint === 'string' ? result.item.source_fingerprint : ''
  if (expectedSourceFingerprint && sourceFingerprint !== expectedSourceFingerprint) return null
  return {
    schemaVersion: SECTION_CACHE_SCHEMA_VERSION,
    asOfDate,
    windowKey,
    sectionKey,
    sourceFingerprint,
    generatedAt: result.generatedAt,
    payload: result.data,
    cached: true,
  }
}

export async function putCachedAnalysisSection(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKey: AnalysisSectionKey,
  sourceFingerprint: string,
  payload: unknown,
): Promise<void> {
  await putJsonItem(
    cachePk(userPk),
    analysisSectionSk(asOfDate, windowKey, sectionKey),
    payload,
    currentBlockExpiresAt(),
    {
      schema_version: SECTION_CACHE_SCHEMA_VERSION,
      cache_version: SECTION_CACHE_VERSION,
      as_of_date: asOfDate,
      window_key: windowKey,
      section_key: sectionKey,
      source_fingerprint: sourceFingerprint,
    },
  )
}

export async function invalidateAnalysisSections(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKeys: AnalysisSectionKey[] = ALL_SECTION_KEYS,
): Promise<void> {
  const pk = cachePk(userPk)
  for (const sectionKey of sectionKeys) {
    await batchDeleteByPrefix(pk, analysisSectionSk(asOfDate, windowKey, sectionKey))
    await batchDeleteByPrefix(pk, analysisJobSk(asOfDate, windowKey, sectionKey))
  }
}

export async function getAnalysisSectionJob(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKey: AnalysisSectionKey,
): Promise<AnalysisSectionJob | null> {
  const response = await docClient.send(new GetCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Key: { pk: cachePk(userPk), sk: analysisJobSk(asOfDate, windowKey, sectionKey) },
  }))
  const item = response.Item
  if (!item) return null
  const status = item.status
  if (!['pending', 'running', 'complete', 'error'].includes(String(status))) return null
  return {
    sectionKey,
    status: status as AnalysisJobStatus,
    asOfDate,
    windowKey,
    sourceFingerprint: String(item.source_fingerprint ?? ''),
    queuedAt: String(item.queued_at ?? ''),
    updatedAt: String(item.updated_at ?? ''),
    startedAt: typeof item.started_at === 'string' ? item.started_at : undefined,
    completedAt: typeof item.completed_at === 'string' ? item.completed_at : undefined,
    error: typeof item.error === 'string' ? item.error : undefined,
    attempts: typeof item.attempts === 'number' ? item.attempts : undefined,
  }
}

export async function queueAnalysisSectionJobs(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKeys: AnalysisSectionKey[],
  sourceFingerprint: string,
): Promise<void> {
  const now = new Date().toISOString()
  for (const sectionKey of sectionKeys) {
    try {
      await docClient.send(new PutCommand({
        TableName: ANALYSIS_CACHE_TABLE,
        Item: {
          pk: cachePk(userPk),
          sk: analysisJobSk(asOfDate, windowKey, sectionKey),
          schema_version: SECTION_CACHE_SCHEMA_VERSION,
          cache_version: SECTION_CACHE_VERSION,
          as_of_date: asOfDate,
          window_key: windowKey,
          section_key: sectionKey,
          source_fingerprint: sourceFingerprint,
          status: 'pending',
          queued_at: now,
          updated_at: now,
          attempts: 0,
          expires_at: currentBlockExpiresAt(),
        },
        ConditionExpression: [
          'attribute_not_exists(pk)',
          'source_fingerprint <> :fp',
          'attribute_not_exists(source_fingerprint)',
          '#status IN (:complete, :errorStatus)',
        ].join(' OR '),
        ExpressionAttributeNames: { '#status': 'status' },
        ExpressionAttributeValues: {
          ':fp': sourceFingerprint,
          ':complete': 'complete',
          ':errorStatus': 'error',
        },
      }))
    } catch (error) {
      if (!isConditionalFailure(error)) throw error
    }
  }
}

export async function claimAnalysisSectionJob(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKey: AnalysisSectionKey,
  sourceFingerprint: string,
): Promise<boolean> {
  const now = new Date().toISOString()
  const staleBefore = new Date(Date.now() - 10 * 60 * 1000).toISOString()
  try {
    await docClient.send(new UpdateCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      Key: { pk: cachePk(userPk), sk: analysisJobSk(asOfDate, windowKey, sectionKey) },
      UpdateExpression: 'SET #status = :running, started_at = :now, updated_at = :now ADD attempts :one',
      ConditionExpression: 'source_fingerprint = :fp AND (#status = :pending OR (#status = :running AND updated_at < :stale))',
      ExpressionAttributeNames: { '#status': 'status' },
      ExpressionAttributeValues: {
        ':running': 'running',
        ':pending': 'pending',
        ':fp': sourceFingerprint,
        ':now': now,
        ':stale': staleBefore,
        ':one': 1,
      },
    }))
    return true
  } catch (error) {
    if (isConditionalFailure(error)) return false
    throw error
  }
}

export async function completeAnalysisSectionJob(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKey: AnalysisSectionKey,
  sourceFingerprint: string,
): Promise<void> {
  const now = new Date().toISOString()
  await docClient.send(new UpdateCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Key: { pk: cachePk(userPk), sk: analysisJobSk(asOfDate, windowKey, sectionKey) },
    UpdateExpression: 'SET #status = :complete, completed_at = :now, updated_at = :now REMOVE #error',
    ConditionExpression: 'source_fingerprint = :fp',
    ExpressionAttributeNames: { '#status': 'status', '#error': 'error' },
    ExpressionAttributeValues: {
      ':complete': 'complete',
      ':fp': sourceFingerprint,
      ':now': now,
    },
  }))
}

export async function failAnalysisSectionJob(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKey: AnalysisSectionKey,
  sourceFingerprint: string,
  message: string,
): Promise<void> {
  const now = new Date().toISOString()
  await docClient.send(new UpdateCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Key: { pk: cachePk(userPk), sk: analysisJobSk(asOfDate, windowKey, sectionKey) },
    UpdateExpression: 'SET #status = :errorStatus, #error = :error, updated_at = :now',
    ConditionExpression: 'source_fingerprint = :fp',
    ExpressionAttributeNames: { '#status': 'status', '#error': 'error' },
    ExpressionAttributeValues: {
      ':errorStatus': 'error',
      ':error': message.slice(0, 1000),
      ':fp': sourceFingerprint,
      ':now': now,
    },
  }))
}

export async function analysisSectionStatus<T = unknown>(
  userPk: string,
  asOfDate: string,
  windowKey: AnalysisWindowKey,
  sectionKey: AnalysisSectionKey,
  expectedSourceFingerprint?: string,
): Promise<AnalysisSectionStatus<T>> {
  const cached = await getCachedAnalysisSection<T>(userPk, asOfDate, windowKey, sectionKey, expectedSourceFingerprint)
  if (cached) {
    return {
      sectionKey,
      status: 'complete',
      generatedAt: cached.generatedAt,
      sourceFingerprint: cached.sourceFingerprint,
      cached: true,
      payload: cached.payload,
    }
  }
  const job = await getAnalysisSectionJob(userPk, asOfDate, windowKey, sectionKey)
  if (job && (!expectedSourceFingerprint || job.sourceFingerprint === expectedSourceFingerprint)) {
    return {
      sectionKey,
      status: job.status,
      updatedAt: job.updatedAt,
      error: job.error,
      sourceFingerprint: job.sourceFingerprint,
      cached: false,
    }
  }
  return { sectionKey, status: 'missing', cached: false }
}

export async function markMarkdownExportDirty(userPk: string, reason = 'session_completion'): Promise<void> {
  const now = new Date().toISOString()
  await docClient.send(new PutCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Item: {
      pk: cachePk(userPk),
      sk: 'markdown_export_dirty#current',
      reason,
      dirty_at: now,
      updated_at: now,
      expires_at: currentBlockExpiresAt(),
    },
  }))
}

export async function clearMarkdownExportDirty(userPk: string): Promise<void> {
  await docClient.send(new DeleteCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Key: { pk: cachePk(userPk), sk: 'markdown_export_dirty#current' },
  }))
}

export async function getMarkdownExportDirty(userPk: string): Promise<{ dirtyAt: string; reason: string } | null> {
  const response = await docClient.send(new GetCommand({
    TableName: ANALYSIS_CACHE_TABLE,
    Key: { pk: cachePk(userPk), sk: 'markdown_export_dirty#current' },
  }))
  const item = response.Item
  if (!item) return null
  return {
    dirtyAt: String(item.dirty_at ?? item.updated_at ?? ''),
    reason: String(item.reason ?? ''),
  }
}

// ─── Markdown export cache ─────────────────────────────────────────────────────

export async function getCachedMarkdownExport(
  userPk: string,
  blockKey = 'current',
): Promise<{ markdown: string; generatedAt: string } | null> {
  const result = await getJsonItem<{ markdown: string }>(cachePk(userPk), markdownSk(blockKey))
  if (!result) return null
  return { markdown: result.data.markdown, generatedAt: result.generatedAt }
}

export async function putCachedMarkdownExport(
  userPk: string,
  markdown: string,
  blockKey = 'current',
): Promise<void> {
  const expiry = blockKey === 'current' ? currentBlockExpiresAt() : undefined
  await putJsonItem(cachePk(userPk), markdownSk(blockKey), { markdown }, expiry)
}
