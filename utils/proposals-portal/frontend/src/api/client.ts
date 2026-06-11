import axios from 'axios'
import type {
  CreateProposalInput,
  ProposalFilters,
  ProposalsListResponse,
  ProposalResponse,
  DirectivesListResponse,
  DirectiveResponse,
} from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ─── Proposals API ───────────────────────────────────────────────────────────

export async function fetchProposals(filters?: ProposalFilters): Promise<ProposalsListResponse> {
  const params: Record<string, string> = {}
  if (filters?.status) params.status = filters.status
  if (filters?.type) params.type = filters.type
  if (filters?.author) params.author = filters.author
  if (filters?.q) params.q = filters.q

  const res = await api.get<ProposalsListResponse>('/proposals', { params })
  return res.data
}

export async function fetchProposal(sk: string): Promise<ProposalResponse> {
  const res = await api.get<ProposalResponse>(`/proposals/${encodeURIComponent(sk)}`)
  return res.data
}

export async function createProposal(input: CreateProposalInput): Promise<ProposalResponse> {
  const res = await api.post<ProposalResponse>('/proposals', input)
  return res.data
}

export async function approveProposal(sk: string): Promise<ProposalResponse> {
  const res = await api.patch<ProposalResponse>(`/proposals/${encodeURIComponent(sk)}/approve`)
  return res.data
}

export async function rejectProposal(sk: string, reason?: string): Promise<ProposalResponse> {
  const res = await api.patch<ProposalResponse>(`/proposals/${encodeURIComponent(sk)}/reject`, { reason })
  return res.data
}

export async function deleteProposal(sk: string): Promise<void> {
  await api.delete(`/proposals/${encodeURIComponent(sk)}`)
}

export async function generatePlan(sk: string): Promise<{ success: boolean }> {
  const res = await api.post<{ success: boolean }>(`/proposals/${encodeURIComponent(sk)}/generate-plan`)
  return res.data
}

export async function fetchPlan(sk: string): Promise<{ plan: string | null }> {
  const res = await api.get<{ plan: string | null }>(`/proposals/${encodeURIComponent(sk)}/plan`)
  return res.data
}

// ─── Directives API ──────────────────────────────────────────────────────────

export async function fetchDirectives(): Promise<DirectivesListResponse> {
  const res = await api.get<DirectivesListResponse>('/directives')
  return res.data
}

export async function fetchDirective(sk: string): Promise<DirectiveResponse> {
  const res = await api.get<DirectiveResponse>(`/directives/${encodeURIComponent(sk)}`)
  return res.data
}

export default api
