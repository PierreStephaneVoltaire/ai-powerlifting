import { callOperation } from '../utils/operations'
import type { DietNote } from '@powerlifting/types'

export async function updateDietNotes(
  pk: string,
  _version: string,
  dietNotes: DietNote[],
  envelope: { expected_revision: number; idempotency_key: string },
): Promise<Record<string, unknown>> {
  return await callOperation('diet_notes_update', { pk, version: _version, notes: dietNotes, ...envelope }) as Record<string, unknown>
}

export async function getDietNotes(pk: string, _version: string): Promise<DietNote[]> {
  const result = await callOperation('health_get_diet_notes', { pk })
  return Array.isArray(result) ? result : []
}
