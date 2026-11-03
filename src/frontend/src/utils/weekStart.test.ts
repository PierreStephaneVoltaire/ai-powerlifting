import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Program } from '@powerlifting/types'
import { weekStartForBlock } from './weekStart'

function program(meta: Record<string, unknown>): Program {
  return { meta, sessions: [], phases: [] } as unknown as Program
}

test('the active block id wins over a stale current key', () => {
  const stale = program({
    current_block_id: 'block-new',
    block_week_start_days: { current: 'Saturday', 'block-new': 'Sunday', 'old-block': 'Saturday' },
  })
  assert.equal(weekStartForBlock(stale, 'current'), 'Sunday')
  assert.equal(weekStartForBlock(stale, 'old-block'), 'Saturday')
})

test('falls back to the active block record, then current, then the program default', () => {
  assert.equal(weekStartForBlock(program({ blocks: [{ id: 'b1', status: 'active', week_start_day: 'Tuesday' }] })), 'Tuesday')
  assert.equal(weekStartForBlock(program({ block_week_start_days: { current: 'Friday' } })), 'Friday')
  assert.equal(weekStartForBlock(program({ program_week_start_day: 'Wednesday' })), 'Wednesday')
  assert.equal(weekStartForBlock(program({})), 'Monday')
})
