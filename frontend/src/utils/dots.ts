import type { Sex, DotsResult } from '@powerlifting/types'

import { DOTS_COEFFICIENTS, calculateDots } from '../../../backend/src/utils/calculations'
export { calculateDots } from '../../../backend/src/utils/calculations'

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

export function getDotsLevel(dots: number, sex: Sex) {
  const levels = DOTS_LEVELS[sex]
  return levels.find(l => dots >= l.min && dots < l.max) || levels[0]
}
