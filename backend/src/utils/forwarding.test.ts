import assert from 'node:assert/strict'
import test from 'node:test'
import { operationScope } from './operationScope'

process.env.INTERNAL_API_TOKEN = 'secret'
process.env.POWERLIFTING_SERVICE_BASE_URL = 'http://service'
process.env.IF_API_URL = 'http://if'

let invokeLambda: typeof import('./lambda').invokeLambda
let invokeSpecialistJson: typeof import('./agent').invokeSpecialistJson
async function load() {
  invokeLambda = (await import('./lambda')).invokeLambda
  invokeSpecialistJson = (await import('./agent')).invokeSpecialistJson
}

test('dispatches legacy pod calls through the registry with scoped body', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }) as typeof fetch
  try {
    await invokeLambda('pod_training_program', { function: 'health_get_program', pk: 'athlete-1' })
    assert.equal(calls[0].url, 'http://service/program/operations/health_get_program')
    assert.equal(calls[0].headers.get('X-Athlete-Pk'), 'athlete-1')
    assert.deepEqual(await calls[0].json(), { pk: 'athlete-1' })
  } finally { globalThis.fetch = original }
})

test('forwards composite analytics operations through the typed analytics service', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }) as typeof fetch
  try {
    await invokeLambda('analytics.manifest', { pk: 'athlete-1', window: 'current' })
    assert.equal(calls[0].url, 'http://service/analytics/operations/analytics.manifest')
    assert.deepEqual(await calls[0].json(), { pk: 'athlete-1', window: 'current' })
  } finally { globalThis.fetch = original }
})

test('does not let a composite operation choose a different authenticated athlete', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }) as typeof fetch
  try {
    await operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => invokeLambda('analytics.manifest', { pk: 'athlete-2' }))
    assert.equal(calls[0].headers.get('X-Athlete-Pk'), 'athlete-1')
  } finally { globalThis.fetch = original }
})

test('forwards active IF job scope to domain operations', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }) as typeof fetch
  try {
    await operationScope.run({ athlete: 'athlete-1', person: 'person-1', ifJobId: 'job-1' }, () => invokeLambda('analytics.manifest', {}))
    assert.equal(calls[0].headers.get('X-IF-Turn-Id'), 'job-1')
    assert.equal(calls[0].headers.get('X-PL-Nested-Operation'), 'true')
  } finally { globalThis.fetch = original }
})

test('uses the authenticated scope instead of a forwarded athlete payload', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }) as typeof fetch
  try {
    await operationScope.run(
      { athlete: 'athlete-1', person: 'person-1' },
      () => invokeLambda('pod_training_program', { function: 'health_get_program', pk: 'athlete-2' }),
    )
    assert.equal(calls[0].headers.get('X-Athlete-Pk'), 'athlete-1')
    assert.equal(calls[0].headers.get('X-Person-Pk'), 'person-1')
  } finally { globalThis.fetch = original }
})

test('fails terminal jobs and submits inference once', async () => {
  await load()
  const original = globalThis.fetch
  let submissions = 0
  globalThis.fetch = (async (input) => {
    const url = String(input)
    if (url.startsWith('http://service/')) return new Response(JSON.stringify({ job_id: 'failed-job', status: 'queued' }), { status: 200 })
    if (url.endsWith('/turns')) { submissions += 1; return new Response(JSON.stringify({ job_id: `job-${submissions}`, status: 'queued' }), { status: 202 }) }
    return new Response(JSON.stringify({ status: 'failed', error: { message: 'cancelled' } }), { status: 200 })
  }) as typeof fetch
  try {
    await assert.rejects(invokeLambda('correlation_analysis', { pk: 'athlete-1' }), /failed/)
    await assert.rejects(operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => invokeSpecialistJson('powerlifting_coach', 'return a result', 'conversation-1')), /failed/)
    assert.equal(submissions, 1)
  } finally { globalThis.fetch = original }
})
