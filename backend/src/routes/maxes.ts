import { Router } from 'express'
import * as maxController from '../controllers/maxController'
import { cacheGet, invalidateAfter } from '../utils/cacheMiddleware'
import type { MaxEntry } from '@powerlifting/types'

export const maxesRouter = Router()

// GET /api/maxes/:version - Get current targets and history
maxesRouter.get('/:version', cacheGet((req) => [`maxes:${req.params.version}`]), async (req, res, next) => {
  try {
    const [targets, history] = await Promise.all([
      maxController.getTargetMaxes(req.mapped_pk!, req.params.version),
      maxController.getMaxHistory(req.mapped_pk!, req.params.version),
    ])
    res.json({
      data: { targets, history },
      error: null,
    })
  } catch (err) {
    next(err)
  }
})

// PUT /api/maxes/:version - Update target maxes
maxesRouter.put('/:version', invalidateAfter((req) => [`maxes:${req.params.version}`, `program:${req.params.version}`]), async (req, res, next) => {
  try {
    const { squat_kg, bench_kg, deadlift_kg } = req.body
    if (!Number.isInteger(req.body?.expected_revision) || req.body.expected_revision < 0 || typeof req.body?.idempotency_key !== 'string' || !req.body.idempotency_key.trim()) {
      return res.status(400).json({ data: null, error: 'expected_revision and idempotency_key are required' })
    }

    if (
      typeof squat_kg !== 'number' ||
      typeof bench_kg !== 'number' ||
      typeof deadlift_kg !== 'number'
    ) {
      return res.status(400).json({
        data: null,
        error: 'Missing or invalid max values (squat_kg, bench_kg, deadlift_kg required)',
      })
    }

    const result = await maxController.updateTargetMaxes(req.mapped_pk!, req.params.version, {
      squat_kg,
      bench_kg,
      deadlift_kg,
    }, { expected_revision: req.body.expected_revision, idempotency_key: req.body.idempotency_key })
    res.json({ data: result, error: null })
  } catch (err) {
    next(err)
  }
})

// POST /api/maxes/:version/history - Add to max history
maxesRouter.post('/:version/history', invalidateAfter((req) => [`maxes:${req.params.version}`]), async (req, res, next) => {
  try {
    const { expected_revision, idempotency_key, ...entry } = req.body
    if (!Number.isInteger(expected_revision) || expected_revision < 0 || typeof idempotency_key !== 'string' || !idempotency_key.trim()) {
      return res.status(400).json({ data: null, error: 'expected_revision and idempotency_key are required' })
    }

    if (!entry.date) {
      return res.status(400).json({
        data: null,
        error: 'Missing date in max entry',
      })
    }

    const history = await maxController.addMaxEntry(req.mapped_pk!, req.params.version, entry as MaxEntry, { expected_revision, idempotency_key })
    res.json({ data: history, error: null })
  } catch (err) {
    next(err)
  }
})
