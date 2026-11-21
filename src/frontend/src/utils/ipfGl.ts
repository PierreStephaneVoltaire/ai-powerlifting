import type { Sex } from '@powerlifting/types'
import constants from '../../../services/runtime/calculation_constants.json'

export type IpfGlMode = 'classic_powerlifting' | 'classic_bench'

const IPF_GL_COEFFICIENTS = constants.ipf_gl_coefficients

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
