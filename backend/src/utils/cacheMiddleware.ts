import type { Request, Response, NextFunction } from 'express'
import { getCached, setCached, invalidateDomains } from './cache'

const CACHEABLE_METHODS = new Set(['GET'])

/**
 * Express middleware. If the GET response is a JSON 200 with a `data` envelope,
 * serve it from the backend cache when present, otherwise capture the response
 * and populate the cache tagged with the supplied domains.
 */
export function cacheGet(domains: string[] | ((req: Request) => string[])) {
  return async function cacheGetMiddleware(
    req: Request,
    res: Response,
    next: NextFunction,
  ): Promise<void> {
    if (!CACHEABLE_METHODS.has(req.method)) return next()
    const mappedPk = req.mapped_pk
    if (!mappedPk) return next()

    const resolvedDomains = typeof domains === 'function' ? domains(req) : domains
    if (resolvedDomains.length === 0) return next()

    const fullUrl = req.originalUrl || req.url
    try {
      const hit = await getCached<unknown>(mappedPk, fullUrl)
      if (hit) {
        res.setHeader('X-Cache', 'HIT')
        res.json(hit.data)
        return
      }
    } catch {
      // fall through to live fetch
    }

    res.setHeader('X-Cache', 'MISS')
    const originalJson = res.json.bind(res)
    res.json = ((body: unknown) => {
      const status = res.statusCode
      if (status >= 200 && status < 300 && body && typeof body === 'object' && 'data' in body) {
        setCached(mappedPk, fullUrl, body, resolvedDomains).catch(() => {})
      }
      return originalJson(body)
    }) as typeof res.json

    next()
  }
}

/**
 * Express middleware. After a successful write (2xx) response, invalidate
 * the listed domains for the request's mapped_pk so the next read pulls
 * fresh data from DynamoDB instead of serving stale cache.
 */
export function invalidateAfter(domains: string[] | ((req: Request) => string[])) {
  return function invalidateAfterMiddleware(
    req: Request,
    res: Response,
    next: NextFunction,
  ): void {
    const originalJson = res.json.bind(res)
    res.json = ((body: unknown) => {
      const status = res.statusCode
      if (status >= 200 && status < 300) {
        const mappedPk = req.mapped_pk
        if (mappedPk) {
          const resolved = typeof domains === 'function' ? domains(req) : domains
          if (resolved.length > 0) {
            invalidateDomains(mappedPk, resolved).catch(() => {})
          }
        }
      }
      return originalJson(body)
    }) as typeof res.json
    next()
  }
}
