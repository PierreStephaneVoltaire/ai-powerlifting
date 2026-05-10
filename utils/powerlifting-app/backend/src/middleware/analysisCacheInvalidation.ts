import type { NextFunction, Request, Response } from 'express'
import { invalidateAnalysisCache } from '../services/analysisCache'

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function shouldInvalidate(method: string, path: string): boolean {
  if (!MUTATING_METHODS.has(method)) return false

  // ONLY invalidate analysis cache when sessions are saved/modified
  if (path.startsWith('/api/sessions')) {
    return true
  }

  return false
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
