import { create } from 'zustand'
import type { UserCompetition, UserCompetitionUpdate, LiftResults, PostMeetReport } from '@powerlifting/types'
import * as api from '@/api/client'
import { requestPartition } from '@/api/context'
import { canApplyCompetitionRequest } from './competitionRequestGuard'

let latestLoadRequest = 0

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
    const partition = requestPartition()
    const request = ++latestLoadRequest
    const f = filters ?? get().filters
    set({ isLoading: true, error: null, filters: f })
    try {
      const competitions = await api.fetchUserCompetitions(f)
      if (canApplyCompetitionRequest(partition, request, requestPartition(), latestLoadRequest)) set({ competitions, isLoading: false })
    } catch (error) {
      if (canApplyCompetitionRequest(partition, request, requestPartition(), latestLoadRequest)) set({ error: String(error), isLoading: false })
    }
  },

  setFilters: (filters) => {
    set({ filters })
  },

  patch: async (masterId, updates) => {
    const current = get().competitions.find((competition) => competition.master_id === masterId)
    if (!current) throw new Error('Competition is no longer loaded')
    const updated = await api.patchUserCompetition(masterId, updates, api.mutationEnvelope((current as UserCompetition & { revision?: number }).revision ?? 0))
    set((state) => ({
      competitions: state.competitions.map((c) =>
        c.master_id === masterId ? updated : c
      ),
    }))
  },

  complete: async (masterId, results, bodyWeightKg, postMeetReport) => {
    const current = get().competitions.find((competition) => competition.master_id === masterId)
    if (!current) throw new Error('Competition is no longer loaded')
    const updated = await api.completeUserCompetition(masterId, results, bodyWeightKg, api.mutationEnvelope((current as UserCompetition & { revision?: number }).revision ?? 0), postMeetReport)
    set((state) => ({
      competitions: state.competitions.map((c) =>
        c.master_id === masterId
          ? updated
          : c
      ),
    }))
  },

  reset: () => set({ competitions: [], filters: {}, isLoading: false, error: null }),
}))
