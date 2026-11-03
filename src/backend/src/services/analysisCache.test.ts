import assert from 'node:assert/strict'
import test from 'node:test'
import type { Program, Session } from '@powerlifting/types'
import { buildAnalysisWindows } from './analysisCache'

function session(date: string, week_number: number): Session {
  return { date, week_number, block: 'current', completed: true, status: 'completed', exercises: [] } as unknown as Session
}

test('analysis windows include every session labelled with the selected weeks', () => {
  const program = {
    meta: { program_start: '2026-10-06', block_week_start_days: { current: 'Saturday' } },
    sessions: [
      session('2026-10-10', 1),
      session('2026-10-12', 2),
      session('2026-10-25', 4),
      session('2026-10-30', 4),
      session('2026-10-31', 4),
    ],
  } as unknown as Program

  const windows = buildAnalysisWindows(program, '2026-10-31')

  assert.equal(windows.current.weekEnd, 4)
  assert.equal(windows.current.end, '2026-10-31')
  assert.equal(windows.previous_4.end, '2026-10-31')
  assert.equal(windows.block.start, '2026-10-06')
})

test('analysis weeks use the active block week start, not a stale current key', () => {
  const program = {
    meta: {
      program_start: '2026-10-06',
      current_block_id: 'block-new',
      block_week_start_days: { current: 'Saturday', 'block-new': 'Sunday' },
    },
    sessions: [session('2026-10-25', 4), session('2026-10-31', 4)],
  } as unknown as Program

  const windows = buildAnalysisWindows(program, '2026-10-31')

  assert.equal(windows.current.start, '2026-10-25')
  assert.equal(windows.current.end, '2026-10-31')
})
