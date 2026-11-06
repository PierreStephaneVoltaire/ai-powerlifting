import assert from 'node:assert/strict'
import test from 'node:test'
import { createClient } from 'redis'
import { analysisSectionStatusDirect } from './analytics'
import { getOrCreateBlockAnalysisBundle } from '../services/blockAnalytics'

function owner(name: string): Record<string, unknown> {
  let prototype = Object.getPrototypeOf(createClient()) as Record<string, unknown> | null
  while (prototype && !Object.prototype.hasOwnProperty.call(prototype, name)) prototype = Object.getPrototypeOf(prototype)
  if (!prototype) throw new Error(`redis client has no ${name}`)
  return prototype
}

async function withValkey(get: (key: string) => string | null, run: () => Promise<void>): Promise<void> {
  const fakes: Record<string, unknown> = {
    async connect() { return this },
    async get(key: string) { return get(key) },
    async set() { return 'OK' },
  }
  const originals = Object.keys(fakes).map((name) => [owner(name), name, owner(name)[name]] as const)
  for (const [prototype, name] of originals) prototype[name] = fakes[name]
  try { await run() } finally { for (const [prototype, name, original] of originals) prototype[name] = original }
}

const context: Parameters<typeof analysisSectionStatusDirect>[0] = {
  pk: 'athlete-a', asOfDate: '2026-08-31', windowKey: 'current', sourceFingerprint: 'source-v1',
}

test('section status only reads the matching cache; missing cache does not generate', async () => {
  let payload: string | null = null
  const keys: string[] = []
  await withValkey((key) => { keys.push(key); return payload }, async () => {
    assert.equal((await analysisSectionStatusDirect(context, 'ai_correlation')).status, 'missing')
    payload = JSON.stringify({ sectionKey: 'ai_correlation', status: 'complete', payload: { summary: 'saved' } })
    const saved = await analysisSectionStatusDirect(context, 'ai_correlation')
    assert.deepEqual(saved.payload, { summary: 'saved' })
    assert.equal(saved.cached, true)
  })
  assert.equal(keys.length, 2)
  assert.ok(keys.every((key) => key.startsWith('pl:analysis:athlete-a:') && key.endsWith('source-v1')))
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
  let invoked = 0
  await withValkey(() => null, async () => {
    const result = await getOrCreateBlockAnalysisBundle('athlete-a', { meta: {}, sessions: [{ id: 'session-1', date: '2026-08-03', block: 'current', week_number: 1, status: 'completed', completed: true, exercises: [] }], phases: [], competitions: [], lift_profiles: [] } as any, 'current', async () => { invoked += 1; return {} }, false, true, [])
    assert.equal(result, null)
  })
  assert.equal(invoked, 0)
})

test('cache-only block analysis returns a cached bundle', async () => {
  const bundle = { schemaVersion: 6, generatedAt: '2026-09-15T00:00:00Z', cached: false, sourceFingerprint: 'source-v1', block: {}, weekly: {}, historical: {} }
  await withValkey(() => JSON.stringify(bundle), async () => {
    const result = await getOrCreateBlockAnalysisBundle('athlete-a', { meta: {}, sessions: [{ id: 'session-1', date: '2026-08-03', block: 'current', week_number: 1, status: 'completed', completed: true, exercises: [] }], phases: [], competitions: [], lift_profiles: [] } as any, 'current', async () => { throw new Error('generation must not run') }, false, true, [])
    assert.equal(result?.cached, true)
    assert.equal(result?.sourceFingerprint, 'source-v1')
  })
})
