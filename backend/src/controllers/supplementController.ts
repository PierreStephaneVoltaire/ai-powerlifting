import { invokeLambda } from '../utils/lambda'
import type { SupplementPhase } from '@powerlifting/types'

export async function updateSupplementPhases(
  pk: string,
  _version: string,
  phases: SupplementPhase[]
): Promise<void> {
  await invokeLambda('health_update_supplements', { pk, patch: { supplement_phases: phases } })
}

export async function getSupplementPhases(pk: string, _version: string): Promise<SupplementPhase[]> {
  const result = await invokeLambda('health_get_supplements', { pk })
  return Array.isArray(result?.supplement_phases) ? result.supplement_phases : []
}
