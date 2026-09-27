import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canApplyCompetitionRequest } from './competitionRequestGuard'

test('late competition success, rejection, and cleanup cannot cross request partitions', () => {
  assert.equal(canApplyCompetitionRequest('[person-a,athlete-a]', 2, '[person-b,athlete-b]', 3), false)
  assert.equal(canApplyCompetitionRequest('[person-a,athlete-a]', 2, '[person-a,athlete-a]', 3), false)
  assert.equal(canApplyCompetitionRequest('[person-a,athlete-a]', 2, '[person-a,athlete-a]', 2), true)
})
