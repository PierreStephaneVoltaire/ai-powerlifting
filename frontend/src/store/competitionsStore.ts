import { create } from 'zustand'
import type { UserCompetition, UserCompetitionUpdate, LiftResults, PostMeetReport } from '@powerlifting/types'
import * as api from '@/api/client'

interface CompetitionsState {
  competitions: UserCompetition[]
  filters: { country?: string; state?: string }
  isLoading: boolean
  error: string | null
  loadAll: (filters?: { country?: string; state?: string }) => Promise<void>
  setFilters: (filters: { country?: string; state?: string }) => void
  patch: (masterId: string, updates: UserCompetitionUpdate) => Promise<void>
  complete: (masterId: string, results: LiftResults, bodyWeightKg: number, postMeetReport?: PostMeetReport) => Promise<void>
  reset: () => void
}

export const useCompetitionsStore = create<CompetitionsState>((set, get) => ({
  competitions: [],
  filters: {},
  isLoading: false,
  error: null,

  loadAll: async (filters?: { country?: string; state?: string }) => {
    const f = filters ?? get().filters
    set({ isLoading: true, error: null, filters: f })
    try {
      const competitions = await api.fetchUserCompetitions(f)
      set({ competitions, isLoading: false })
    } catch (error) {
      set({ error: String(error), isLoading: false })
    }
  },

  setFilters: (filters) => {
    set({ filters })
  },

  patch: async (masterId, updates) => {
    await api.patchUserCompetition(masterId, updates)
    // Optimistic update
    set((state) => ({
      competitions: state.competitions.map((c) =>
        c.master_id === masterId ? { ...c, ...updates } : c
      ),
    }))
  },

  complete: async (masterId, results, bodyWeightKg, postMeetReport) => {
    await api.completeUserCompetition(masterId, results, bodyWeightKg, postMeetReport)
    // Optimistic update
    set((state) => ({
      competitions: state.competitions.map((c) =>
        c.master_id === masterId
          ? { ...c, user_status: 'completed', results, body_weight_kg: bodyWeightKg, post_meet_report: postMeetReport ?? c.post_meet_report }
          : c
      ),
    }))
  },

  reset: () => set({ competitions: [], filters: {}, isLoading: false, error: null }),
}))
