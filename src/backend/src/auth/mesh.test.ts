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

function token(claims: Record<string, unknown>): string {
  return ['header', Buffer.from(JSON.stringify(claims)).toString('base64url'), 'signature'].join('.')
}

test('gateway reads the proxy identity, resolves the Person and rejects forged identity headers and cross-origin writes', async () => {
  process.env.AUTHENTIK_ISSUER_URL = 'https://auth.example/application/o/nolift/'
  process.env.AUTHENTIK_CLIENT_ID = 'nolift'
  process.env.FRONTEND_URL = 'https://app.example'
  const verified = token({ iss: process.env.AUTHENTIK_ISSUER_URL, aud: 'nolift', sub: 'verified-subject', preferred_username: 'Person', discord_subjects: ['123', 'bad'] })
  const originalFetch = globalThis.fetch
  const calls: Request[] = []
  globalThis.fetch = (async (input, init) => {
    const request = new Request(input, init)
    calls.push(request)
    return Response.json({ settings: { pk: 'person', mapped_pk: 'own-athlete', username: 'person', roles: ['athlete'] }, created: false })
  }) as typeof fetch
  const app = express()
  configureMeshAuthentication(app)
  app.use(requireUserOptional, resolvePk)
  app.all('/api/profiles', (req, res) => res.json({ person: req.actor_mapped_pk, athlete: req.mapped_pk, identity: req.user?.identity.sub, scope: operationScope.getStore()?.person }))
  app.use(errorHandler)
  const server = app.listen(0, '127.0.0.1')
  try {
    await once(server, 'listening')
    const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/api/profiles`
    const anonymous = await originalFetch(url, { headers: { 'X-Person-Pk': 'victim' } })
    assert.equal(anonymous.status, 200)
    assert.equal((await anonymous.json()).person, '')
    assert.equal(calls.length, 0)
    const signedIn = await originalFetch(url, { headers: { Authorization: `Bearer ${verified}`, 'X-Selected-Athlete-Pk': 'selected-athlete', 'X-Person-Pk': 'victim' } })
    assert.deepEqual(await signedIn.json(), { person: 'person', athlete: 'selected-athlete', identity: 'verified-subject', scope: 'person' })
    assert.equal(calls[0].url, 'http://pl-profile:8000/operations/identity_resolve')
    assert.equal(calls[0].headers.get('X-Person-Pk'), '')
    assert.deepEqual(await calls[0].json(), { issuer: process.env.AUTHENTIK_ISSUER_URL, provider: 'authentik', sub: 'verified-subject', display_name: 'Person', avatar_url: null, discord_subjects: ['123'] })
    assert.equal((await originalFetch(url, { headers: { Authorization: `Bearer ${token({ iss: 'https://evil.example/', aud: 'nolift', sub: 'x' })}` } })).status, 401)
    assert.equal((await originalFetch(url, { headers: { Authorization: 'Bearer forged' } })).status, 401)
    assert.equal((await originalFetch(url, { method: 'POST', headers: { Origin: 'https://evil.example' } })).status, 403)
    assert.equal((await originalFetch(url, { method: 'POST' })).status, 403)
    assert.equal((await originalFetch(url, { method: 'POST', headers: { Origin: 'https://app.example', Authorization: `Bearer ${verified}` } })).status, 200)
  } finally {
    server.closeAllConnections()
    await new Promise<void>(resolve => server.close(() => resolve()))
    globalThis.fetch = originalFetch
  }
})

test('operation forwarding states the acting Person and Athlete to the domain service', async () => {
  const originalFetch = globalThis.fetch
  const calls: Request[] = []
  globalThis.fetch = (async (input, init) => {
    const request = new Request(input, init)
    calls.push(request)
    return Response.json({ ok: true })
  }) as typeof fetch
  try {
    await operationScope.run({ person: 'person', athlete: 'selected-athlete' }, () => callOperation('program_get', {}))
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, 'http://pl-program:8000/operations/program_get')
    assert.equal(calls[0].headers.get('X-Person-Pk'), 'person')
    assert.equal(calls[0].headers.get('X-Athlete-Pk'), 'selected-athlete')
    assert.equal(calls[0].headers.has('X-PL-Principal'), false)
    await assert.rejects(callOperation('program_get', {}), /Authenticated operation context required/)
  } finally { globalThis.fetch = originalFetch }
})
