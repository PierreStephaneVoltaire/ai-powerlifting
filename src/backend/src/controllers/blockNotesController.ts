import { callOperation } from '../utils/operations'
import type { BlockNote } from '@powerlifting/types'

export async function getBlockNotes(pk: string): Promise<BlockNote[]> {
  const result = await callOperation('block_notes_get', { pk })
  return Array.isArray(result?.block_notes) ? result.block_notes : []
}

export async function updateBlockNotes(pk: string, blockNotes: BlockNote[]): Promise<Record<string, unknown>> {
  return await callOperation('block_notes_update', { pk, block_notes: blockNotes }) as Record<string, unknown>
}
