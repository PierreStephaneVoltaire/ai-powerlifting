import assert from 'node:assert/strict'
import test from 'node:test'
import { relayResponse } from './analyticsRelay'

test('relayed exports keep their download filename', async () => {
  const upstream = new Response('# Block', { status: 200, headers: { 'Content-Type': 'text/markdown; charset=utf-8', 'Content-Disposition': 'attachment; filename="sunny-daze-apex-prep.md"' } })
  const headers: Record<string, string> = {}
  let status = 0
  let sent = ''
  const res = { status(code: number) { status = code; return this }, setHeader(name: string, value: string) { headers[name.toLowerCase()] = value }, send(body: Buffer) { sent = body.toString() } }
  await relayResponse(upstream, res as never)
  assert.equal(status, 200)
  assert.equal(headers['content-disposition'], 'attachment; filename="sunny-daze-apex-prep.md"')
  assert.equal(headers['content-type'], 'text/markdown; charset=utf-8')
  assert.equal(sent, '# Block')
})
