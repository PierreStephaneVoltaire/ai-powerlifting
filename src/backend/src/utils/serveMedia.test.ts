import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mediaRange } from './serveMedia'

test('media ranges handle suffixes, open ends, and invalid or unsatisfiable requests', () => {
  assert.equal(mediaRange('bytes=0-99', 1000), 'bytes=0-99')
  assert.equal(mediaRange('bytes=990-', 1000), 'bytes=990-999')
  assert.equal(mediaRange('bytes=-10', 1000), 'bytes=990-999')
  assert.equal(mediaRange('bytes=0-2000', 1000), 'bytes=0-999')
  for (const range of ['bytes=-', 'bytes=-0', 'bytes=1000-', 'bytes=9-2', 'bytes=0-1,3-4', 'items=0-9']) assert.equal(mediaRange(range, 1000), null)
})
