import api from './http'



type JobStatus = 'queued' | 'starting' | 'running' | 'succeeded' | 'failed' | 'cancel_requested' | 'cancelled' | 'uncertain' | 'cancel_requested' | 'cancelled' | 'uncertain'
type Job = { job_id: string; status: JobStatus; result?: { content?: string | Record<string, unknown> }; error?: { code?: string; message?: string } }

export async function cancelJob(jobId: string): Promise<Job> {
  const response = await api.post<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`)
  return response.data
}
