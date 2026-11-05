import { Request, Response, NextFunction, RequestHandler } from 'express'
import { authorizeScope } from './rbac'
import type { HttpMethod } from './scopes'
import { findRouteRule } from './scopes'
import { AppError } from '../middleware/errorHandler'

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
