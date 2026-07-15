import { test } from 'node:test'
import assert from 'node:assert/strict'
import jwt from 'jsonwebtoken'

process.env.JWT_SECRET = 'test-secret'

// Use tsx to import the TypeScript source files
const { signToken, verifyToken, tokenToIdentity } = await import('../src/middleware/auth.ts')

function makeDiscordToken() {
  return {
    provider: 'discord',
    sub: '1234567890',
    username: 'oliver',
    display_name: 'Oliver',
    avatar: 'https://example.com/avatar.png',
    groups: [],
    roles: [],
    email: null,
    discord_id: '1234567890',
  }
}

function makeAuthentikToken() {
  return {
    provider: 'authentik',
    sub: 'authentik-user-uuid',
    username: 'oliver',
    display_name: 'Oliver Simpalot',
    avatar: null,
    groups: ['powerlifting', 'coaches'],
    roles: ['app:coach'],
    email: 'oliver@example.com',
    discord_id: '',
  }
}

test('Discord token roundtrips and yields a discord identity', () => {
  const token = signToken(makeDiscordToken())
  const payload = verifyToken(token)
  assert.ok(payload, 'payload should not be null')
  assert.equal(payload.provider, 'discord')
  assert.equal(payload.sub, '1234567890')
  const identity = tokenToIdentity(payload)
  assert.equal(identity.provider, 'discord')
  assert.equal(identity.username, 'oliver')
})

test('Authentik token roundtrips and preserves groups and roles', () => {
  const token = signToken(makeAuthentikToken())
  const payload = verifyToken(token)
  assert.ok(payload, 'payload should not be null')
  assert.equal(payload.provider, 'authentik')
  assert.equal(payload.sub, 'authentik-user-uuid')
  assert.deepEqual(payload.groups, ['powerlifting', 'coaches'])
  assert.deepEqual(payload.roles, ['app:coach'])
  assert.equal(payload.email, 'oliver@example.com')
  const identity = tokenToIdentity(payload)
  assert.equal(identity.provider, 'authentik')
  assert.ok(identity.groups.includes('powerlifting'))
})

test('Old discord tokens (no provider field) are migrated to provider=discord', () => {
  const legacy = jwt.sign(
    { discord_id: '42', username: 'legacy', avatar: null, sub: '42' },
    process.env.JWT_SECRET,
    { expiresIn: '7d' },
  )
  const payload = verifyToken(legacy)
  assert.ok(payload, 'payload should not be null')
  assert.equal(payload.provider, 'discord')
  assert.equal(payload.username, 'legacy')
})

test('invalid tokens return null', () => {
  const bad = verifyToken('not-a-jwt')
  assert.equal(bad, null)
})

test('expired tokens return null', () => {
  const expired = jwt.sign(
    { ...makeDiscordToken() },
    process.env.JWT_SECRET,
    { expiresIn: '-1s' },
  )
  const payload = verifyToken(expired)
  assert.equal(payload, null)
})
