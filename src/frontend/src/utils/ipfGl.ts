import type { Sex } from '@powerlifting/types'

export type IpfGlMode = 'classic_powerlifting' | 'classic_bench'

type IpfGlCoefficients = { a: number; b: number; c: number }

const IPF_GL_COEFFICIENTS: Record<IpfGlMode, Record<Sex, IpfGlCoefficients>> = {
  classic_powerlifting: {
    male: { a: 1199.72839, b: 1025.18162, c: 0.00921 },
    female: { a: 610.32796, b: 1045.59282, c: 0.03048 },
  },
  classic_bench: {
    male: { a: 320.98041, b: 281.40258, c: 0.01008 },
    female: { a: 142.40398, b: 442.52671, c: 0.04724 },
  },
}

const IPF_GL_MODE_LABELS: Record<IpfGlMode, string> = {
  classic_powerlifting: 'Classic',
  classic_bench: 'Bench',
}

export function calculateIpfGl(
  resultKg: number,
  bodyweightKg: number,
  sex: Sex,
  mode: IpfGlMode,
): number | null {
  if (!Number.isFinite(resultKg) || !Number.isFinite(bodyweightKg) || resultKg <= 0 || bodyweightKg <= 0) {
    return null
  }

  const coeff = IPF_GL_COEFFICIENTS[mode][sex]
  const denominator = coeff.a - coeff.b * Math.exp(-coeff.c * bodyweightKg)
  if (Math.abs(denominator) < 1e-12) return null

  return Number(((resultKg * 100) / denominator).toFixed(2))
}

export function getIpfGlModeLabel(mode: IpfGlMode): string {
  return IPF_GL_MODE_LABELS[mode]
}
