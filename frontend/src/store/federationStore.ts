import { create } from 'zustand'
import type { FederationLibrary } from '@powerlifting/types'
import * as api from '@/api/client'

interface FederationState {
  library: FederationLibrary | null
  isLoading: boolean
  error: string | null
  loadLibrary: (force?: boolean) => Promise<FederationLibrary | null>
  saveLibrary: (library: FederationLibrary) => Promise<FederationLibrary>
  reset: () => void
}

export const useFederationStore = create<FederationState>((set, get) => ({
  library: null,
  isLoading: false,
  error: null,

  loadLibrary: async (force = false) => {
    if (get().library && !force) {
      return get().library
    }

    set({ isLoading: true, error: null })
    try {
      const library = await api.fetchFederationLibrary()
      set({ library, isLoading: false })
      return library
    } catch (error) {
      set({ error: String(error), isLoading: false })
      return null
    }
  },

  saveLibrary: async (library) => {
    set({ isLoading: true, error: null })
    try {
      const nextLibrary = await api.updateFederationLibrary(library)
      set({ library: nextLibrary, isLoading: false })
      return nextLibrary
    } catch (error) {
      set({ error: String(error), isLoading: false })
      throw error
    }
  },

  reset: () => set({ library: null, isLoading: false, error: null }),
}))
