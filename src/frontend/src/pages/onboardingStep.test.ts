import assert from 'node:assert/strict'
import { test } from 'node:test'
import { onboardingStepFor } from './onboardingStep'

test('selected Coach and Handler views never enter Athlete basics', () => {
  assert.equal(onboardingStepFor('athlete_basics', 'coach', false, false), 1)
  assert.equal(onboardingStepFor('done', 'handler', false, false), 1)
  assert.equal(onboardingStepFor('athlete_basics', 'athlete', false, false), 2)
})
