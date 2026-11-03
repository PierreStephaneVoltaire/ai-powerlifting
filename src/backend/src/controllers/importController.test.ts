import assert from 'node:assert/strict'
import { test } from 'node:test'
import { operationScope } from '../utils/operationScope'

test('apply preserves domain validation status through the gateway', async () => {
  process.env.INTERNAL_API_TOKEN = 'import-controller-test-token'
  process.env.PL_PRINCIPAL_SECRET = 'import-controller-test-principal-secret'
  process.env.POWERLIFTING_SERVICE_BASE_URL = 'http://import-controller-test'
  const { applyImport } = await import('./importController')
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input) => {
    const url = String(input)
    if (url.endsWith('/profile/internal/access')) return new Response('{}', { status: 200 })
    if (url.endsWith('/operations/import_apply')) {
      return new Response(JSON.stringify({ detail: { code: 'operation_failed', message: 'Import already applied' } }), { status: 422 })
    }
    throw new Error(`Unexpected request ${url}`)
  }) as typeof fetch
  const response = { json(value: unknown) { return value } }
  try {
    await assert.rejects(
      operationScope.run({ athlete: 'athlete-1', person: 'person-1' }, () => applyImport(
        { params: { importId: 'import-1' }, body: {}, mapped_pk: 'athlete-1' } as any,
        response as any,
      )),
      (error: any) => error.statusCode === 422 && error.code === 'operation_failed' && error.message === 'Import already applied',
    )
  } finally {
    globalThis.fetch = originalFetch
  }
})
