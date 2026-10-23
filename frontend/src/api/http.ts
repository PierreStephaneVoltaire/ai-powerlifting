import axios, { CanceledError } from 'axios'
import { requestAthlete, requestPartition } from './context'
import { isQueueableMutation, markMutationBlocked, prepareMutation, removeMutation } from './drafts'

declare module 'axios' {
  interface AxiosRequestConfig {
    powerliftingReplay?: boolean
    powerliftingPartition?: string
  }
  interface InternalAxiosRequestConfig {
    powerliftingPartition?: string
    powerliftingMutationId?: string
    powerliftingReplay?: boolean
  }
}

export class OfflineQueuedError extends Error {
  readonly mutationId: string
  constructor(mutationId: string) { super('Saved locally; it will synchronize after reauthorization'); this.name = 'OfflineQueuedError'; this.mutationId = mutationId }
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use(async config => {
  const partition = config.powerliftingPartition || requestPartition()
  if (partition !== requestPartition()) throw new CanceledError('The Person or Athlete context changed')
  config.powerliftingPartition = partition
  config.headers.set('X-Selected-Athlete-Pk', requestAthlete())
  if (config.powerliftingReplay) return config
  const method = (config.method || 'get').toUpperCase()
  const url = config.url || ''
  if (!isQueueableMutation(method, url, config.data)) return config
  const body = config.data as Record<string, unknown>
  const mutation = await prepareMutation({ method, url, data: body, expected_revision: Number(body.expected_revision), idempotency_key: String(body.idempotency_key) }, partition)
  if (partition !== requestPartition()) throw new CanceledError('The change remains saved for the original Person and Athlete')
  config.powerliftingMutationId = mutation.id
  config.data = { ...body, idempotency_key: mutation.idempotency_key }
  if (mutation.status === 'blocked') throw new CanceledError('This change needs access reauthorization before retrying')
  if (!navigator.onLine) throw new OfflineQueuedError(mutation.id)
  return config
})

api.interceptors.response.use(async response => {
  const mutationId = response.config.powerliftingMutationId
  if (mutationId) await removeMutation(mutationId).catch(() => {})
  if (response.config.powerliftingPartition !== requestPartition()) throw new CanceledError('The Person or Athlete context changed')
  return response
}, async error => {
  const mutationId = error.config?.powerliftingMutationId
  if (mutationId && error.response?.status === 409) await removeMutation(mutationId).catch(() => {})
  if (mutationId && [401, 403].includes(error.response?.status)) void markMutationBlocked(mutationId).catch(() => {})
  if (error.config?.powerliftingPartition === requestPartition() && [401, 403].includes(error.response?.status)) window.dispatchEvent(new Event('powerlifting-access-changed'))
  return Promise.reject(error)
})

export default api
