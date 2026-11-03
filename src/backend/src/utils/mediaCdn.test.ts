import assert from 'node:assert/strict'
import { createVerify, generateKeyPairSync } from 'node:crypto'
import { test } from 'node:test'
import { isPublicMediaKey, mediaCdnConfig, publicMediaUrl, signedMediaUrl, signedUrlExpiry } from './mediaCdn'

const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 })
const config = {
  baseUrl: 'https://media.example.net',
  keyPairId: 'K2EXAMPLE',
  privateKey: privateKey.export({ type: 'pkcs1', format: 'pem' }).toString(),
  videoTtlSeconds: 72 * 3600,
}

test('config requires base url, key pair id and private key, defaulting the video ttl to 72 hours', () => {
  assert.equal(mediaCdnConfig({ MEDIA_CDN_BASE_URL: 'https://x', MEDIA_SIGNING_KEY_PAIR_ID: 'K' }), null)
  const loaded = mediaCdnConfig({ MEDIA_CDN_BASE_URL: 'https://x/', MEDIA_SIGNING_KEY_PAIR_ID: 'K', MEDIA_SIGNING_PRIVATE_KEY: 'pem' })
  assert.deepEqual(loaded, { baseUrl: 'https://x', keyPairId: 'K', privateKey: 'pem', videoTtlSeconds: 259200 })
})

test('only thumbnails are public and their urls encode each path segment', () => {
  assert.equal(isPublicMediaKey('thumbnails/2026-05-16/a b.jpg'), true)
  assert.equal(isPublicMediaKey('processed/2026-05-16/a.mp4'), false)
  assert.equal(publicMediaUrl(config, 'thumbnails/2026-05-16/a b.jpg'), 'https://media.example.net/thumbnails/2026-05-16/a%20b.jpg')
})

test('expiry is stable within a day and always leaves at least the ttl', () => {
  const dayStart = Date.UTC(2026, 8, 26)
  const early = signedUrlExpiry(config.videoTtlSeconds, dayStart + 1000)
  const late = signedUrlExpiry(config.videoTtlSeconds, dayStart + 86_399_000)
  assert.equal(early, late)
  assert.ok(early - (dayStart + 86_399_000) / 1000 >= config.videoTtlSeconds)
  assert.notEqual(signedUrlExpiry(config.videoTtlSeconds, dayStart + 86_400_000), early)
})

test('signed urls carry a canned-policy signature verifiable with the public key', () => {
  const url = new URL(signedMediaUrl(config, 'processed/2026-05-16/v1/r1.mp4', Date.UTC(2026, 8, 26, 12)))
  const expires = Number(url.searchParams.get('Expires'))
  assert.equal(url.searchParams.get('Key-Pair-Id'), 'K2EXAMPLE')
  const resource = `${url.origin}${url.pathname}`
  const policy = JSON.stringify({ Statement: [{ Resource: resource, Condition: { DateLessThan: { 'AWS:EpochTime': expires } } }] })
  const signature = Buffer.from(url.searchParams.get('Signature')!.replace(/-/g, '+').replace(/_/g, '=').replace(/~/g, '/'), 'base64')
  assert.ok(createVerify('RSA-SHA1').update(policy).verify(publicKey, signature))
})
