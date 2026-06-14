import { create } from 'zustand'
import type { AthleteGoal } from '@powerlifting/types'
import * as api from '@/api/client'

// Goals still use versioned endpoints for now (the backend goalsController
// already reads from POWERLIFTING_GOALS_TABLE, but the route still takes :version)

interface GoalsState {
  goals: AthleteGoal[]
  isLoading: boolean
  error: string | null
  loadAll: (version: string) => Promise<void>
  saveAll: (version: string, goals: AthleteGoal[]) => Promise<void>
  reset: () => void
}

export const useGoalsStore = create<GoalsState>((set) => ({
  goals: [],
  isLoading: false,
  error: null,

  loadAll: async (version: string) => {
    set({ isLoading: true, error: null })
    try {
      const goals = await api.fetchGoals(version)
      set({ goals, isLoading: false })
    } catch (error) {
      set({ error: String(error), isLoading: false })
    }
  },

  saveAll: async (version: string, goals: AthleteGoal[]) => {
    set({ isLoading: true, error: null })
    try {
      await api.updateGoals(version, goals)
      set({ goals, isLoading: false })
    } catch (error) {
      set({ error: String(error), isLoading: false })
      throw error
    }
  },

  reset: () => set({ goals: [], isLoading: false, error: null }),
}))
