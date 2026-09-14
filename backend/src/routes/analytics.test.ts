import assert from 'node:assert/strict'
import test from 'node:test'
import { gzipSync } from 'node:zlib'
import { DynamoDBDocumentClient, GetCommand } from '@aws-sdk/lib-dynamodb'
import { analysisSectionStatusDirect } from './analytics'

const context: Parameters<typeof analysisSectionStatusDirect>[0] = {
  pk: 'athlete-a', asOfDate: '2026-08-31', windowKey: 'current', sourceFingerprint: 'source-v1',
}

test('section status only reads the matching cache; missing cache does not generate', async () => {
  const original = DynamoDBDocumentClient.prototype.send
  let payload: string | undefined
  let reads = 0
  DynamoDBDocumentClient.prototype.send = (async (command: unknown) => {
    assert.ok(command instanceof GetCommand)
    assert.equal(command.input.Key?.pk, 'analysis#athlete-a')
    assert.match(String(command.input.Key?.sk), /source-v1$/)
    reads += 1
    return { Item: payload ? { payload } : undefined }
  }) as typeof original
  try {
    assert.equal((await analysisSectionStatusDirect(context, 'ai_correlation')).status, 'missing')
    payload = gzipSync(JSON.stringify({ sectionKey: 'ai_correlation', status: 'complete', payload: { summary: 'saved' } })).toString('base64')
    const saved = await analysisSectionStatusDirect(context, 'ai_correlation')
    assert.deepEqual(saved.payload, { summary: 'saved' })
    assert.equal(saved.cached, true)
    assert.equal(reads, 2)
  } finally { DynamoDBDocumentClient.prototype.send = original }
})

test('unchanged multi-block report inputs ignore generation timestamps', async () => {
  const { getOrCreateAiBlockComparison } = await import('../services/blockAnalytics')
  const requests: unknown[] = []
  const invoke = async (_name: string, args: Record<string, unknown>) => { requests.push(args); return { cached: false, cache_miss: true } }
  await getOrCreateAiBlockComparison('athlete-a', [], invoke, false, true)
  await new Promise((resolve) => setTimeout(resolve, 5))
  await getOrCreateAiBlockComparison('athlete-a', [], invoke, false, true)
  assert.deepEqual(requests[0], requests[1])
})
