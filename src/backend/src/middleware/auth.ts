import type { Express, Request, Response, NextFunction } from 'express'
import type { UserSettings } from '../services/userSettings'
import { groupsFromSettings, type AuthIdentity } from '../auth/identity'
import { operationScope } from '../utils/operationScope'
import { AppError } from './errorHandler'
import { configureMeshAuthentication } from './meshAuth'

declare global { namespace Express { interface User {
  discord_id: string; username: string; avatar: string | null; actor_mapped_pk: string; identity: AuthIdentity
} interface Request {
  user?: User; mapped_pk?: string; actor_mapped_pk?: string; readOnly?: boolean; settings?: UserSettings; identityToken?: string; operationPrincipal?: string
} } }

export async function configureAuthentication(app: Express): Promise<void> {
  configureMeshAuthentication(app)
}

function identityUser(identity: AuthIdentity) { return { discord_id: '', username: identity.username, avatar: identity.avatar, actor_mapped_pk: '', identity } }

export async function requireUserOptional(req: Request, _res: Response, next: NextFunction): Promise<void> {
  const identity = req.user?.identity
  req.user = identity ? identityUser(identity) : undefined
  next()
}

export async function resolvePk(req: Request, _res: Response, next: NextFunction): Promise<void> {
  try {
    const mediaAthlete = req.path.includes('/media/') && ['GET', 'HEAD'].includes(req.method) && typeof req.query.athlete === 'string' ? req.query.athlete : undefined
    const selected = req.get('X-Selected-Athlete-Pk') || mediaAthlete
    if (selected && !/^[A-Za-z0-9:_#-]{1,128}$/.test(selected)) throw new AppError('Invalid Athlete selector', 400)
    if (!req.user) {
      req.mapped_pk = selected || 'operator'
      req.actor_mapped_pk = ''
      req.readOnly = true
    } else {
      const identity = req.user.identity
      const settings = req.settings
      if (!settings) throw new AppError('Verified settings required', 401, 'AUTH_REQUIRED')
      req.settings = settings
      req.actor_mapped_pk = settings.pk
      req.mapped_pk = selected || settings.mapped_pk || settings.pk
      req.readOnly = false
      req.user.actor_mapped_pk = settings.pk
      req.user.username = settings.username
      req.user.identity = { ...identity, username: settings.username, ...groupsFromSettings(identity.groups, identity.roles, settings.roles, settings.active_role) }
    }
    operationScope.run({ athlete: req.mapped_pk || '', person: req.actor_mapped_pk || '', identityToken: req.identityToken, principal: req.operationPrincipal }, next)
  } catch (error) { next(error instanceof AppError ? error : new AppError('Failed to resolve authenticated identity', 503, 'AUTH_CONTEXT_FAILED')) }
}

export function requireWriteAuth(req: Request, _res: Response, next: NextFunction): void {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next()
  if (!req.user) return next(new AppError('Sign in required', 401, 'AUTH_REQUIRED'))
  if (req.readOnly) return next(new AppError('Read-only access: writes are not permitted', 403, 'READ_ONLY'))
  next()
}

export function requireAdmin(req: Request, _res: Response, next: NextFunction): void {
  if (req.readOnly || !req.user) return next(new AppError('Sign in required', 401, 'AUTH_REQUIRED'))
  if (req.settings?.mapped_pk !== 'operator') return next(new AppError('Admin access required', 403, 'ADMIN_REQUIRED'))
  next()
}
