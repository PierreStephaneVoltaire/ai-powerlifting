import type { Session, Exercise, GlossaryExercise, MuscleGroup } from '@powerlifting/types'

export type LiftCategory = 'squat' | 'bench' | 'deadlift' | 'back' | 'chest' | 'arm' | 'legs' | 'core' | 'lower_back'

const ALL_CATEGORIES: LiftCategory[] = ['squat', 'bench', 'deadlift', 'back', 'chest', 'arm', 'legs', 'core', 'lower_back']

function zeroCategoryRecord(): Record<LiftCategory, number> {
  return { squat: 0, bench: 0, deadlift: 0, back: 0, chest: 0, arm: 0, legs: 0, core: 0, lower_back: 0 }
}

/**
 * Calculate volume (sets * reps * kg) for a single exercise.
 */
export function executedSets(ex: Pick<Exercise, 'sets' | 'set_statuses'>): number {
  if (ex.set_statuses?.length) {
    return ex.set_statuses.filter((status) => status === 'completed' || status === 'failed').length
  }
  return ex.sets || 0
}

export function exerciseVolume(ex: Exercise): number {
  const sets = executedSets(ex)
  if (!ex.kg || !sets || !ex.reps) return 0
  return sets * ex.reps * ex.kg
}

/**
 * Calculate total volume for a session.
 */
export function sessionVolume(session: Session): number {
  return session.exercises.reduce((sum, ex) => sum + exerciseVolume(ex), 0)
}

/**
 * Map exercise names to lift categories (8-category system).
 */
const LIFT_CATEGORY_MAP: Record<string, LiftCategory> = {
  // ─── Squat ──────────────────────────────────────────────────────
  'Squat': 'squat',
  'Squat (Backout Heavy)': 'squat',
  'Squat (Backout Light)': 'squat',
  'Back Squat': 'squat',
  'Front Squat': 'squat',
  'Box Squat': 'squat',
  'Pause Squat': 'squat',
  'Tempo Squat': 'squat',
  'Safety Bar Squat': 'squat',
  'Hack Squat': 'squat',

  // ─── Bench ──────────────────────────────────────────────────────
  'Bench Press': 'bench',
  'Bench Press (Backout)': 'bench',
  'Pause Bench Press': 'bench',
  'Spoto Press': 'bench',
  'Close-Grip Bench Press': 'bench',
  'Wide-Grip Bench Press': 'bench',
  'Floor Press': 'bench',
  'Incline Bench Press': 'bench',

  // ─── Deadlift ───────────────────────────────────────────────────
  'Deadlift': 'deadlift',
  'Deadlift (Backout)': 'deadlift',
  'Conventional Deadlift': 'deadlift',
  'Sumo Deadlift': 'deadlift',
  'Stiff-Leg Deadlift': 'deadlift',
  'Deficit Deadlift': 'deadlift',
  'Rack Pull': 'deadlift',
  'Block Pull': 'deadlift',

  // ─── Back ───────────────────────────────────────────────────────
  'Lat Pulldown': 'back',
  'Row': 'back',
  'Barbell Row': 'back',
  'DB Row': 'back',
  'Cable Row': 'back',
  'Face Pull': 'back',
  'Pull-up': 'back',
  'Weighted Pull-up': 'back',
  'Chin-up': 'back',
  'Shrug': 'back',

  // ─── Lower Back ─────────────────────────────────────────────────
  'Romanian Deadlift': 'lower_back',
  'RDL': 'lower_back',
  'Good Morning': 'lower_back',
  'Back Extension': 'lower_back',

  // ─── Chest ──────────────────────────────────────────────────────
  'OHP': 'chest',
  'Overhead Press': 'chest',
  'Shoulder Press': 'chest',
  'DB Shoulder Press': 'chest',
  'Push Press': 'chest',
  'Lateral Raise': 'chest',
  'Rear Delt Fly': 'chest',
  'DB Bench Press': 'chest',
  'DB Incline Press': 'chest',
  'Push-up': 'chest',
  'Dip': 'chest',

  // ─── Arm ────────────────────────────────────────────────────────
  'Curl': 'arm',
  'Barbell Curl': 'arm',
  'DB Curl': 'arm',
  'Hammer Curl': 'arm',
  'Tricep Pushdown': 'arm',
  'Skull Crusher': 'arm',
  'Cable Curl': 'arm',
  'Preacher Curl': 'arm',
  'Incline DB Curl': 'arm',
  'Tricep Extension': 'arm',
  'Overhead Tricep Extension': 'arm',

  // ─── Legs ───────────────────────────────────────────────────────
  'Leg Press': 'legs',
  'Lunges': 'legs',
  'Split Squat': 'legs',
  'Bulgarian Split Squat': 'legs',
  'Leg Curl': 'legs',
  'Nordic Hamstring Curl': 'legs',
  'Glute Ham Raise': 'legs',
  'Hip Thrust': 'legs',
  'Reverse Hyper': 'legs',
  'Leg Extension': 'legs',
  'Calf Raise': 'legs',
  'Seated Calf Raise': 'legs',

  // ─── Core ───────────────────────────────────────────────────────
  'Plank': 'core',
  'Ab Rollout': 'core',
  'Ab Wheel': 'core',
  'Russian Twist': 'core',
  'Hanging Leg Raise': 'core',
  'Cable Crunch': 'core',
  'Pallof Press': 'core',
  'Dead Bug': 'core',
  'Side Plank': 'core',
  'Cable Woodchop': 'core',
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

/**
 * Normalize an exercise name for matching: strip parenthetical suffixes
 * like (heavy), (light), (backout), trim whitespace, lowercase, singularize.
 */
export function normalizeExerciseName(name: string): string {
  const stripped = name.replace(/\s*\(.*?\)\s*/g, ' ').trim().toLowerCase()
  return stripped.split(/\s+/).map(singularize).join(' ')
}

/**
 * Build a lookup from normalized exercise name to its category (from glossary).
 */
function buildCategoryLookup(glossary: GlossaryExercise[]): Map<string, LiftCategory> {
  const lookup = new Map<string, LiftCategory>()
  for (const ex of glossary) {
    lookup.set(normalizeExerciseName(ex.name), ex.category as LiftCategory)
  }
  return lookup
}

/**
 * Categorize an exercise by name. Uses glossary when available, falls back to
 * hardcoded map. Defaults to 'arm'.
 */
export function categorizeExercise(name: string, glossaryLookup?: Map<string, LiftCategory>): LiftCategory {
  if (glossaryLookup) {
    const norm = normalizeExerciseName(name)
    const cat = glossaryLookup.get(norm)
    if (cat) return cat
  }
  return LIFT_CATEGORY_MAP[name] ?? LIFT_CATEGORY_MAP[normalizeExerciseName(name)] ?? 'arm'
}

/**
 * Calculate volume by category system for a list of sessions.
 * Uses glossary categories when available, falls back to hardcoded map.
 */
export function volumeByCategory6(sessions: Session[], block?: string, glossary?: GlossaryExercise[]): Record<LiftCategory, number> {
  const result = zeroCategoryRecord()
  const lookup = glossary ? buildCategoryLookup(glossary) : undefined

  for (const session of filterByBlock(sessions, block)) {
    for (const ex of session.exercises) {
      const vol = exerciseVolume(ex)
      result[categorizeExercise(ex.name, lookup)] += vol
    }
  }

  return result
}

/**
 * Calculate volume by legacy 4-category system (backward compat).
 */
export function volumeByCategory(sessions: Session[], block?: string): Record<string, number> {
  const result = { squat: 0, bench: 0, deadlift: 0, accessory: 0 }

  for (const session of filterByBlock(sessions, block)) {
    for (const ex of session.exercises) {
      const vol = exerciseVolume(ex)
      const cat = categorizeExercise(ex.name)
      if (cat === 'squat' || cat === 'bench' || cat === 'deadlift') {
        result[cat] += vol
      } else {
        result.accessory += vol
      }
    }
  }

  return result
}

/**
 * Get weekly volume data for charting.
 * Uses glossary categories when available, falls back to hardcoded map.
 */
export function weeklyVolumeByCategory6(
  sessions: Session[],
  block?: string,
  glossary?: GlossaryExercise[]
): Array<{ week: number; squat: number; bench: number; deadlift: number; back: number; chest: number; arm: number; legs: number; core: number; lower_back: number }> {
  const weekMap = new Map<number, Record<LiftCategory, number>>()
  const lookup = glossary ? buildCategoryLookup(glossary) : undefined

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

/**
 * Get weekly volume data for charting (legacy 4-category, backward compat).
 */
export function weeklyVolumeByCategory(
  sessions: Session[],
  block?: string
): Array<{ week: number; squat: number; bench: number; deadlift: number; accessory: number }> {
  const weekMap = new Map<number, { squat: number; bench: number; deadlift: number; accessory: number }>()

  for (const session of filterByBlock(sessions, block)) {
    const week = session.week_number
    if (!weekMap.has(week)) {
      weekMap.set(week, { squat: 0, bench: 0, deadlift: 0, accessory: 0 })
    }
    const weekData = weekMap.get(week)!

    for (const ex of session.exercises) {
      const vol = exerciseVolume(ex)
      const cat = categorizeExercise(ex.name)
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

// ─── Muscle Group Utilities ──────────────────────────────────────────────────

/**
 * Build a lookup from exercise name to its muscle contributions.
 * Keys are normalized (lowered, parenthetical suffixes stripped, trimmed)
 * so that session exercise names with extra annotations still match.
 */
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

/**
 * Calculate total volume (sets * reps * kg) per muscle group.
 * Primary muscles get full weight, secondary muscles get half weight,
 * and tertiary muscles get quarter weight.
 * Exercises not found in the glossary are skipped.
 */
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

/**
 * Calculate weekly sets per muscle group.
 * Primary muscles get full set credit, secondary muscles get half set credit,
 * and tertiary muscles get quarter set credit.
 * Exercises not found in the glossary are skipped.
 */
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

/**
 * Filter sessions by training block. Default: "current".
 * Pass "*" to include all blocks.
 */
function filterByBlock(sessions: Session[], block?: string): Session[] {
  if (!block || block === '*') return sessions
  return sessions.filter((s) => (s.block || 'current') === block)
}

// ─── Max Tracking ───────────────────────────────────────────────────────────────

/**
 * Find the heaviest weight lifted per unique exercise across all completed sessions.
 * Returns a Map keyed by normalized name, with { kg, displayName } values.
 */
export function allTimeMaxByExercise(
  sessions: Session[],
  block?: string
): Map<string, { kg: number; displayName: string }> {
  const maxes = new Map<string, { kg: number; displayName: string }>()

  for (const session of filterByBlock(sessions, block)) {
    if (!session.completed) continue
    for (const ex of session.exercises) {
      if (ex.kg == null) continue
      const key = normalizeExerciseName(ex.name)
      const existing = maxes.get(key)
      if (!existing || ex.kg > existing.kg) {
        maxes.set(key, { kg: ex.kg, displayName: ex.name })
      }
    }
  }

  return maxes
}

/**
 * Find the heaviest weight per lift category within a date window.
 * Only considers completed sessions.
 */
export function maxByCategoryInWindow(
  sessions: Session[],
  startDate: string,
  endDate: string,
  categories: LiftCategory[] = ['squat', 'bench', 'deadlift'],
  block?: string
): Record<string, number> {
  const result: Record<string, number> = {}
  for (const cat of categories) result[cat] = 0

  for (const session of filterByBlock(sessions, block)) {
    if (!session.completed) continue
    if (session.date < startDate || session.date > endDate) continue
    for (const ex of session.exercises) {
      if (ex.kg == null) continue
      const cat = categorizeExercise(ex.name)
      if (cat in result && ex.kg > result[cat]) {
        result[cat] = ex.kg
      }
    }
  }

  return result
}

/**
 * Calculate weekly volume per muscle group.
 * Primary muscles get full volume, secondary muscles get half volume,
 * and tertiary muscles get quarter volume.
 * Exercises not found in the glossary are skipped.
 */
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
