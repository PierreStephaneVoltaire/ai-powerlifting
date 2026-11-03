import type { Exercise } from '@powerlifting/types'
import { estimateSetE1rm } from './rpe'
import { normalizeExerciseName } from './volume'

export type MainLift = 'squat' | 'bench' | 'deadlift'

const BENCH_NAMES = new Set(['bench press', 'bench', 'pause bench press', 'paused bench press', 'competition bench press'])

export function mainLiftFor(name: string): MainLift | null {
  const norm = normalizeExerciseName(name)
  if (norm.includes('squat') && !norm.includes('hack') && !norm.includes('split')) return 'squat'
  if (BENCH_NAMES.has(norm)) return 'bench'
  if (norm.includes('deadlift') && !norm.includes('rdl') && !norm.includes('romanian')) return 'deadlift'
  return null
}

export function bestSetE1rm(exercise: Exercise, sessionRpe?: number | null): number | null {
  const statuses = exercise.set_statuses ?? []
  const fallbackRpe = (exercise as { rpe?: number | null }).rpe ?? sessionRpe ?? null
  const sets = exercise.sets_data?.length
    ? exercise.sets_data.map((set) => ({ kg: set.kg, reps: set.reps, rpe: set.rpe ?? fallbackRpe }))
    : [{ kg: exercise.kg, reps: exercise.reps, rpe: fallbackRpe }]
  let best: number | null = null
  sets.forEach((set, i) => {
    if (statuses[i] === 'skipped' || statuses[i] === 'pending') return
    const e1rm = estimateSetE1rm(set.kg || 0, set.reps || 0, set.rpe)?.e1rmKg ?? null
    if (e1rm != null && (best == null || e1rm > best)) best = e1rm
  })
  return best
}
