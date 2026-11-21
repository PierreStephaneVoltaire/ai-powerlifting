import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { PlannedExercise } from '@powerlifting/types'
import { formatPlannedExercise, hasRepRange, plannedSets, repsLabel } from './plannedPrescription'
import { templatePrescription } from './templatePrescription'
import { exerciseVolume } from './volume'
import { bestSetE1rm } from './sbdE1rm'

const kg = (value: number) => `${value}kg`

test('keeps AMRAP and cardio minutes visible from template through planned session', () => {
  const curl: PlannedExercise = { name: 'Leg Curl', sets: 2, reps: null, rep_mode: 'amrap', kg: null, rpe_target: 8 }
  const bike: PlannedExercise = { name: 'Air Bike', sets: 1, reps: null, duration_minutes: 15, kg: null }
  assert.equal(templatePrescription(curl), '2 × AMRAP')
  assert.equal(formatPlannedExercise(curl, kg), '2 × AMRAP @RPE 8')
  assert.equal(templatePrescription(bike), '15 min')
  assert.equal(formatPlannedExercise({ ...bike, sets: 3 }, kg), '3 × 15 min')
})

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


test('formats seconds, minutes, and timed loads', () => {
  const timed: PlannedExercise = { name: 'Carry', sets: 2, reps: 30, rep_unit: 'seconds', kg: 20 }
  assert.equal(templatePrescription(timed), '2 × 30 sec')
  assert.equal(formatPlannedExercise(timed, kg), '2 × 30 sec @20kg')
  assert.equal(formatPlannedExercise({ ...timed, set_plan: [{ reps: 30, kg: 20 }, { reps: 45, kg: 25 }] }, kg), '30 sec @20kg, 45 sec @25kg')
  assert.equal(formatPlannedExercise({ ...timed, sets: 1, reps: 15, rep_unit: 'minutes', kg: null, rpe_target: 7 }, kg), '15 min @RPE 7')
})


test('timed exercises are excluded from tonnage and rep-based estimated maxes', () => {
  const exercise = { name: 'Bench Press', sets: 3, reps: 30, rep_unit: 'seconds' as const, kg: 20, notes: '' }
  assert.equal(exerciseVolume(exercise), 0)
  assert.equal(bestSetE1rm(exercise), null)
})
