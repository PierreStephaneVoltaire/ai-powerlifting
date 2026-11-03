import type { PlannedExercise, PlannedSet } from '@powerlifting/types'

export function repsLabel(reps: number | null | undefined, repsMax?: number | null): string {
  const low = reps ?? '?'
  return repsMax != null && reps != null && repsMax > reps ? `${low}-${repsMax}` : `${low}`
}

export function plannedSets(exercise: PlannedExercise): PlannedSet[] {
  if (exercise.set_plan?.length) return exercise.set_plan
  const count = Math.max(0, Math.round(Number(exercise.sets) || 0))
  return Array.from({ length: count }, () => ({
    reps: exercise.reps,
    reps_max: exercise.reps_max ?? null,
    kg: exercise.kg,
    rpe_target: exercise.rpe_target ?? null,
  }))
}

export function hasRepRange(exercise: PlannedExercise): boolean {
  return exercise.reps_max != null || (exercise.set_plan ?? []).some((set) => set.reps_max != null)
}

function sameSet(a: PlannedSet, b: PlannedSet): boolean {
  return a.reps === b.reps && (a.reps_max ?? null) === (b.reps_max ?? null) && a.kg === b.kg && (a.rpe_target ?? null) === (b.rpe_target ?? null)
}

function loadLabel(set: Pick<PlannedSet, 'kg' | 'rpe_target'>, formatLoad: (kg: number) => string): string {
  if (set.kg !== null) return ` @${formatLoad(set.kg)}`
  return set.rpe_target != null ? ` @RPE ${set.rpe_target}` : ''
}

export function formatPlannedExercise(exercise: PlannedExercise, formatLoad: (kg: number) => string): string {
  if (!exercise.set_plan?.length) {
    return `${exercise.sets}x${repsLabel(exercise.reps, exercise.reps_max)}${loadLabel(exercise, formatLoad)}`
  }
  const groups: { count: number; set: PlannedSet }[] = []
  for (const set of exercise.set_plan) {
    const last = groups[groups.length - 1]
    if (last && sameSet(last.set, set)) last.count += 1
    else groups.push({ count: 1, set })
  }
  return groups
    .map(({ count, set }) => `${count}x${repsLabel(set.reps, set.reps_max)}${loadLabel(set, formatLoad)}`)
    .join(', ')
}
