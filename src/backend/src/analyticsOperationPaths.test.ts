import assert from 'node:assert/strict'
import test from 'node:test'
import { blocksGetPath } from './analyticsOperationPaths'

test('block analysis cache-only intent reaches the sidecar query', () => {
  assert.equal(blocksGetPath({ blockKey: 'current', refresh: false, cacheOnly: true }), '/blocks/current/analysis?refresh=false&cacheOnly=true')
  assert.equal(blocksGetPath({ blockKey: 'current', refresh: true, cacheOnly: false }), '/blocks/current/analysis?refresh=true&cacheOnly=false')
})
