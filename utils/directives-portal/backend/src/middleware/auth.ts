import { Request, Response, NextFunction } from 'express'
import jwt from 'jsonwebtoken'
import { AppError } from './errorHandler'

declare global {
  namespace Express {
    interface Request {
      user?: { discord_id: string; username: string; avatar: string | null } | null
      isAuthenticated?: boolean
    }
  }
}

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me'
const JWT_EXPIRY = '7d'

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