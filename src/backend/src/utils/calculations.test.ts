import assert from 'node:assert/strict'
import test from 'node:test'
import { estimateSetE1rm, estimateSetE1rmValue, setPercentage } from './calculations'

test('set e1RM covers 1-10 reps and treats a missing RPE as RPE 10', () => {
  assert.equal(setPercentage(8, 9), 0.785)
  assert.equal(setPercentage(10, 8), 0.715)
  assert.equal(setPercentage(8), 0.82)
  assert.equal(setPercentage(11), null)
  assert.equal(setPercentage(11, 9), null)
  assert.equal(estimateSetE1rmValue(100, 1), 100)
  assert.equal(estimateSetE1rm(100, 6)?.method, 'assumed_rpe_10')
  assert.equal(estimateSetE1rm(100, 6, 8)?.method, 'rpe_table')
})
