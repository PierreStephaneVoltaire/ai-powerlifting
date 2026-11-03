import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isUploadKeyFor, MAX_VIDEO_PARTS, normalizeParts, parsePartNumber, partCount, VIDEO_PART_BYTES } from './videoMultipart'

test('part plan keeps every part under the proxy body cap', () => {
  assert.equal(partCount(1), 1)
  assert.equal(partCount(VIDEO_PART_BYTES), 1)
  assert.equal(partCount(VIDEO_PART_BYTES + 1), 2)
  assert.equal(partCount(500 * 1024 * 1024), MAX_VIDEO_PARTS)
  assert.ok(VIDEO_PART_BYTES < 100 * 1000 * 1000)
})

test('upload keys must belong to the routed session date and video', () => {
  const videoId = '5dfb0fc5-281a-5b98-ab27-53ec04dd8002'
  assert.ok(isUploadKeyFor(`videos/2026-10-21/${videoId}.mp4`, '2026-10-21', videoId))
  assert.ok(!isUploadKeyFor(`videos/2026-10-22/${videoId}.mp4`, '2026-10-21', videoId))
  assert.ok(!isUploadKeyFor(`videos/2026-10-21/other.mp4`, '2026-10-21', videoId))
  assert.ok(!isUploadKeyFor(`videos/2026-10-21/${videoId}.mp4/../x`, '2026-10-21', videoId))
  assert.ok(!isUploadKeyFor(`videos/2026-10-21/${videoId}.`, '2026-10-21', videoId))
})

test('part numbers and completion lists are validated', () => {
  assert.equal(parsePartNumber('1'), 1)
  for (const value of ['0', String(MAX_VIDEO_PARTS + 1), '1.5', 'x']) assert.equal(parsePartNumber(value), null)
  assert.deepEqual(normalizeParts([{ partNumber: 2, etag: 'b' }, { partNumber: 1, etag: 'a' }]), [{ partNumber: 1, etag: 'a' }, { partNumber: 2, etag: 'b' }])
  assert.equal(normalizeParts([{ partNumber: 1, etag: 'a' }, { partNumber: 3, etag: 'c' }]), null)
  assert.equal(normalizeParts([{ partNumber: 1, etag: '' }]), null)
  assert.equal(normalizeParts([]), null)
})
