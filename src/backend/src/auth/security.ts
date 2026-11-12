import { AppError } from '../middleware/errorHandler'

export async function securityRequest<T>(path: string, body: unknown): Promise<T> {
  let response: globalThis.Response
  try {
    response = await fetch(`${(process.env.PL_SECURITY_URL || 'http://pl-security:8000').replace(/\/$/, '')}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    })
  } catch {
    throw new AppError('Security service unavailable', 503, 'AUTH_CONTEXT_FAILED')
  }
  if (!response.ok) throw new AppError('Security request denied', [401, 403].includes(response.status) ? response.status : 503, 'AUTH_CONTEXT_FAILED')
  try {
    const result: unknown = await response.json()
    if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error('Invalid security response')
    return result as T
  } catch { throw new AppError('Invalid security response', 503, 'AUTH_CONTEXT_FAILED') }
}
