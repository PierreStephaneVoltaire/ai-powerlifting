import type { Session, Exercise, GlossaryExercise } from '@powerlifting/types'

export type LiftCategory = 'squat' | 'bench' | 'deadlift' | 'back' | 'chest' | 'arm' | 'legs' | 'core' | 'lower_back'

export function executedSets(ex: Pick<Exercise, 'sets' | 'set_statuses'>): number {
  if (ex.set_statuses?.length) {
    return ex.set_statuses.filter((status) => status === 'completed' || status === 'failed').length
  }
  return Number(ex.sets) || 0
}

export function exerciseVolume(ex: Exercise): number {
  const sets = executedSets(ex)
  if (!ex.kg || !sets || !ex.reps) return 0
  return sets * ex.reps * ex.kg
}

function singularize(word: string): string {
  if (word.endsWith('sses') || word.endsWith('ches') || word.endsWith('shes') || word.endsWith('xes')) {
    return word.slice(0, -2)
  }
  if (word.endsWith('s') && !word.endsWith('ss')) {
    return word.slice(0, -1)
  }
  return word
}

export function normalizeExerciseName(name: string): string {
  const stripped = name.replace(/\s*\(.*?\)\s*/g, ' ').trim().toLowerCase()
  return stripped.split(/\s+/).map(singularize).join(' ')
}

function buildCategoryLookup(glossary: GlossaryExercise[]): Map<string, LiftCategory> {
  const lookup = new Map<string, LiftCategory>()
  for (const ex of glossary) {
    lookup.set(normalizeExerciseName(ex.name), ex.category)
  }
  return lookup
}

export function categorizeExercise(name: string, glossaryLookup: Map<string, LiftCategory>): LiftCategory {
  const norm = normalizeExerciseName(name)
  return glossaryLookup.get(norm) ?? 'arm'
}

function filterByBlock(sessions: Session[], block?: string): Session[] {
  if (!block || block === '*') return sessions
  return sessions.filter((s) => (s.block || 'current') === block)
}


export function allTimeMaxByExercise(
  sessions: Session[],
  block?: string
): Map<string, { kg: number; displayName: string }> {
  const maxes = new Map<string, { kg: number; displayName: string }>()

  for (const session of filterByBlock(sessions, block)) {
    if (!session.completed) continue
    for (const ex of session.exercises) {
      if (ex.kg == null || executedSets(ex) <= 0) continue
      const key = normalizeExerciseName(ex.name)
      const existing = maxes.get(key)
      if (!existing || ex.kg > existing.kg) {
        maxes.set(key, { kg: ex.kg, displayName: ex.name })
      }
    }
  }

  return maxes
}

export function maxByCategoryInWindow(
  sessions: Session[],
  glossary: GlossaryExercise[],
  startDate: string,
  endDate: string,
  categories: LiftCategory[] = ['squat', 'bench', 'deadlift'],
  block?: string
): Record<string, number> {
  const result: Record<string, number> = {}
  for (const cat of categories) result[cat] = 0
  const lookup = buildCategoryLookup(glossary)

  for (const session of filterByBlock(sessions, block)) {
    if (!session.completed) continue
    if (session.date < startDate || session.date > endDate) continue
    for (const ex of session.exercises) {
      if (ex.kg == null || executedSets(ex) <= 0) continue
      const cat = categorizeExercise(ex.name, lookup)
      if (cat in result && ex.kg > result[cat]) {
        result[cat] = ex.kg
      }
    }
  }

  return result
}
