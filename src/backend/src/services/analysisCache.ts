import { valkey } from '../utils/valkey'
import type { Program } from '@powerlifting/types'

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

interface AnalysisWindow {
  key: AnalysisWindowKey
  label: string
  start: string
  end: string
  weekStart: number
  weekEnd: number
  weeks: number
  currentWeek: number
}

interface WeeklyAnalysisBundle<T = unknown> {
  schemaVersion: number
  asOfDate: string
  generatedAt: string
  cached: boolean
  windows: Record<AnalysisWindowKey, AnalysisWindow>
  results: Record<AnalysisWindowKey, T>
}

export const CACHE_SCHEMA_VERSION = 5
const SECTION_CACHE_SCHEMA_VERSION = 4

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
export const DETERMINISTIC_SECTION_KEYS: AnalysisSectionKey[] = [
  'overview',
  'fatigue_readiness',
  'peaking',
  'workload',
  'alerts',
]
const AI_SECTION_KEYS: AnalysisSectionKey[] = ['ai_correlation', 'program_evaluation']
export const ALL_SECTION_KEYS: AnalysisSectionKey[] = [...DETERMINISTIC_SECTION_KEYS, ...AI_SECTION_KEYS]

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

function activeBlockId(program: Program): string | null {
  const meta = program.meta
  if (meta?.current_block_id) return meta.current_block_id
  const active = (meta?.blocks ?? []).find((candidate) => candidate?.status === 'active')
  const id = String(active?.id ?? active?.block_id ?? '')
  return id && id !== 'current' ? id : null
}

function weekStartForBlock(program: Program, block = 'current'): WeekStartDay {
  const blockValue = block || 'current'
  const blockId = blockValue === 'current' ? activeBlockId(program) ?? 'current' : blockValue
  const blockRecord = (program.meta?.blocks ?? []).find((candidate) => String(candidate?.id ?? candidate?.block_id ?? '') === blockId)
  return normalizeWeekStartDay(blockRecord?.week_start_day, 'Monday')
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

function maxIso(a: string, b: string | undefined): string {
  return b !== undefined && b > a ? b : a
}

function minIso(a: string, b: string | undefined): string {
  return b !== undefined && b < a ? b : a
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
  const currentBlock = (program.meta?.blocks ?? []).find((candidate) => candidate?.status === 'active')
  const programStart = currentBlock?.start_date || program.meta?.program_start || sessions.find((session) => (session.block ?? 'current') === 'current')?.date || asOfDate
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

    const labelledDates = sessions
      .filter((session) => (session.block ?? 'current') === 'current' && session.date <= asOfDate)
      .filter((session) => {
        const week = parseWeekNumber(session.week_number)
        return week !== null && week >= weekStart && week <= weekEnd
      })
      .map((session) => session.date)
      .sort()
    const weekStartDate = minIso(programWeekStartDate(programStart, weekStart, weekStartDay), labelledDates[0])
    const weekEndDate = maxIso(addDaysIso(programWeekStartDate(programStart, weekEnd, weekStartDay), 6), labelledDates[labelledDates.length - 1])
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


export async function analysisVersion(pk: string): Promise<string> {
  return (await (await valkey()).get(`pl:analysis-version:${pk}`)) ?? '0'
}

export function analysisSourceKey(version: string, window: { start?: string; end?: string }): string {
  return `s${SECTION_CACHE_SCHEMA_VERSION}-v${version}-${window.start ?? ''}-${window.end ?? ''}`
}
