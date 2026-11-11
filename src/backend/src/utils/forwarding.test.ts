import assert from 'node:assert/strict'
import test from 'node:test'
import { operationScope } from './operationScope'

process.env.POWERLIFTING_SERVICE_BASE_URL = 'http://service'
process.env.IF_API_URL = 'http://if'

let callOperation: typeof import('./operations').callOperation
let invokeSpecialistJson: typeof import('./agent').invokeSpecialistJson
async function load() {
  callOperation = (await import('./operations')).callOperation
  invokeSpecialistJson = (await import('./agent')).invokeSpecialistJson
}

test('denied current operation permissions prevent gateway forwarding', async () => {
  await load()
  const original = globalThis.fetch
  const calls: Request[] = []
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return Response.json({}, { status: 403 })
  }) as typeof fetch
  try {
    await assert.rejects(operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => callOperation('session_patch', { session_id: 'session-1' })), /Security request denied/)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, 'http://pl-security:8000/v1/principals')
    assert.deepEqual(await calls[0].json(), { operation: 'session_patch', athlete: 'athlete-1', destination: 'pl-sessions' })
  } finally { globalThis.fetch = original }
})

test('dispatches operation calls through the registry with scoped body', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return Response.json(calls.length === 1 ? { principal: 'operation-token' } : { ok: true })
  }) as typeof fetch
  try {
    await operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => callOperation('program_get', { pk: 'athlete-1' }))
    assert.equal(calls[0].url, 'http://pl-security:8000/v1/principals')
    assert.deepEqual(await calls[0].json(), { operation: 'program_get', athlete: 'athlete-1', destination: 'pl-program' })
    assert.equal(calls[1].url, 'http://service/program/operations/program_get')
    assert.equal(calls[1].headers.get('X-Athlete-Pk'), 'athlete-1')
    assert.ok(calls[1].headers.get('X-PL-Principal'))
    assert.deepEqual(await calls[1].json(), { pk: 'athlete-1' })
  } finally { globalThis.fetch = original }
})

test('forwards composite analytics operations through the typed analytics service', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return Response.json(calls.length === 1 ? { principal: 'operation-token' } : { ok: true })
  }) as typeof fetch
  try {
    await operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => callOperation('analytics.manifest', { pk: 'athlete-1', window: 'current' }))
    assert.equal(calls[1].url, 'http://service/analytics/operations/analytics.manifest')
    assert.deepEqual(await calls[1].json(), { pk: 'athlete-1', window: 'current' })
  } finally { globalThis.fetch = original }
})

test('does not let a composite operation choose a different authenticated athlete', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return Response.json(calls.length === 1 ? { principal: 'operation-token' } : { ok: true })
  }) as typeof fetch
  try {
    await operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => callOperation('analytics.manifest', { pk: 'athlete-2' }))
    assert.equal(calls[1].headers.get('X-Athlete-Pk'), 'athlete-1')
  } finally { globalThis.fetch = original }
})

test('forwards active IF job scope to domain operations', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return Response.json(calls.length === 1 ? { principal: 'operation-token' } : { ok: true })
  }) as typeof fetch
  try {
    await operationScope.run({ athlete: 'athlete-1', person: 'person-1', ifJobId: 'job-1' }, () => callOperation('analytics.manifest', {}))
    assert.equal(calls[1].headers.get('X-IF-Turn-Id'), 'job-1')
    assert.equal(calls[1].headers.get('X-PL-Nested-Operation'), 'true')
  } finally { globalThis.fetch = original }
})

test('uses the authenticated scope instead of a forwarded athlete payload', async () => {
  await load()
  const calls: Request[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input, init) => {
    calls.push(new Request(input, init))
    return Response.json(calls.length === 1 ? { principal: 'operation-token' } : { ok: true })
  }) as typeof fetch
  try {
    await operationScope.run(
      { athlete: 'athlete-1', person: 'person-1' },
      () => callOperation('program_get', { pk: 'athlete-2' }),
    )
    assert.equal(calls[1].headers.get('X-Athlete-Pk'), 'athlete-1')
    assert.equal(calls[1].headers.get('X-Person-Pk'), 'person-1')
  } finally { globalThis.fetch = original }
})

test('fails terminal jobs and submits inference once', async () => {
  await load()
  const original = globalThis.fetch
  let submissions = 0
  globalThis.fetch = (async (input) => {
    const url = String(input)
    if (url.endsWith('/v1/principals')) return Response.json({ principal: 'operation-token' })
    if (url.startsWith('http://service/')) return new Response(JSON.stringify({ job_id: 'failed-job', status: 'queued' }), { status: 200 })
    if (url.endsWith('/turns')) { submissions += 1; return new Response(JSON.stringify({ job_id: `job-${submissions}`, status: 'queued' }), { status: 202 }) }
    return new Response(JSON.stringify({ status: 'failed', error: { message: 'cancelled' } }), { status: 200 })
  }) as typeof fetch
  try {
    await assert.rejects(operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => callOperation('correlation_analysis', { pk: 'athlete-1' })), /failed/)
    await assert.rejects(operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => invokeSpecialistJson('powerlifting_coach', 'return a result', 'conversation-1')), /failed/)
    assert.equal(submissions, 1)
  } finally { globalThis.fetch = original }
})
