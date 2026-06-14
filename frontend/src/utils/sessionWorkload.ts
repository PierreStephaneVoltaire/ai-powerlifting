import type { GlossaryExercise, MuscleGroup, Session } from '@powerlifting/types'
import { executedSets, normalizeExerciseName } from './volume'

type WorkoutEntry = Pick<Session['exercises'][number], 'name' | 'sets' | 'set_statuses' | 'reps' | 'kg'>

export const MUSCLE_CONTRIBUTION_MULTIPLIERS = {
  primary: 1,
  secondary: 0.5,
  tertiary: 0.25,
} as const

interface MuscleContribution {
  primary: MuscleGroup[]
  secondary: MuscleGroup[]
  tertiary: MuscleGroup[]
}

function buildGlossaryLookup(glossary: GlossaryExercise[]): Map<string, MuscleContribution> {
  const lookup = new Map<string, MuscleContribution>()
  for (const ex of glossary) {
    lookup.set(normalizeExerciseName(ex.name), {
      primary: ex.primary_muscles,
      secondary: ex.secondary_muscles,
      tertiary: ex.tertiary_muscles ?? [],
    })
  }
  return lookup
}

function addWeightedSets(
  volumes: Partial<Record<MuscleGroup, number>>,
  muscles: MuscleGroup[],
  sets: number,
  multiplier: number
) {
  for (const muscle of muscles) {
    volumes[muscle] = (volumes[muscle] ?? 0) + sets * multiplier
  }
}

export function sessionMuscleSets(
  entries: WorkoutEntry[],
  glossary: GlossaryExercise[]
): Partial<Record<MuscleGroup, number>> {
  const lookup = buildGlossaryLookup(glossary)
  const volumes: Partial<Record<MuscleGroup, number>> = {}

  for (const ex of entries) {
    const muscles = lookup.get(normalizeExerciseName(ex.name))
    if (!muscles) continue

    const sets = executedSets(ex)
    if (sets <= 0) continue

    addWeightedSets(volumes, muscles.primary, sets, MUSCLE_CONTRIBUTION_MULTIPLIERS.primary)
    addWeightedSets(volumes, muscles.secondary, sets, MUSCLE_CONTRIBUTION_MULTIPLIERS.secondary)
    addWeightedSets(volumes, muscles.tertiary, sets, MUSCLE_CONTRIBUTION_MULTIPLIERS.tertiary)
  }

  return volumes
}

export function sessionEntriesFromSession(session: Session): WorkoutEntry[] {
  return session.exercises.length > 0 ? session.exercises : session.planned_exercises ?? []
}
