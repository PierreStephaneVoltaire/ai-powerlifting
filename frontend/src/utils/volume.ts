import type { Session, Exercise, GlossaryExercise, MuscleGroup } from '@powerlifting/types'

export type LiftCategory = 'squat' | 'bench' | 'deadlift' | 'back' | 'chest' | 'arm' | 'legs' | 'core' | 'lower_back'

const ALL_CATEGORIES: LiftCategory[] = ['squat', 'bench', 'deadlift', 'back', 'chest', 'arm', 'legs', 'core', 'lower_back']

function zeroCategoryRecord(): Record<LiftCategory, number> {
  return { squat: 0, bench: 0, deadlift: 0, back: 0, chest: 0, arm: 0, legs: 0, core: 0, lower_back: 0 }
}

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

export function sessionVolume(session: Session): number {
  return session.exercises.reduce((sum, ex) => sum + exerciseVolume(ex), 0)
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



export function volumeByCategory(
  sessions: Session[],
  glossary: GlossaryExercise[],
  block?: string
): Record<LiftCategory, number> {
  const result = zeroCategoryRecord()
  const lookup = buildCategoryLookup(glossary)

  for (const session of filterByBlock(sessions, block)) {
    for (const ex of session.exercises) {
      const vol = exerciseVolume(ex)
      result[categorizeExercise(ex.name, lookup)] += vol
    }
  }

  return result
}

export function weeklyVolumeByCategory(
  sessions: Session[],
  glossary: GlossaryExercise[],
  block?: string
): Array<{ week: number; squat: number; bench: number; deadlift: number; back: number; chest: number; arm: number; legs: number; core: number; lower_back: number }> {
  const weekMap = new Map<number, Record<LiftCategory, number>>()
  const lookup = buildCategoryLookup(glossary)

  for (const session of filterByBlock(sessions, block)) {
    const week = session.week_number
    if (!weekMap.has(week)) {
      weekMap.set(week, zeroCategoryRecord())
    }
    const weekData = weekMap.get(week)!

    for (const ex of session.exercises) {
      const vol = exerciseVolume(ex)
      weekData[categorizeExercise(ex.name, lookup)] += vol
    }
  }

  return Array.from(weekMap.entries())
    .map(([week, data]) => ({ week, ...data }))
    .sort((a, b) => a.week - b.week)
}

export function weeklyVolumeByBig3(
  sessions: Session[],
  glossary: GlossaryExercise[],
  block?: string
): Array<{ week: number; squat: number; bench: number; deadlift: number; accessory: number }> {
  const weekMap = new Map<number, { squat: number; bench: number; deadlift: number; accessory: number }>()
  const lookup = buildCategoryLookup(glossary)

  for (const session of filterByBlock(sessions, block)) {
    const week = session.week_number
    if (!weekMap.has(week)) {
      weekMap.set(week, { squat: 0, bench: 0, deadlift: 0, accessory: 0 })
    }
    const weekData = weekMap.get(week)!

    for (const ex of session.exercises) {
      const vol = exerciseVolume(ex)
      const cat = categorizeExercise(ex.name, lookup)
      if (cat === 'squat' || cat === 'bench' || cat === 'deadlift') {
        weekData[cat] += vol
      } else {
        weekData.accessory += vol
      }
    }
  }

  return Array.from(weekMap.entries())
    .map(([week, data]) => ({ week, ...data }))
    .sort((a, b) => a.week - b.week)
}

export function volumeByBig3(
  sessions: Session[],
  glossary: GlossaryExercise[],
  block?: string
): Record<string, number> {
  const result = { squat: 0, bench: 0, deadlift: 0, accessory: 0 }
  const lookup = buildCategoryLookup(glossary)

  for (const session of filterByBlock(sessions, block)) {
    for (const ex of session.exercises) {
      const vol = exerciseVolume(ex)
      const cat = categorizeExercise(ex.name, lookup)
      if (cat === 'squat' || cat === 'bench' || cat === 'deadlift') {
        result[cat] += vol
      } else {
        result.accessory += vol
      }
    }
  }

  return result
}


function buildGlossaryLookup(
  glossary: GlossaryExercise[]
): Map<string, { primary: MuscleGroup[]; secondary: MuscleGroup[]; tertiary: MuscleGroup[] }> {
  const lookup = new Map<string, { primary: MuscleGroup[]; secondary: MuscleGroup[]; tertiary: MuscleGroup[] }>()
  for (const ex of glossary) {
    const key = normalizeExerciseName(ex.name)
    lookup.set(key, {
      primary: ex.primary_muscles,
      secondary: ex.secondary_muscles,
      tertiary: ex.tertiary_muscles ?? [],
    })
  }
  return lookup
}

export function volumeByMuscleGroup(
  sessions: Session[],
  glossary: GlossaryExercise[],
  block?: string
): Record<string, number> {
  const lookup = buildGlossaryLookup(glossary)
  const volumes: Record<string, number> = {}

  for (const session of filterByBlock(sessions, block)) {
    for (const ex of session.exercises) {
      const muscles = lookup.get(normalizeExerciseName(ex.name))
      if (!muscles || ex.kg === null) continue

      const vol = exerciseVolume(ex)

      for (const m of muscles.primary) {
        volumes[m] = (volumes[m] ?? 0) + vol
      }
      for (const m of muscles.secondary) {
        volumes[m] = (volumes[m] ?? 0) + vol * 0.5
      }
      for (const m of muscles.tertiary) {
        volumes[m] = (volumes[m] ?? 0) + vol * 0.25
      }
    }
  }

  return volumes
}

export function weeklySetsByMuscleGroup(
  sessions: Session[],
  glossary: GlossaryExercise[],
  block?: string
): Array<Record<string, number>> {
  const lookup = buildGlossaryLookup(glossary)
  const weekMap = new Map<number, Record<string, number>>()

  // Collect all muscle group names from the glossary
  const allMuscles = new Set<string>()
  for (const ex of glossary) {
    for (const m of ex.primary_muscles) allMuscles.add(m)
    for (const m of ex.secondary_muscles) allMuscles.add(m)
    for (const m of ex.tertiary_muscles ?? []) allMuscles.add(m)
  }

  for (const session of filterByBlock(sessions, block)) {
    const week = session.week_number
    if (!weekMap.has(week)) {
      weekMap.set(week, { week })
    }
    const weekData = weekMap.get(week)!

    for (const ex of session.exercises) {
      const muscles = lookup.get(normalizeExerciseName(ex.name))
      if (!muscles) continue

      const sets = executedSets(ex)

      for (const m of muscles.primary) {
        weekData[m] = (weekData[m] ?? 0) + sets
      }
      for (const m of muscles.secondary) {
        weekData[m] = (weekData[m] ?? 0) + sets * 0.5
      }
      for (const m of muscles.tertiary) {
        weekData[m] = (weekData[m] ?? 0) + sets * 0.25
      }
    }
  }

  return Array.from(weekMap.values())
    .sort((a, b) => (a.week as number) - (b.week as number))
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

export function weeklyVolumeByMuscleGroup(
  sessions: Session[],
  glossary: GlossaryExercise[],
  block?: string
): Array<Record<string, number>> {
  const lookup = buildGlossaryLookup(glossary)
  const weekMap = new Map<number, Record<string, number>>()

  for (const session of filterByBlock(sessions, block)) {
    const week = session.week_number
    if (!weekMap.has(week)) {
      weekMap.set(week, { week })
    }
    const weekData = weekMap.get(week)!

    for (const ex of session.exercises) {
      const muscles = lookup.get(normalizeExerciseName(ex.name))
      if (!muscles || ex.kg === null) continue

      const vol = exerciseVolume(ex)

      for (const m of muscles.primary) {
        weekData[m] = (weekData[m] ?? 0) + vol
      }
      for (const m of muscles.secondary) {
        weekData[m] = (weekData[m] ?? 0) + vol * 0.5
      }
      for (const m of muscles.tertiary) {
        weekData[m] = (weekData[m] ?? 0) + vol * 0.25
      }
    }
  }

  return Array.from(weekMap.values())
    .sort((a, b) => (a.week as number) - (b.week as number))
}
