import { Router } from 'express'
import * as supplementController from '../controllers/supplementController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { SupplementPhase } from '@powerlifting/types'
import { AppError } from '../middleware/errorHandler'

function mutationEnvelope(body: unknown): { expected_revision: number; idempotency_key: string } {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  if (typeof input.expected_revision !== 'number' || !Number.isInteger(input.expected_revision) || input.expected_revision < 0) throw new AppError('expected_revision must be a nonnegative integer', 400)
  if (typeof input.idempotency_key !== 'string' || !input.idempotency_key.trim()) throw new AppError('idempotency_key must be a nonempty string', 400)
  return { expected_revision: input.expected_revision, idempotency_key: input.idempotency_key }
}

export const supplementsRouter = Router({ mergeParams: true })

// GET /api/supplements/:version - Get supplement phases
supplementsRouter.get('/:version', cacheGet((req) => [`supplements:${req.params.version}`]), async (req, res, next) => {
  try {
    const phases = await supplementController.getSupplementPhases(req.mapped_pk!, req.params.version)
    res.json({ data: phases, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/supplements/:version - Update all supplement phases
supplementsRouter.put('/:version', invalidateAfter((req) => [`supplements:${req.params.version}`]), async (req, res, next) => {
  try {
    const { phases } = req.body

    if (!Array.isArray(phases)) {
      return res.status(400).json({
        data: null,
        error: 'phases must be an array',
      })
    }

    const result = await supplementController.updateSupplementPhases(
      req.mapped_pk!,
      req.params.version,
      phases as SupplementPhase[],
      mutationEnvelope(req.body),
    )
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})
