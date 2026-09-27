import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildCurrentProgramBlockIndex, resolveCurrentBlockId } from './blockAnalytics'

test('current block is resolved from program metadata', () => {
  assert.equal(resolveCurrentBlockId({ meta: { current_block_id: 'block-2' } } as any), 'block-2')
  assert.equal(resolveCurrentBlockId({ meta: { current_block_id: 'current' } } as any), 'current')
  assert.equal(resolveCurrentBlockId({ meta: {} } as any), 'current')
  assert.equal(resolveCurrentBlockId({ meta: { current_block_id: null } } as any), null)
  assert.equal(resolveCurrentBlockId({ meta: { blocks: [{ id: 'block-3', status: 'active' }] } } as any), 'block-3')
  assert.equal(resolveCurrentBlockId({ meta: { blocks: [{ id: 'block-3', status: 'completed' }] } } as any), null)
})

test('block index uses stable active metadata and never marks archived blocks Current', async () => {
  const session = (block: string) => ({ id: block, date: '2026-01-01', block, status: 'planned', week_number: 1, exercises: [] })
  const entries = await buildCurrentProgramBlockIndex('', { meta: { current_block_id: 'block-2', blocks: [{ id: 'block-1', name: 'Current' }, { id: 'block-2', name: 'Peak' }] }, sessions: [session('block-1'), session('block-2')] } as any, [])
  assert.equal(entries.find(entry => entry.block === 'block-1')?.isCurrent, false)
  assert.equal(entries.find(entry => entry.block === 'block-1')?.label, '2026-01-01')
  assert.equal(entries.find(entry => entry.block === 'block-2')?.isCurrent, true)
  assert.equal(entries.find(entry => entry.block === 'block-2')?.label, 'Peak')
  const completed = await buildCurrentProgramBlockIndex('', { meta: { current_block_id: null }, sessions: [session('block-1')] } as any, [])
  assert.equal(completed[0]?.isCurrent, false)
  assert.notEqual(completed[0]?.label, 'Current')
  assert.notEqual(completed[0]?.label, 'current')
})
