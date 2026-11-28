import assert from 'node:assert/strict'
import { once } from 'node:events'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import express from 'express'
import { createServer } from 'vite'
import { configureMeshAuthentication } from './backend/dist/middleware/meshAuth.js'
import { errorHandler } from './backend/dist/middleware/errorHandler.js'
import { importRouter } from './backend/dist/routes/import.js'
import agent from './backend/dist/utils/agent.js'

test('portal HTTP dependencies', async t => {
  process.env.AUTHENTIK_ISSUER_URL = 'https://issuer.example'
  process.env.AUTHENTIK_CLIENT_ID = 'test-client'
  const app = express()
  configureMeshAuthentication(app)
  app.get('/api/client', (req, res) => res.json({ ip: req.ip, athlete: req.get('X-Selected-Athlete-Pk') }))
  app.use('/api/import', importRouter)
  app.use(errorHandler)
  const server = app.listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => new Promise(resolve => server.close(resolve)))
  const origin = `http://127.0.0.1:${server.address().port}`
  process.env.FRONTEND_URL = origin
  const vite = await createServer({
    root: fileURLToPath(new URL('./frontend/', import.meta.url)),
    configFile: false,
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true },
  })
  t.after(() => vite.close())
  const { default: api } = await vite.ssrLoadModule('/src/api/http.ts')
  api.defaults.baseURL = origin + '/api'
  api.defaults.headers.common.Origin = origin
  const { setRequestAthlete } = await vite.ssrLoadModule('/src/api/context.ts')
  setRequestAthlete('test-athlete')

  await t.test('the HTTP client sends the selected athlete and Express trusts one proxy hop', async () => {
    const response = await api.get('/client', { headers: { 'X-Forwarded-For': '192.0.2.1, 192.0.2.2' } })
    assert.deepEqual(response.data, { ip: '192.0.2.2', athlete: 'test-athlete' })
  })

  await t.test('the import route forwards the uploaded bytes and filters unsupported files', async t => {
    const parse = t.mock.method(agent, 'invokeToolDirect', async () => ({ import_id: 'test-import' }))
    const { uploadImport } = await vite.ssrLoadModule('/src/api/client.ts')
    const csv = 'day,exercise\nMonday,Squat\n'
    const result = await uploadImport(new File([csv], 'week.csv', { type: 'text/csv' }), 'session_import', 'Week one')
    assert.equal(result.import_id, 'test-import')
    assert.deepEqual(parse.mock.calls[0].arguments, ['import_parse_file', {
      base64_content: Buffer.from(csv).toString('base64'),
      filename: 'week.csv',
      import_type: 'session_import',
      import_instructions: 'Week one',
      pk: undefined,
    }])
    await assert.rejects(uploadImport(new File(['text'], 'notes.txt', { type: 'text/plain' }), 'session_import', ''),
      error => error.response?.status === 400 && error.response.data.error === 'No file uploaded')
    assert.equal(parse.mock.callCount(), 1)
  })
})
