import { invokeLambda } from '../utils/lambda'
import type { BlockNote } from '@powerlifting/types'

export async function getBlockNotes(pk: string, version: string): Promise<BlockNote[]> {
  const result = await invokeLambda('pod_training_program', { function: 'block_notes_get',  pk, version })
  return Array.isArray(result?.block_notes) ? result.block_notes : []
}

export async function updateBlockNotes(pk: string, version: string, blockNotes: BlockNote[]): Promise<void> {
  await invokeLambda('pod_training_program', { function: 'block_notes_update',  pk, version, block_notes: blockNotes })
}
