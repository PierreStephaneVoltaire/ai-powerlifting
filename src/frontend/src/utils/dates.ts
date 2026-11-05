import { format, differenceInDays, parse } from 'date-fns'
import type { Session } from '@powerlifting/types'

export const parseLocalDate = (dateStr: string): Date =>
  parse(dateStr, 'yyyy-MM-dd', new Date())
export const formatDateShort = (dateStr: string): string =>
  format(parseLocalDate(dateStr), 'MMM d')

export const daysUntil = (dateStr: string): number =>
  differenceInDays(parseLocalDate(dateStr), new Date())
export const getDayOfWeek = (dateStr: string): string =>
  format(parseLocalDate(dateStr), 'EEEE')

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
