import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRequire } from 'node:module'
import type * as SbdE1rm from './sbdE1rm'

const { bestSetE1rm, mainLiftFor } = createRequire(import.meta.url)('./sbdE1rm.ts') as typeof SbdE1rm

test('main lifts match regardless of case, plurals and pause variants', () => {
  assert.equal(mainLiftFor('Back Squats'), 'squat')
  assert.equal(mainLiftFor('squat'), 'squat')
  assert.equal(mainLiftFor('Pause Bench Press'), 'bench')
  assert.equal(mainLiftFor('BENCH PRESS'), 'bench')
  assert.equal(mainLiftFor('Deadlifts'), 'deadlift')
  assert.equal(mainLiftFor('Romanian Deadlift'), null)
  assert.equal(mainLiftFor('Incline DB Bench Press'), null)
  assert.equal(mainLiftFor('Hack Squat'), null)
})

test('per-set data is used and the heaviest estimate wins', () => {
  const exercise = {
    name: 'Squat', sets: 3, reps: 6, kg: 124.738, notes: '',
    sets_data: [{ kg: 124.738, reps: 6, rpe: 8 }, { kg: 142.882, reps: 6, rpe: 9 }, { kg: 124.738, reps: 6, rpe: 8.5 }],
  }
  assert.equal(bestSetE1rm(exercise), Number((142.882 / 0.825).toFixed(1)))
})

test('skipped sets are ignored and session RPE is the fallback', () => {
  const exercise = {
    name: 'Bench Press', sets: 2, reps: 5, kg: 100, notes: '',
    set_statuses: ['completed', 'skipped'] as const,
    sets_data: [{ kg: 80, reps: 5, rpe: null }, { kg: 120, reps: 5, rpe: 9 }],
  }
  assert.equal(bestSetE1rm({ ...exercise, set_statuses: [...exercise.set_statuses] }, 8), Number((80 / 0.815).toFixed(1)))
})
