import type { Request } from 'express'
import { AppError } from '../middleware/errorHandler'
import { checkGrant, type CheckGrantResult } from '../services/grants'
import type { Scope, Access } from './scopes'
import { OPERATOR_MAPPED_PK } from './identity'

export interface ActorIdentity {
  provider: 'discord' | 'authentik'
  sub: string
  username: string
  display_name: string
  avatar: string | null
  groups: string[]
  roles: string[]
  actor_mapped_pk: string
  isAuthenticated: boolean
}

export interface RbacContext {
  actor: ActorIdentity | null
  athleteMappedPk: string
  isSelf: boolean
  isOperator: boolean
  isCoachOnAthlete: boolean | null
  isHandlerOnAthlete: boolean | null
  activeGrant: CheckGrantResult['grant'] | null
}

function contextFromRequest(req: Request): Omit<RbacContext, 'isCoachOnAthlete' | 'isHandlerOnAthlete' | 'activeGrant'> {
  const actorMappedPk = req.user?.actor_mapped_pk ?? 'operator'
  const athleteMappedPk = req.mapped_pk ?? 'operator'
  return {
    actor: req.user?.identity
      ? {
          provider: req.user.identity.provider,
          sub: req.user.identity.sub,
          username: req.user.identity.username,
          display_name: req.user.identity.display_name,
          avatar: req.user.identity.avatar,
          groups: req.user.identity.groups,
          roles: req.user.identity.roles,
          actor_mapped_pk: actorMappedPk,
          isAuthenticated: true,
        }
      : null,
    athleteMappedPk,
    isSelf: actorMappedPk === athleteMappedPk,
    isOperator: actorMappedPk === OPERATOR_MAPPED_PK,
  }
}

export async function evaluateRbac(req: Request): Promise<RbacContext> {
  const ctx: RbacContext = {
    ...contextFromRequest(req),
    isCoachOnAthlete: null,
    isHandlerOnAthlete: null,
    activeGrant: null,
  }
  if (!ctx.actor || ctx.isSelf || ctx.isOperator) {
    return ctx
  }
  try {
    const [coach, handler] = await Promise.all([
      checkGrant({
        athlete_mapped_pk: ctx.athleteMappedPk,
        actor_mapped_pk: ctx.actor.actor_mapped_pk,
        grant_type: 'coach',
        scope: 'read',
      }),
      checkGrant({
        athlete_mapped_pk: ctx.athleteMappedPk,
        actor_mapped_pk: ctx.actor.actor_mapped_pk,
        grant_type: 'handler',
        scope: 'read',
      }),
    ])
    ctx.isCoachOnAthlete = coach.allowed
    ctx.isHandlerOnAthlete = handler.allowed
    ctx.activeGrant = coach.allowed ? coach.grant ?? null : handler.allowed ? handler.grant ?? null : null
  } catch (err) {
    console.error('RBAC grant check failed', err)
    ctx.isCoachOnAthlete = false
    ctx.isHandlerOnAthlete = false
    ctx.activeGrant = null
  }
  return ctx
}

export async function authorizeScope(req: Request, scope: Scope, access: Access): Promise<RbacContext> {
  const ctx = await evaluateRbac(req)
  if (!ctx.actor) {
    if (access === 'read') {
      throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
    }
    throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  }
  if (ctx.isOperator) return ctx
  if (ctx.isSelf) return ctx
  if (ctx.isCoachOnAthlete && (scope === 'sessions' || scope === 'program' || scope === 'competitions' || scope === 'attempts' || scope === 'analytics' || scope === 'maxes' || scope === 'lift_profile' || scope === 'budget')) {
    if (access === 'read') return ctx
  }
  if (ctx.isHandlerOnAthlete) {
    if (access === 'read' && (scope === 'sessions' || scope === 'program' || scope === 'competitions' || scope === 'attempts' || scope === 'analytics' || scope === 'maxes' || scope === 'lift_profile' || scope === 'budget' || scope === 'profile')) {
      return ctx
    }
    if (access === 'write' && scope === 'sessions') {
      return ctx
    }
  }
  if (ctx.activeGrant) {
    const grant = ctx.activeGrant
    if (grant.scope === 'write' || (grant.scope === 'read' && access === 'read')) {
      return ctx
    }
  }
  throw new AppError('Not permitted', 403, 'NOT_PERMITTED')
}
