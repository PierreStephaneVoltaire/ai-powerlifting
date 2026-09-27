import assert from 'node:assert/strict'
import test from 'node:test'

process.env.AUTHENTIK_ISSUER_URL = 'https://auth.nolift.training/application/o/powerlifting/'
process.env.DISCORD_CLIENT_ID = '1459678985473757400'
process.env.DISCORD_CLIENT_SECRET = 'test-secret'
process.env.DISCORD_REDIRECT_URI = 'https://dev.nolift.training/api/auth/discord/callback'

import { createDiscordStrategy, discordIdentityFromProfile, isValidIdentity } from '../middleware/auth'

function request(session: Record<string, unknown>, query: Record<string, string> = {}) {
  return { session, query, body: {}, headers: {}, connection: { encrypted: true }, method: 'GET', url: '/api/auth/discord/callback' } as never
}

test('configured Passport strategy issues Discord authorization with exact client, callback, state, and PKCE', () => {
  const strategy = createDiscordStrategy(() => undefined)
  let location = ''
  strategy.redirect = (value: string) => { location = value }
  const session: Record<string, unknown> = {}
  strategy.authenticate(request(session, {}))
  const url = new URL(location)
  assert.equal(url.origin, 'https://discord.com')
  assert.equal(url.pathname, '/api/oauth2/authorize')
  assert.equal(url.searchParams.get('client_id'), '1459678985473757400')
  assert.equal(url.searchParams.get('redirect_uri'), 'https://dev.nolift.training/api/auth/discord/callback')
  assert.match(url.searchParams.get('state') || '', /^\w+$/)
  assert.match(url.searchParams.get('code_challenge') || '', /^[-_A-Za-z0-9]+$/)
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256')
})

test('configured Passport strategy rejects missing, invalid, and replayed state before token exchange', () => {
  const strategy = createDiscordStrategy(() => undefined)
  let exchanges = 0
  ;(strategy as unknown as { _oauth2: { getOAuthAccessToken: Function } })._oauth2.getOAuthAccessToken = (() => { exchanges += 1 }) as never
  strategy.fail = () => undefined
  strategy.error = () => undefined
  strategy.authenticate(request({}, { code: 'code', state: 'missing' }))
  assert.equal(exchanges, 0)

  const invalidSession: Record<string, unknown> = {}
  strategy.authenticate(request(invalidSession, {}))
  strategy.authenticate(request(invalidSession, { code: 'code', state: 'wrong' }))
  assert.equal(exchanges, 0)

  const validSession: Record<string, unknown> = {}
  strategy.authenticate(request(validSession, {}))
  const stored = validSession['oauth2:discord'] as { state: { handle: string } }
  const handle = stored.state.handle
  strategy.authenticate(request(validSession, { code: 'code', state: handle }))
  assert.equal(exchanges, 1)
  strategy.authenticate(request(validSession, { code: 'code', state: handle }))
  assert.equal(exchanges, 1)
})

test('callback exchanges mocked code and profile, then consumes state', async () => {
  let verifiedUser: Express.User | undefined
  const strategy = createDiscordStrategy(async (_accessToken: string, _refreshToken: string, profile: unknown, done: (error?: Error | null, user?: Express.User | false) => void) => {
    const identity = discordIdentityFromProfile(profile)
    done(null, identity ? { discord_id: identity.sub, username: identity.username, avatar: identity.avatar, actor_mapped_pk: '', identity } : false)
  })
  let location = ''
  strategy.redirect = (value: string) => { location = value }
  const session: Record<string, unknown> = {}
  strategy.authenticate(request(session, {}))
  const state = new URL(location).searchParams.get('state')!
  ;(strategy as unknown as { _oauth2: { getOAuthAccessToken: Function } })._oauth2.getOAuthAccessToken = ((_code: string, _params: object, callback: (error: null, accessToken: string, refreshToken: string, params: object) => void) => callback(null, 'access-token', '', {})) as never
  ;(strategy as unknown as { _loadUserProfile: (token: string, done: (error: null, profile: unknown) => void) => void })._loadUserProfile = (_token, done) => done(null, { id: '1459678985473757400', username: 'luna', email: 'ignored@example.com' })
  strategy.success = (user: Express.User) => { verifiedUser = user }
  strategy.authenticate(request(session, { code: 'code', state }))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(verifiedUser?.identity.sub, '1459678985473757400')
  assert.equal(session['oauth2:discord'], undefined)
})

test('profile and session identity validation use verified provider subject and issuer pairing', () => {
  const identity = discordIdentityFromProfile({ id: '1459678985473757400', username: 'luna', email: 'ignored@example.com' })!
  assert.equal(identity.sub, '1459678985473757400')
  assert.equal(identity.email, null)
  assert.equal(discordIdentityFromProfile(null), null)
  assert.equal(discordIdentityFromProfile({ id: 'not-a-discord-id', username: 'luna' }), null)
  assert.equal(isValidIdentity(identity), true)
  assert.equal(isValidIdentity({ ...identity, issuer: 'https://auth.nolift.training' }), false)
  assert.equal(isValidIdentity({ ...identity, provider: 'authentik', issuer: 'https://auth.nolift.training' }), false)
})
