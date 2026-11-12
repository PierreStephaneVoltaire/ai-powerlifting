import { serviceHeaders, type ServiceScope } from './serviceHeaders'
import { AppError } from '../middleware/errorHandler'
import { operationScope } from './operationScope'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { coachUrl } from './coachUrl'

type Operation = { name: string; domain: string }
const SERVICE_BASE_URL = process.env.POWERLIFTING_SERVICE_BASE_URL
const operations = new Map<string, Operation>()
for (const domain of ['program', 'sessions', 'competition', 'federation', 'glossary', 'goals', 'budget', 'calculations', 'performance', 'weight-log', 'templates', 'imports', 'profile', 'lift-profiles', 'analytics', 'videos', 'export', 'rankings']) {
  const records = JSON.parse(readFileSync(resolve(__dirname, '../../../services/operations', `${domain}.json`), 'utf8')) as Operation[]
  for (const operation of records) {
    operations.set(operation.name, operation)
  }
}

function serviceUrl(domain: string): string {
  return SERVICE_BASE_URL ? `${SERVICE_BASE_URL.replace(/\/$/, '')}/${domain}` : `http://pl-${domain}:8000`
}

export async function pollJob(jobId: string, operation: string, person: string, athlete?: string): Promise<any> {
  for (let attempt = 0; attempt < 1800; attempt += 1) {
    const scope = operationScope.getStore()
    const response = await fetch(`${coachUrl()}/v1/jobs/${encodeURIComponent(jobId)}/result`, { headers: serviceHeaders({ athlete: athlete || scope?.athlete || '', person }) })
    if (response.status === 202) { await new Promise((done) => setTimeout(done, 500)); continue }
    if (!response.ok) throw new Error(`Job error ${response.status} for ${operation}: ${await response.text()}`)
    const body: any = await response.json()
    if (['failed', 'cancelled', 'uncertain'].includes(body?.status)) throw new Error(`Job ${body.status} for ${operation}: ${body.error?.message || body.error || 'unknown error'}`)
    const content = body?.result?.content ?? body?.content ?? body?.result ?? body
    if (typeof content === 'string') {
      try { return JSON.parse(content) } catch { return content }
    }
    return content
  }
  throw new Error(`Job still pending for ${operation}`)
}

export async function callOperationAs(name: string, payload: Record<string, unknown>, scope: ServiceScope & { ifJobId?: string }): Promise<any> {
  const operation = operations.get(name)
  if (!operation) throw new Error(`Unknown powerlifting operation: ${name}`)
  const response = await fetch(`${serviceUrl(operation.domain)}/operations/${encodeURIComponent(operation.name)}`, {
    method: 'POST',
    headers: { ...serviceHeaders(scope), ...(scope.ifJobId ? { 'X-IF-Turn-Id': scope.ifJobId, 'X-PL-Nested-Operation': 'true' } : {}) },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: { code?: string; message?: string; current_revision?: number; current_record?: unknown } }
    const detail = typeof body.detail === 'object' ? body.detail : {}
    const error = new AppError(detail.message || `Operation ${name} failed`, response.status, detail.code)
    Object.assign(error, { current_revision: detail.current_revision, current_record: detail.current_record })
    throw error
  }
  return response.json()
}

export async function callOperation(name: string, payload: Record<string, unknown>, waitForResult = true): Promise<any> {
  const scope = operationScope.getStore()
  if (!scope) throw new AppError('Authenticated operation context required', 401, 'AUTH_REQUIRED')
  const result: any = await callOperationAs(name, payload, scope)
  return result?.job_id && waitForResult ? pollJob(result.job_id, name, scope.person, scope.athlete) : result
}

export async function readGeneration(generationId: string, athlete: string): Promise<any> {
  const scope = operationScope.getStore()
  if (!scope || scope.athlete !== athlete) throw new AppError('Authenticated scope required', 401)
  const response = await fetch(`${serviceUrl('analytics')}/generations/${encodeURIComponent(generationId)}`, { headers: serviceHeaders(scope) })
  if (!response.ok) throw new Error(`Generation status failed ${response.status}: ${await response.text()}`)
  return response.json()
}
