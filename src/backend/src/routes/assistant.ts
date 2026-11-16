import { Router, Request, Response, NextFunction } from 'express'
import { AppError } from '../middleware/errorHandler'
import { serviceHeaders } from '../utils/serviceHeaders'
import { assistantUrl } from '../utils/coachUrl'

const SCOPES = ['general', 'session-design', 'template-phase', 'goals', 'supplements', 'biometrics', 'research']
const AREAS = ['program']
const router = Router()

function identity(req: Request): { athlete: string; person: string } {
  if (!req.user) throw new AppError('Sign in required', 401, 'AUTH_REQUIRED')
  const athlete = req.mapped_pk || ''
  const person = req.actor_mapped_pk || ''
  if (!athlete || !person) throw new AppError('Authenticated Person and Athlete scope required', 401, 'AUTH_REQUIRED')
  return { athlete, person }
}

function conversationId(req: Request, athlete: string, person: string): string {
  const scope = String(req.params.scope)
  if (!SCOPES.includes(scope)) throw new AppError('Unknown assistant scope', 422, 'VALIDATION')
  return `powerlifting:${athlete}:web:${person}:${scope}`
}

function optionalInt(value: unknown): number | undefined {
  return Number.isInteger(value) && (value as number) >= 0 ? (value as number) : undefined
}

function turnBody(req: Request, athlete: string) {
  const { messages, surface, context } = req.body || {}
  if (!Array.isArray(messages) || messages.length === 0) throw new AppError('messages are required', 422, 'VALIDATION')
  const scope = String(req.params.scope)
  if (surface !== undefined && surface !== scope) throw new AppError('surface must match the scope', 422, 'VALIDATION')
  const source = context && typeof context === 'object' ? context : {}
  const clean: Record<string, unknown> = {}
  if (typeof source.session_date === 'string') clean.session_date = source.session_date
  if (typeof source.template_sk === 'string') clean.template_sk = source.template_sk
  if (typeof source.area === 'string' && AREAS.includes(source.area)) clean.area = source.area
  const sessionIndex = optionalInt(source.session_index)
  const exerciseIndex = optionalInt(source.exercise_index)
  if (sessionIndex !== undefined) clean.session_index = sessionIndex
  if (exerciseIndex !== undefined) clean.exercise_index = exerciseIndex
  return { athlete, messages, surface: scope, context: clean }
}

function proxy(path: (req: Request, athlete: string, person: string) => string, method: 'GET' | 'POST', body?: (req: Request, athlete: string) => unknown) {
  return async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { athlete, person } = identity(req)
      const target = path(req, athlete, person)
      const response = await fetch(`${assistantUrl()}${target}`, {
        method,
        headers: serviceHeaders({ athlete, person }),
        ...(body ? { body: JSON.stringify(body(req, athlete)) } : {}),
      })
      const text = await response.text()
      let result: unknown
      try { result = JSON.parse(text) } catch { result = { error: text } }
      res.status(response.status).json(result)
    } catch (error) { next(error) }
  }
}

function historyQuery(req: Request): string {
  const params = new URLSearchParams()
  for (const key of ['limit', 'before', 'expand']) {
    const value = req.query[key]
    if (typeof value === 'string' && value) params.set(key, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

router.get('/conversations', proxy(() => '/v1/conversations', 'GET'))
router.get('/history/:id', proxy((req, athlete) => {
  const id = String(req.params.id)
  if (!id.startsWith(`powerlifting:${athlete}:discord:`)) throw new AppError('Unknown conversation', 404, 'NOT_FOUND')
  return `/v1/conversations/${encodeURIComponent(id)}/history${historyQuery(req)}`
}, 'GET'))
router.post('/conversations/:scope/turns', proxy(
  (req, athlete, person) => `/v1/conversations/${encodeURIComponent(conversationId(req, athlete, person))}/turns`,
  'POST',
  turnBody,
))
router.get('/conversations/:scope/history', proxy(
  (req, athlete, person) => `/v1/conversations/${encodeURIComponent(conversationId(req, athlete, person))}/history${historyQuery(req)}`,
  'GET',
))
router.get('/jobs/:id/result', proxy(req => `/v1/jobs/${encodeURIComponent(req.params.id as string)}/result`, 'GET'))
router.get('/jobs/:id', proxy(req => `/v1/jobs/${encodeURIComponent(req.params.id as string)}`, 'GET'))
router.post('/jobs/:id/cancel', proxy(req => `/v1/jobs/${encodeURIComponent(req.params.id as string)}/cancel`, 'POST', () => ({})))
router.post('/proposals/:id/approve', proxy(
  req => `/v1/proposals/${encodeURIComponent(req.params.id as string)}/approve`,
  'POST',
  req => (typeof req.body?.target === 'string' ? { target: req.body.target } : {}),
))
router.post('/proposals/:id/reject', proxy(
  req => `/v1/proposals/${encodeURIComponent(req.params.id as string)}/reject`,
  'POST',
  () => ({}),
))

export const assistantRouter = router
