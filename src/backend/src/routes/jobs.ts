import { Router, Request, Response, NextFunction } from 'express'
import { AppError } from '../middleware/errorHandler'
import { serviceHeaders } from '../utils/serviceHeaders'
import { coachUrl } from '../utils/coachUrl'

const router = Router()

function checkScope(value: unknown, athlete: string): void {
  if (!value || typeof value !== 'object') return
  for (const [key, item] of Object.entries(value)) {
    if (['athlete', 'pk', 'user_pk', 'mapped_pk', 'person_pk', '_user_pk'].includes(key) && item !== athlete) {
      throw new AppError('Job payload scope conflicts with authenticated Athlete', 403, 'SCOPE_CONFLICT')
    }
    checkScope(item, athlete)
  }
}

function forward(path: (req: Request) => string, method: string) {
  return async (req: Request, res: Response, next: NextFunction) => {
    try {
      if (!req.user) throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
      const athlete = req.mapped_pk || ''
      const person = req.actor_mapped_pk || ''
      if (!athlete || !person) throw new AppError('Authenticated Person and Athlete scope required', 401, 'AUTH_REQUIRED')
      let body = req.body || {}
      if (method === 'POST' && path(req) === '/v1/jobs') {
        if (body.kind !== 'domain' || !body.payload || typeof body.payload.operation !== 'string' || typeof body.payload.domain !== 'string') {
          throw new AppError('A domain operation is required', 422)
        }
        checkScope(body.payload.arguments, athlete)
        body = {
          kind: 'domain', conversation_id: `powerlifting:${athlete}`,
          priority: 0,
          payload: { domain: body.payload.domain, operation: body.payload.operation, arguments: body.payload.arguments || {}, athlete },
        }
      }
      const response = await fetch(`${coachUrl()}${path(req)}`, {
        method,
        headers: serviceHeaders({ athlete, person }),
        ...(method === 'POST' ? { body: JSON.stringify(body) } : {}),
      })
      const text = await response.text()
      let result: unknown
      try { result = JSON.parse(text) } catch { result = { error: text } }
      res.status(response.status).json(result)
    } catch (error) { next(error) }
  }
}

router.post('/', forward(() => '/v1/jobs', 'POST'))
router.get('/:jobId/result', forward(req => `/v1/jobs/${encodeURIComponent(req.params.jobId)}/result`, 'GET'))
router.get('/:jobId', forward(req => `/v1/jobs/${encodeURIComponent(req.params.jobId)}`, 'GET'))
router.post('/:jobId/cancel', forward(req => `/v1/jobs/${encodeURIComponent(req.params.jobId)}/cancel`, 'POST'))

export const jobsRouter = router
