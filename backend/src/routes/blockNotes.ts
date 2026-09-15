import { Router } from 'express'
import * as blockNotesController from '../controllers/blockNotesController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { BlockNote } from '@powerlifting/types'
import { AppError } from '../middleware/errorHandler'

function mutationEnvelope(body: unknown): { expected_revision: number; idempotency_key: string } {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  if (typeof input.expected_revision !== 'number' || !Number.isInteger(input.expected_revision) || input.expected_revision < 0) throw new AppError('expected_revision must be a nonnegative integer', 400)
  if (typeof input.idempotency_key !== 'string' || !input.idempotency_key.trim()) throw new AppError('idempotency_key must be a nonempty string', 400)
  return { expected_revision: input.expected_revision, idempotency_key: input.idempotency_key }
}

export const blockNotesRouter = Router({ mergeParams: true })

blockNotesRouter.get('/:version', cacheGet((req) => [`block-notes:${req.params.version}`]), async (req, res, next) => {
  try {
    const notes = await blockNotesController.getBlockNotes(req.mapped_pk!, req.params.version)
    res.json({ data: notes, error: null })
  } catch (err) {
    next(err)
  }
})

blockNotesRouter.put('/:version', invalidateAfter((req) => [`block-notes:${req.params.version}`]), async (req, res, next) => {
  try {
    const { blockNotes } = req.body

    if (!Array.isArray(blockNotes)) {
      return res.status(400).json({
        data: null,
        error: 'blockNotes must be an array',
      })
    }

    const result = await blockNotesController.updateBlockNotes(
      req.mapped_pk!,
      req.params.version,
      blockNotes as BlockNote[],
      mutationEnvelope(req.body),
    )
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})
