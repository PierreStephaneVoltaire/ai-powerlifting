import { create } from 'zustand'

export type RestTimerStatus = 'idle' | 'running' | 'paused' | 'finished'

interface RestTimerState {
  status: RestTimerStatus
  totalSeconds: number
  remainingMs: number
  deadlineMs: number | null
  pausedRemainingMs: number | null
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
  deadlineMs: null,
  pausedRemainingMs: null,
  finishedAt: null,
  dialogOpen: false,

  start: (seconds) => {
    const total = clampSeconds(seconds)
    set({
      status: 'running',
      totalSeconds: total,
      remainingMs: total * 1000,
      deadlineMs: Date.now() + total * 1000,
      pausedRemainingMs: null,
      finishedAt: null,
    })
  },

  pause: () => {
    const { status, deadlineMs } = get()
    if (status !== 'running' || deadlineMs === null) return
    const now = Date.now()
    const remaining = Math.max(0, deadlineMs - now)
    set({
      status: 'paused',
      deadlineMs: null,
      pausedRemainingMs: remaining,
      remainingMs: remaining,
    })
  },

  resume: () => {
    const { status, pausedRemainingMs } = get()
    if (status !== 'paused' || pausedRemainingMs === null) return
    const now = Date.now()
    set({
      status: 'running',
      deadlineMs: now + pausedRemainingMs,
      pausedRemainingMs: null,
      remainingMs: pausedRemainingMs,
    })
  },

  reset: () => {
    set({
      status: 'idle',
      totalSeconds: 0,
      remainingMs: 0,
      deadlineMs: null,
      pausedRemainingMs: null,
      finishedAt: null,
    })
  },

  addSeconds: (delta) => {
    const { status, deadlineMs, pausedRemainingMs, totalSeconds } = get()
    const deltaMs = delta * 1000
    const now = Date.now()

    if (status === 'idle') return

    if (status === 'running' && deadlineMs !== null) {
      const currentRemaining = Math.max(0, deadlineMs - now)
      const newRemaining = Math.max(0, currentRemaining + deltaMs)
      set({
        deadlineMs: now + newRemaining,
        remainingMs: newRemaining,
        totalSeconds: Math.max(0, totalSeconds + delta),
      })
      return
    }

    if (status === 'paused' && pausedRemainingMs !== null) {
      const newRemaining = Math.max(0, pausedRemainingMs + deltaMs)
      set({
        pausedRemainingMs: newRemaining,
        remainingMs: newRemaining,
        totalSeconds: Math.max(0, totalSeconds + delta),
      })
      return
    }

    if (status === 'finished') {
      const newRemaining = Math.max(0, 0 + deltaMs)
      if (newRemaining <= 0) return
      set({
        status: 'running',
        deadlineMs: now + newRemaining,
        remainingMs: newRemaining,
        totalSeconds: Math.ceil(newRemaining / 1000),
        pausedRemainingMs: null,
        finishedAt: null,
      })
    }
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
      deadlineMs: null,
      pausedRemainingMs: null,
      finishedAt: Date.now(),
    })
  },

  openDialog: () => set({ dialogOpen: true }),
  closeDialog: () => set({ dialogOpen: false }),
}))

export function computeRemainingMs(state: RestTimerState, now: number = Date.now()): number {
  if (state.status === 'idle') return 0
  if (state.status === 'finished') return 0
  if (state.status === 'paused') return Math.max(0, state.pausedRemainingMs ?? 0)
  if (state.status === 'running') {
    if (state.deadlineMs === null) return state.remainingMs
    return Math.max(0, state.deadlineMs - now)
  }
  return 0
}

export function formatRestMs(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}