import { create } from 'zustand'
import {
  fetchProposals,
  fetchProposal,
  createProposal as apiCreateProposal,
  approveProposal as apiApproveProposal,
  rejectProposal as apiRejectProposal,
  deleteProposal as apiDeleteProposal,
  fetchDirectives,
  fetchDirective,
} from '../api/client'
import type {
  CreateProposalInput,
  Directive,
  Proposal,
  ProposalFilters,
} from '../types'

interface ProposalsState {
  // State
  proposals: Proposal[]
  selectedProposal: Proposal | null
  directives: Directive[]
  selectedDirective: Directive | null
  loading: boolean
  error: string | null
  filters: ProposalFilters

  // Actions
  loadProposals: (filters?: ProposalFilters) => Promise<void>
  loadProposal: (sk: string) => Promise<void>
  createProposal: (input: CreateProposalInput) => Promise<Proposal>
  approveProposal: (sk: string) => Promise<void>
  rejectProposal: (sk: string, reason?: string) => Promise<void>
  deleteProposal: (sk: string) => Promise<void>
  loadDirectives: () => Promise<void>
  loadDirective: (sk: string) => Promise<void>
  setFilters: (filters: ProposalFilters) => void
  setSelectedProposal: (proposal: Proposal | null) => void
  updateProposalInList: (proposal: Proposal) => void
  clearError: () => void
}

export const useProposalsStore = create<ProposalsState>((set, get) => ({
  // Initial state
  proposals: [],
  selectedProposal: null,
  directives: [],
  selectedDirective: null,
  loading: false,
  error: null,
  filters: {},

  // Actions
  loadProposals: async (filters?: ProposalFilters) => {
    set({ loading: true, error: null, filters: filters ?? get().filters })
    try {
      const { proposals } = await fetchProposals(filters ?? get().filters)
      set({ proposals, loading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load proposals', loading: false })
    }
  },

  loadProposal: async (sk: string) => {
    set({ loading: true, error: null })
    try {
      const { proposal } = await fetchProposal(sk)
      set({ selectedProposal: proposal, loading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load proposal', loading: false })
    }
  },

  createProposal: async (input: CreateProposalInput) => {
    set({ loading: true, error: null })
    try {
      const { proposal } = await apiCreateProposal(input)
      set((state) => ({
        proposals: [proposal, ...state.proposals],
        loading: false,
      }))
      return proposal
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to create proposal', loading: false })
      throw error
    }
  },

  approveProposal: async (sk: string) => {
    set({ loading: true, error: null })
    try {
      const { proposal } = await apiApproveProposal(sk)
      set((state) => ({
        proposals: state.proposals.map((p) => (p.sk === sk ? proposal : p)),
        selectedProposal:
          state.selectedProposal?.sk === sk ? proposal : state.selectedProposal,
        loading: false,
      }))
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to approve proposal', loading: false })
    }
  },

  rejectProposal: async (sk: string, reason?: string) => {
    set({ loading: true, error: null })
    try {
      const { proposal } = await apiRejectProposal(sk, reason)
      set((state) => ({
        proposals: state.proposals.map((p) => (p.sk === sk ? proposal : p)),
        selectedProposal:
          state.selectedProposal?.sk === sk ? proposal : state.selectedProposal,
        loading: false,
      }))
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to reject proposal', loading: false })
    }
  },

  deleteProposal: async (sk: string) => {
    set({ loading: true, error: null })
    try {
      await apiDeleteProposal(sk)
      set((state) => ({
        proposals: state.proposals.filter((p) => p.sk !== sk),
        selectedProposal: state.selectedProposal?.sk === sk ? null : state.selectedProposal,
        loading: false,
      }))
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to delete proposal', loading: false })
    }
  },

  loadDirectives: async () => {
    set({ loading: true, error: null })
    try {
      const { directives } = await fetchDirectives()
      set({ directives, loading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load directives', loading: false })
    }
  },

  loadDirective: async (sk: string) => {
    set({ loading: true, error: null })
    try {
      const { directive } = await fetchDirective(sk)
      set({ selectedDirective: directive, loading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load directive', loading: false })
    }
  },

  setFilters: (filters: ProposalFilters) => {
    set({ filters })
  },

  setSelectedProposal: (proposal: Proposal | null) => {
    set({ selectedProposal: proposal })
  },

  updateProposalInList: (proposal: Proposal) => {
    set((state) => ({
      proposals: state.proposals.map((p) => (p.sk === proposal.sk ? proposal : p)),
      selectedProposal:
        state.selectedProposal?.sk === proposal.sk ? proposal : state.selectedProposal,
    }))
  },

  clearError: () => {
    set({ error: null })
  },
}))