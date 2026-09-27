import assert from 'node:assert/strict'
import { test } from 'node:test'
import { shouldRestoreOwnContext } from './contextRestore'

test('Back and Settings restore the own Athlete after delegated navigation', () => {
  assert.equal(shouldRestoreOwnContext('/', 'athlete-b', 'athlete-a'), true)
  assert.equal(shouldRestoreOwnContext('/settings', 'athlete-b', 'athlete-a'), true)
  assert.equal(shouldRestoreOwnContext('/programs/current', 'athlete-b', 'athlete-a'), false)
  assert.equal(shouldRestoreOwnContext('/profile', 'athlete-a', 'athlete-a'), false)
})
