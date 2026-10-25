import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Session } from '@powerlifting/types'
import { lastPerformance } from './lastPerformance'

function session(date: string, exercises: Session['exercises'], block = 'current'): Session {
  return { id: date, date, block, completed: true, exercises } as Session
}

test('picks the latest same-block Session in the last four weeks and groups its sets', () => {
  const current = session('2026-10-26', [])
  const sessions = [
    session('2026-09-20', [{ name: 'Bench Press', sets: 3, reps: 5, kg: 100, notes: '' }]),
    session('2026-10-12', [{ name: 'Bench Press', sets: 3, reps: 8, kg: 80, notes: '' }]),
    session('2026-10-19', [
      { name: 'Bench Press', sets: 3, reps: 6, kg: 85, notes: '', sets_data: [{ reps: 6, kg: 85, rpe: 9 }, { reps: 6, kg: 85, rpe: 8 }, { reps: 6, kg: 75, rpe: 8 }] },
    ]),
    session('2026-10-22', [{ name: 'Bench Press', sets: 3, reps: 5, kg: 90, notes: '' }], 'old-block'),
    current,
  ]
  assert.deepEqual(lastPerformance(sessions, current, 'Bench Press'), {
    date: '2026-10-19',
    groups: [{ sets: 2, reps: 6, kg: 85 }, { sets: 1, reps: 6, kg: 75 }],
  })
})

test('returns null when the exercise was not performed in range', () => {
  const current = session('2026-10-26', [])
  const sessions = [session('2026-09-01', [{ name: 'Squat', sets: 3, reps: 5, kg: 120, notes: '' }]), current]
  assert.equal(lastPerformance(sessions, current, 'Squat'), null)
  assert.equal(lastPerformance(sessions, current, 'Pallof Press'), null)
})

test('ignores skipped and pending sets', () => {
  const current = session('2026-10-26', [])
  const sessions = [
    session('2026-10-20', [{ name: 'Squat', sets: 3, reps: 5, kg: 120, notes: '', set_statuses: ['completed', 'skipped', 'pending'] }]),
    current,
  ]
  assert.deepEqual(lastPerformance(sessions, current, 'Squat')?.groups, [{ sets: 1, reps: 5, kg: 120 }])
})
