import assert from 'node:assert/strict'
import test from 'node:test'
import type { Program } from '@powerlifting/types'
import { scopeProgramToBlock } from './blockScope'

const program = {
  meta: { current_block_id: 'block-new', block_notes: [] },
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
  assert.deepEqual(scoped.sessions.map((s) => s.date), ['2026-10-05'])
  assert.deepEqual(scoped.diet_notes.map((n) => n.notes), ['legacy'])
  assert.deepEqual(scoped.weight_log.map((e) => e.kg), [92])
})

test('scopeProgramToBlock selects a past block by id', () => {
  const scoped = scopeProgramToBlock(program, 'block-2025')
  assert.deepEqual(scoped.sessions.map((s) => s.date), ['2025-01-06'])
  assert.deepEqual(scoped.weight_log.map((e) => e.kg), [90])
})

test('scopeProgramToBlock leaves the program whole for all blocks', () => {
  assert.equal(scopeProgramToBlock(program, 'all'), program)
})
