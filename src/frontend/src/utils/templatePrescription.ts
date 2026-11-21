export function templatePrescription(exercise: {
  sets: number
  reps?: number | null
  rep_mode?: 'amrap'
  rep_unit?: 'reps' | 'minutes' | 'seconds'
  duration_minutes?: number
}) {
  const unit = exercise.rep_unit ?? (exercise.duration_minutes != null ? 'minutes' : 'reps')
  if (unit !== 'reps') {
    const amount = exercise.rep_unit ? exercise.reps : exercise.duration_minutes
    const duration = `${amount ?? ''} ${unit === 'minutes' ? 'min' : 'sec'}`
    return exercise.sets > 1 ? `${exercise.sets} × ${duration}` : duration
  }
  if (exercise.rep_mode === 'amrap') return `${exercise.sets} × AMRAP`
  return `${exercise.sets} × ${exercise.reps ?? ''}`
}
