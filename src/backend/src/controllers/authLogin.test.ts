import assert from 'node:assert/strict'
import test from 'node:test'
import express from 'express'
import { once } from 'node:events'
import type { AddressInfo } from 'node:net'
import { authRouter } from '../routes/auth'

test('the gateway advertises Authentik and directs logout to the proxy without legacy login callbacks', async () => {
  const app = express()
  app.use('/api/auth', authRouter)
  const server = app.listen(0, '127.0.0.1')
  try {
    await once(server, 'listening')
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}/api/auth`
    assert.deepEqual(await (await fetch(`${base}/providers`)).json(), { authentik: { enabled: true } })
    assert.deepEqual(await (await fetch(`${base}/logout`, { method: 'POST' })).json(), { ok: true, redirect: '/oauth2/sign_out?rd=%2F' })
    for (const route of ['/discord/login', '/discord/callback', '/authentik/login', '/authentik/callback']) {
      assert.equal((await fetch(`${base}${route}`)).status, 404)
    }
  } finally {
    server.closeAllConnections()
    await new Promise<void>(resolve => server.close(() => resolve()))
  }
})
