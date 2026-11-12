import type { Express, NextFunction, Request, Response } from 'express'
import type { AuthIdentity } from '../auth/identity'
import { securityRequest } from '../auth/security'
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
      const result = await securityRequest<{ identity: AuthIdentity; settings: Record<string, unknown> }>('/v1/identity', { id_token: match[1] })
      if (!result.identity || result.identity.provider !== 'authentik' || result.identity.issuer !== process.env.AUTHENTIK_ISSUER_URL || typeof result.identity.sub !== 'string' || !result.identity.sub || typeof result.settings?.pk !== 'string' || !result.settings.pk || typeof result.identity.username !== 'string' || typeof result.identity.display_name !== 'string' || !Array.isArray(result.identity.groups) || !Array.isArray(result.identity.roles)) {
        throw new AppError('Invalid verified identity', 401, 'AUTH_REQUIRED')
      }
      req.identityToken = match[1]
      req.settings = normalizeSettings(result.settings)
      req.user = { identity: result.identity, discord_id: '', username: req.settings.username, avatar: result.identity.avatar, actor_mapped_pk: req.settings.pk }
      next()
    } catch (error) { next(error) }
  })
}
