import { Request, Response, NextFunction, RequestHandler } from 'express'
import { authorizeScope } from './rbac'
import type { Scope, Access, HttpMethod } from './scopes'
import { findRouteRule } from './scopes'
import { AppError } from '../middleware/errorHandler'

export function requireScope(scope: Scope, access: Access): RequestHandler {
  return async (req: Request, _res: Response, next: NextFunction) => {
    try {
      await authorizeScope(req, scope, access)
      next()
    } catch (err) {
      next(err)
    }
  }
}

export function autoScopeForRoute(): RequestHandler {
  return async (req: Request, _res: Response, next: NextFunction) => {
    const rule = findRouteRule(req.method as HttpMethod, req.path, req.query)
    if (!rule) {
      if (req.path === '/api/profiles' || req.path.startsWith('/api/profiles/') || req.path.startsWith('/api/authored-notes/')) return next()
      return next(new AppError('Unmapped route', 404, 'NOT_FOUND'))
    }
    try {
      await authorizeScope(req, rule.scope, rule.access)
      next()
    } catch (err) {
      next(err)
    }
  }
}

export function forbidOperatorWrite(req: Request, _res: Response, next: NextFunction): void {
  if (!req.user && req.mapped_pk === 'operator' && !['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
    return next(new AppError('Sign in required', 401, 'AUTH_REQUIRED'))
  }
  next()
}

