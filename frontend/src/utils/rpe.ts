import { setPercentage } from '../../../backend/src/utils/calculations'
export { estimateSetE1rm } from '../../../backend/src/utils/calculations'

const RPE_ROWS = [6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10] as const

export function buildPercentRows(e1rmKg: number): Array<{ pct: number; weightKg: number }> {
  return Array.from({ length: 9 }, (_, i) => {
    const pct = 60 + i * 5
    return {
      pct,
      weightKg: parseFloat((e1rmKg * (pct / 100)).toFixed(2)),
    }
  })
}

export function buildRpeRows(reps: number, e1rmKg: number): Array<{ rpe: number; pct: number; weightKg: number }> {
  return RPE_ROWS.flatMap((rpe) => {
    const pct = setPercentage(reps, rpe)
    if (pct == null) return []
    return {
      rpe,
      pct,
      weightKg: parseFloat((e1rmKg * pct).toFixed(2)),
    }
  })
}
