import type { ExerciseCategory, GlossaryExercise, Session } from '@powerlifting/types'
import { executedSets, exerciseVolume, normalizeExerciseName } from '@/utils/volume'

export type MuscleLookup = Map<string, { primary: string[]; secondary: string[]; tertiary: string[] }>
export type CategoryLookup = Map<string, ExerciseCategory>
export type PerLiftDetails = Record<string, { frequency: number; raw_sets: number; accessories: { name: string; sets: number; volume: number }[] }>

export function glossaryMuscleLookup(glossary: GlossaryExercise[]): MuscleLookup {
  const lookup: MuscleLookup = new Map()
  for (const ex of glossary) {
    lookup.set(normalizeExerciseName(ex.name), {
      primary: ex.primary_muscles,
      secondary: ex.secondary_muscles,
      tertiary: ex.tertiary_muscles ?? [],
    })
  }
  return lookup
}

export function glossaryCategoryLookup(glossary: GlossaryExercise[]): CategoryLookup {
  const lookup: CategoryLookup = new Map()
  for (const ex of glossary) lookup.set(normalizeExerciseName(ex.name), ex.category)
  return lookup
}

export function muscleGroupAverages(sessions: Session[], muscles: MuscleLookup, weeks: number): { sets: Record<string, number>; volume: Record<string, number> } {
  if (!muscles.size || !sessions.length) return { sets: {}, volume: {} }
  const periodWeeks = Math.max(1, weeks)
  const mgSets: Record<string, number> = {}
  const mgVol: Record<string, number> = {}
  for (const s of sessions) {
    for (const ex of s.exercises || []) {
      const entry = muscles.get(normalizeExerciseName(ex.name))
      if (!entry) continue
      const sets = executedSets(ex)
      const vol = exerciseVolume(ex)
      for (const m of entry.primary) { mgSets[m] = (mgSets[m] || 0) + sets; mgVol[m] = (mgVol[m] || 0) + vol }
      for (const m of entry.secondary) { mgSets[m] = (mgSets[m] || 0) + sets * 0.5; mgVol[m] = (mgVol[m] || 0) + vol * 0.5 }
      for (const m of entry.tertiary) { mgSets[m] = (mgSets[m] || 0) + sets * 0.25; mgVol[m] = (mgVol[m] || 0) + vol * 0.25 }
    }
  }
  const avgSets: Record<string, number> = {}
  const avgVol: Record<string, number> = {}
  for (const m of Object.keys(mgSets)) {
    avgSets[m] = Math.round((mgSets[m] / periodWeeks) * 10) / 10
    avgVol[m] = Math.round(mgVol[m] / periodWeeks)
  }
  return { sets: avgSets, volume: avgVol }
}

export function perLiftBreakdown(sessions: Session[], categories: CategoryLookup): PerLiftDetails {
  if (!categories.size || !sessions.length) return {}
  const numWeeks = new Set(sessions.map(s => s.week_number)).size || 1
  const result: PerLiftDetails = {}
  for (const [liftName, category] of [['squat', 'squat'], ['bench', 'bench'], ['deadlift', 'deadlift']] as const) {
    let liftSessions = 0, rawSets = 0
    const accessoryMap: Record<string, { sets: number; volume: number }> = {}
    for (const s of sessions) {
      let hasLift = false
      for (const ex of s.exercises || []) {
        const sets = executedSets(ex)
        if (sets <= 0) continue
        const exLower = ex.name.toLowerCase().trim()
        const info = categories.get(normalizeExerciseName(ex.name))
        const isMainLift = exLower === liftName || (liftName === 'bench' && exLower === 'bench press')
        if (isMainLift || (info && info === category)) hasLift = true
        if (isMainLift) rawSets += sets
        if (info && info === category && !isMainLift) {
          const vol = exerciseVolume(ex)
          if (!accessoryMap[ex.name]) accessoryMap[ex.name] = { sets: 0, volume: 0 }
          accessoryMap[ex.name].sets += sets
          accessoryMap[ex.name].volume += vol
        }
      }
      if (hasLift) liftSessions++
    }
    result[liftName] = {
      frequency: Math.round((liftSessions / numWeeks) * 10) / 10,
      raw_sets: rawSets,
      accessories: Object.entries(accessoryMap).map(([name, d]) => ({ name, ...d })).sort((a, b) => b.volume - a.volume),
    }
  }
  return result
}
