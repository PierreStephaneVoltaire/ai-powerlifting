// Shared types for Proposals Portal

export type ProposalType =
  | 'new_directive'
  | 'rewrite_directive'
  | 'deprecate_directive'
  | 'new_tool'
  | 'system_observation'

export type ProposalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'implemented'

export type ProposalAuthor = 'agent' | 'user'

export interface Proposal {
  pk: string
  sk: string
  type: ProposalType
  status: ProposalStatus
  author: ProposalAuthor
  title: string
  rationale: string
  content: string
  target_id: string | null
  implementation_plan: string | null
  created_at: string
  resolved_at: string | null
  resolved_by: string | null
  rejection_reason: string | null
}

export interface CreateProposalInput {
  type: ProposalType
  title: string
  rationale: string
  content: string
  target_id?: string
}

export interface ProposalFilters {
  status?: ProposalStatus
  type?: ProposalType
  author?: ProposalAuthor
  q?: string
}

export interface Directive {
  pk: string
  sk: string
  alpha: number
  beta: number
  label: string
  content: string
  types: string[]
  version: number
  active: boolean
  created_by: string
  created_at: string
  superseded_at: string | null
}

// API Response types
export interface ProposalsListResponse {
  proposals: Proposal[]
  total: number
}

export interface ProposalResponse {
  proposal: Proposal
}

export interface DirectivesListResponse {
  directives: Directive[]
  total: number
}

export interface DirectiveResponse {
  directive: Directive
}

export interface GeneratePlanResponse {
  success: boolean
  plan: string | null
  error?: string
}

export interface RejectProposalInput {
  reason: string
}

// Type metadata — labels and Mantine colors used in badges
export const TYPE_LABELS: Record<ProposalType, string> = {
  new_directive: 'New Directive',
  rewrite_directive: 'Rewrite Directive',
  deprecate_directive: 'Deprecate Directive',
  new_tool: 'New Tool',
  system_observation: 'System Observation',
}

// Mantine color names keyed by ProposalType
export const TYPE_BADGE_COLORS: Record<ProposalType, string> = {
  new_directive: 'blue',
  rewrite_directive: 'yellow',
  deprecate_directive: 'red',
  new_tool: 'green',
  system_observation: 'violet',
}

export const STATUS_LABELS: Record<ProposalStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  implemented: 'Implemented',
}

// Mantine color names keyed by ProposalStatus
export const STATUS_BADGE_COLORS: Record<ProposalStatus, string> = {
  pending: 'yellow',
  approved: 'green',
  rejected: 'red',
  implemented: 'blue',
}
