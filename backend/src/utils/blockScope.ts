import type { Program } from '@powerlifting/types'

export const ALL_BLOCKS = 'all'

type BlockScoped = {
  block_id?: string | null
  block?: string | null
  date?: string | null
  start_date?: string | null
  meet_date?: string | null
  competition_date?: string | null
  entry_date?: string | null
  start_week?: number | string | null
  week?: number | string | null
  phase_week?: number | string | null
  name?: string | null
}

type BlockMetadata = {
  id?: string | null
  block_id?: string | null
  start_date?: string | null
  status?: string | null
  completed_at?: string | null
}

type ProgramScope = Pick<Program, 'meta'> | null | undefined

function blockId(block: BlockMetadata): string {
  return String(block.id || block.block_id || '')
}

function blocks(program: ProgramScope): BlockMetadata[] {
  const values = (program?.meta?.blocks ?? []) as BlockMetadata[]
  return values
    .filter((block) => block && blockId(block))
    .sort((a, b) => `${a.start_date || ''}|${blockId(a)}`.localeCompare(`${b.start_date || ''}|${blockId(b)}`))
}

export function currentBlockId(program: ProgramScope): string {
  const configured = String(program?.meta?.current_block_id || '')
  if (configured && configured !== 'current') return configured
  const active = blocks(program).filter((block) => block.status === 'active')
  return blockId(active.at(-1) || {}) || configured || 'current'
}

function recordDate(record: BlockScoped): string | null {
  for (const field of ['date', 'start_date', 'meet_date', 'competition_date', 'entry_date'] as const) {
    const value = record[field]
    if (value) return String(value).slice(0, 10)
  }
  return null
}

function phaseStart(record: BlockScoped, program: ProgramScope): string | null {
  const explicit = recordDate(record)
  if (explicit) return explicit
  const week = Number(record.start_week || record.week || record.phase_week || 0)
  const start = program?.meta?.program_start
  if (!start || !Number.isFinite(week) || week <= 0) return null
  const date = new Date(`${start.slice(0, 10)}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + (week - 1) * 7)
  return date.toISOString().slice(0, 10)
}

function mostRecentCompleted(program: ProgramScope): string | null {
  const completed = blocks(program).filter((block) => block.status === 'completed')
  completed.sort((a, b) => `${a.completed_at || ''}|${a.start_date || ''}`.localeCompare(`${b.completed_at || ''}|${b.start_date || ''}`))
  return completed.length ? blockId(completed.at(-1)!) : null
}

function blockForDate(value: string, program: ProgramScope): string {
  const dated = blocks(program).filter((block) => block.start_date)
  const active = currentBlockId(program)
  if (!dated.length) return active
  const activeStart = dated.find((block) => blockId(block) === active)?.start_date
  if (activeStart && value >= activeStart.slice(0, 10)) return active
  if (value < dated[0].start_date!.slice(0, 10)) return blockId(dated[0])
  for (let index = 0; index < dated.length; index += 1) {
    const block = dated[index]
    const start = block.start_date!.slice(0, 10)
    const next = dated[index + 1]?.start_date?.slice(0, 10)
    if (value >= start && (!next || value < next)) return blockId(block)
  }
  return blockId(dated.at(-1)!)
}

export function recordBlock(record: BlockScoped, field: string, program: ProgramScope): string {
  const active = currentBlockId(program)
  const stamped = record.block_id || record.block
  if (stamped) return stamped === 'current' ? active : stamped
  if (field === 'supplements') return active
  if (field === 'supplement_phases') {
    const start = phaseStart(record, program)
    return start ? blockForDate(start, program) : mostRecentCompleted(program) || active
  }
  const date = recordDate(record)
  return date ? blockForDate(date, program) : active
}

export function isInBlock(record: BlockScoped, blockId: string, activeBlockId: string): boolean {
  const key = record.block_id || record.block || ''
  if (blockId === activeBlockId || blockId === 'current') return key === activeBlockId || key === 'current'
  return key === blockId
}

const SCOPED_PROGRAM_LISTS = ['phases', 'sessions', 'diet_notes', 'supplements', 'supplement_phases', 'competitions'] as const

export function scopeProgramToBlock<T extends Program & { weight_log?: BlockScoped[] }>(program: T, blockId = 'current'): T {
  if (blockId === ALL_BLOCKS) return program
  const active = currentBlockId(program)
  const target = blockId === 'current' ? active : blockId
  const keep = (records: unknown, field: string) => Array.isArray(records)
    ? records.filter((record: BlockScoped) => record && recordBlock(record, field, program) === target)
    : records
  const scoped = { ...program } as T & Record<string, unknown>
  for (const field of SCOPED_PROGRAM_LISTS) scoped[field] = keep(program[field], field) as never
  if (program.weight_log) scoped.weight_log = keep(program.weight_log, 'weight_log') as never
  if (program.meta?.block_notes) scoped.meta = { ...program.meta, block_notes: keep(program.meta.block_notes, 'meta.block_notes') as never }
  if (Array.isArray(scoped.competitions)) {
    const dates = scoped.competitions.map((entry) => String(entry.date || '').slice(0, 10)).filter(Boolean).sort()
    scoped.meta = { ...(scoped.meta || program.meta), ...(dates.length ? { comp_date: dates[0] } : {}) }
    if (!dates.length) delete (scoped.meta as unknown as Record<string, unknown>).comp_date
  }
  return scoped
}
