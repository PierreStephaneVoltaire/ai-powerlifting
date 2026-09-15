import type { Express, Request, Response, NextFunction } from 'express'
import session from 'express-session'
import passport from 'passport'
import { RedisStore } from 'connect-redis'
import { createClient } from 'redis'
import { discovery, randomState } from 'openid-client'
import { Strategy, type VerifyFunction } from 'openid-client/passport'
import { getOrCreateSettingsForIdentity } from '../services/userSettings'
import { groupsFromSettings, type AuthIdentity } from '../auth/identity'
import { operationScope } from '../utils/operationScope'
import { AppError } from './errorHandler'


declare global { namespace Express { interface User {
  discord_id: string; username: string; avatar: string | null; actor_mapped_pk: string; identity: AuthIdentity
} interface Request {
  mapped_pk?: string; actor_mapped_pk?: string; readOnly?: boolean; settings?: import('../services/userSettings').UserSettings
} } }

const issuer = process.env.AUTHENTIK_ISSUER_URL
const clientId = process.env.AUTHENTIK_CLIENT_ID
const clientSecret = process.env.AUTHENTIK_CLIENT_SECRET
const callbackURL = process.env.AUTHENTIK_REDIRECT_URI

export function isAuthentikEnabled(): boolean { return Boolean(issuer && clientId && clientSecret && callbackURL) }

class AuthentikStrategy extends Strategy {
  override authorizationRequestParams(req: Request, options: Parameters<Strategy['authorizationRequestParams']>[1]): URLSearchParams {
    const params = super.authorizationRequestParams(req, options)
    const result = params instanceof URLSearchParams ? params : new URLSearchParams(params)
    if (!result.has('state')) result.set('state', randomState())
    return result
  }
}

export async function configureAuthentication(app: Express): Promise<void> {
  if (!isAuthentikEnabled()) throw new Error('Authentik OIDC is not configured')
  const oidcIssuer = issuer!
  const oidcClientId = clientId!
  const oidcSecret = clientSecret!
  const oidcCallback = callbackURL!
  app.set('trust proxy', 1)
  const redis = createClient({ url: process.env.VALKEY_URL || 'redis://pl-valkey:6379' })
  redis.on('error', (error) => console.error('Session store error', error))
  await redis.connect()
  app.use(session({
    store: new RedisStore({ client: redis, prefix: 'if:session:' }),
    secret: process.env.SESSION_SECRET || (() => { throw new Error('SESSION_SECRET is required') })(),
    resave: false, saveUninitialized: false,
    cookie: { httpOnly: true, sameSite: 'lax', secure: process.env.COOKIE_SECURE === 'true', maxAge: 7 * 24 * 60 * 60 * 1000 },
  }))
  const config = await discovery(new URL(oidcIssuer), oidcClientId, oidcSecret)
  const verifyIdentity: VerifyFunction = async (tokens, verified) => {
    const claims = tokens.claims()
    if (!claims?.sub) return verified(new Error('OIDC subject missing'))
    const fallback = `authentik_${claims.sub}`
    const username = String(claims.preferred_username || fallback).toLowerCase().replace(/[^a-z0-9_-]/g, '_').slice(0, 32) || fallback
    const identity: AuthIdentity = {
      issuer: claims.iss, provider: 'authentik', sub: String(claims.sub), username,
      discord_subjects: Array.isArray(claims.discord_subjects) ? claims.discord_subjects.filter((value): value is string => typeof value === 'string' && /^\d{1,32}$/.test(value)) : [],
      display_name: String(claims.name || claims.preferred_username || username), avatar: typeof claims.picture === 'string' ? claims.picture : null,
      groups: Array.isArray(claims.groups) ? claims.groups.map(String) : [], roles: Array.isArray(claims.roles) ? claims.roles.map(String) : [],
      email: typeof claims.email === 'string' ? claims.email : null,
    }
    await getOrCreateSettingsForIdentity(identity.provider, identity.sub, identity.username, identity.avatar, identity.discord_subjects)
    verified(null, identityUser(identity))
  }
  passport.use('authentik', new AuthentikStrategy({ config, callbackURL: oidcCallback, scope: 'openid profile email groups roles powerlifting_identity' }, verifyIdentity))
  passport.serializeUser((user: Express.User, done) => done(null, user.identity))
  passport.deserializeUser((identity: AuthIdentity, done) => done(null, identity.issuer === issuer ? identityUser(identity) : false))
  app.use(passport.initialize())
  app.use(passport.session())
}

function identityUser(identity: AuthIdentity) { return { discord_id: identity.provider === 'discord' ? identity.sub : '', username: identity.username, avatar: identity.avatar, actor_mapped_pk: '', identity } }

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
      const settings = await getOrCreateSettingsForIdentity(identity.provider, identity.sub, identity.username, identity.avatar, identity.discord_subjects)
      req.settings = settings
      req.actor_mapped_pk = settings.pk
      req.mapped_pk = selected || settings.mapped_pk || settings.pk
      req.readOnly = false
      req.user.actor_mapped_pk = settings.pk
      req.user.username = settings.username
      req.user.identity = { ...identity, username: settings.username, ...groupsFromSettings(identity.groups, identity.roles, settings.roles, settings.active_role) }
    }
    operationScope.run({ athlete: req.mapped_pk || '', person: req.actor_mapped_pk || '' }, next)
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
