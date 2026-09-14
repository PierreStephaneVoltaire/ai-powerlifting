import { operationScope } from './operationScope'
import { readFileSync } from 'fs'
import { resolve } from 'path'

type Operation = { name: string; domain: string; legacy?: string[] }
const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN || ''
const IF_API_URL = process.env.IF_API_URL || 'http://if-agent-api.if-portals.svc.cluster.local:8000'
const SERVICE_BASE_URL = process.env.POWERLIFTING_SERVICE_BASE_URL
const operations = new Map<string, Operation>()
for (const domain of ['program', 'sessions', 'competition', 'federation', 'glossary', 'goals', 'budget', 'calculations', 'performance', 'weight-log', 'templates', 'imports', 'profile', 'lift-profiles', 'analytics', 'videos']) {
  const records = JSON.parse(readFileSync(resolve(__dirname, '../../../services/operations', `${domain}.json`), 'utf8')) as Operation[]
  for (const operation of records) {
    operations.set(operation.name, operation)
  }
}

function serviceUrl(domain: string): string {
  return SERVICE_BASE_URL ? `${SERVICE_BASE_URL.replace(/\/$/, '')}/${domain}` : `http://pl-${domain}.if-portals.svc.cluster.local:8000`
}

export async function pollJob(jobId: string, operation: string, person: string): Promise<any> {
  for (let attempt = 0; attempt < 1800; attempt += 1) {
    const response = await fetch(`${IF_API_URL}/v1/jobs/${encodeURIComponent(jobId)}/result`, { headers: { 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Person-Pk': person } })
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

export async function invokeLambda(functionName: string, args: Record<string, unknown>, waitForResult = true): Promise<any> {
  if (!INTERNAL_API_TOKEN) throw new Error('INTERNAL_API_TOKEN is not set')
  const requestedName = typeof args.function === 'string' ? args.function : functionName
  const operation = operations.get(requestedName)
  if (!operation) throw new Error(`Unknown powerlifting operation: ${functionName}`)
  const payload = { ...args }
  delete payload.function
  const scope = operationScope.getStore()
  const pk = String(scope?.athlete || payload.pk || payload.user_pk || payload.mapped_pk || payload.athlete_mapped_pk || payload.grantee_mapped_pk || payload.username || payload.discord_username || '')
  const person = String(scope?.person || payload.actor_mapped_pk || payload.person_pk || payload.created_by || payload.revoked_by || pk)
  const response = await fetch(`${serviceUrl(operation.domain)}/operations/${encodeURIComponent(operation.name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Internal-Token': INTERNAL_API_TOKEN, ...(pk ? { 'X-Athlete-Pk': pk } : {}), ...(person ? { 'X-Person-Pk': person } : {}), ...(scope?.ifJobId ? { 'X-IF-Turn-Id': scope.ifJobId, 'X-PL-Nested-Operation': 'true' } : {}) },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Powerlifting service error ${response.status} for ${functionName}: ${await response.text()}`)
  const result: any = await response.json()
  return result?.job_id && waitForResult ? pollJob(result.job_id, requestedName, person) : result
}

export async function readGeneration(generationId: string, athlete: string): Promise<any> {
  const response = await fetch(`${serviceUrl('analytics')}/generations/${encodeURIComponent(generationId)}`, { headers: { 'X-Internal-Token': INTERNAL_API_TOKEN, 'X-Athlete-Pk': athlete } })
  if (!response.ok) throw new Error(`Generation status failed ${response.status}: ${await response.text()}`)
  return response.json()
}
