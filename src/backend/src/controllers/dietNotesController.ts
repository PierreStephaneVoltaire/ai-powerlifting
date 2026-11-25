import { callOperation } from '../utils/operations'
import type { DietNote } from '@powerlifting/types'

export async function updateDietNotes(
  pk: string,
  dietNotes: DietNote[]
): Promise<Record<string, unknown>> {
  return await callOperation('diet_notes_update', { pk, notes: dietNotes }) as Record<string, unknown>
}

export async function getDietNotes(pk: string): Promise<DietNote[]> {
  const result = await callOperation('health_get_diet_notes', { pk })
  return Array.isArray(result) ? result : []
}
