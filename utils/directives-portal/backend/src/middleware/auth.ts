import { Request, Response, NextFunction } from 'express'
import jwt from 'jsonwebtoken'
import { GetCommand, PutCommand } from '@aws-sdk/lib-dynamodb'
import { docClient, USER_TABLE } from '../db/dynamo'
import { AppError } from './errorHandler'

declare global {
  namespace Express {
    interface Request {
      user?: { discord_id: string; username: string; avatar: string | null } | null
      mapped_pk?: string
      isAuthenticated?: boolean
    }
  }
}

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me'
const JWT_EXPIRY = '7d'
const TEST_MAPPED_PK_RE = /^[A-Za-z0-9:_#-]{1,128}$/
const PK_CACHE_TTL_MS = 60_000
const pkCache = new Map<string, { pk: string; expires: number }>()

function testMappedPkOverride(): string | null {
  const override = process.env.DIRECTIVES_TEST_MAPPED_PK?.trim()
  if (!override) return null
  if (!TEST_MAPPED_PK_RE.test(override)) {
    throw new Error('Invalid DIRECTIVES_TEST_MAPPED_PK')
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
  const token = req.cookies?.dir_auth
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
    return next()
  }

  if (!req.user) {
    return next(new AppError('Cannot resolve PK: no authenticated user', 401, 'AUTH_REQUIRED'))
  }

  const username = req.user.username
  const discordId = req.user.discord_id

  try {
    const cached = pkCache.get(discordId)
    if (cached && cached.expires > Date.now()) {
      req.mapped_pk = cached.pk
      return next()
    }

    // Look up user by pk = Discord username in if-user table
    const result = await docClient.send(new GetCommand({
      TableName: USER_TABLE,
      Key: { pk: username },
    }))

    if (result.Item) {
      const item = result.Item
      const mappedPk = typeof item.mapped_pk === 'string' ? item.mapped_pk.trim() : ''
      const pk = typeof item.pk === 'string' ? item.pk.trim() : ''
      const resolvedPk = mappedPk || pk

      if (!resolvedPk) {
        return next(new AppError(`User ${username} has neither mapped_pk nor pk`, 500, 'AUTH_CONTEXT_FAILED'))
      }

      pkCache.set(discordId, { pk: resolvedPk, expires: Date.now() + PK_CACHE_TTL_MS })
      req.mapped_pk = resolvedPk
      return next()
    }

    // User not found — auto-create with pk = Discord username
    const now = new Date().toISOString()
    const pk = username
    await docClient.send(new PutCommand({
      TableName: USER_TABLE,
      Item: {
        pk,
        discord_id: discordId,
        discord_username: username,
        username,
        display_name: username,
        nickname: '',
        bio: '',
        avatar_url: req.user.avatar || '',
        created_at: now,
        updated_at: now,
        profile_visibility: 'private',
        public_training_summary_enabled: false,
      },
      ConditionExpression: 'attribute_not_exists(pk)',
    }))

    pkCache.set(discordId, { pk, expires: Date.now() + PK_CACHE_TTL_MS })
    req.mapped_pk = pk
    next()
  } catch (err) {
    console.error('Failed to resolve PK for user', username, err)
    return next(new AppError('Failed to resolve user PK', 500, 'AUTH_CONTEXT_FAILED'))
  }
}

export function requireAuth(req: Request, _res: Response, next: NextFunction): void {
  const token = req.cookies?.dir_auth
  if (!token) {
    return next(new AppError('Authentication required', 401, 'AUTH_REQUIRED'))
  }

  const payload = verifyToken(token)
  if (!payload) {
    return next(new AppError('Invalid or expired token', 401, 'AUTH_REQUIRED'))
  }

  req.user = {
    discord_id: payload.discord_id,
    username: payload.username,
    avatar: payload.avatar,
  }
  req.isAuthenticated = true
  next()
}

export async function resolvePkOptional(req: Request, _res: Response, next: NextFunction): Promise<void> {
  // Same as resolvePk but silently skips if no authenticated user
  if (!req.user) {
    return next()
  }

  const testMappedPk = testMappedPkOverride()
  if (testMappedPk) {
    req.mapped_pk = testMappedPk
    return next()
  }

  const username = req.user.username
  const discordId = req.user.discord_id

  try {
    const cached = pkCache.get(discordId)
    if (cached && cached.expires > Date.now()) {
      req.mapped_pk = cached.pk
      return next()
    }

    const result = await docClient.send(new GetCommand({
      TableName: USER_TABLE,
      Key: { pk: username },
    }))

    if (result.Item) {
      const item = result.Item
      const mappedPk = typeof item.mapped_pk === 'string' ? item.mapped_pk.trim() : ''
      const pk = typeof item.pk === 'string' ? item.pk.trim() : ''
      const resolvedPk = mappedPk || pk

      if (resolvedPk) {
        pkCache.set(discordId, { pk: resolvedPk, expires: Date.now() + PK_CACHE_TTL_MS })
        req.mapped_pk = resolvedPk
      }
    }

    next()
  } catch (err) {
    // Silently fail - mapped_pk will be undefined
    console.error('Failed to resolve PK for user (optional)', username, err)
    next()
  }
}
