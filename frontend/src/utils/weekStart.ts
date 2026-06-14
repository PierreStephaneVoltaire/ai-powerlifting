import { addDays, differenceInCalendarDays, format } from 'date-fns'
import type { Program, Session, WeekStartDay } from '@powerlifting/types'
import { parseLocalDate } from './dates'

export const WEEK_START_DAYS: WeekStartDay[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

const DAY_INDEX: Record<WeekStartDay, number> = {
  Monday: 0,
  Tuesday: 1,
  Wednesday: 2,
  Thursday: 3,
  Friday: 4,
  Saturday: 5,
  Sunday: 6,
}

function isWeekStartDay(value: unknown): value is WeekStartDay {
  return typeof value === 'string' && WEEK_START_DAYS.includes(value as WeekStartDay)
}

export function normalizeWeekStartDay(value: unknown, fallback: WeekStartDay): WeekStartDay {
  return isWeekStartDay(value) ? value : fallback
}

export function weekStartForBlock(program: Program | null | undefined, block = 'current'): WeekStartDay {
  const blockValue = block || 'current'
  const stored = program?.meta?.block_week_start_days?.[blockValue]
  if (isWeekStartDay(stored)) return stored
  return 'Monday'
}

export function programWeekAnchorDate(programStart: string | undefined, weekStartDay: WeekStartDay): string {
  const start = programStart || format(new Date(), 'yyyy-MM-dd')
  const parsed = parseLocalDate(start)
  const currentIndex = (parsed.getDay() + 6) % 7
  const offset = (currentIndex - DAY_INDEX[weekStartDay] + 7) % 7
  return format(addDays(parsed, -offset), 'yyyy-MM-dd')
}

export function programWeekStartDate(
  programStart: string | undefined,
  week: number,
  weekStartDay: WeekStartDay,
): string {
  const anchor = programWeekAnchorDate(programStart, weekStartDay)
  return format(addDays(parseLocalDate(anchor), (Math.max(1, week) - 1) * 7), 'yyyy-MM-dd')
}

export function programWeekEndDate(
  programStart: string | undefined,
  week: number,
  weekStartDay: WeekStartDay,
): string {
  return format(addDays(parseLocalDate(programWeekStartDate(programStart, week, weekStartDay)), 6), 'yyyy-MM-dd')
}

export function trainingWeekForDate(
  dateStr: string,
  programStart: string | undefined,
  weekStartDay: WeekStartDay,
): number {
  const anchor = programWeekAnchorDate(programStart, weekStartDay)
  const days = differenceInCalendarDays(parseLocalDate(dateStr), parseLocalDate(anchor))
  return Math.max(1, Math.floor(days / 7) + 1)
}

export function trainingWeekStartForDate(
  dateStr: string,
  programStart: string | undefined,
  weekStartDay: WeekStartDay,
): string {
  const week = trainingWeekForDate(dateStr, programStart, weekStartDay)
  return programWeekStartDate(programStart, week, weekStartDay)
}

function parseWeekNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

export function resolveTrainingWeekForDate(
  dateStr: string,
  programStart: string | undefined,
  weekStartDay: WeekStartDay,
  sessions: Session[] = [],
  block = 'current',
): number {
  const calculatedWeek = trainingWeekForDate(dateStr, programStart, weekStartDay)
  const calculatedStart = programWeekStartDate(programStart, calculatedWeek, weekStartDay)
  const calculatedEnd = format(addDays(parseLocalDate(calculatedStart), 6), 'yyyy-MM-dd')
  const dueWeekNumbers = sessions
    .filter((session) => (session.block ?? 'current') === block)
    .filter((session) =>
      session.date >= calculatedStart &&
      session.date <= calculatedEnd &&
      session.date <= dateStr
    )
    .map((session) => parseWeekNumber(session.week_number))
    .filter((week): week is number => week !== null)

  return dueWeekNumbers.length ? Math.max(...dueWeekNumbers) : calculatedWeek
}
