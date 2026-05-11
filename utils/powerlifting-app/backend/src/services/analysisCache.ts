import {
  BatchWriteCommand,
  DeleteCommand,
  GetCommand,
  PutCommand,
  QueryCommand,
} from '@aws-sdk/lib-dynamodb'
import { createHash } from 'crypto'
import { gzipSync, gunzipSync } from 'zlib'
import { docClient, TABLE as HEALTH_TABLE } from '../db/dynamo'
import type { Program, Session, WeekStartDay } from '@powerlifting/types'

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
  sourceFingerprint?: string
  windows: Record<AnalysisWindowKey, AnalysisWindow>
  results: Record<AnalysisWindowKey, T>
}

const CACHE_SCHEMA_VERSION = 4
const ANALYSIS_CACHE_TABLE = process.env.ANALYSIS_CACHE_TABLE_NAME || 'if-powerlifting-analysis-cache'
const CACHE_TTL_DAYS = Number.parseInt(process.env.ANALYSIS_CACHE_TTL_DAYS || '30', 10)
const MAX_INLINE_PAYLOAD_CHARS = 300_000

const WINDOW_SPECS: Array<{ key: AnalysisWindowKey; label: string; mode: number | 'current' | 'block' }> = [
  { key: 'current', label: 'Current Week', mode: 'current' },
  { key: 'previous_1', label: 'Previous Week', mode: 1 },
  { key: 'previous_2', label: 'Previous 2 Weeks', mode: 2 },
  { key: 'previous_4', label: 'Previous 4 Weeks', mode: 4 },
  { key: 'previous_8', label: 'Previous 8 Weeks', mode: 8 },
  { key: 'block', label: 'Full Block', mode: 'block' },
]

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

function minIso(a: string, b: string): string {
  return a < b ? a : b
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

export function analysisSourceFingerprint(program: Program): string {
  const sessions = (program.sessions ?? [])
    .map((session) => ({
      id: session.id ?? null,
      date: session.date,
      week: session.week,
      week_number: session.week_number,
      block: session.block ?? 'current',
      status: session.status ?? null,
      completed: Boolean(session.completed),
      updated_at: (session as unknown as Record<string, unknown>).updated_at ?? null,
      session_rpe: session.session_rpe ?? null,
      body_weight_kg: session.body_weight_kg ?? null,
      exercises: session.exercises ?? [],
      planned_exercises: session.planned_exercises ?? [],
    }))
    .sort((a, b) =>
      `${a.block}:${a.week_number}:${a.date}:${a.id ?? ''}`.localeCompare(
        `${b.block}:${b.week_number}:${b.date}:${b.id ?? ''}`,
      ),
    )

  const source = {
    meta_updated_at: program.meta?.updated_at ?? null,
    program_week_start_day: program.meta?.program_week_start_day ?? null,
    block_week_start_days: program.meta?.block_week_start_days ?? null,
    competitions: program.competitions ?? [],
    phases: program.phases ?? [],
    sessions,
  }

  return createHash('sha256').update(JSON.stringify(source)).digest('hex')
}

function cachePk(userPk: string): string {
  return `analysis#${userPk}`
}

function bundleSk(asOfDate: string): string {
  return `weekly_bundle#${asOfDate}`
}

function partSk(baseSk: string, index: number): string {
  return `${baseSk}#part#${String(index).padStart(3, '0')}`
}

function expiresAt(): number {
  const ttlDays = Number.isFinite(CACHE_TTL_DAYS) && CACHE_TTL_DAYS > 0 ? CACHE_TTL_DAYS : 30
  return Math.floor(Date.now() / 1000) + ttlDays * 24 * 60 * 60
}

function encodePayload(bundle: WeeklyAnalysisBundle): string {
  return gzipSync(Buffer.from(JSON.stringify(bundle), 'utf8')).toString('base64')
}

function decodePayload(payload: string): WeeklyAnalysisBundle {
  return JSON.parse(gunzipSync(Buffer.from(payload, 'base64')).toString('utf8')) as WeeklyAnalysisBundle
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

async function deleteHealthReportPrefix(userPk: string, prefix: string): Promise<void> {
  const keys: Array<{ pk: string; sk: string }> = []
  let ExclusiveStartKey: Record<string, unknown> | undefined
  do {
    const response = await docClient.send(new QueryCommand({
      TableName: HEALTH_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: {
        ':pk': userPk,
        ':prefix': prefix,
      },
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

  await batchDelete(HEALTH_TABLE, keys)
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

export async function getCachedWeeklyAnalysisBundle(
  userPk: string,
  asOfDate: string,
  expectedSourceFingerprint?: string,
): Promise<WeeklyAnalysisBundle | null> {
  try {
    const pk = cachePk(userPk)
    const skPrefix = `weekly_bundle#`
    
    // Query for ALL weekly bundles to find the latest
    const queryResponse = await docClient.send(new QueryCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
      ExpressionAttributeValues: {
        ':pk': pk,
        ':prefix': skPrefix,
      },
    }))
    
    const items = queryResponse.Items || []
    if (items.length === 0) return null

    // Sort by generated_at desc
    const sorted = items.sort((a, b) => {
      return String(b.generated_at || '').localeCompare(String(a.generated_at || ''))
    })
    
    const item = sorted[0]

    let payload = typeof item.payload_gzip_b64 === 'string' ? item.payload_gzip_b64 : ''
    const shardCount = Number(item.shard_count || 0)
    if (!payload && shardCount > 0) {
      const parts = await Promise.all(
        Array.from({ length: shardCount }, async (_, index) => {
          const part = await docClient.send(new GetCommand({
            TableName: ANALYSIS_CACHE_TABLE,
            Key: { pk, sk: partSk(item.sk as string, index) },
          }))
          return String(part.Item?.payload_gzip_b64 ?? '')
        }),
      )
      payload = parts.join('')
    }

    if (!payload) return null
    const bundle = decodePayload(payload)
    if (expectedSourceFingerprint && bundle.sourceFingerprint !== expectedSourceFingerprint) return null
    return { ...bundle, cached: true }
  } catch (error) {
    console.warn('Analysis cache read failed:', error)
    return null
  }
}

export async function putCachedWeeklyAnalysisBundle(userPk: string, bundle: WeeklyAnalysisBundle): Promise<void> {
  try {
    const pk = cachePk(userPk)
    const sk = bundleSk(bundle.asOfDate)
    const encoded = encodePayload({ ...bundle, cached: false })
    const expiry = expiresAt()

    await deleteBundleObject(pk, sk)

    if (encoded.length <= MAX_INLINE_PAYLOAD_CHARS) {
      await docClient.send(new PutCommand({
        TableName: ANALYSIS_CACHE_TABLE,
        Item: {
          pk,
          sk,
          as_of_date: bundle.asOfDate,
          generated_at: bundle.generatedAt,
          encoding: 'gzip+base64',
          payload_gzip_b64: encoded,
          expires_at: expiry,
        },
      }))
      return
    }

    const chunks = chunkString(encoded, MAX_INLINE_PAYLOAD_CHARS)
    await docClient.send(new PutCommand({
      TableName: ANALYSIS_CACHE_TABLE,
      Item: {
        pk,
        sk,
        as_of_date: bundle.asOfDate,
        generated_at: bundle.generatedAt,
        encoding: 'gzip+base64-sharded',
        shard_count: chunks.length,
        expires_at: expiry,
      },
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
                payload_gzip_b64: payload,
                expires_at: expiry,
              },
            },
          })),
        },
      }))
    }
  } catch (error) {
    console.warn('Analysis cache write failed:', error)
  }
}

export async function invalidateAnalysisCache(userPk: string): Promise<void> {
  try {
    const pk = cachePk(userPk)
    const keys: Array<{ pk: string; sk: string }> = []
    let ExclusiveStartKey: Record<string, unknown> | undefined
    do {
      const response = await docClient.send(new QueryCommand({
        TableName: ANALYSIS_CACHE_TABLE,
        KeyConditionExpression: 'pk = :pk AND begins_with(sk, :prefix)',
        ExpressionAttributeValues: {
          ':pk': pk,
          ':prefix': 'weekly_bundle#',
        },
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

    await batchDelete(ANALYSIS_CACHE_TABLE, keys)
  } catch (error) {
    console.warn('Analysis bundle cache invalidation failed:', error)
  }

  try {
    await Promise.all([
      deleteHealthReportPrefix(userPk, 'corr_report#'),
      deleteHealthReportPrefix(userPk, 'program_eval#'),
    ])
  } catch (error) {
    console.warn('Analysis report cache invalidation failed:', error)
  }
}

export function makeWeeklyAnalysisBundle<T>(
  asOfDate: string,
  windows: Record<AnalysisWindowKey, AnalysisWindow>,
  results: Record<AnalysisWindowKey, T>,
  sourceFingerprint?: string,
): WeeklyAnalysisBundle<T> {
  return {
    schemaVersion: CACHE_SCHEMA_VERSION,
    asOfDate,
    generatedAt: new Date().toISOString(),
    cached: false,
    sourceFingerprint,
    windows,
    results,
  }
}
