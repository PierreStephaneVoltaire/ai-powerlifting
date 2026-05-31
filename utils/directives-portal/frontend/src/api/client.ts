import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface Directive {
  alpha: number
  beta: number
  version: number
  label: string
  content: string
  types: string[]
  created_by: string
  created_at: string
}

export interface DirectiveVersion {
  version: number
  label: string
  content: string
  types: string[]
  active: boolean
  created_by: string
  created_at: string
  superseded_at: string | null
}

export interface DirectiveHistoryResponse {
  directive: string
  versions: DirectiveVersion[]
}

// ─── API functions ────────────────────────────────────────────────────────────

export async function fetchDirectives(alpha?: number): Promise<Directive[]> {
  const params = alpha !== undefined ? { alpha } : {}
  const res = await api.get<{ directives: Directive[] }>('/directives/', { params })
  return res.data.directives ?? []
}

export async function fetchDirective(alpha: number, beta: number): Promise<Directive> {
  const res = await api.get<Directive>(`/directives/${alpha}/${beta}`)
  return res.data
}

export interface CreateDirectiveInput {
  alpha: number
  label: string
  content: string
  types?: string[]
  created_by?: string
}

export async function createDirective(input: CreateDirectiveInput): Promise<Directive> {
  const res = await api.post<Directive>('/directives/', {
    alpha: input.alpha,
    label: input.label,
    content: input.content,
    types: input.types ?? ['core'],
    created_by: input.created_by ?? 'operator',
  })
  return res.data
}

export interface ReviseDirectiveInput {
  content: string
  label?: string
  types?: string[]
  created_by?: string
}

export async function reviseDirective(
  alpha: number,
  beta: number,
  input: ReviseDirectiveInput
): Promise<Directive> {
  const res = await api.put<Directive>(`/directives/${alpha}/${beta}`, {
    content: input.content,
    label: input.label,
    types: input.types,
    created_by: input.created_by ?? 'operator',
  })
  return res.data
}

export async function reorderDirective(
  alpha: number,
  beta: number,
  newAlpha: number,
  newBeta: number
): Promise<Directive> {
  const res = await api.put<Directive>(`/directives/${alpha}/${beta}/reorder`, {
    new_alpha: newAlpha,
    new_beta: newBeta,
  })
  return res.data
}

export async function deleteDirective(alpha: number, beta: number): Promise<void> {
  await api.delete(`/directives/${alpha}/${beta}`)
}

export async function fetchDirectiveHistory(
  alpha: number,
  beta: number
): Promise<DirectiveHistoryResponse> {
  const res = await api.get<DirectiveHistoryResponse>(`/directives/${alpha}/${beta}/history`)
  return res.data
}

export default api