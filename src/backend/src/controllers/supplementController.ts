import { invokeLambda } from '../utils/lambda'
import type { SupplementPhase } from '@powerlifting/types'

export async function updateSupplementPhases(
  pk: string,
  _version: string,
  phases: SupplementPhase[],
  envelope: { expected_revision: number; idempotency_key: string },
): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'supplement_phases_update', pk, version: _version, phases, ...envelope }) as Record<string, unknown>
}

export async function getSupplementPhases(pk: string, _version: string): Promise<SupplementPhase[]> {
  const result = await invokeLambda('health_get_supplements', { pk })
  return Array.isArray(result?.supplement_phases) ? result.supplement_phases : []
}
