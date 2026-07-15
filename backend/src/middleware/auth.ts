import { Request, Response, NextFunction } from 'express'
import jwt from 'jsonwebtoken'
import { resolveMappedPk, getSettings as fetchSettings } from '../services/userSettings'
import { AppError } from './errorHandler'
import type { AuthIdentity, IdentityProvider } from '../auth/identity'
import {
  groupsFromSettings,
  isAppRole,
  type AppRole,
} from '../auth/identity'
import { setAuthCookie } from '../auth/cookies'

declare global {
  namespace Express {
    interface Request {
      user?:
        | ({
            discord_id: string
            username: string
            avatar: string | null
            actor_mapped_pk: string
            identity: AuthIdentity
          } | null)
      mapped_pk?: string
      actor_mapped_pk?: string
      isAuthenticated?: boolean
      readOnly?: boolean
    }
  }
}

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me'
const JWT_EXPIRY = '7d'
const TEST_MAPPED_PK_RE = /^[A-Za-z0-9:_#-]{1,128}$/

function testMappedPkOverride(): string | null {
  const override = process.env.POWERLIFTING_TEST_MAPPED_PK?.trim()
  if (!override) return null
  if (!TEST_MAPPED_PK_RE.test(override)) {
    throw new Error('Invalid POWERLIFTING_TEST_MAPPED_PK')
  }
  return override
}

export interface AuthToken {
  provider: IdentityProvider
  sub: string
  username: string
  display_name: string
  avatar: string | null
  groups: string[]
  roles: string[]
  email?: string | null
  // Self-declared app role (settings.roles / settings.active_role). Not
  // present for tokens issued before the role onboarding shipped.
  active_role?: AppRole | null
  // Backwards-compat field for code paths that still read `payload.discord_id`.
  discord_id: string
}

export function signToken(payload: AuthToken): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: JWT_EXPIRY })
}

export function verifyToken(token: string): AuthToken | null {
  try {
    const decoded = jwt.verify(token, JWT_SECRET) as Partial<AuthToken>
    if (!decoded || typeof decoded !== 'object') return null
    if (!decoded.provider) decoded.provider = 'discord'
    if (!decoded.sub) decoded.sub = decoded.discord_id || ''
    if (!decoded.username) return null
    if (!Array.isArray(decoded.groups)) decoded.groups = []
    if (!Array.isArray(decoded.roles)) decoded.roles = []
    return decoded as AuthToken
  } catch {
    return null
  }
}

export function signState(): string {
  return jwt.sign({ t: Date.now() }, JWT_SECRET, { expiresIn: '10m' })
}

export function verifyState(state: string): boolean {
  try {
    jwt.verify(state, JWT_SECRET)
    return true
  } catch {
    return false
  }
}

export function tokenToIdentity(token: AuthToken): AuthIdentity {
  return {
    provider: token.provider,
    sub: token.sub,
    username: token.username,
    display_name: token.display_name || token.username,
    avatar: token.avatar ?? null,
    groups: token.groups ?? [],
    roles: token.roles ?? [],
    active_role: isAppRole(token.active_role) ? token.active_role : null,
    email: token.email ?? null,
  }
}

function legacyUserShape(token: AuthToken) {
  return {
    discord_id: token.provider === 'discord' ? token.sub : token.discord_id || '',
    username: token.username,
    avatar: token.avatar ?? null,
  }
}

export async function requireUserOptional(req: Request, _res: Response, next: NextFunction): Promise<void> {
  const token = req.cookies?.pl_auth
  if (!token) {
    req.user = null
    req.isAuthenticated = false
    return next()
  }

  const payload = verifyToken(token)
  if (!payload) {
    req.user = null
    req.isAuthenticated = false
    return next()
  }

  const identity = tokenToIdentity(payload)
  req.user = {
    ...legacyUserShape(payload),
    identity,
    actor_mapped_pk: 'operator',
  }
  req.isAuthenticated = true
  next()
}

export async function resolvePk(req: Request, _res: Response, next: NextFunction): Promise<void> {
  const testMappedPk = testMappedPkOverride()
  if (testMappedPk) {
    req.mapped_pk = testMappedPk
    req.actor_mapped_pk = testMappedPk
    req.readOnly = false
    if (req.user) req.user.actor_mapped_pk = testMappedPk
    return next()
  }

  if (!req.user) {
    req.mapped_pk = 'operator'
    req.actor_mapped_pk = 'operator'
    req.readOnly = true
    return next()
  }

  try {
    const mappedPk = await resolveMappedPk(
      req.user.discord_id,
      req.user.username,
      req.user.avatar,
    )
    req.mapped_pk = mappedPk
    req.actor_mapped_pk = mappedPk
    req.readOnly = false
    req.user.actor_mapped_pk = mappedPk
  } catch (err) {
    console.error('Failed to resolve PK for user', req.user.discord_id, err)
    return next(new AppError('Failed to resolve authenticated user settings', 500, 'AUTH_CONTEXT_FAILED'))
  }

  next()
}

export function requireWriteAuth(req: Request, _res: Response, next: NextFunction): void {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
    return next()
  }

  const readOnlySafePost = req.method === 'POST' && [
    '/api/analytics/analysis/sections/queue',
    '/api/analytics/block-comparison/ai',
    '/api/analytics/budget/timeline',
    '/api/budget/ai-analysis',
  ].includes(req.path)

  if (readOnlySafePost) {
    return next()
  }

  if (testMappedPkOverride()) {
    return next()
  }

  if (!req.user) {
    return next(new AppError('Sign in required', 401, 'AUTH_REQUIRED'))
  }
  if (req.readOnly) {
    return next(new AppError('Read-only access: writes are not permitted', 403, 'READ_ONLY'))
  }

  next()
}

export function requireAdmin(req: Request, _res: Response, next: NextFunction): void {
  if (testMappedPkOverride()) {
    return next()
  }

  if (req.readOnly || !req.user) {
    return next(new AppError('Sign in required', 401, 'AUTH_REQUIRED'))
  }

  if (req.mapped_pk !== 'operator') {
    return next(new AppError('Admin access required', 403, 'ADMIN_REQUIRED'))
  }

  next()
}

/**
 * Re-sign the user's JWT with the latest `groups`, `roles`, and `active_role`
 * claims derived from their settings record. Used by the login callbacks and
 * by the onboarding endpoint after a role / profile / athlete-basics change so
 * the next request sees fresh claims without forcing a re-login.
 */
export async function reissueTokenFromSettings(
  res: Response,
  currentToken: AuthToken,
  username: string,
): Promise<AuthToken> {
  const settings = await fetchSettings(username).catch(() => null)
  const merged = groupsFromSettings(
    currentToken.groups ?? [],
    currentToken.roles ?? [],
    settings?.roles,
    settings?.active_role,
  )
  const nextToken: AuthToken = {
    ...currentToken,
    groups: merged.groups,
    roles: merged.roles,
    active_role: merged.active_role,
  }
  setAuthCookie(res, signToken(nextToken))
  return nextToken
}
