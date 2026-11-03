import { invokeLambda } from '../utils/lambda'
import type { DietNote } from '@powerlifting/types'

export async function updateDietNotes(
  pk: string,
  _version: string,
  dietNotes: DietNote[],
  envelope: { expected_revision: number; idempotency_key: string },
): Promise<Record<string, unknown>> {
  return await invokeLambda('pod_training_program', { function: 'diet_notes_update', pk, version: _version, notes: dietNotes, ...envelope }) as Record<string, unknown>
}

export async function getDietNotes(pk: string, _version: string): Promise<DietNote[]> {
  const result = await invokeLambda('health_get_diet_notes', { pk })
  return Array.isArray(result) ? result : []
}
