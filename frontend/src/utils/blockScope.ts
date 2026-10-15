import type { Program } from '@powerlifting/types'

type BlockScoped = { block_id?: string | null; block?: string | null }

export function currentBlockId(program: Program | null | undefined): string {
  return program?.meta?.current_block_id || 'current'
}

export function isInBlock(record: BlockScoped, blockId: string, activeBlockId: string): boolean {
  const key = record.block_id || record.block || 'current'
  if (blockId === activeBlockId || blockId === 'current') return key === activeBlockId || key === 'current'
  return key === blockId
}

export function recordsInBlock<T extends BlockScoped>(records: T[] | null | undefined, program: Program | null | undefined, blockId = 'current'): T[] {
  const active = currentBlockId(program)
  return (records ?? []).filter((record) => isInBlock(record, blockId, active))
}
