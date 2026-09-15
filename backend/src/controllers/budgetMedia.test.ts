import assert from 'node:assert/strict'
import { test } from 'node:test'
import { operationScope } from '../utils/operationScope'

test('budget photo resolution rejects a forged attachment from another Athlete', async (t) => {
  process.env.INTERNAL_API_TOKEN = 'local-test'
  process.env.PL_PRINCIPAL_SECRET = 'local-test-principal-secret-for-budget-media'
  const { resolveItemPhoto } = await import('./budgetController')
  const valid = 'budget/athlete-a/item-1/photo.jpg'
  const forged = 'budget/athlete-b/item-2/private.jpg'
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ items: [
    { id: 'item-1', photo_s3_key: valid }, { id: 'item-2', photo_s3_key: forged },
  ] })))
  await operationScope.run({ person: 'person-a', athlete: 'athlete-a' }, async () => {
    assert.equal(await resolveItemPhoto('athlete-a', valid), valid)
    await assert.rejects(resolveItemPhoto('athlete-a', forged), /Photo not found/)
  })
})
