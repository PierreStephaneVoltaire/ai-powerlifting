import type { NextFunction, Request, Response } from 'express'
import { invalidateAnalysisCache } from '../services/analysisCache'

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function shouldInvalidate(method: string, path: string): boolean {
  if (!MUTATING_METHODS.has(method)) return false

  if (path.startsWith('/api/auth')) return false
  if (path.startsWith('/api/settings')) return false
  if (path.startsWith('/api/stats')) return false
  if (path.startsWith('/api/videos')) return false

  if (path.startsWith('/api/import')) {
    return /\/apply$/.test(path)
  }

  if (path.startsWith('/api/templates')) {
    return /\/apply\/confirm$/.test(path)
  }

  if (path.startsWith('/api/analytics')) {
    return false
  }

  return path.startsWith('/api/')
}

export function analysisCacheInvalidationMiddleware(
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  const shouldDelete = shouldInvalidate(req.method, req.path)
  const userPk = req.effectivePk

  if (shouldDelete && userPk) {
    res.on('finish', () => {
      if (res.statusCode >= 200 && res.statusCode < 400) {
        void invalidateAnalysisCache(userPk)
      }
    })
  }

  next()
}
