import crypto from 'crypto'
import { invokeLambda } from '../utils/lambda'
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

export const CACHE_SCHEMA_VERSION = 5
export const SECTION_CACHE_SCHEMA_VERSION = 2
// Current-block window caches expire after 7 days. Past-block caches have no TTL.
// Shard size: keep individual DynamoDB string attributes under 400KB.
// ~350_000 JSON chars is a safe ceiling before sharding kicks in.

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

const DETERMINISTIC_SECTION_SET = new Set(DETERMINISTIC_SECTION_KEYS)
const ALL_WINDOW_KEY_SET = new Set(ALL_WINDOW_KEYS)
const ALL_SECTION_KEY_SET = new Set(ALL_SECTION_KEYS)

export function normalizeAnalysisWindowKey(value: unknown): AnalysisWindowKey {
  return typeof value === 'string' && ALL_WINDOW_KEY_SET.has(value as AnalysisWindowKey)
    ? value as AnalysisWindowKey
    : 'current'
}

export function normalizeAnalysisSectionKeys(
  value: unknown,
  fallback: AnalysisSectionKey[] = ALL_SECTION_KEYS,
): AnalysisSectionKey[] {
  if (!Array.isArray(value)) return fallback
  const filtered = value.filter((v): v is AnalysisSectionKey => typeof v === 'string' && ALL_SECTION_KEY_SET.has(v as AnalysisSectionKey))
  return filtered.length ? filtered : fallback
}

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
  const items = (await invokeLambda('goals_list', { pk })) as Record<string, unknown>[]
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
