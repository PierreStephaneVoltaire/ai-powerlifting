import assert from 'node:assert/strict'
import test from 'node:test'
import express from 'express'
import type { AddressInfo } from 'node:net'
import { once } from 'node:events'
import { configureMeshAuthentication } from '../middleware/meshAuth'
import { requireUserOptional, resolvePk } from '../middleware/auth'
import { errorHandler } from '../middleware/errorHandler'
import { callOperation } from '../utils/operations'
import { operationScope } from '../utils/operationScope'

test('mesh gateway derives identity through the broker and rejects forged identity headers and cross-origin writes', async () => {
  process.env.AUTHENTIK_ISSUER_URL = 'https://auth.example/application/o/nolift/'
  process.env.AUTHENTIK_CLIENT_ID = 'nolift'
  process.env.FRONTEND_URL = 'https://app.example'
  const originalFetch = globalThis.fetch
  const calls: Request[] = []
  globalThis.fetch = (async (input, init) => {
    const request = new Request(input, init)
    calls.push(request)
    const body = await request.json() as { id_token: string }
    if (body.id_token !== 'verified-token') return Response.json({}, { status: 401 })
    return Response.json({
      identity: { issuer: process.env.AUTHENTIK_ISSUER_URL, provider: 'authentik', sub: 'verified-subject', username: 'person', display_name: 'Person', avatar: null, groups: [], roles: [] },
      settings: { pk: 'person', mapped_pk: 'own-athlete', username: 'person', roles: ['athlete'] },
    })
  }) as typeof fetch
  const app = express()
  configureMeshAuthentication(app)
  app.use(requireUserOptional, resolvePk)
  app.all('/api/profiles', (req, res) => res.json({ person: req.actor_mapped_pk, athlete: req.mapped_pk, identity: req.user?.identity.sub, scope: operationScope.getStore()?.identityToken }))
  app.use(errorHandler)
  const server = app.listen(0, '127.0.0.1')
  try {
    await once(server, 'listening')
    const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/api/profiles`
    const anonymous = await originalFetch(url, { headers: { 'X-Person-Pk': 'victim', 'X-PL-Access-Context': '{"person":"victim"}' } })
    assert.equal(anonymous.status, 200)
    assert.equal((await anonymous.json()).person, '')
    assert.equal(calls.length, 0)
    const signedIn = await originalFetch(url, { headers: { Authorization: 'Bearer verified-token', 'X-Selected-Athlete-Pk': 'selected-athlete', 'X-Person-Pk': 'victim' } })
    assert.deepEqual(await signedIn.json(), { person: 'person', athlete: 'selected-athlete', identity: 'verified-subject', scope: 'verified-token' })
    assert.equal(calls[0].url, 'http://pl-security:8000/v1/identity')
    assert.equal((await originalFetch(url, { headers: { Authorization: 'Bearer forged' } })).status, 401)
    assert.equal((await originalFetch(url, { method: 'POST', headers: { Origin: 'https://evil.example' } })).status, 403)
    assert.equal((await originalFetch(url, { method: 'POST' })).status, 403)
    assert.equal((await originalFetch(url, { method: 'POST', headers: { Origin: 'https://app.example', Authorization: 'Bearer verified-token' } })).status, 200)
  } finally {
    server.closeAllConnections()
    await new Promise<void>(resolve => server.close(() => resolve()))
    globalThis.fetch = originalFetch
  }
})

test('mesh operation forwarding mints a scoped principal without sharing a signing key or repeating the policy request', async () => {
  const originalFetch = globalThis.fetch
  const calls: Request[] = []
  globalThis.fetch = (async (input, init) => {
    const request = new Request(input, init)
    calls.push(request)
    if (request.url.endsWith('/v1/principals')) return Response.json({ principal: 'operation-token' })
    return Response.json({ ok: true })
  }) as typeof fetch
  try {
    await operationScope.run({ person: 'person', athlete: 'selected-athlete', identityToken: 'oidc-token' }, () => callOperation('program_get', {}))
    assert.equal(calls.length, 2)
    assert.deepEqual(await calls[0].json(), { identity_token: 'oidc-token', athlete: 'selected-athlete', operation: 'program_get', destination: 'pl-program' })
    assert.equal(calls[1].url, 'http://pl-program:8000/operations/program_get')
    assert.equal(calls[1].headers.get('X-PL-Principal'), 'operation-token')
    assert.equal(calls[1].headers.has('X-Internal-Token'), false)
    globalThis.fetch = (async () => Response.json({}, { status: 503 })) as typeof fetch
    await assert.rejects(operationScope.run({ person: 'person', athlete: 'selected-athlete', identityToken: 'oidc-token' }, () => callOperation('program_get', {})), /Security request denied/)
  } finally {
    globalThis.fetch = originalFetch
  }
})
