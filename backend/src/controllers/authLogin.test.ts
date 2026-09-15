import assert from 'node:assert/strict'
import test from 'node:test'
import passport, { Strategy } from 'passport'
import { discordSourceRedirect } from './authController'
import { discordLogin } from './authController'

test('Discord source wrapper encodes only trusted Authentik continuations', () => {
  const origin = 'https://auth.nolift.training'
  const continuation = `${origin}/application/o/authorize/?state=state&code_challenge=challenge`
  const result = discordSourceRedirect(continuation, origin)
  assert.equal(result, `${origin}/source/oauth/login/discord/?next=${encodeURIComponent(continuation)}`)
  assert.equal(discordSourceRedirect('https://evil.example/application/o/authorize/?state=x', origin), null)
  assert.equal(discordSourceRedirect(`${origin}/other?next=https://evil.example`, origin), null)
})

test('Discord login wraps Passport setHeader Location redirects at the response boundary', () => {
  const originalIssuer = process.env.AUTHENTIK_ISSUER_URL
  const strategies = passport as unknown as { _strategies: Record<string, Strategy> }
  const originalStrategy = strategies._strategies.authentik
  const continuation = 'https://auth.nolift.training/application/o/authorize/?state=state&code_challenge=challenge'
  const headers = new Map<string, string>()
  let ended = false
  class RedirectStrategy extends Strategy {
    authenticate() { this.redirect(continuation) }
  }
  passport.use('authentik', new RedirectStrategy())
  process.env.AUTHENTIK_ISSUER_URL = 'https://auth.nolift.training/application/o'
  const res = {
    statusCode: 200,
    setHeader(name: string, value: string) { headers.set(name.toLowerCase(), value); return this },
    end() { ended = true; return this },
  }
  try {
    discordLogin({} as never, res as never, () => undefined)
  } finally {
    strategies._strategies.authentik = originalStrategy
    if (originalIssuer === undefined) delete process.env.AUTHENTIK_ISSUER_URL
    else process.env.AUTHENTIK_ISSUER_URL = originalIssuer
  }
  assert.equal(res.statusCode, 302)
  assert.equal(ended, true)
  assert.equal(headers.get('location'), `${'https://auth.nolift.training'}/source/oauth/login/discord/?next=${encodeURIComponent(continuation)}`)
})

test('Discord login leaves untrusted Passport Location redirects unchanged', () => {
  const originalAuthenticate = passport.authenticate
  const headers = new Map<string, string>()
  passport.authenticate = (() => (_req: unknown, res: { setHeader: (name: string, value: string) => unknown; end: () => unknown }) => {
    res.setHeader('Location', 'https://evil.example/application/o/authorize/?state=state')
    res.end()
  }) as typeof passport.authenticate
  const res = {
    setHeader(name: string, value: string) { headers.set(name.toLowerCase(), value); return this },
    end() { return this },
  }
  try {
    discordLogin({} as never, res as never, () => undefined)
  } finally {
    passport.authenticate = originalAuthenticate
  }
  assert.equal(headers.get('location'), 'https://evil.example/application/o/authorize/?state=state')
})
