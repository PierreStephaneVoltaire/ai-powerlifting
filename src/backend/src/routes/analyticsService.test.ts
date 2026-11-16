import assert from 'node:assert/strict'
import { once } from 'node:events'
import type { AddressInfo } from 'node:net'
import test from 'node:test'
import express from 'express'
import { autoScopeForRoute } from '../auth/scope'
import { resolvePk, requireWriteAuth } from '../middleware/auth'
import { errorHandler } from '../middleware/errorHandler'
import { analyticsServiceRouter } from './analyticsService'

test('anonymous published block analysis loads without a cached bundle', async () => {
  const originalFetch = globalThis.fetch
  const calls: Request[] = []
  let published = true
  const bundle = { block: { blockKey: 'current' }, weekly: {}, cached: false }
  globalThis.fetch = (async (input, init) => {
    const request = new Request(input, init)
    if (request.url.endsWith('/operations/access_context')) {
      return Response.json({ permissions: published ? ['analytics:read'] : [] })
    }
    calls.push(request)
    assert.ok(request.url.endsWith('/operations/analytics.blocks_get'))
    const args = await request.clone().json()
    return args.cacheOnly
      ? Response.json({ detail: { message: 'Block current not cached' } }, { status: 404 })
      : Response.json(bundle)
  }) as typeof fetch
  const app = express()
  app.use(resolvePk, requireWriteAuth, autoScopeForRoute())
  app.use('/api/analytics', analyticsServiceRouter)
  app.use(errorHandler)
  const server = app.listen(0, '127.0.0.1')
  try {
    await once(server, 'listening')
    const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/api/analytics/blocks/current/analysis`
    const headers = { 'X-Selected-Athlete-Pk': 'public-athlete' }
    const response = await originalFetch(`${url}?refresh=false`, { headers })
    assert.equal(response.status, 200)
    assert.deepEqual(await response.json(), { data: bundle, error: null })
    assert.equal(calls[0].headers.get('X-Person-Pk'), '')
    assert.equal(calls[0].headers.get('X-Athlete-Pk'), 'public-athlete')
    assert.deepEqual(await calls[0].json(), { pk: 'public-athlete', blockKey: 'current', refresh: false, cacheOnly: false })
    assert.equal((await originalFetch(`${url}?cacheOnly=true`, { headers })).status, 404)
    assert.equal((await originalFetch(`${url}?refresh=true`, { headers })).status, 401)
    published = false
    assert.equal((await originalFetch(url, { headers })).status, 401)
    assert.equal(calls.length, 2)
  } finally {
    server.closeAllConnections()
    await new Promise<void>(resolve => server.close(() => resolve()))
    globalThis.fetch = originalFetch
  }
})
