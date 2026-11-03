import assert from 'node:assert/strict'
import test from 'node:test'
import { gzipSync } from 'node:zlib'
import { DynamoDBDocumentClient, GetCommand } from '@aws-sdk/lib-dynamodb'
import { analysisSectionStatusDirect } from './analytics'
import { getOrCreateBlockAnalysisBundle } from '../services/blockAnalytics'

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

test('cache-only block analysis misses without invoking generation', async () => {
  const original = DynamoDBDocumentClient.prototype.send
  let invoked = 0
  DynamoDBDocumentClient.prototype.send = (async () => ({ Item: undefined })) as typeof original
  try {
    const result = await getOrCreateBlockAnalysisBundle('athlete-a', { meta: {}, sessions: [{ id: 'session-1', date: '2026-08-03', block: 'current', week_number: 1, status: 'completed', completed: true, exercises: [] }], phases: [], competitions: [], lift_profiles: [] } as any, 'current', async () => { invoked += 1; return {} }, false, true, [])
    assert.equal(result, null)
    assert.equal(invoked, 0)
  } finally { DynamoDBDocumentClient.prototype.send = original }
})

test('cache-only block analysis returns a cached bundle', async () => {
  const original = DynamoDBDocumentClient.prototype.send
  const bundle = { schemaVersion: 6, generatedAt: '2026-09-15T00:00:00Z', cached: false, sourceFingerprint: 'source-v1', block: {}, weekly: {}, historical: {} }
  DynamoDBDocumentClient.prototype.send = (async () => ({ Item: { payload: gzipSync(JSON.stringify(bundle)).toString('base64') } })) as typeof original
  try {
    const result = await getOrCreateBlockAnalysisBundle('athlete-a', { meta: {}, sessions: [{ id: 'session-1', date: '2026-08-03', block: 'current', week_number: 1, status: 'completed', completed: true, exercises: [] }], phases: [], competitions: [], lift_profiles: [] } as any, 'current', async () => { throw new Error('generation must not run') }, false, true, [])
    assert.equal(result?.cached, true)
    assert.equal(result?.sourceFingerprint, 'source-v1')
  } finally { DynamoDBDocumentClient.prototype.send = original }
})
