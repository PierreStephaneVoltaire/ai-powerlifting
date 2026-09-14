import constants from '../../../services/calculation_constants.json'

export const DOTS_COEFFICIENTS = constants.dots_coefficients
const rpePercent: Record<string, number> = constants.rpe_percent
const conservativePercent: Record<string, number> = constants.conservative_percent

export function setPercentage(reps: number, rpe?: number | null): number | null {
  if (!Number.isInteger(reps)) return null
  if (rpe != null) return reps >= 1 && reps <= 6 && rpe >= 6 && rpe <= 10 ? rpePercent[`${reps}-${Math.trunc(rpe)}`] ?? null : null
  return conservativePercent[String(reps)] ?? null
}

export function estimateSetE1rm(weightKg: number, reps: number, rpe?: number | null): { e1rmKg: number; pct: number; method: 'rpe_table' | 'conservative' } | null {
  const value = estimateSetE1rmValue(weightKg, reps, rpe)
  if (value == null) return null
  const pct = setPercentage(reps, rpe) as number
  return { e1rmKg: Number(value.toFixed(1)), pct, method: rpe != null ? 'rpe_table' : 'conservative' }
}

export function estimateSetE1rmValue(weightKg: number, reps: number, rpe?: number | null): number | null {
  if (!Number.isFinite(weightKg) || weightKg <= 0) return null
  const pct = setPercentage(reps, rpe)
  if (!pct) return null
  return weightKg / pct
}

export function calculateDots(totalKg: number, bodyweightKg: number, sex: 'male' | 'female'): number {
  if (!Number.isFinite(totalKg) || !Number.isFinite(bodyweightKg) || totalKg < 0 || bodyweightKg <= 0) throw new Error('Expected nonnegative total and positive bodyweight')
  const c = DOTS_COEFFICIENTS[sex]
  const denominator = c.a + c.b * bodyweightKg + c.c * bodyweightKg ** 2 + c.d * bodyweightKg ** 3 + c.e * bodyweightKg ** 4
  return Math.abs(denominator) < 1e-12 ? 0 : Number((500 * totalKg / denominator).toFixed(2))
}
