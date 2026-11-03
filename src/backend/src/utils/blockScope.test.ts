import assert from 'node:assert/strict'
import test from 'node:test'
import type { Program } from '@powerlifting/types'
import { recordBlock, scopeProgramToBlock } from './blockScope'

const program = {
  meta: {
    current_block_id: 'block-new',
    program_start: '2026-02-15',
    block_notes: [],
    blocks: [
      { id: 'block-old', status: 'completed', completed_at: '2026-09-27', start_date: '2026-02-15' },
      { id: 'block-new', status: 'active', start_date: '2026-10-06' },
    ],
  },
  phases: [],
  sessions: [
    { date: '2025-01-06', week_number: 1, block: 'block-2025', block_id: 'block-2025' },
    { date: '2026-10-05', week_number: 1, block: 'current', block_id: 'block-new' },
  ],
  diet_notes: [{ date: '2025-01-07', notes: 'old', block_id: 'block-2025' }, { date: '2026-10-06', notes: 'legacy' }],
  supplements: [],
  supplement_phases: [],
  competitions: [],
  weight_log: [{ date: '2025-01-06', kg: 90, block_id: 'block-2025' }, { date: '2026-10-06', kg: 92, block_id: 'block-new' }],
} as unknown as Program & { weight_log: { date: string; kg: number; block_id?: string }[] }

test('scopeProgramToBlock keeps only the active block by default', () => {
  const scoped = scopeProgramToBlock(program)
  assert.deepEqual(scoped.sessions.map((s) => s.date), [])
  assert.deepEqual(scoped.diet_notes.map((n) => n.notes), ['legacy'])
  assert.deepEqual(scoped.weight_log.map((e) => e.kg), [92])
})

test('scopeProgramToBlock selects a past block by id', () => {
  const scoped = scopeProgramToBlock(program, 'block-2025')
  assert.deepEqual(scoped.sessions.map((s) => s.date), [])
  assert.deepEqual(scoped.weight_log.map((e) => e.kg), [])
})

test('scopeProgramToBlock leaves the program whole for all blocks', () => {
  assert.equal(scopeProgramToBlock(program, 'all'), program)
})

test('recordBlock follows boundaries and fallback rules', () => {
  assert.equal(recordBlock({ date: '2026-10-05' }, 'diet_notes', program), 'block-old')
  assert.equal(recordBlock({ date: '2026-10-06' }, 'diet_notes', program), 'block-new')
  assert.equal(recordBlock({ date: '2025-01-01' }, 'diet_notes', program), 'block-old')
  assert.equal(recordBlock({ name: 'creatine' }, 'supplements', program), 'block-new')
  assert.equal(recordBlock({ start_week: 29 }, 'supplement_phases', program), 'block-old')
})
