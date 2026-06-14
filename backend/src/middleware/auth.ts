import { Request, Response, NextFunction } from 'express'
import jwt from 'jsonwebtoken'
import { resolveMappedPk } from '../services/userSettings'
import { AppError } from './errorHandler'

declare global {
  namespace Express {
    interface Request {
      user?: { discord_id: string; username: string; avatar: string | null } | null
      mapped_pk?: string
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
  discord_id: string
  username: string
  avatar: string | null
}

export function signToken(payload: AuthToken): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: JWT_EXPIRY })
}

export function verifyToken(token: string): AuthToken | null {
  try {
    return jwt.verify(token, JWT_SECRET) as AuthToken
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

  req.user = { discord_id: payload.discord_id, username: payload.username, avatar: payload.avatar }
  req.isAuthenticated = true
  next()
}

export async function resolvePk(req: Request, _res: Response, next: NextFunction): Promise<void> {
  const testMappedPk = testMappedPkOverride()
  if (testMappedPk) {
    req.mapped_pk = testMappedPk
    req.readOnly = false
    return next()
  }

  if (!req.user) {
    req.mapped_pk = 'operator'
    req.readOnly = true
    return next()
  }

  try {
    req.mapped_pk = await resolveMappedPk(
      req.user.discord_id,
      req.user.username,
      req.user.avatar,
    )
    req.readOnly = false
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
  ].includes(req.path)

  if (readOnlySafePost) {
    return next()
  }

  if (testMappedPkOverride()) {
    return next()
  }

  if (req.readOnly || !req.user) {
    return next(new AppError('Sign in required', 401, 'AUTH_REQUIRED'))
  }

  next()
}
