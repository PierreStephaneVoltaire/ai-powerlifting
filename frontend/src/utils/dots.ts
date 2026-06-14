import type { Sex, DotsResult } from '@powerlifting/types'

// Official DOTS polynomial coefficients
const DOTS_COEFFICIENTS: Record<Sex, {
  a: number; b: number; c: number; d: number; e: number
}> = {
  male: {
    a: -307.75076,
    b:   24.0900756,
    c:   -0.1918759221,
    d:    0.0007391293,
    e:   -0.000001093,
  },
  female: {
    a:  -57.96288,
    b:   13.6175032,
    c:   -0.1126655495,
    d:    0.0005158568,
    e:   -0.0000010706,
  },
}

/**
 * Calculate DOTS score.
 * Formula: DOTS = (500 / denominator) * total
 * denominator = a + b*bw + c*bw^2 + d*bw^3 + e*bw^4
 */
export function calculateDots(
  totalKg: number,
  bodyweightKg: number,
  sex: Sex
): number {
  const { a, b, c, d, e } = DOTS_COEFFICIENTS[sex]
  const bw = bodyweightKg
  const denominator = a + b*bw + c*bw**2 + d*bw**3 + e*bw**4
  return parseFloat(((500 / denominator) * totalKg).toFixed(2))
}

/**
 * Convenience wrapper for the three-lift breakdown.
 */
export function calculateDotsFromLifts(
  squatKg: number,
  benchKg: number,
  deadliftKg: number,
  bodyweightKg: number,
  sex: Sex
): DotsResult {
  const total = squatKg + benchKg + deadliftKg
  return {
    dots: calculateDots(total, bodyweightKg, sex),
    total_kg: total,
    bodyweight_kg: bodyweightKg,
    sex,
  }
}

/**
 * Reverse: what total is needed to hit a target DOTS at a given bodyweight?
 * Rearrangement: total = (targetDots * denominator) / 500
 */
export function totalForTargetDots(
  targetDots: number,
  bodyweightKg: number,
  sex: Sex
): number {
  const { a, b, c, d, e } = DOTS_COEFFICIENTS[sex]
  const bw = bodyweightKg
  const denominator = a + b*bw + c*bw**2 + d*bw**3 + e*bw**4
  return parseFloat(((targetDots * denominator) / 500).toFixed(1))
}

/**
 * Weight class optimizer: compute DOTS score at the current total
 * across a list of bodyweight scenarios.
 */
export function dotsAcrossWeightClasses(
  total: number,
  bodyweights: number[],
  sex: Sex
): Array<{ bodyweightKg: number; dots: number }> {
  return bodyweights.map(bw => ({
    bodyweightKg: bw,
    dots: calculateDots(total, bw, sex),
  }))
}

/**
 * Performance level thresholds for DOTS scores.
 */
export const DOTS_LEVELS = {
  male: [
    { name: 'Beginner', min: 0, max: 150, context: 'Just starting out' },
    { name: 'Novice', min: 150, max: 200, context: '6-18 months' },
    { name: 'Intermediate', min: 200, max: 250, context: 'Consistent 2-3 years' },
    { name: 'Advanced', min: 250, max: 300, context: 'Competitive regional' },
    { name: 'Elite', min: 300, max: 350, context: 'National-level' },
    { name: 'World-class', min: 350, max: Infinity, context: 'International podium' },
  ],
  female: [
    { name: 'Beginner', min: 0, max: 100, context: 'Just starting out' },
    { name: 'Novice', min: 100, max: 140, context: '6-18 months' },
    { name: 'Intermediate', min: 140, max: 180, context: 'Consistent 2-3 years' },
    { name: 'Advanced', min: 180, max: 220, context: 'Competitive regional' },
    { name: 'Elite', min: 220, max: 270, context: 'National-level' },
    { name: 'World-class', min: 270, max: Infinity, context: 'International podium' },
  ],
} as const

/**
 * Get the performance level for a given DOTS score.
 */
export function getDotsLevel(dots: number, sex: Sex) {
  const levels = DOTS_LEVELS[sex]
  return levels.find(l => dots >= l.min && dots < l.max) || levels[0]
}
