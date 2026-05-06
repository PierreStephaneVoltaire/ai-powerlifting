import { format, differenceInDays, parse, startOfWeek, endOfWeek, isWithinInterval } from 'date-fns'
import type { Session } from '@powerlifting/types'

/**
 * Parse a date string (yyyy-MM-dd) as local time, not UTC.
 * This avoids the timezone shift issue where parseISO would show
 * the wrong day in certain timezones.
 */
export const parseLocalDate = (dateStr: string): Date =>
  parse(dateStr, 'yyyy-MM-dd', new Date())

export const formatDate = (dateStr: string): string =>
  format(parseLocalDate(dateStr), 'EEE MMM d')

export const formatDateLong = (dateStr: string): string =>
  format(parseLocalDate(dateStr), 'EEEE, MMMM d, yyyy')

export const formatDateShort = (dateStr: string): string =>
  format(parseLocalDate(dateStr), 'MMM d')

export const daysUntil = (dateStr: string): number =>
  differenceInDays(parseLocalDate(dateStr), new Date())

export const isToday = (dateStr: string): boolean =>
  format(new Date(), 'yyyy-MM-dd') === dateStr

export const isPast = (dateStr: string): boolean =>
  parseLocalDate(dateStr) < new Date()

export const isFuture = (dateStr: string): boolean =>
  parseLocalDate(dateStr) > new Date()

export const currentProgramWeek = (programStart: string): number => {
  const days = differenceInDays(new Date(), parseLocalDate(programStart))
  return Math.max(1, Math.floor(days / 7) + 1)
}

export const getDayOfWeek = (dateStr: string): string =>
  format(parseLocalDate(dateStr), 'EEEE')

export const getWeekNumber = (dateStr: string, programStart: string): number => {
  const days = differenceInDays(parseLocalDate(dateStr), parseLocalDate(programStart))
  return Math.max(1, Math.floor(days / 7) + 1)
}

export function sessionsThisCalendarWeek(sessions: Session[]): Session[] {
  const now = new Date()
  const weekStart = startOfWeek(now, { weekStartsOn: 0 })
  const weekEnd = endOfWeek(now, { weekStartsOn: 0 })

  return sessions.filter(s => {
    const sessionDate = parseLocalDate(s.date)
    return isWithinInterval(sessionDate, { start: weekStart, end: weekEnd })
  })
}

export function sessionsInDateRange(
  sessions: Session[],
  startDate: string,
  endDate: string
): Session[] {
  return sessions.filter(s => s.date >= startDate && s.date <= endDate)
}

export function findClosestSessionToToday(sessions: Session[]): Session | null {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  let closest: { session: Session; distanceMs: number } | null = null

  for (const session of sessions) {
    const sessionDate = parseLocalDate(session.date)
    const sessionTime = sessionDate.getTime()
    if (!Number.isFinite(sessionTime)) continue

    sessionDate.setHours(0, 0, 0, 0)
    const distanceMs = Math.abs(sessionDate.getTime() - today.getTime())

    if (!closest || distanceMs < closest.distanceMs) {
      closest = { session, distanceMs }
    }
  }

  return closest?.session ?? null
}

export function groupSessionsByWeek(sessions: Session[], block?: string): Map<number, Session[]> {
  const groups = new Map<number, Session[]>()

  for (const session of sessions) {
    if (block && (session.block || 'current') !== block) continue
    const week = session.week_number
    if (!groups.has(week)) {
      groups.set(week, [])
    }
    groups.get(week)!.push(session)
  }

  // Sort sessions within each week by date
  for (const [_, weekSessions] of groups) {
    weekSessions.sort((a, b) => a.date.localeCompare(b.date))
  }

  return groups
}
