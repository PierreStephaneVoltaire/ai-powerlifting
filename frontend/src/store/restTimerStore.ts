import { create } from 'zustand'

export type RestTimerStatus = 'idle' | 'running' | 'paused' | 'finished'

interface RestTimerState {
  status: RestTimerStatus
  totalSeconds: number
  remainingMs: number
  runningStartedAt: number | null
  pausedAccumulatedMs: number
  pausedAt: number | null
  finishedAt: number | null
  dialogOpen: boolean

  start: (seconds: number) => void
  pause: () => void
  resume: () => void
  reset: () => void
  addSeconds: (delta: number) => void
  setRemainingMs: (ms: number) => void
  markFinished: () => void
  openDialog: () => void
  closeDialog: () => void
}

function clampSeconds(seconds: number): number {
  if (!Number.isFinite(seconds)) return 60
  return Math.max(5, Math.min(60 * 60, Math.round(seconds)))
}

export const useRestTimerStore = create<RestTimerState>()((set, get) => ({
  status: 'idle',
  totalSeconds: 0,
  remainingMs: 0,
  runningStartedAt: null,
  pausedAccumulatedMs: 0,
  pausedAt: null,
  finishedAt: null,
  dialogOpen: false,

  start: (seconds) => {
    const total = clampSeconds(seconds)
    set({
      status: 'running',
      totalSeconds: total,
      remainingMs: total * 1000,
      runningStartedAt: Date.now(),
      pausedAccumulatedMs: 0,
      pausedAt: null,
      finishedAt: null,
    })
  },

  pause: () => {
    const { status, runningStartedAt, pausedAccumulatedMs, remainingMs } = get()
    if (status !== 'running' || runningStartedAt === null) return
    const elapsedSinceRunStart = Date.now() - runningStartedAt
    set({
      status: 'paused',
      pausedAt: Date.now(),
      pausedAccumulatedMs: pausedAccumulatedMs + elapsedSinceRunStart,
      runningStartedAt: null,
      remainingMs,
    })
  },

  resume: () => {
    const { status, pausedAt, pausedAccumulatedMs, remainingMs } = get()
    if (status !== 'paused' || pausedAt === null) return
    set({
      status: 'running',
      runningStartedAt: Date.now(),
      pausedAt: null,
      pausedAccumulatedMs: pausedAccumulatedMs + (Date.now() - pausedAt),
      remainingMs,
    })
  },

  reset: () => {
    set({
      status: 'idle',
      totalSeconds: 0,
      remainingMs: 0,
      runningStartedAt: null,
      pausedAccumulatedMs: 0,
      pausedAt: null,
      finishedAt: null,
    })
  },

  addSeconds: (delta) => {
    const { status, totalSeconds, remainingMs } = get()

    if (status === 'finished') {
      const newTotal = 15
      set({
        status: 'running',
        totalSeconds: newTotal,
        remainingMs: newTotal * 1000,
        runningStartedAt: Date.now(),
        pausedAccumulatedMs: 0,
        pausedAt: null,
        finishedAt: null,
      })
      return
    }

    if (status === 'idle') return

    const deltaMs = delta * 1000
    const capMs = (totalSeconds + 600) * 1000
    const elapsedMs = Math.max(0, totalSeconds * 1000 - remainingMs)
    let newRemaining = remainingMs + deltaMs

    if (deltaMs < 0 && newRemaining < 15 * 1000) {
      newRemaining = 0
    } else {
      newRemaining = Math.max(0, Math.min(capMs, newRemaining))
    }

    const newTotalSeconds = Math.max(0, Math.ceil((newRemaining + elapsedMs) / 1000))

    set({ remainingMs: newRemaining, totalSeconds: newTotalSeconds })
  },

  setRemainingMs: (ms) => {
    const { status } = get()
    if (status === 'running' || status === 'paused') {
      set({ remainingMs: Math.max(0, ms) })
    }
  },

  markFinished: () => {
    if (get().status === 'finished') return
    set({
      status: 'finished',
      remainingMs: 0,
      runningStartedAt: null,
      pausedAt: null,
      finishedAt: Date.now(),
    })
  },

  openDialog: () => set({ dialogOpen: true }),
  closeDialog: () => set({ dialogOpen: false }),
}))

export function computeRemainingMs(state: RestTimerState, now: number = Date.now()): number {
  if (state.status === 'idle' || state.totalSeconds === 0) return 0
  if (state.status === 'finished') return 0
  if (state.status === 'paused') return Math.max(0, state.remainingMs)

  if (state.runningStartedAt === null) return state.remainingMs
  const elapsed = now - state.runningStartedAt - state.pausedAccumulatedMs
  return Math.max(0, state.totalSeconds * 1000 - elapsed)
}

export function formatRestMs(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}