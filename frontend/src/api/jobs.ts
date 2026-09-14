import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export type JobStatus = 'queued' | 'starting' | 'running' | 'succeeded' | 'failed' | 'cancel_requested' | 'cancelled' | 'uncertain' | 'cancel_requested' | 'cancelled' | 'uncertain'
export type Job = { job_id: string; status: JobStatus; result?: { content?: string | Record<string, unknown> }; error?: { code?: string; message?: string } }

export async function submitJob(input: { conversation_id: string; kind: string; payload: unknown; idempotency_key: string }): Promise<Job> {
  const response = await api.post<Job>('/jobs', input)
  return response.data
}

export async function getJobResult(jobId: string): Promise<Job> {
  const response = await api.get<Job>(`/jobs/${encodeURIComponent(jobId)}/result`, { validateStatus: (status) => status === 200 || status === 202 })
  return response.data
}

export async function cancelJob(jobId: string): Promise<Job> {
  const response = await api.post<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`)
  return response.data
}
