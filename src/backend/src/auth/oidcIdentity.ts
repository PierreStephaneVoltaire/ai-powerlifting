import type { AuthIdentity } from './identity'
import { AppError } from '../middleware/errorHandler'

const DISCORD_SUBJECT = /^\d{1,32}$/

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : []
}

function claimsFrom(token: string): Record<string, unknown> {
  const payload = token.split('.')[1]
  if (!payload) throw new AppError('Invalid login token', 401, 'AUTH_REQUIRED')
  try {
    const claims: unknown = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'))
    if (!claims || typeof claims !== 'object' || Array.isArray(claims)) throw new Error('Invalid claims')
    return claims as Record<string, unknown>
  } catch { throw new AppError('Invalid login token', 401, 'AUTH_REQUIRED') }
}

export function identityFromToken(token: string): AuthIdentity {
  const claims = claimsFrom(token)
  const issuer = process.env.AUTHENTIK_ISSUER_URL
  const audience = Array.isArray(claims.aud) ? claims.aud : [claims.aud]
  if (claims.iss !== issuer || !audience.includes(process.env.AUTHENTIK_CLIENT_ID)) throw new AppError('Login token is not for this application', 401, 'AUTH_REQUIRED')
  if (typeof claims.sub !== 'string' || !claims.sub) throw new AppError('Invalid identity subject', 401, 'AUTH_REQUIRED')
  const fallback = `authentik_${claims.sub}`
  const username = String(claims.preferred_username || fallback).toLowerCase().replace(/[^a-z0-9_-]/g, '_').slice(0, 32) || fallback
  return {
    issuer: issuer as string,
    provider: 'authentik',
    sub: claims.sub,
    username,
    display_name: String(claims.name || claims.preferred_username || username),
    avatar: typeof claims.picture === 'string' ? claims.picture : null,
    email: typeof claims.email === 'string' ? claims.email : null,
    groups: strings(claims.groups),
    roles: strings(claims.roles),
    discord_subjects: strings(claims.discord_subjects).filter(value => DISCORD_SUBJECT.test(value)),
  }
}
