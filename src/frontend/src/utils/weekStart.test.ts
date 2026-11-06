import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Program } from '@powerlifting/types'
import { weekStartForBlock } from './weekStart'

function program(meta: Record<string, unknown>): Program {
  return { meta, sessions: [], phases: [] } as unknown as Program
}

test('week start comes from the block record', () => {
  const blocks = program({
    current_block_id: 'block-new',
    blocks: [{ id: 'old-block', status: 'completed', week_start_day: 'Saturday' }, { id: 'block-new', status: 'active', week_start_day: 'Sunday' }],
  })
  assert.equal(weekStartForBlock(blocks, 'current'), 'Sunday')
  assert.equal(weekStartForBlock(blocks, 'old-block'), 'Saturday')
})

test('falls back to the active block record, then Monday', () => {
  assert.equal(weekStartForBlock(program({ blocks: [{ id: 'b1', status: 'active', week_start_day: 'Tuesday' }] })), 'Tuesday')
  assert.equal(weekStartForBlock(program({})), 'Monday')
})
