import { Router } from 'express'
import * as dietNotesController from '../controllers/dietNotesController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { DietNote } from '@powerlifting/types'
import { AppError } from '../middleware/errorHandler'

function mutationEnvelope(body: unknown): { expected_revision: number; idempotency_key: string } {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  if (typeof input.expected_revision !== 'number' || !Number.isInteger(input.expected_revision) || input.expected_revision < 0) throw new AppError('expected_revision must be a nonnegative integer', 400)
  if (typeof input.idempotency_key !== 'string' || !input.idempotency_key.trim()) throw new AppError('idempotency_key must be a nonempty string', 400)
  return { expected_revision: input.expected_revision, idempotency_key: input.idempotency_key }
}

export const dietNotesRouter = Router({ mergeParams: true })

// GET /api/diet-notes/:version - Get diet notes
dietNotesRouter.get('/:version', cacheGet((req) => [`diet-notes:${req.params.version}`]), async (req, res, next) => {
  try {
    const notes = await dietNotesController.getDietNotes(req.mapped_pk!, req.params.version)
    res.json({ data: notes, error: null })
  } catch (err) {
    next(err)
  }
})

// PUT /api/diet-notes/:version - Update all diet notes
dietNotesRouter.put('/:version', invalidateAfter((req) => [`diet-notes:${req.params.version}`]), async (req, res, next) => {
  try {
    const { dietNotes } = req.body

    if (!Array.isArray(dietNotes)) {
      return res.status(400).json({
        data: null,
        error: 'dietNotes must be an array',
      })
    }

    const result = await dietNotesController.updateDietNotes(
      req.mapped_pk!,
      req.params.version,
      dietNotes as DietNote[],
      mutationEnvelope(req.body),
    )
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})
