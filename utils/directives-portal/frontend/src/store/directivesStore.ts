import { create } from 'zustand'
import {
  Directive,
  fetchDirectives,
  createDirective,
  reviseDirective,
  reorderDirective,
  deleteDirective,
  bulkReorderDirectives,
  fetchDirectiveHistory,
  DirectiveHistoryResponse,
  CreateDirectiveInput,
  ReviseDirectiveInput,
  BulkReorderItem,
} from '../api/client'

interface DirectivesStore {
  directives: Directive[]
  loading: boolean
  error: string | null
  history: DirectiveHistoryResponse | null
  historyLoading: boolean

  fetchAll: () => Promise<void>
  create: (input: CreateDirectiveInput) => Promise<Directive>
  revise: (alpha: number, beta: number, input: ReviseDirectiveInput) => Promise<Directive>
  reorder: (alpha: number, beta: number, newAlpha: number, newBeta: number) => Promise<Directive>
  bulkReorder: (items: BulkReorderItem[]) => Promise<Directive[]>
  remove: (alpha: number, beta: number) => Promise<void>
  fetchHistory: (alpha: number, beta: number) => Promise<void>
  clearHistory: () => void
  clearError: () => void
}

export const useDirectivesStore = create<DirectivesStore>((set, get) => ({
  directives: [],
  loading: false,
  error: null,
  history: null,
  historyLoading: false,

  fetchAll: async () => {
    set({ loading: true, error: null })
    try {
      const directives = await fetchDirectives()
      set({ directives, loading: false })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load directives'
      set({ error: msg, loading: false })
    }
  },

  create: async (input: CreateDirectiveInput) => {
    const directive = await createDirective(input)
    await get().fetchAll()
    return directive
  },

  revise: async (alpha: number, beta: number, input: ReviseDirectiveInput) => {
    const directive = await reviseDirective(alpha, beta, input)
    await get().fetchAll()
    return directive
  },

  reorder: async (alpha: number, beta: number, newAlpha: number, newBeta: number) => {
    const directive = await reorderDirective(alpha, beta, newAlpha, newBeta)
    await get().fetchAll()
    return directive
  },

  bulkReorder: async (items: BulkReorderItem[]) => {
    const directives = await bulkReorderDirectives(items)
    set({ directives })
    return directives
  },

  remove: async (alpha: number, beta: number) => {
    await deleteDirective(alpha, beta)
    await get().fetchAll()
  },

  fetchHistory: async (alpha: number, beta: number) => {
    set({ historyLoading: true })
    try {
      const history = await fetchDirectiveHistory(alpha, beta)
      set({ history, historyLoading: false })
    } catch {
      set({ history: null, historyLoading: false })
    }
  },

  clearHistory: () => set({ history: null }),
  clearError: () => set({ error: null }),
}))