const RPE_ROWS = [6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10] as const

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function approxPctAtRpe(reps: number, rpe: number): number {
  const repsClamped = clamp(reps, 1, 10)
  const rpeClamped = clamp(rpe, 6, 10)

  // Epley-like baseline at RPE 10 with a modest penalty for lower RPEs.
  const basePct = 1 / (1 + repsClamped / 30)
  const rpePenalty = (10 - rpeClamped) * 0.025
  return clamp(basePct - rpePenalty, 0.5, 1)
}

export function estimateSetE1rm(weightKg: number, reps: number, rpe?: number | null): {
  e1rmKg: number
  pct: number
  method: 'rpe_table' | 'epley'
} | null {
  if (!Number.isFinite(weightKg) || weightKg <= 0) return null
  if (!Number.isFinite(reps) || reps <= 0) return null

  const pct = rpe != null && Number.isFinite(rpe)
    ? approxPctAtRpe(reps, rpe)
    : 1 / (1 + clamp(reps, 1, 10) / 30)

  return {
    e1rmKg: parseFloat((weightKg / pct).toFixed(2)),
    pct,
    method: rpe != null && Number.isFinite(rpe) ? 'rpe_table' : 'epley',
  }
}

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
  return RPE_ROWS.map((rpe) => {
    const pct = approxPctAtRpe(reps, rpe)
    return {
      rpe,
      pct,
      weightKg: parseFloat((e1rmKg * pct).toFixed(2)),
    }
  })
}
