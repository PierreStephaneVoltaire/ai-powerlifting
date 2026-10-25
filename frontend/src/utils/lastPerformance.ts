import type { Exercise, Session } from '@powerlifting/types'
import { normalizeExerciseName } from './volume'

const LOOKBACK_DAYS = 28

export type PerformedSet = { reps: number | null; kg: number | null }

export type SetGroup = { sets: number; reps: number | null; kg: number | null }

function blockKey(session: Pick<Session, 'block_id' | 'block'>): string {
  return String(session.block_id || session.block || 'current')
}

function shiftDays(date: string, days: number): string {
  const value = new Date(`${date}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}

function performedSets(exercise: Exercise): PerformedSet[] {
  const statuses = exercise.set_statuses ?? []
  const sets = exercise.sets_data?.length
    ? exercise.sets_data.map((set) => ({ reps: set.reps, kg: set.kg }))
    : Array.from({ length: exercise.sets || 0 }, () => ({ reps: exercise.reps, kg: exercise.kg }))
  return sets.filter((set, i) => statuses[i] !== 'skipped' && statuses[i] !== 'pending' && (set.reps ?? 0) > 0)
}

export function groupSets(sets: PerformedSet[]): SetGroup[] {
  const groups: SetGroup[] = []
  for (const set of sets) {
    const last = groups.at(-1)
    if (last && last.reps === set.reps && last.kg === set.kg) last.sets += 1
    else groups.push({ sets: 1, reps: set.reps, kg: set.kg })
  }
  return groups
}

export function lastPerformance(sessions: Session[], current: Session, exerciseName: string): { date: string; groups: SetGroup[] } | null {
  const name = normalizeExerciseName(exerciseName)
  const block = blockKey(current)
  const earliest = shiftDays(current.date, -LOOKBACK_DAYS)
  let latest: { date: string; groups: SetGroup[] } | null = null
  for (const session of sessions) {
    if (session === current || (current.id && session.id === current.id)) continue
    if (blockKey(session) !== block || session.date >= current.date || session.date < earliest) continue
    if (latest && session.date <= latest.date) continue
    const sets = session.exercises
      .filter((exercise) => normalizeExerciseName(exercise.name) === name)
      .flatMap(performedSets)
    if (sets.length) latest = { date: session.date, groups: groupSets(sets) }
  }
  return latest
}
