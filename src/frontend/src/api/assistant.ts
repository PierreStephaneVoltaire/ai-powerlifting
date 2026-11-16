import api from './http'

export type AssistantScope = 'session-design' | 'template-phase' | 'goals' | 'supplements' | 'biometrics' | 'research'

export interface AssistantContext {
  session_date?: string
  session_index?: number
  exercise_index?: number
  template_sk?: string
}

export type ProposalState = 'pending' | 'approved' | 'rejected' | 'applied' | 'failed' | 'cancelled' | 'expired' | string

export interface AssistantProposal {
  id: string
  operation: string
  summary: string
  target_id: string
  destructive: boolean
  state: ProposalState
  diff: unknown
}

export interface AssistantActivity {
  at: string
  kind: string
  model: string
  outcome: string
  label: string
}

export interface AssistantProgress {
  stage: string
  text: string
  updated_at: string
}

export interface AssistantJob {
  id: string
  job_id: string
  status: 'queued' | 'starting' | 'running' | 'succeeded' | 'failed' | 'cancel_requested' | 'cancelled' | 'uncertain'
  error?: string
  result?: { content?: string } | null
  proposals: AssistantProposal[]
  activity?: AssistantActivity[]
  progress?: AssistantProgress | null
}

export interface AssistantHistoryTurn {
  id: string
  status: string
  created_at: string
  summary: string
  error?: string
  content?: { request: string; reply: string }
}

export interface AssistantHistory {
  conversation_id: string
  turns: AssistantHistoryTurn[]
  next_before?: string
}

const TERMINAL = ['succeeded', 'failed', 'cancelled', 'uncertain']

export function isTerminal(status: string): boolean {
  return TERMINAL.includes(status)
}

function scopePath(scope: AssistantScope): string {
  return `/assistant/conversations/${encodeURIComponent(scope)}`
}

export async function submitTurn(scope: AssistantScope, message: string, context: AssistantContext): Promise<AssistantJob> {
  const response = await api.post<AssistantJob>(`${scopePath(scope)}/turns`, {
    messages: [{ role: 'user', content: message }],
    surface: scope,
    context,
  })
  return response.data
}

export async function fetchJob(jobId: string): Promise<AssistantJob> {
  const response = await api.get<AssistantJob>(`/assistant/jobs/${encodeURIComponent(jobId)}`)
  return response.data
}

export async function cancelJob(jobId: string): Promise<AssistantJob> {
  const response = await api.post<AssistantJob>(`/assistant/jobs/${encodeURIComponent(jobId)}/cancel`, {})
  return response.data
}

export async function pollTurn(jobId: string, onUpdate: (job: AssistantJob) => void, isCancelled: () => boolean): Promise<AssistantJob> {
  for (let attempt = 0; attempt < 900; attempt += 1) {
    const job = await fetchJob(jobId)
    if (isCancelled()) return job
    onUpdate(job)
    if (isTerminal(job.status)) return job
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error('Turn is still running. Reopen the assistant to check it.')
}

export async function fetchHistory(scope: AssistantScope, expand?: string): Promise<AssistantHistory> {
  const response = await api.get<AssistantHistory>(`${scopePath(scope)}/history`, {
    params: { limit: 20, ...(expand ? { expand } : {}) },
  })
  return response.data
}

export async function approveProposal(id: string, target?: string): Promise<AssistantProposal> {
  const response = await api.post<AssistantProposal>(`/assistant/proposals/${encodeURIComponent(id)}/approve`, target ? { target } : {})
  return response.data
}

export async function rejectProposal(id: string): Promise<AssistantProposal> {
  const response = await api.post<AssistantProposal>(`/assistant/proposals/${encodeURIComponent(id)}/reject`, {})
  return response.data
}
