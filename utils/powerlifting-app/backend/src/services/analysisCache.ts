import {
  BatchWriteCommand,
  GetCommand,
  PutCommand,
  QueryCommand,
} from '@aws-sdk/lib-dynamodb'
import { docClient } from '../db/dynamo'
import type { Program, Session, WeightEntry } from '@powerlifting/types'

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

export interface WeeklyAnalysisBundle<T = unknown> {
  schemaVersion: number
  asOfDate: string
  generatedAt: string
  cached: boolean
  windows: Record<AnalysisWindowKey, AnalysisWindow>
  results: Record<AnalysisWindowKey, T>
}

const CACHE_SCHEMA_VERSION = 5
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

/** SK for a weekly analysis window on the current block. */
function windowSk(windowKey: AnalysisWindowKey): string {
  return `weekly_analysis#${windowKey}`
}

/** SK for a cached markdown export. blockKey defaults to 'current'. */
function markdownSk(blockKey = 'current'): string {
  return `markdown_export#${blockKey}`
}

/** SK segment for a shard of a large payload. */
function shardSk(baseSk: string, index: number): string {
  return `${baseSk}#shard#${String(index).padStart(3, '0')}`
}

function currentBlockExpiresAt(): number {
  return Math.floor(Date.now() / 1000) + CACHE_TTL_DAYS * 24 * 60 * 60
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

/**
 * Write a JSON-serialisable value to DynamoDB.
 * Shards the payload if it exceeds MAX_SHARD_CHARS.
 * expiresAt is only set for current-block items (undefined = no TTL = permanent past-block storage).
 */
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

/** Read a JSON item that may be sharded. Returns null on miss or parse error. */
async function getJsonItem<T>(pk: string, sk: string): Promise<{ data: T; generatedAt: string } | null> {
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
      return { data: JSON.parse(joined) as T, generatedAt }
    }

    // Inline item
    const payload = item.payload
    if (typeof payload !== 'string' || !payload) return null
    return { data: JSON.parse(payload) as T, generatedAt }
  } catch {
    return null
  }
}

// ─── Window analysis cache (current block only) ───────────────────────────────

/**
 * Read a single analysis window from cache.
 * Returns the window result and generatedAt, or null on miss.
 */
export async function getCachedWindowAnalysis(
  userPk: string,
  windowKey: AnalysisWindowKey,
): Promise<{ data: unknown; generatedAt: string } | null> {
  return getJsonItem(cachePk(userPk), windowSk(windowKey))
}

/**
 * Read all 6 window analyses from cache.
 * Returns null if ANY window is missing (treat as full cache miss).
 */
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

/**
 * Write all 6 window analyses to cache with 7-day TTL.
 * Past-block caches are handled separately by blockAnalytics.ts.
 */
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

// ─── Markdown export cache ─────────────────────────────────────────────────────

/**
 * Read the cached markdown export.
 * blockKey defaults to 'current'. Returns null on miss.
 */
export async function getCachedMarkdownExport(
  userPk: string,
  blockKey = 'current',
): Promise<{ markdown: string; generatedAt: string } | null> {
  const result = await getJsonItem<{ markdown: string }>(cachePk(userPk), markdownSk(blockKey))
  if (!result) return null
  return { markdown: result.data.markdown, generatedAt: result.generatedAt }
}

/**
 * Write the markdown export to cache.
 * Current block uses 7-day TTL; past blocks are permanent.
 */
export async function putCachedMarkdownExport(
  userPk: string,
  markdown: string,
  blockKey = 'current',
): Promise<void> {
  const expiry = blockKey === 'current' ? currentBlockExpiresAt() : undefined
  await putJsonItem(cachePk(userPk), markdownSk(blockKey), { markdown }, expiry)
}
