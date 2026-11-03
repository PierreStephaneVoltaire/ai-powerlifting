import { test } from 'node:test'
import assert from 'node:assert/strict'

process.env.AUTHENTIK_ISSUER_URL = 'https://auth.example.com/application/o/powerlifting/'
process.env.SESSION_SECRET = 'test-secret'

const { discordIdentityFromProfile, isValidIdentity } = await import('../src/middleware/auth.ts')

function authentikIdentity() {
  return {
    issuer: process.env.AUTHENTIK_ISSUER_URL,
    provider: 'authentik',
    sub: 'authentik-user-uuid',
    username: 'oliver',
    display_name: 'Oliver Simpalot',
    avatar: null,
    groups: ['powerlifting', 'coaches'],
    roles: ['app:coach'],
    email: 'oliver@example.com',
  }
}

test('Discord profile becomes a verified discord identity', () => {
  const identity = discordIdentityFromProfile({ id: '1234567890', username: 'oliver', global_name: 'Oliver', avatar: 'abc' })
  assert.equal(identity.provider, 'discord')
  assert.equal(identity.issuer, 'https://discord.com')
  assert.equal(identity.sub, '1234567890')
  assert.equal(identity.display_name, 'Oliver')
  assert.equal(identity.avatar, 'https://cdn.discordapp.com/avatars/1234567890/abc.png')
  assert.deepEqual(identity.discord_subjects, ['1234567890'])
  assert.ok(isValidIdentity(identity))
})

test('Discord profile without a display name falls back to the username', () => {
  const identity = discordIdentityFromProfile({ id: '42', username: 'legacy' })
  assert.equal(identity.display_name, 'legacy')
  assert.equal(identity.avatar, null)
})

test('malformed Discord profiles are rejected', () => {
  assert.equal(discordIdentityFromProfile(null), null)
  assert.equal(discordIdentityFromProfile({ id: 'not-a-snowflake', username: 'x' }), null)
  assert.equal(discordIdentityFromProfile({ id: '42' }), null)
})

test('Authentik identity from the configured issuer is valid and keeps groups and roles', () => {
  const identity = authentikIdentity()
  assert.ok(isValidIdentity(identity))
  assert.deepEqual(identity.groups, ['powerlifting', 'coaches'])
})

test('identities from another issuer or with missing fields are invalid', () => {
  assert.equal(isValidIdentity({ ...authentikIdentity(), issuer: 'https://evil.example.com/' }), false)
  assert.equal(isValidIdentity({ ...authentikIdentity(), groups: undefined }), false)
  assert.equal(isValidIdentity('not-an-identity'), false)
})
