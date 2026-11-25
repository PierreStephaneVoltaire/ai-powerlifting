import { callOperation } from '../utils/operations'
import type { SupplementPhase } from '@powerlifting/types'

export async function updateSupplementPhases(
  pk: string,
  phases: SupplementPhase[]
): Promise<Record<string, unknown>> {
  return await callOperation('supplement_phases_update', { pk, phases }) as Record<string, unknown>
}

export async function getSupplementPhases(pk: string): Promise<SupplementPhase[]> {
  const result = await callOperation('health_get_supplements', { pk })
  return Array.isArray(result?.supplement_phases) ? result.supplement_phases : []
}
