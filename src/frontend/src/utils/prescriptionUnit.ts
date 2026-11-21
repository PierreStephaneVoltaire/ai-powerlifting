import type { RepUnit } from '@powerlifting/types'

export type PrescriptionMode = RepUnit | 'amrap'

type Prescription = {
  reps?: number | null
  rep_unit?: RepUnit
  rep_mode?: 'amrap'
  duration_minutes?: number
}

export function prescriptionMode(exercise: Prescription): PrescriptionMode {
  return exercise.rep_mode === 'amrap' ? 'amrap' : exercise.rep_unit ?? (exercise.duration_minutes != null ? 'minutes' : 'reps')
}

export function convertDuration(amount: number, from: PrescriptionMode, to: PrescriptionMode): number {
  if (from === 'minutes' && to === 'seconds') return amount * 60
  if (from === 'seconds' && to === 'minutes') return amount / 60
  return amount
}

export function changePrescription(exercise: Prescription, next: PrescriptionMode) {
  const previous = prescriptionMode(exercise)
  const previousTimed = previous === 'minutes' || previous === 'seconds'
  const timed = next === 'minutes' || next === 'seconds'
  const amount = exercise.rep_unit ? exercise.reps : exercise.duration_minutes ?? exercise.reps
  let reps: number | null = amount ?? 1
  if (next === 'amrap') reps = null
  else if (timed) reps = previousTimed && amount != null ? convertDuration(amount, previous, next) : next === 'minutes' ? 15 : 30
  else if (previousTimed) reps = 1
  return { reps, rep_unit: timed ? next : 'reps' as const, rep_mode: next === 'amrap' ? 'amrap' as const : undefined, duration_minutes: undefined }
}
