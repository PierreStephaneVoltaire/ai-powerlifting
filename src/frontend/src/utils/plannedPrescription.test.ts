import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { PlannedExercise } from '@powerlifting/types'
import { formatPlannedExercise, hasRepRange, plannedSets, repsLabel } from './plannedPrescription'

const kg = (value: number) => `${value}kg`

test('formats straight sets with fixed reps and with a rep range', () => {
  assert.equal(formatPlannedExercise({ name: 'Squat', sets: 3, reps: 5, kg: 100 }, kg), '3x5 @100kg')
  assert.equal(formatPlannedExercise({ name: 'Row', sets: 3, reps: 8, reps_max: 12, kg: null }, kg), '3x8-12')
  assert.equal(repsLabel(5, 5), '5')
})

test('groups identical consecutive planned sets in a per-set plan', () => {
  const exercise: PlannedExercise = {
    name: 'Bench',
    sets: 3,
    reps: 5,
    kg: 90,
    set_plan: [
      { reps: 5, reps_max: 8, kg: 90 },
      { reps: 5, reps_max: 8, kg: 90 },
      { reps: 3, kg: 100 },
    ],
  }
  assert.equal(formatPlannedExercise(exercise, kg), '2x5-8 @90kg, 1x3 @100kg')
  assert.equal(hasRepRange(exercise), true)
})

test('expands straight sets into a per-set plan', () => {
  assert.deepEqual(plannedSets({ name: 'Squat', sets: 2, reps: 5, kg: 100, rpe_target: 8 }), [
    { reps: 5, reps_max: null, kg: 100, rpe_target: 8 },
    { reps: 5, reps_max: null, kg: 100, rpe_target: 8 },
  ])
})
