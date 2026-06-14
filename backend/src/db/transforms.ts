import type { Program, Session, Phase } from '@powerlifting/types'

/**
 * Parse week number from a week label string.
 * Examples: 'W7 (Intensification)' -> 7, 'W1 (Warmup)' -> 1, 'W10' -> 10, '1' -> 1
 */
function parseWeekNumber(weekLabel: string | number | undefined): number {
  if (typeof weekLabel === 'number') {
    return weekLabel
  }
  if (!weekLabel) {
    return 0
  }
  // Try to match "W<number>" pattern first
  const match = weekLabel.match(/W(\d+)/i)
  if (match) {
    return parseInt(match[1], 10)
  }
  // Try to parse as plain number
  const num = parseInt(weekLabel, 10)
  return isNaN(num) ? 0 : num
}

const DEFAULT_BLOCK = 'current'

function phaseBlock(p: Phase): string {
  return p.block ?? DEFAULT_BLOCK
}

function sessionBlock(s: Session): string {
  return s.block ?? DEFAULT_BLOCK
}

/**
 * Resolve the correct Phase object for a given week number, scoped to the session's block.
 * Phases match only if they share the same block as the session (default "current").
 * start_week/end_week are block-local (1 = first week of the block).
 */
function resolvePhase(weekNum: number, block: string, phases: Phase[]): Phase {
  if (weekNum <= 0 || phases.length === 0) {
    return { name: 'Unscheduled', intent: '', start_week: 0, end_week: 0, block }
  }
  const phase = phases.find(
    p => phaseBlock(p) === block && weekNum >= p.start_week && weekNum <= p.end_week
  )
  return phase ?? { name: 'Unscheduled', intent: '', start_week: weekNum, end_week: weekNum, block }
}

/**
 * Transform DynamoDB item into a clean Program object.
 */
export function transformProgram(item: Record<string, unknown>): Program {
  const program = item as unknown as Program
  const legacyBlockNotes = Array.isArray((item as { block_notes?: unknown }).block_notes)
    ? (item as { block_notes: Program['meta']['block_notes'] }).block_notes
    : []

  // Ensure sessions and phases arrays exist
  if (!program.sessions) {
    program.sessions = []
  }
  if (!program.phases) {
    program.phases = []
  }
  if (!program.competitions) {
    program.competitions = []
  }
  if (!program.goals) {
    program.goals = []
  }
  if (!program.diet_notes) {
    program.diet_notes = []
  }
  if (!program.supplements) {
    program.supplements = []
  }
  if (!program.supplement_phases) {
    program.supplement_phases = []
  }
  if (!Array.isArray(program.meta.block_notes) || (program.meta.block_notes.length === 0 && legacyBlockNotes.length > 0)) {
    program.meta.block_notes = legacyBlockNotes
  }

  // Derive week_number and resolve phase for each session within its block
  program.sessions = program.sessions.map(session => {
    const weekNum = typeof session.week_number === 'number'
      ? session.week_number
      : parseWeekNumber(session.week as string | number | undefined)
    const block = sessionBlock(session)
    const phase = resolvePhase(weekNum, block, program.phases)

    return {
      ...session,
      week_number: weekNum,
      phase,
      phase_name: phase.name,
    }
  })

  // Sort sessions by date
  program.sessions.sort((a, b) => a.date.localeCompare(b.date))

  return program
}

/**
 * Get the current week number based on program start date.
 */
export function getCurrentWeek(programStart: string): number {
  const start = new Date(programStart)
  const now = new Date()
  const diffTime = now.getTime() - start.getTime()
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24))
  return Math.max(1, Math.floor(diffDays / 7) + 1)
}
