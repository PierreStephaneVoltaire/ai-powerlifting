import type { Express, NextFunction, Request, Response } from 'express'
import { identityFromToken } from '../auth/oidcIdentity'
import { callOperationAs } from '../utils/operations'
import { normalizeSettings } from '../services/userSettings'
import { AppError } from './errorHandler'

export function requireSameOrigin(req: Request, _res: Response, next: NextFunction): void {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next()
  const origin = new URL(process.env.FRONTEND_URL || 'http://localhost:5173').origin
  if (req.get('Origin') !== origin) return next(new AppError('Same-origin request required', 403, 'INVALID_ORIGIN'))
  next()
}

export function configureMeshAuthentication(app: Express): void {
  if (!process.env.AUTHENTIK_ISSUER_URL || !process.env.AUTHENTIK_CLIENT_ID) throw new Error('Authentik OIDC is not configured')
  app.set('trust proxy', 1)
  app.use(requireSameOrigin)
  app.use(async (req: Request, _res: Response, next: NextFunction) => {
    try {
      const authorization = req.get('Authorization')
      if (!authorization) return next()
      const match = /^Bearer ([^\s]+)$/.exec(authorization)
      if (!match) throw new AppError('Invalid login token', 401, 'AUTH_REQUIRED')
      const identity = identityFromToken(match[1])
      const result = await callOperationAs('identity_resolve', { issuer: identity.issuer, provider: identity.provider, sub: identity.sub, display_name: identity.display_name, avatar_url: identity.avatar, discord_subjects: identity.discord_subjects }, { athlete: '', person: '' }) as { settings?: Record<string, unknown> }
      if (typeof result?.settings?.pk !== 'string' || !result.settings.pk) throw new AppError('Identity resolution failed', 503, 'AUTH_CONTEXT_FAILED')
      req.settings = normalizeSettings(result.settings)
      req.user = { identity, discord_id: '', username: req.settings.username, avatar: identity.avatar, actor_mapped_pk: req.settings.pk }
      next()
    } catch (error) { next(error) }
  })
}
