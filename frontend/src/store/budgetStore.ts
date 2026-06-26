import { create } from 'zustand'
import type { BudgetItem, BudgetConfig, BudgetStore } from '@powerlifting/types'
import * as api from '@/api/client'

interface BudgetState {
  config: BudgetConfig
  items: BudgetItem[]
  isLoading: boolean
  error: string | null
  loaded: boolean
  load: (force?: boolean) => Promise<void>
  save: (store: { config: BudgetConfig; items: BudgetItem[] }) => Promise<void>
  setItemPhoto: (itemId: string, photoS3Key: string | null) => void
  reset: () => void
}

const DEFAULT_CONFIG: BudgetConfig = {
  user_pk: '',
  monthly_cap: 0,
  currency: 'CAD',
  notes: null,
  updated_at: new Date().toISOString(),
}

export const useBudgetStore = create<BudgetState>((set, get) => ({
  config: DEFAULT_CONFIG,
  items: [],
  isLoading: false,
  error: null,
  loaded: false,

  load: async (force = false) => {
    if (get().loaded && !force) return
    set({ isLoading: true, error: null })
    try {
      const store = await api.fetchBudget()
      set({ config: store.config, items: store.items, isLoading: false, loaded: true })
    } catch (error) {
      set({ error: String(error), isLoading: false, loaded: true })
    }
  },

  save: async (store) => {
    set({ isLoading: true, error: null })
    try {
      await api.putBudget(store)
      set({ config: store.config, items: store.items, isLoading: false })
    } catch (error) {
      set({ error: String(error), isLoading: false })
      throw error
    }
  },

  setItemPhoto: (itemId, photoS3Key) => {
    set((state) => ({
      items: state.items.map((it) =>
        it.id === itemId ? { ...it, photo_s3_key: photoS3Key } : it,
      ),
    }))
  },

  reset: () => set({ config: DEFAULT_CONFIG, items: [], isLoading: false, error: null, loaded: false }),
}))

export type { BudgetStore }
