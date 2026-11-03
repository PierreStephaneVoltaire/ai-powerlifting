import type { MuscleGroup, Session } from '@powerlifting/types'
import { MUSCLE_CONTRIBUTION_MULTIPLIERS } from './sessionWorkload'
import { exerciseVolume } from './volume'

interface MuscleContribution {
  primary: MuscleGroup[]
  secondary: MuscleGroup[]
  tertiary?: MuscleGroup[]
}

export const MUSCLE_MAP: Record<string, MuscleContribution> = {
  // ─── Squat variants ─────────────────────────────────────────────
  'Back Squat': { primary: ['quads', 'glutes'], secondary: ['hamstrings', 'erectors', 'core'] },
  'Squat': { primary: ['quads', 'glutes'], secondary: ['hamstrings', 'erectors', 'core'] },
  'Squat (Backout Heavy)': { primary: ['quads', 'glutes'], secondary: ['hamstrings', 'erectors'] },
  'Squat (Backout Light)': { primary: ['quads', 'glutes'], secondary: ['hamstrings', 'erectors'] },
  'Front Squat': { primary: ['quads'], secondary: ['glutes', 'erectors', 'core'] },
  'Box Squat': { primary: ['glutes', 'quads'], secondary: ['hamstrings', 'erectors'] },
  'Pause Squat': { primary: ['quads', 'glutes'], secondary: ['hamstrings', 'erectors'] },
  'Tempo Squat': { primary: ['quads', 'glutes'], secondary: ['hamstrings', 'erectors'] },
  'Hack Squat': { primary: ['quads'], secondary: ['glutes', 'hamstrings'] },
  'Bulgarian Split Squat': { primary: ['quads', 'glutes'], secondary: ['hamstrings', 'hip_flexors'] },
  'Leg Press': { primary: ['quads', 'glutes'], secondary: ['hamstrings'] },
  'Leg Extension': { primary: ['quads'], secondary: [] },

  // ─── Bench variants ─────────────────────────────────────────────
  'Bench Press': { primary: ['chest', 'triceps'], secondary: ['front_delts'] },
  'Bench Press (Backout)': { primary: ['chest', 'triceps'], secondary: ['front_delts'] },
  'Pause Bench Press': { primary: ['chest', 'triceps'], secondary: ['front_delts'] },
  'Spoto Press': { primary: ['chest', 'triceps'], secondary: ['front_delts'] },
  'Close-Grip Bench Press': { primary: ['triceps', 'chest'], secondary: ['front_delts'] },
  'Wide-Grip Bench Press': { primary: ['chest'], secondary: ['triceps', 'front_delts'] },
  'Floor Press': { primary: ['triceps', 'chest'], secondary: ['front_delts'] },
  'Incline Bench Press': { primary: ['chest', 'front_delts'], secondary: ['triceps'] },
  'DB Bench Press': { primary: ['chest', 'triceps'], secondary: ['front_delts'] },
  'DB Incline Press': { primary: ['chest', 'front_delts'], secondary: ['triceps'] },
  'Dip': { primary: ['triceps', 'chest'], secondary: ['front_delts'] },
  'Push-up': { primary: ['chest', 'triceps'], secondary: ['front_delts', 'core'] },
  'Skull Crusher': { primary: ['triceps'], secondary: [] },
  'Tricep Pushdown': { primary: ['triceps'], secondary: [] },

  // ─── Deadlift variants ──────────────────────────────────────────
  'Deadlift': { primary: ['hamstrings', 'glutes', 'erectors'], secondary: ['lats', 'quads', 'traps', 'forearms'] },
  'Deadlift (Backout)': { primary: ['hamstrings', 'glutes', 'erectors'], secondary: ['lats', 'quads', 'forearms'] },
  'Conventional Deadlift': { primary: ['hamstrings', 'glutes', 'erectors'], secondary: ['lats', 'quads', 'forearms'] },
  'Sumo Deadlift': { primary: ['glutes', 'quads', 'hamstrings'], secondary: ['erectors', 'lats', 'forearms'] },
  'Romanian Deadlift': { primary: ['hamstrings', 'glutes'], secondary: ['erectors', 'forearms'] },
  'RDL': { primary: ['hamstrings', 'glutes'], secondary: ['erectors', 'forearms'] },
  'Stiff-Leg Deadlift': { primary: ['hamstrings', 'erectors'], secondary: ['glutes', 'forearms'] },
  'Deficit Deadlift': { primary: ['hamstrings', 'glutes', 'erectors'], secondary: ['quads', 'lats', 'forearms'] },
  'Rack Pull': { primary: ['erectors', 'traps'], secondary: ['hamstrings', 'glutes', 'forearms'] },
  'Block Pull': { primary: ['hamstrings', 'glutes', 'erectors'], secondary: ['lats', 'forearms'] },
  'Good Morning': { primary: ['hamstrings', 'erectors'], secondary: ['glutes'] },

  // ─── Posterior chain ────────────────────────────────────────────
  'Leg Curl': { primary: ['hamstrings'], secondary: ['calves'] },
  'Nordic Hamstring Curl': { primary: ['hamstrings'], secondary: ['calves', 'glutes'] },
  'Glute Ham Raise': { primary: ['hamstrings'], secondary: ['glutes', 'erectors', 'calves'] },
  'Back Extension': { primary: ['erectors'], secondary: ['glutes', 'hamstrings'] },
  'Reverse Hyper': { primary: ['glutes', 'hamstrings'], secondary: ['erectors'] },
  'Hip Thrust': { primary: ['glutes'], secondary: ['hamstrings', 'quads'] },

  // ─── Upper back / pulling ────────────────────────────────────────
  'Pull-up': { primary: ['lats', 'biceps'], secondary: ['traps', 'rhomboids'] },
  'Weighted Pull-up': { primary: ['lats', 'biceps'], secondary: ['traps', 'rhomboids', 'rear_delts', 'teres_major'] },
  'Chin-up': { primary: ['lats', 'biceps'], secondary: ['traps'] },
  'Lat Pulldown': { primary: ['lats'], secondary: ['biceps', 'traps'] },
  'Barbell Row': { primary: ['lats', 'traps'], secondary: ['biceps', 'erectors'] },
  'DB Row': { primary: ['lats', 'traps'], secondary: ['biceps', 'rear_delts'] },
  'Cable Row': { primary: ['lats', 'traps'], secondary: ['biceps', 'rear_delts'] },
  'Face Pull': { primary: ['rear_delts', 'traps'], secondary: ['rhomboids', 'biceps'] },
  'Shrug': { primary: ['traps'], secondary: ['forearms'] },

  // ─── Shoulders ──────────────────────────────────────────────────
  'Overhead Press': { primary: ['front_delts', 'side_delts', 'triceps'], secondary: ['traps', 'core'] },
  'Push Press': { primary: ['front_delts', 'side_delts', 'triceps'], secondary: ['quads', 'glutes', 'core'] },
  'DB Shoulder Press': { primary: ['front_delts', 'side_delts', 'triceps'], secondary: [] },
  'Lateral Raise': { primary: ['side_delts'], secondary: ['traps'] },
  'Rear Delt Fly': { primary: ['rear_delts'], secondary: ['rhomboids', 'traps'] },

  // ─── Arms ───────────────────────────────────────────────────────
  'Barbell Curl': { primary: ['biceps'], secondary: ['forearms'] },
  'DB Curl': { primary: ['biceps'], secondary: ['forearms'] },
  'Hammer Curl': { primary: ['biceps', 'forearms'], secondary: [] },

  // ─── Core ───────────────────────────────────────────────────────
  'Hanging Leg Raise': { primary: ['core', 'hip_flexors'], secondary: ['obliques'] },
  'Plank': { primary: ['core'], secondary: ['hip_flexors'] },
  'Cable Crunch': { primary: ['core'], secondary: ['obliques'] },
  'Pallof Press': { primary: ['core', 'obliques'], secondary: ['front_delts'] },
}

export function muscleVolumeFromSessions(
  sessions: Session[]
): Partial<Record<MuscleGroup, number>> {
  const volumes: Partial<Record<MuscleGroup, number>> = {}

  for (const session of sessions) {
    for (const ex of session.exercises) {
      const map = MUSCLE_MAP[ex.name]
      if (!map || ex.kg === null) continue

      const vol = exerciseVolume(ex)

      map.primary.forEach(m => {
        volumes[m] = (volumes[m] ?? 0) + vol
      })
      map.secondary.forEach(m => {
        volumes[m] = (volumes[m] ?? 0) + vol * MUSCLE_CONTRIBUTION_MULTIPLIERS.secondary
      })
      map.tertiary?.forEach(m => {
        volumes[m] = (volumes[m] ?? 0) + vol * MUSCLE_CONTRIBUTION_MULTIPLIERS.tertiary
      })
    }
  }

  return volumes
}

export function normalizeMuscleVolumes(
  volumes: Partial<Record<MuscleGroup, number>>
): Partial<Record<MuscleGroup, number>> {
  const values = Object.values(volumes)
  const max = Math.max(...values, 1)

  const normalized: Partial<Record<MuscleGroup, number>> = {}
  for (const [muscle, vol] of Object.entries(volumes)) {
    normalized[muscle as MuscleGroup] = vol! / max
  }

  return normalized
}

export function heatmapColor(value: number): string {
  if (value < 0.01) return '#f8fafc' // nearly white
  if (value < 0.25) return '#bfdbfe' // light blue
  if (value < 0.5) return '#3b82f6'  // blue
  if (value < 0.75) return '#1d4ed8' // dark blue
  return '#dc2626'                    // red
}

export const MUSCLE_DISPLAY_NAMES: Record<MuscleGroup, string> = {
  quads: 'Quadriceps',
  hamstrings: 'Hamstrings',
  glutes: 'Glutes',
  calves: 'Calves',
  tibialis_anterior: 'Tibialis Anterior',
  hip_flexors: 'Hip Flexors',
  adductors: 'Adductors',
  chest: 'Chest',
  triceps: 'Triceps',
  front_delts: 'Front Delts',
  side_delts: 'Side Delts',
  rear_delts: 'Rear Delts',
  lats: 'Lats',
  traps: 'Traps',
  rhomboids: 'Rhomboids',
  teres_major: 'Teres Major',
  biceps: 'Biceps',
  forearms: 'Forearms',
  erectors: 'Erectors',
  lower_back: 'Lower Back',
  core: 'Core',
  obliques: 'Obliques',
  serratus: 'Serratus',
}
