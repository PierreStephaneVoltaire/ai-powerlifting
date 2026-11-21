export function templatePrescription(exercise: {
  sets: number
  reps?: number | null
  rep_mode?: 'amrap'
  duration_minutes?: number
}) {
  if (exercise.duration_minutes != null) return exercise.sets > 1 ? `${exercise.sets} × ${exercise.duration_minutes} min` : `${exercise.duration_minutes} min`
  if (exercise.rep_mode === 'amrap') return `${exercise.sets} × AMRAP`
  return `${exercise.sets} × ${exercise.reps ?? ''}`
}
