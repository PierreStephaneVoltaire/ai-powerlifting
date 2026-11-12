import type { Sex } from '@powerlifting/types'
import constants from '../../../services/runtime/calculation_constants.json'

export const DOTS_COEFFICIENTS = constants.dots_coefficients
const rpePercent: Record<string, number> = constants.rpe_percent

export function setPercentage(reps: number, rpe?: number | null): number | null {
  if (!Number.isInteger(reps)) return null
  if (reps < 1 || reps > 10) return null
  if (rpe != null) return rpe >= 6 && rpe <= 10 ? rpePercent[`${reps}-${Math.trunc(rpe)}`] ?? null : null
  return rpePercent[`${reps}-10`] ?? null
}

export function estimateSetE1rm(weightKg: number, reps: number, rpe?: number | null): { e1rmKg: number; pct: number; method: 'rpe_table' | 'assumed_rpe_10' } | null {
  const value = estimateSetE1rmValue(weightKg, reps, rpe)
  if (value == null) return null
  const pct = setPercentage(reps, rpe) as number
  return { e1rmKg: Number(value.toFixed(1)), pct, method: rpe != null ? 'rpe_table' : 'assumed_rpe_10' }
}

export function estimateSetE1rmValue(weightKg: number, reps: number, rpe?: number | null): number | null {
  if (!Number.isFinite(weightKg) || weightKg <= 0) return null
  const pct = setPercentage(reps, rpe)
  if (!pct) return null
  return weightKg / pct
}

export function calculateDots(totalKg: number, bodyweightKg: number, sex: Sex): number {
  if (!Number.isFinite(totalKg) || !Number.isFinite(bodyweightKg) || totalKg < 0 || bodyweightKg <= 0) throw new Error('Expected nonnegative total and positive bodyweight')
  const c = DOTS_COEFFICIENTS[sex]
  const denominator = c.a + c.b * bodyweightKg + c.c * bodyweightKg ** 2 + c.d * bodyweightKg ** 3 + c.e * bodyweightKg ** 4
  return Math.abs(denominator) < 1e-12 ? 0 : Number((500 * totalKg / denominator).toFixed(2))
}
