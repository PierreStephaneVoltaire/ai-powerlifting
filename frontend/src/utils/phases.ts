import type { Phase, Session } from '@powerlifting/types'

const DEFAULT_BLOCK = 'current'

const PHASE_PALETTE = [
  '#94a3b8', // index 0 - slate
  '#3b82f6', // index 1 - blue
  '#f97316', // index 2 - orange
  '#ef4444', // index 3 - red
  '#14b8a6', // index 4 - teal
  '#a855f7', // index 5 - purple
  '#22c55e', // index 6 - green
  '#eab308', // index 7 - yellow
]

function phaseBlock(p: Phase): string {
  return p.block ?? DEFAULT_BLOCK
}

/**
 * Filter phases to a single block (default "current").
 */
export function phasesForBlock(phases: Phase[], block: string = DEFAULT_BLOCK): Phase[] {
  return phases.filter(p => phaseBlock(p) === block)
}

/**
 * Color is indexed within the phase's own block so adding/removing phases
 * in one block does not shift colors in another.
 */
export function phaseColor(phase: Phase, allPhases: Phase[]): string {
  const block = phaseBlock(phase)
  const blockPhases = allPhases.filter(p => phaseBlock(p) === block)
  const index = blockPhases.findIndex(p => p.name === phase.name)
  return PHASE_PALETTE[index >= 0 ? index % PHASE_PALETTE.length : 0]
}

/**
 * Build a map from week number to Phase for O(1) lookup within a single block.
 */
export function buildPhaseMap(phases: Phase[], block: string = DEFAULT_BLOCK): Map<number, Phase> {
  const map = new Map<number, Phase>()
  for (const phase of phases) {
    if (phaseBlock(phase) !== block) continue
    for (let w = phase.start_week; w <= phase.end_week; w++) {
      map.set(w, phase)
    }
  }
  return map
}

/**
 * Filter sessions by phase name, optionally scoped to a block.
 */
export function sessionsByPhase(sessions: Session[], phaseName: string, block?: string): Session[] {
  return sessions.filter(s => {
    if (s.phase.name !== phaseName) return false
    if (block === undefined) return true
    return (s.block ?? DEFAULT_BLOCK) === block
  })
}

/**
 * Get unique phase names from sessions, optionally scoped to a block.
 */
export function uniquePhaseNames(sessions: Session[], block?: string): string[] {
  const names = new Set<string>()
  for (const s of sessions) {
    if (block !== undefined && (s.block ?? DEFAULT_BLOCK) !== block) continue
    names.add(s.phase.name)
  }
  return Array.from(names)
}
