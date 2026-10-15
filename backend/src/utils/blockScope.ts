import type { Program } from '@powerlifting/types'

export const ALL_BLOCKS = 'all'

type BlockScoped = { block_id?: string | null; block?: string | null }

const SCOPED_PROGRAM_LISTS = ['phases', 'sessions', 'diet_notes', 'supplements', 'supplement_phases', 'competitions'] as const

export function currentBlockId(program: Pick<Program, 'meta'> | null | undefined): string {
  return program?.meta?.current_block_id || 'current'
}

export function isInBlock(record: BlockScoped, blockId: string, activeBlockId: string): boolean {
  const key = record.block_id || record.block || 'current'
  if (blockId === activeBlockId || blockId === 'current') return key === activeBlockId || key === 'current'
  return key === blockId
}

export function scopeProgramToBlock<T extends Program & { weight_log?: BlockScoped[] }>(program: T, blockId = 'current'): T {
  if (blockId === ALL_BLOCKS) return program
  const active = currentBlockId(program)
  const keep = (records: unknown) => Array.isArray(records)
    ? records.filter((record: BlockScoped) => record && isInBlock(record, blockId, active))
    : records
  const scoped = { ...program } as T & Record<string, unknown>
  for (const field of SCOPED_PROGRAM_LISTS) scoped[field] = keep(program[field]) as never
  if (program.weight_log) scoped.weight_log = keep(program.weight_log) as never
  if (program.meta?.block_notes) scoped.meta = { ...program.meta, block_notes: keep(program.meta.block_notes) as never }
  return scoped
}
